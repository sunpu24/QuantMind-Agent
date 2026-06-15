from __future__ import annotations

import time

from quantmind.agents.base import BaseAgent
from quantmind.config import settings
from quantmind.llm.client import DeepSeekChatClient, LLMError
from quantmind.llm.parsing import parse_trade_decision_payload
from quantmind.schemas import AgentState, RiskLevel, Signal, TradeAction, TradeDecision


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

        bullish_votes = 0
        bearish_votes = 0
        if tech and tech.signal == Signal.BULLISH:
            bullish_votes += 1
        elif tech and tech.signal == Signal.BEARISH:
            bearish_votes += 1
        if news and news.sentiment == Signal.BULLISH:
            bullish_votes += 1
        elif news and news.sentiment == Signal.BEARISH:
            bearish_votes += 1
        if fundamental and fundamental.signal == Signal.BULLISH:
            bullish_votes += 1
        elif fundamental and fundamental.signal == Signal.BEARISH:
            bearish_votes += 1
        if sentiment and sentiment.sentiment == Signal.BULLISH:
            bullish_votes += 1
        elif sentiment and sentiment.sentiment == Signal.BEARISH:
            bearish_votes += 1
        if research and research.conclusion == Signal.BULLISH:
            bullish_votes += 2
        elif research and research.conclusion == Signal.BEARISH:
            bearish_votes += 2

        high_risk = risk is not None and risk.level == RiskLevel.HIGH
        if bullish_votes > bearish_votes and not high_risk:
            action = TradeAction.BUY
            confidence = 0.62 + bullish_votes * 0.05
            summary = "技术、新闻、基本面、舆情或研究经理结论整体偏正向，且风险未达到高风险区间，倾向买入或试探性建仓。"
        elif bearish_votes > bullish_votes or high_risk:
            action = TradeAction.SELL
            confidence = 0.62 + bearish_votes * 0.05
            summary = "负面信号、研究经理偏空或风险水平较高，倾向卖出、减仓或暂不参与。"
        else:
            action = TradeAction.WAIT
            confidence = 0.58
            summary = "多空信号尚不充分，建议继续观察。"

        position = risk.suggested_position if risk else 0.0
        if action != TradeAction.BUY:
            position = 0.0

        return TradeDecision(
            action=action,
            confidence=round(min(confidence, 0.95), 2),
            position_size=position,
            summary=summary,
            risk_notes=risk.summary if risk else "暂无风险报告。",
            decision_source="rule",
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            llm_reasoning=summary,
        )

    def _build_prompt_summary(self, state: AgentState, rule_decision: TradeDecision) -> str:
        tech = state.technical_report
        news = state.news_report
        fundamental = state.fundamental_report
        sentiment = state.sentiment_report
        research = state.research_debate_report
        risk = state.risk_report
        return (
            f"symbol={state.symbol}, date={state.trade_date}, "
            f"market_source={state.market_data.get('source', 'unknown')}, "
            f"tech={tech.signal.value if tech else 'N/A'}/{tech.score if tech else 'N/A'}, "
            f"news={news.sentiment.value if news else 'N/A'}/{news.score if news else 'N/A'}, "
            f"fundamental={fundamental.signal.value if fundamental else 'N/A'}/{fundamental.score if fundamental else 'N/A'}, "
            f"sentiment={sentiment.sentiment.value if sentiment else 'N/A'}/{sentiment.score if sentiment else 'N/A'}, "
            f"research={research.conclusion.value if research else 'N/A'}/{research.confidence if research else 'N/A'}, "
            f"risk={risk.level.value if risk else 'N/A'}/{risk.score if risk else 'N/A'}, "
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
                    f"position_size={rule_decision.position_size}, summary={rule_decision.summary}\n\n"
                    f"{ACTION_RULES_TEXT}\n\n"
                    f"约束: 最终决策只能依赖以上技术分析、新闻分析、基本面分析、舆情分析、研究经理结论、风险控制报告；如果新闻分析为“{NO_RELEVANT_NEWS_SUMMARY}”，"
                    "请把新闻面视为信息不足/中性，不得编造新闻。research_debate_report 是重要中间结论；risk_report 为 high 时不能激进 BUY。\n"
                    "请返回 JSON，字段必须包含: "
                    "action(BUY/HOLD/WAIT/SELL), confidence(0到0.95), position_size(0到风险建议仓位), "
                    "summary(中文结论), reasoning(中文依据，说明如何权衡技术/新闻/风险), risk_notes(中文风险提示)。"
                ),
            },
        ]
