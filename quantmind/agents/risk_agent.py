from __future__ import annotations

from quantmind.agents.base import BaseAgent
from quantmind.config import settings
from quantmind.llm.client import DeepSeekChatClient, LLMError
from quantmind.llm.parsing import parse_risk_report_payload
from quantmind.schemas import AgentState, RiskLevel, RiskReport, Signal


class RiskControlAgent(BaseAgent):
    name = "risk_control_agent"
    role = "风险控制 Agent"

    def run(self, state: AgentState) -> AgentState:
        rule_report = self._make_rule_report(state)

        if settings.llm_provider != "deepseek":
            state.risk_report = rule_report
            return state

        if not settings.has_llm_api_key:
            state.risk_report = rule_report
            return state

        try:
            payload = DeepSeekChatClient().chat_json(self._build_deepseek_messages(state, rule_report))
            state.risk_report = parse_risk_report_payload(
                payload,
                rule_report=rule_report,
                max_position_size=settings.max_position_size,
                stop_loss_pct=settings.stop_loss_pct,
            )
        except (LLMError, ValueError, TypeError):
            state.risk_report = rule_report
        return state

    def _make_rule_report(self, state: AgentState) -> RiskReport:
        tech = state.technical_report
        news = state.news_report

        risk_score = 50
        if tech and tech.signal == Signal.BULLISH:
            risk_score -= 10
        if tech and tech.signal == Signal.BEARISH:
            risk_score += 18
        if news and news.sentiment == Signal.BULLISH:
            risk_score -= 6
        if news and news.sentiment == Signal.BEARISH:
            risk_score += 16

        risk_score = max(0, min(100, risk_score))

        if risk_score <= 35:
            level = RiskLevel.LOW
            position = min(settings.default_position_size + 0.1, settings.max_position_size)
            summary = "综合风险较低，可在纪律约束下适度参与。"
        elif risk_score <= 65:
            level = RiskLevel.MEDIUM
            position = settings.default_position_size
            summary = "综合风险中等，建议控制仓位并设置止损。"
        else:
            level = RiskLevel.HIGH
            position = min(settings.default_position_size, 0.15)
            summary = "综合风险较高，建议降低仓位或观望。"

        return RiskReport(
            level=level,
            score=risk_score,
            suggested_position=round(position, 2),
            stop_loss_pct=settings.stop_loss_pct,
            summary=summary,
            risk_source="rule",
        )

    def _build_deepseek_messages(self, state: AgentState, rule_report: RiskReport) -> list[dict[str, str]]:
        tech = state.technical_report
        news = state.news_report

        return [
            {
                "role": "system",
                "content": (
                    "你是 QuantMind 的风险控制 Agent。你的任务是基于用户提供的技术分析、新闻情绪和规则基线风险报告，"
                    "生成中文风险解释，并可给出风险等级、风险评分和建议仓位。\n\n"
                    "请输出严格 JSON 对象，不要输出 Markdown，不要输出解释性前后缀。\n"
                    "JSON 字段必须包含：\n"
                    "- level: 只能是 low、medium、high\n"
                    "- score: 0 到 100 的整数，数值越高表示风险越高\n"
                    "- suggested_position: 0 到 1 的数字，表示建议仓位比例\n"
                    "- stop_loss_pct: 0 到 1 的数字\n"
                    "- summary: 中文风险控制说明\n\n"
                    "重要约束：\n"
                    "1. 你可以解释风险来源，但最终仓位、最大仓位和止损会由 Python 规则 Guardrails 裁剪。\n"
                    "2. 不要要求突破用户提供的 max_position_size。\n"
                    "3. 如果技术或新闻报告缺失，应降低确信度并说明信息不足。\n"
                    "4. 输出必须为中文 summary。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"股票代码: {state.symbol}\n"
                    f"分析日期: {state.trade_date}\n\n"
                    "技术分析报告:\n"
                    "{\n"
                    f"  \"signal\": \"{tech.signal.value if tech else 'N/A'}\",\n"
                    f"  \"score\": {tech.score if tech else 'N/A'},\n"
                    f"  \"summary\": \"{tech.summary if tech else 'N/A'}\"\n"
                    "}\n\n"
                    "新闻分析报告:\n"
                    "{\n"
                    f"  \"sentiment\": \"{news.sentiment.value if news else 'N/A'}\",\n"
                    f"  \"score\": {news.score if news else 'N/A'},\n"
                    f"  \"summary\": \"{news.summary if news else 'N/A'}\"\n"
                    "}\n\n"
                    "规则基线风险控制:\n"
                    "{\n"
                    f"  \"level\": \"{rule_report.level.value}\",\n"
                    f"  \"score\": {rule_report.score},\n"
                    f"  \"suggested_position\": {rule_report.suggested_position},\n"
                    f"  \"stop_loss_pct\": {rule_report.stop_loss_pct},\n"
                    f"  \"summary\": \"{rule_report.summary}\"\n"
                    "}\n\n"
                    "Python Guardrails:\n"
                    f"max_position_size: {settings.max_position_size}\n"
                    f"rule_stop_loss_pct: {settings.stop_loss_pct}\n\n"
                    "请返回 JSON：\n"
                    "{\n"
                    "  \"level\": \"low|medium|high\",\n"
                    "  \"score\": 0-100,\n"
                    "  \"suggested_position\": 0.0,\n"
                    "  \"stop_loss_pct\": 0.0,\n"
                    "  \"summary\": \"中文风险控制结论\"\n"
                    "}"
                ),
            },
        ]
