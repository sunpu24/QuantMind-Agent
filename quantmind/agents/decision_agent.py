from __future__ import annotations

import time

from quantmind.agents.base import BaseAgent
from quantmind.config import settings
from quantmind.llm.client import DeepSeekChatClient, LLMError
from quantmind.llm.parsing import parse_trade_decision_payload
from quantmind.schemas import AgentState, MarketRegime, RiskLevel, Signal, TradeAction, TradeDecision


NO_RELEVANT_NEWS_SUMMARY = "没有找到相关的新闻"


def _brief_text(value: object, *, limit: int = 80) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


MOCK_DATA_DECISION_WARNING = (
    "未找到可用行情数据，无法基于真实行情给出买入或卖出判断。"
    "为避免误导，最终决策为 WAIT。"
)

ACTION_RULES_TEXT = (
    "动作含义与仓位规则：BUY=买入/加仓/试探性建仓，仓位必须大于0且不超过风险建议仓位和最大仓位；"
    "HOLD=已有仓位继续持有但不新增买入，当前系统无持仓上下文时仓位输出0；"
    "WAIT=观望等待、不买不卖，信息不足/信号冲突/数据不可靠时使用，仓位必须为0；"
    "SELL=卖出/减仓/规避风险，当前系统无持仓数量时仓位输出0。"
)


REGIME_WEIGHTS: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.UPTREND: {"technical": 0.28, "news": 0.12, "fundamental": 0.18, "sentiment": 0.10, "research": 0.22, "risk": 0.10},
    MarketRegime.DOWNTREND: {"technical": 0.22, "news": 0.12, "fundamental": 0.16, "sentiment": 0.10, "research": 0.18, "risk": 0.22},
    MarketRegime.SIDEWAYS: {"technical": 0.12, "news": 0.16, "fundamental": 0.22, "sentiment": 0.14, "research": 0.18, "risk": 0.18},
    MarketRegime.HIGH_VOLATILITY: {"technical": 0.10, "news": 0.12, "fundamental": 0.16, "sentiment": 0.14, "research": 0.14, "risk": 0.34},
    MarketRegime.INSUFFICIENT_DATA: {"technical": 0.10, "news": 0.10, "fundamental": 0.15, "sentiment": 0.10, "research": 0.15, "risk": 0.40},
}


RISK_PENALTIES: dict[RiskLevel, float] = {
    RiskLevel.LOW: 0.1,
    RiskLevel.MEDIUM: 0.35,
    RiskLevel.HIGH: 0.7,
}


def _uses_mock_market_data(state: AgentState) -> bool:
    source = str((state.market_data or {}).get("source", "")).lower()
    fallback_type = (state.market_data or {}).get("fallback_type")
    return "mock" in source or fallback_type is not None


class TradingDecisionAgent(BaseAgent):
    name = "trading_decision_agent"
    role = "交易决策 Agent"

    def run(self, state: AgentState) -> AgentState:
        rule_decision = self._make_rule_decision(state)
        if settings.llm_provider != "deepseek":
            state.final_decision = self._apply_market_data_guardrail(state, rule_decision)
            return state

        if not settings.has_llm_api_key:
            rule_decision.decision_source = "rule_fallback"
            rule_decision.llm_provider = settings.llm_provider
            rule_decision.llm_model = settings.llm_model
            rule_decision.llm_fallback_reason = "未配置 DeepSeek API Key"
            rule_decision.llm_fallback_type = "missing_api_key"
            rule_decision.llm_prompt_summary = self._build_prompt_summary(state, rule_decision)
            state.final_decision = self._apply_market_data_guardrail(state, rule_decision)
            return state

        messages = self._build_deepseek_messages(state, rule_decision)
        prompt_summary = self._build_prompt_summary(state, rule_decision)
        started_at = time.perf_counter()
        try:
            payload = DeepSeekChatClient().chat_json(messages)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            risk_position = state.risk_report.suggested_position if state.risk_report else 0.0
            llm_decision = parse_trade_decision_payload(
                payload,
                max_position_size=settings.max_position_size,
                risk_position_size=risk_position,
                llm_provider=settings.llm_provider,
                llm_model=settings.llm_model,
                llm_elapsed_ms=elapsed_ms,
                llm_prompt_summary=prompt_summary,
                llm_response_summary=self._build_response_summary(payload),
            )
            llm_decision.weighted_score = rule_decision.weighted_score
            llm_decision.contribution_breakdown = dict(rule_decision.contribution_breakdown)
            llm_decision.regime_adjustment = rule_decision.regime_adjustment
            state.final_decision = self._apply_market_data_guardrail(state, llm_decision)
        except (LLMError, ValueError, TypeError) as exc:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            rule_decision.decision_source = "rule_fallback"
            rule_decision.llm_provider = settings.llm_provider
            rule_decision.llm_model = settings.llm_model
            rule_decision.llm_fallback_reason = str(exc)
            rule_decision.llm_elapsed_ms = elapsed_ms
            rule_decision.llm_fallback_type = self._classify_llm_fallback(exc)
            rule_decision.llm_prompt_summary = prompt_summary
            state.final_decision = self._apply_market_data_guardrail(state, rule_decision)
        return state

    def _apply_market_data_guardrail(self, state: AgentState, decision: TradeDecision) -> TradeDecision:
        """当未找到可用真实行情时，避免输出高置信 BUY/SELL。"""
        if not _uses_mock_market_data(state):
            return decision

        decision.action = TradeAction.WAIT
        decision.confidence = min(decision.confidence, 0.55)
        decision.position_size = 0.0
        decision.regime_adjustment = self._append_note(
            decision.regime_adjustment,
            "行情数据来自 mock/fallback 或不可用，强制覆盖为 WAIT 且仓位为 0。",
        )
        if MOCK_DATA_DECISION_WARNING not in decision.summary:
            decision.summary = MOCK_DATA_DECISION_WARNING
        if MOCK_DATA_DECISION_WARNING not in decision.risk_notes:
            decision.risk_notes = f"{MOCK_DATA_DECISION_WARNING} {decision.risk_notes}"
        if decision.llm_reasoning and MOCK_DATA_DECISION_WARNING not in decision.llm_reasoning:
            decision.llm_reasoning = f"{MOCK_DATA_DECISION_WARNING} {decision.llm_reasoning}"
        return decision

    def _make_rule_decision(self, state: AgentState) -> TradeDecision:
        tech = state.technical_report
        news = state.news_report
        fundamental = state.fundamental_report
        sentiment = state.sentiment_report
        research = state.research_debate_report
        risk = state.risk_report
        market_regime = state.market_regime_report.regime if state.market_regime_report else MarketRegime.INSUFFICIENT_DATA
        weights = REGIME_WEIGHTS.get(market_regime, REGIME_WEIGHTS[MarketRegime.INSUFFICIENT_DATA])
        risk_level = risk.level if risk else RiskLevel.MEDIUM
        risk_penalty = RISK_PENALTIES.get(risk_level, RISK_PENALTIES[RiskLevel.MEDIUM])

        contribution_breakdown = {
            "technical": self._signal_to_score(tech.signal if tech else None) * weights["technical"],
            "news": self._signal_to_score(news.sentiment if news else None) * weights["news"],
            "fundamental": self._signal_to_score(fundamental.signal if fundamental else None) * weights["fundamental"],
            "sentiment": self._signal_to_score(sentiment.sentiment if sentiment else None) * weights["sentiment"],
            "research": self._signal_to_score(research.conclusion if research else None) * weights["research"],
            "risk_penalty": -risk_penalty * weights["risk"],
        }
        contribution_breakdown = {key: round(value, 4) for key, value in contribution_breakdown.items()}
        weighted_score = round(sum(contribution_breakdown.values()), 4)

        high_risk = risk_level == RiskLevel.HIGH
        if market_regime == MarketRegime.INSUFFICIENT_DATA:
            action = TradeAction.WAIT
        elif weighted_score >= 0.25 and not high_risk:
            action = TradeAction.BUY
        elif weighted_score <= -0.20 or high_risk:
            action = TradeAction.SELL
        else:
            action = TradeAction.WAIT

        position = risk.suggested_position if risk and action == TradeAction.BUY else 0.0
        if action == TradeAction.BUY and market_regime == MarketRegime.HIGH_VOLATILITY:
            position = min(position, 0.15)

        confidence = self._score_to_confidence(weighted_score, action, high_risk)
        regime_adjustment = self._build_regime_adjustment(market_regime, weights)
        summary = self._build_rule_summary(action, market_regime, weighted_score, regime_adjustment)
        risk_notes = self._append_note(risk.summary if risk else "暂无风险报告。", regime_adjustment)

        return TradeDecision(
            action=action,
            confidence=round(min(confidence, 0.95), 2),
            position_size=round(position, 4),
            summary=summary,
            risk_notes=risk_notes,
            decision_source="rule",
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            llm_reasoning=summary,
            weighted_score=weighted_score,
            contribution_breakdown=contribution_breakdown,
            regime_adjustment=regime_adjustment,
        )

    @staticmethod
    def _signal_to_score(signal: Signal | None) -> int:
        if signal == Signal.BULLISH:
            return 1
        if signal == Signal.BEARISH:
            return -1
        return 0

    @staticmethod
    def _score_to_confidence(weighted_score: float, action: TradeAction, high_risk: bool) -> float:
        if action == TradeAction.WAIT:
            return 0.58 + min(abs(weighted_score), 0.2)
        if high_risk:
            return 0.72
        return 0.62 + min(abs(weighted_score), 0.28)

    @staticmethod
    def _build_regime_adjustment(regime: MarketRegime, weights: dict[str, float]) -> str:
        if regime == MarketRegime.HIGH_VOLATILITY:
            return f"当前市场状态为 {regime.value}，系统提高风险控制权重至 {weights['risk']:.0%}，并限制 BUY 仓位不超过 15%。"
        if regime == MarketRegime.INSUFFICIENT_DATA:
            return f"当前市场状态为 {regime.value}，行情不足或不可靠，系统提高风险控制权重至 {weights['risk']:.0%} 并强制观望。"
        if regime == MarketRegime.UPTREND:
            return f"当前市场状态为 {regime.value}，系统相对提高技术与研究结论权重。"
        if regime == MarketRegime.DOWNTREND:
            return f"当前市场状态为 {regime.value}，系统提高风险控制权重以防范下行延续。"
        return f"当前市场状态为 {regime.value}，系统更重视基本面、新闻与风险约束的均衡判断。"

    @staticmethod
    def _build_rule_summary(action: TradeAction, regime: MarketRegime, weighted_score: float, regime_adjustment: str) -> str:
        action_text = {
            TradeAction.BUY: "动态加权评分偏正向，且风险未达到高风险区间，倾向买入或试探性建仓。",
            TradeAction.SELL: "动态加权评分偏负向或风险水平较高，倾向卖出、减仓或暂不参与。",
            TradeAction.WAIT: "动态加权评分尚不足以支持积极交易，建议继续观察。",
            TradeAction.HOLD: "动态加权评分建议维持现状。",
        }[action]
        return f"{action_text} weighted_score={weighted_score:.4f}。{regime_adjustment}"

    @staticmethod
    def _append_note(text: str, note: str) -> str:
        if not note:
            return text
        if note in text:
            return text
        return f"{text} {note}".strip()

    def _build_prompt_summary(self, state: AgentState, rule_decision: TradeDecision) -> str:
        tech = state.technical_report
        news = state.news_report
        fundamental = state.fundamental_report
        sentiment = state.sentiment_report
        research = state.research_debate_report
        risk = state.risk_report
        regime = state.market_regime_report
        return (
            f"symbol={state.symbol}, date={state.trade_date}, "
            f"market_source={state.market_data.get('source', 'unknown')}, "
            f"market_regime={regime.regime.value if regime else 'N/A'}, "
            f"volatility={regime.volatility if regime else 'N/A'}, "
            f"trend_strength={regime.trend_strength if regime else 'N/A'}, "
            f"max_drawdown={regime.max_drawdown if regime else 'N/A'}, "
            f"tech={tech.signal.value if tech else 'N/A'}/{tech.score if tech else 'N/A'}, "
            f"news={news.sentiment.value if news else 'N/A'}/{news.score if news else 'N/A'}, "
            f"fundamental={fundamental.signal.value if fundamental else 'N/A'}/{fundamental.score if fundamental else 'N/A'}, "
            f"sentiment={sentiment.sentiment.value if sentiment else 'N/A'}/{sentiment.score if sentiment else 'N/A'}, "
            f"research={research.conclusion.value if research else 'N/A'}/{research.confidence if research else 'N/A'}, "
            f"risk={risk.level.value if risk else 'N/A'}/{risk.score if risk else 'N/A'}, "
            f"weighted_score={rule_decision.weighted_score}, "
            f"contribution_breakdown={rule_decision.contribution_breakdown}, "
            f"rule={rule_decision.action.value}/{rule_decision.confidence}"
        )

    def _build_response_summary(self, payload: dict[str, object]) -> str:
        return (
            f"action={payload.get('action', 'N/A')}, "
            f"confidence={payload.get('confidence', 'N/A')}, "
            f"position_size={payload.get('position_size', 'N/A')}, "
            f"summary={_brief_text(payload.get('summary', 'N/A'))}"
        )

    def _classify_llm_fallback(self, exc: Exception) -> str:
        message = str(exc)
        if isinstance(exc, LLMError):
            if "HTTP" in message:
                return "http_error"
            if "超时" in message:
                return "timeout"
            if "网络" in message:
                return "network_error"
            if "JSON" in message:
                return "invalid_response"
            return "llm_error"
        if isinstance(exc, ValueError):
            return "invalid_response"
        if isinstance(exc, TypeError):
            return "schema_mismatch"
        return "unknown"

    def _build_deepseek_messages(
        self,
        state: AgentState,
        rule_decision: TradeDecision,
    ) -> list[dict[str, str]]:
        tech = state.technical_report
        news = state.news_report
        fundamental = state.fundamental_report
        sentiment = state.sentiment_report
        research = state.research_debate_report
        risk = state.risk_report
        regime = state.market_regime_report
        news_meta = state.news_data[0] if state.news_data else {}
        return [
            {
                "role": "system",
                "content": (
                    "你是 QuantMind 的交易决策 Agent。请只基于用户提供的结构化分析结果给出辅助交易决策，"
                    "尤其只能依赖技术分析、新闻分析、基本面分析、舆情分析、研究经理结论和风险控制报告，不要编造不存在的数据或新闻事实。"
                    "兼容旧版约束：只能依赖技术分析、新闻分析和风险控制报告；新增基本面、舆情和研究经理结论也必须来自用户提供的结构化报告。"
                    f"当新闻分析 summary 为“{NO_RELEVANT_NEWS_SUMMARY}”时，新闻面必须按信息不足/中性处理。"
                    "research_debate_report 是重要中间结论，但如果 risk_report 为 high，不能给出激进 BUY。"
                    "market_regime_report 是动态权重决策的重要依据，不能忽略 Python 规则生成的 weighted_score 和 contribution_breakdown。"
                    "如果 market_regime 为 high_volatility 或 insufficient_data，不要给出激进 BUY。"
                    "输出必须是严格 JSON 对象，不要包含 Markdown。"
                    f"{ACTION_RULES_TEXT}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"股票代码: {state.symbol}\n"
                    f"分析日期: {state.trade_date}\n"
                    f"行情数据源: {state.market_data.get('source', 'unknown')}\n"
                    f"新闻数据源: {news_meta.get('news_source', news_meta.get('source', 'unknown'))}\n"
                    f"新闻回退类型: {news_meta.get('news_fallback_type')}\n\n"
                    f"市场状态: regime={regime.regime.value if regime else 'N/A'}, volatility={regime.volatility if regime else 'N/A'}, "
                    f"trend_strength={regime.trend_strength if regime else 'N/A'}, max_drawdown={regime.max_drawdown if regime else 'N/A'}, "
                    f"summary={regime.summary if regime else 'N/A'}\n"
                    f"技术分析: signal={tech.signal.value if tech else 'N/A'}, score={tech.score if tech else 'N/A'}, "
                    f"summary={tech.summary if tech else 'N/A'}, indicators={tech.indicators if tech else {}}\n"
                    f"新闻分析: sentiment={news.sentiment.value if news else 'N/A'}, score={news.score if news else 'N/A'}, "
                    f"summary={news.summary if news else 'N/A'}, headlines={news.headlines if news else []}\n"
                    f"基本面分析: signal={fundamental.signal.value if fundamental else 'N/A'}, score={fundamental.score if fundamental else 'N/A'}, "
                    f"summary={fundamental.summary if fundamental else 'N/A'}, metrics={fundamental.metrics if fundamental else {}}, "
                    f"data_source={fundamental.data_source if fundamental else 'N/A'}\n"
                    f"舆情分析: sentiment={sentiment.sentiment.value if sentiment else 'N/A'}, score={sentiment.score if sentiment else 'N/A'}, "
                    f"buzz_score={sentiment.buzz_score if sentiment else 'N/A'}, disagreement_score={sentiment.disagreement_score if sentiment else 'N/A'}, "
                    f"summary={sentiment.summary if sentiment else 'N/A'}, sources={sentiment.sources if sentiment else []}\n"
                    f"研究经理结论: conclusion={research.conclusion.value if research else 'N/A'}, confidence={research.confidence if research else 'N/A'}, "
                    f"bullish_summary={research.bullish_summary if research else 'N/A'}, bearish_summary={research.bearish_summary if research else 'N/A'}, "
                    f"final_summary={research.final_summary if research else 'N/A'}, key_evidence={research.key_evidence if research else []}\n"
                    f"风险控制: level={risk.level.value if risk else 'N/A'}, score={risk.score if risk else 'N/A'}, "
                    f"suggested_position={risk.suggested_position if risk else 0.0}, stop_loss_pct={risk.stop_loss_pct if risk else 0.0}, "
                    f"summary={risk.summary if risk else 'N/A'}\n"
                    f"规则基线决策: action={rule_decision.action.value}, confidence={rule_decision.confidence}, "
                    f"position_size={rule_decision.position_size}, weighted_score={rule_decision.weighted_score}, "
                    f"contribution_breakdown={rule_decision.contribution_breakdown}, "
                    f"regime_adjustment={rule_decision.regime_adjustment}, summary={rule_decision.summary}\n\n"
                    f"{ACTION_RULES_TEXT}\n\n"
                    f"约束: 最终决策只能依赖以上技术分析、新闻分析、基本面分析、舆情分析、研究经理结论、风险控制报告；如果新闻分析为“{NO_RELEVANT_NEWS_SUMMARY}”，"
                    "请把新闻面视为信息不足/中性，不得编造新闻。research_debate_report 是重要中间结论；risk_report 为 high 时不能激进 BUY。"
                    "市场状态是动态权重决策的重要依据，不能忽略 Python 规则生成的 weighted_score 和 contribution_breakdown；"
                    "如果 market_regime 为 high_volatility 或 insufficient_data，不要给出激进 BUY。\n"
                    "请返回 JSON，字段必须包含: "
                    "action(BUY/HOLD/WAIT/SELL), confidence(0到0.95), position_size(0到风险建议仓位), "
                    "summary(中文结论), reasoning(中文依据，说明如何权衡技术/新闻/风险), risk_notes(中文风险提示)。"
                ),
            },
        ]
