from __future__ import annotations

from typing import Any

from quantmind.agents.base import BaseAgent
from quantmind.config import settings
from quantmind.llm.client import DeepSeekChatClient, LLMError
from quantmind.llm.parsing import parse_fundamental_report_payload
from quantmind.schemas import AgentState, FundamentalReport, Signal


NO_FUNDAMENTAL_DATA_SUMMARY = "没有可用的真实财务指标，基本面暂时保持中性判断。"


class FundamentalAnalysisAgent(BaseAgent):
    name = "fundamental_analysis_agent"
    role = "基本面分析 Agent"

    def run(self, state: AgentState) -> AgentState:
        metrics = self._extract_metrics(state.fundamental_data)
        data_source = str((state.fundamental_data or {}).get("source", "unknown"))
        if not metrics:
            state.fundamental_report = self._make_insufficient_data_report(data_source=data_source)
            return state

        rule_report = self._make_rule_report(metrics, data_source=data_source)
        if settings.llm_provider != "deepseek":
            state.fundamental_report = rule_report
            return state

        if not settings.has_llm_api_key:
            state.fundamental_report = rule_report
            return state

        try:
            payload = DeepSeekChatClient().chat_json(self._build_deepseek_messages(state, metrics, rule_report))
            state.fundamental_report = parse_fundamental_report_payload(
                payload,
                metrics=metrics,
                data_source="deepseek_guardrailed",
            )
        except (LLMError, ValueError, TypeError):
            state.fundamental_report = rule_report
        return state

    def _make_insufficient_data_report(self, *, data_source: str = "unknown") -> FundamentalReport:
        return FundamentalReport(
            signal=Signal.NEUTRAL,
            score=50,
            summary=NO_FUNDAMENTAL_DATA_SUMMARY,
            metrics={},
            data_source=data_source,
        )

    def _extract_metrics(self, fundamental_data: dict[str, Any]) -> dict[str, Any]:
        metrics = fundamental_data.get("metrics", {}) if fundamental_data else {}
        if not isinstance(metrics, dict):
            return {}
        return {key: value for key, value in metrics.items() if value is not None}

    def _make_rule_report(self, metrics: dict[str, Any], *, data_source: str) -> FundamentalReport:
        roe = self._to_float(metrics.get("roe"))
        profit_growth = self._first_float(metrics, ["profit_growth_yoy", "earnings_growth_yoy", "net_profit_growth"])
        debt_ratio = self._first_float(metrics, ["debt_ratio", "asset_liability_ratio"])
        debt_to_equity = self._to_float(metrics.get("debt_to_equity"))
        pe_ratio = self._to_float(metrics.get("pe_ratio"))
        profit_margin = self._to_float(metrics.get("profit_margin"))
        revenue_growth = self._to_float(metrics.get("revenue_growth_yoy"))

        evidence_count = sum(
            value is not None
            for value in (roe, profit_growth, debt_ratio, debt_to_equity, pe_ratio, profit_margin, revenue_growth)
        )
        if evidence_count < 2:
            return FundamentalReport(
                signal=Signal.NEUTRAL,
                score=50,
                summary="基本面可用指标较少，无法形成可靠方向判断。",
                metrics=metrics,
                data_source=data_source,
            )

        bullish_points = 0
        bearish_points = 0
        notes = []

        if roe is not None:
            if roe >= 0.15:
                bullish_points += 1
                notes.append("ROE 较高")
            elif roe < 0.05:
                bearish_points += 1
                notes.append("ROE 偏低")
        if profit_growth is not None:
            if profit_growth > 0.05:
                bullish_points += 1
                notes.append("利润增长为正")
            elif profit_growth < 0:
                bearish_points += 1
                notes.append("利润增长为负")
        if revenue_growth is not None:
            if revenue_growth > 0.05:
                bullish_points += 1
                notes.append("营收增长为正")
            elif revenue_growth < 0:
                bearish_points += 1
                notes.append("营收增长为负")
        if profit_margin is not None:
            if profit_margin >= 0.15:
                bullish_points += 1
                notes.append("利润率较好")
            elif profit_margin < 0.03:
                bearish_points += 1
                notes.append("利润率偏低")
        if pe_ratio is not None:
            if pe_ratio <= 35:
                bullish_points += 1
                notes.append("估值未明显过高")
            elif pe_ratio >= 80:
                bearish_points += 1
                notes.append("PE 估值偏高")
        if debt_ratio is not None:
            if debt_ratio <= 0.45:
                bullish_points += 1
                notes.append("负债率较低")
            elif debt_ratio >= 0.70:
                bearish_points += 1
                notes.append("负债率较高")
        if debt_to_equity is not None:
            if debt_to_equity <= 100:
                bullish_points += 1
                notes.append("产权比率可控")
            elif debt_to_equity >= 250:
                bearish_points += 1
                notes.append("产权比率较高")

        if bullish_points >= bearish_points + 2:
            signal = Signal.BULLISH
            score = min(62 + (bullish_points - bearish_points) * 6, 88)
            summary = "基本面规则判断偏多：" + "、".join(notes[:4]) + "。"
        elif bearish_points >= bullish_points + 2:
            signal = Signal.BEARISH
            score = max(38 - (bearish_points - bullish_points) * 6, 12)
            summary = "基本面规则判断偏空：" + "、".join(notes[:4]) + "。"
        else:
            signal = Signal.NEUTRAL
            score = 52
            summary = "基本面指标多空信号不够一致，暂维持中性判断。"

        return FundamentalReport(
            signal=signal,
            score=score,
            summary=summary,
            metrics=metrics,
            data_source=data_source,
        )

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            if value in (None, "", "None", "-"):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _first_float(self, metrics: dict[str, Any], keys: list[str]) -> float | None:
        for key in keys:
            value = self._to_float(metrics.get(key))
            if value is not None:
                return value
        return None

    def _build_deepseek_messages(
        self,
        state: AgentState,
        metrics: dict[str, Any],
        rule_report: FundamentalReport,
    ) -> list[dict[str, str]]:
        data = state.fundamental_data or {}
        return [
            {
                "role": "system",
                "content": (
                    "你是 QuantMind 的基本面分析 Agent。你的任务是只基于用户提供的财务指标判断基本面强弱。\n\n"
                    "请输出严格 JSON 对象，不要输出 Markdown，不要输出解释性前后缀。\n"
                    "JSON 字段必须包含：\n"
                    "- signal: 只能是 bullish、neutral、bearish\n"
                    "- score: 0 到 100 的整数，数值越高表示基本面越偏强\n"
                    "- summary: 中文摘要，说明基本面判断依据\n"
                    "- metrics: 对象，必须原样保留用户提供的财务指标\n\n"
                    "重要约束：\n"
                    "1. 只能基于用户提供的财务字段分析。\n"
                    "2. 不得编造财报数据、行业数据、估值数据或公司事实。\n"
                    "3. metrics 字段必须原样返回用户提供的 metrics，不得修改数值、不得新增未经提供的指标。\n"
                    "4. 如果财务字段不足，应输出 neutral，并在 summary 中说明数据不足。\n"
                    "5. 输出必须为中文 summary。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"股票代码: {state.symbol}\n"
                    f"分析日期: {state.trade_date}\n"
                    f"基本面数据源: {data.get('source', 'unknown')}\n"
                    f"请求 Provider: {data.get('requested_provider', 'unknown')}\n"
                    f"回退类型: {data.get('fallback_type')}\n"
                    f"回退原因: {data.get('fallback_reason')}\n\n"
                    f"财务指标 metrics: {metrics}\n\n"
                    "规则基线基本面判断:\n"
                    "{\n"
                    f"  \"signal\": \"{rule_report.signal.value}\",\n"
                    f"  \"score\": {rule_report.score},\n"
                    f"  \"summary\": \"{rule_report.summary}\"\n"
                    "}\n\n"
                    "请返回 JSON：\n"
                    "{\n"
                    "  \"signal\": \"bullish|neutral|bearish\",\n"
                    "  \"score\": 0-100,\n"
                    "  \"summary\": \"中文基本面分析结论\",\n"
                    f"  \"metrics\": {metrics}\n"
                    "}"
                ),
            },
        ]