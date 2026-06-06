from __future__ import annotations

from quantmind.agents.base import BaseAgent
from quantmind.config import settings
from quantmind.llm.client import DeepSeekChatClient, LLMError
from quantmind.llm.parsing import parse_technical_report_payload
from quantmind.schemas import AgentState, Signal, TechnicalReport


FALLBACK_MOCK_WARNING = (
    "重要提示：当前行情数据为 mock 或 fallback mock，占位性质较强，不能当作真实行情证据。"
    "请在 summary 中明确说明这一点，并降低技术判断确信度。"
)


class TechnicalAnalysisAgent(BaseAgent):
    name = "technical_analysis_agent"
    role = "技术分析 Agent"

    def run(self, state: AgentState) -> AgentState:
        prices = state.market_data.get("close_prices", [])
        volumes = state.market_data.get("volumes", [])

        if len(prices) < 5:
            state.technical_report = self._make_insufficient_data_report()
            return state

        indicators = self._calculate_indicators(prices, volumes)
        rule_report = self._make_rule_report(indicators)

        if settings.llm_provider != "deepseek":
            state.technical_report = rule_report
            return state

        if not settings.has_llm_api_key:
            state.technical_report = rule_report
            return state

        try:
            payload = DeepSeekChatClient().chat_json(
                self._build_deepseek_messages(state, indicators, rule_report)
            )
            state.technical_report = parse_technical_report_payload(payload, indicators=indicators)
        except (LLMError, ValueError, TypeError):
            state.technical_report = rule_report
        return state

    def _make_insufficient_data_report(self) -> TechnicalReport:
        return TechnicalReport(
            signal=Signal.NEUTRAL,
            score=50,
            summary="行情数据不足，技术面暂时保持中性判断。",
        )

    def _calculate_indicators(self, prices: list[float], volumes: list[float]) -> dict[str, float]:
        ma5 = sum(prices[-5:]) / 5
        ma10 = sum(prices[-10:]) / min(len(prices), 10)
        latest = prices[-1]
        volume_change = 0.0
        if len(volumes) >= 2 and volumes[-2] != 0:
            volume_change = (volumes[-1] - volumes[-2]) / volumes[-2]

        return {
            "ma5": round(ma5, 2),
            "ma10": round(ma10, 2),
            "latest": latest,
            "volume_change": round(volume_change, 4),
        }

    def _make_rule_report(self, indicators: dict[str, float]) -> TechnicalReport:
        ma5 = indicators["ma5"]
        ma10 = indicators["ma10"]
        latest = indicators["latest"]
        volume_change = indicators["volume_change"]

        if latest > ma5 > ma10:
            signal = Signal.BULLISH
            score = 78
            summary = "最新价格站上短期与中期均线，趋势偏强。"
        elif latest < ma5 < ma10:
            signal = Signal.BEARISH
            score = 32
            summary = "最新价格跌破短期与中期均线，趋势偏弱。"
        else:
            signal = Signal.NEUTRAL
            score = 55
            summary = "均线结构尚未形成明确方向，技术面中性。"

        if volume_change > 0.15 and signal == Signal.BULLISH:
            summary += " 同时成交量有所放大，强化上涨信号。"
            score = min(score + 6, 100)

        return TechnicalReport(
            signal=signal,
            score=score,
            summary=summary,
            indicators=indicators,
        )

    def _build_deepseek_messages(
        self,
        state: AgentState,
        indicators: dict[str, float],
        rule_report: TechnicalReport,
    ) -> list[dict[str, str]]:
        market_source = state.market_data.get("source", "unknown")
        requested_provider = state.market_data.get("requested_provider", "unknown")
        fallback_type = state.market_data.get("fallback_type")
        fallback_reason = state.market_data.get("fallback_reason")
        fallback_warning = FALLBACK_MOCK_WARNING if "mock" in str(market_source).lower() else ""

        return [
            {
                "role": "system",
                "content": (
                    "你是 QuantMind 的技术分析 Agent。你的任务是基于用户提供的、已经由 Python 计算完成的技术指标，判断技术结构含义并生成中文解释。\n\n"
                    "请输出严格 JSON 对象，不要输出 Markdown，不要输出解释性前后缀。\n"
                    "JSON 字段必须包含：\n"
                    "- signal: 只能是 bullish、neutral、bearish\n"
                    "- score: 0 到 100 的整数，数值越高表示技术面越偏强\n"
                    "- summary: 中文摘要，说明技术结构判断依据\n"
                    "- indicators: 对象，必须原样保留用户提供的指标值\n\n"
                    "重要约束：\n"
                    "1. 不要重新计算 MA5、MA10、latest、volume_change。\n"
                    "2. 不要根据价格序列自行推导新指标。\n"
                    "3. indicators 字段必须原样返回用户提供的 indicators，不得修改数值、不得新增未经提供的指标。\n"
                    "4. 只能基于用户提供的指标、规则基线和数据源 metadata 做结构判断。\n"
                    "5. 如果指标数量不足或用户明确说明数据不足，应输出 neutral，并在 summary 中说明数据不足。\n"
                    "6. 输出必须为中文 summary。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"股票代码: {state.symbol}\n"
                    f"分析日期: {state.trade_date}\n"
                    f"行情数据源: {market_source}\n"
                    f"请求行情 Provider: {requested_provider}\n"
                    f"行情回退类型: {fallback_type}\n"
                    f"行情回退原因: {fallback_reason}\n\n"
                    f"{fallback_warning}\n\n"
                    "以下技术指标已经由 Python 计算完成，请不要重新计算：\n"
                    "indicators:\n"
                    "{\n"
                    f"  \"ma5\": {indicators['ma5']},\n"
                    f"  \"ma10\": {indicators['ma10']},\n"
                    f"  \"latest\": {indicators['latest']},\n"
                    f"  \"volume_change\": {indicators['volume_change']}\n"
                    "}\n\n"
                    "规则基线技术判断:\n"
                    "{\n"
                    f"  \"signal\": \"{rule_report.signal.value}\",\n"
                    f"  \"score\": {rule_report.score},\n"
                    f"  \"summary\": \"{rule_report.summary}\"\n"
                    "}\n\n"
                    "请只判断这些指标反映的技术结构含义，例如：\n"
                    "- latest 与 ma5、ma10 的相对位置；\n"
                    "- ma5 与 ma10 的相对位置；\n"
                    "- volume_change 是否强化或削弱价格信号；\n"
                    "- 行情数据源是否为 fallback mock，如果是，应降低技术判断确信度。\n\n"
                    "请返回 JSON：\n"
                    "{\n"
                    "  \"signal\": \"bullish|neutral|bearish\",\n"
                    "  \"score\": 0-100,\n"
                    "  \"summary\": \"中文技术分析结论\",\n"
                    "  \"indicators\": {\n"
                    f"    \"ma5\": {indicators['ma5']},\n"
                    f"    \"ma10\": {indicators['ma10']},\n"
                    f"    \"latest\": {indicators['latest']},\n"
                    f"    \"volume_change\": {indicators['volume_change']}\n"
                    "  }\n"
                    "}"
                ),
            },
        ]
