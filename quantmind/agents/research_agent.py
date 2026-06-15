from __future__ import annotations

from dataclasses import asdict
from typing import Any

from quantmind.agents.base import BaseAgent
from quantmind.config import settings
from quantmind.llm.client import DeepSeekChatClient, LLMError
from quantmind.llm.parsing import (
    parse_research_debate_report_payload,
    parse_research_perspective_report_payload,
)
from quantmind.schemas import AgentState, ResearchDebateReport, ResearchPerspectiveReport, Signal


NO_BULLISH_EVIDENCE_SUMMARY = "现有报告中缺少明确多头证据，多头研究员暂时保持中性观点。"
NO_BEARISH_EVIDENCE_SUMMARY = "现有报告中缺少明确空头证据，空头研究员暂时保持中性观点。"
NO_RESEARCH_DEBATE_SUMMARY = "多空研究报告均缺失，研究经理暂时保持中性结论。"


class BullishResearchAgent(BaseAgent):
    name = "bullish_research_agent"
    role = "多头研究员 Agent"

    def run(self, state: AgentState) -> AgentState:
        rule_report = self._make_rule_report(state)
        if not self._collect_report_evidence(state):
            state.bullish_research_report = rule_report
            return state

        if settings.llm_provider != "deepseek":
            state.bullish_research_report = rule_report
            return state

        if not settings.has_llm_api_key:
            state.bullish_research_report = rule_report
            return state

        try:
            payload = DeepSeekChatClient().chat_json(self._build_deepseek_messages(state, rule_report))
            state.bullish_research_report = parse_research_perspective_report_payload(payload)
        except (LLMError, ValueError, TypeError):
            state.bullish_research_report = rule_report
        return state

    def _make_rule_report(self, state: AgentState) -> ResearchPerspectiveReport:
        evidence = self._collect_report_evidence(state)
        if not evidence:
            return ResearchPerspectiveReport(
                stance=Signal.NEUTRAL,
                confidence=0.35,
                thesis=NO_BULLISH_EVIDENCE_SUMMARY,
                key_points=[],
                concerns=["technical/news/fundamental/sentiment 报告均缺失，不能构造多头论据。"],
            )

        key_points: list[str] = []
        concerns: list[str] = []
        bullish_strength = 0
        bearish_pressure = 0

        for item in evidence:
            label = item["label"]
            signal = item["signal"]
            score = item["score"]
            summary = item["summary"]
            if signal == Signal.BULLISH:
                bullish_strength += 2
                key_points.append(f"{label}偏多：{summary}")
            elif signal == Signal.NEUTRAL and score >= 58:
                bullish_strength += 1
                key_points.append(f"{label}略有支撑：{summary}")
            elif signal == Signal.BEARISH:
                bearish_pressure += 2
                concerns.append(f"{label}偏空，削弱多头论证：{summary}")
            else:
                concerns.append(f"{label}未形成明确多头信号：{summary}")

        if not key_points:
            return ResearchPerspectiveReport(
                stance=Signal.NEUTRAL,
                confidence=0.4,
                thesis=NO_BULLISH_EVIDENCE_SUMMARY,
                key_points=[],
                concerns=concerns or ["现有报告没有可引用的上涨或买入理由。"],
            )

        net_strength = bullish_strength - bearish_pressure
        if net_strength >= 3:
            stance = Signal.BULLISH
            confidence = min(0.55 + net_strength * 0.08, 0.85)
            thesis = "多头研究员认为现有报告中存在较一致的上涨支撑，可以形成偏多研究观点。"
        elif net_strength >= 1:
            stance = Signal.BULLISH
            confidence = min(0.5 + net_strength * 0.06, 0.68)
            thesis = "多头研究员认为现有报告中存在一定上涨理由，但仍需关注反向证据。"
        else:
            stance = Signal.NEUTRAL
            confidence = 0.45
            thesis = "多头研究员能找到部分上涨理由，但反向或中性证据较多，暂不形成强多头结论。"

        return ResearchPerspectiveReport(
            stance=stance,
            confidence=round(confidence, 2),
            thesis=thesis,
            key_points=key_points[:5],
            concerns=concerns[:5],
        )

    def _collect_report_evidence(self, state: AgentState) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        if state.technical_report is not None:
            evidence.append(
                {
                    "label": "技术面",
                    "signal": state.technical_report.signal,
                    "score": state.technical_report.score,
                    "summary": state.technical_report.summary,
                }
            )
        if state.news_report is not None:
            evidence.append(
                {
                    "label": "新闻面",
                    "signal": state.news_report.sentiment,
                    "score": state.news_report.score,
                    "summary": state.news_report.summary,
                }
            )
        if state.fundamental_report is not None:
            evidence.append(
                {
                    "label": "基本面",
                    "signal": state.fundamental_report.signal,
                    "score": state.fundamental_report.score,
                    "summary": state.fundamental_report.summary,
                }
            )
        if state.sentiment_report is not None:
            evidence.append(
                {
                    "label": "舆情面",
                    "signal": state.sentiment_report.sentiment,
                    "score": state.sentiment_report.score,
                    "summary": state.sentiment_report.summary,
                }
            )
        return evidence

    def _build_deepseek_messages(
        self,
        state: AgentState,
        rule_report: ResearchPerspectiveReport,
    ) -> list[dict[str, str]]:
        reports = {
            "technical_report": asdict(state.technical_report) if state.technical_report else None,
            "news_report": asdict(state.news_report) if state.news_report else None,
            "fundamental_report": asdict(state.fundamental_report) if state.fundamental_report else None,
            "sentiment_report": asdict(state.sentiment_report) if state.sentiment_report else None,
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是 QuantMind 的多头研究员 Agent。你的任务是只站在多头角度，"
                    "从用户提供的 technical_report、news_report、fundamental_report、sentiment_report 中寻找上涨或买入理由。\n\n"
                    "请输出严格 JSON 对象，不要输出 Markdown，不要输出解释性前后缀。\n"
                    "JSON 字段必须包含：\n"
                    "- stance: 只能是 bullish、neutral、bearish；多头研究员通常只能输出 bullish 或 neutral，除非完全找不到多头证据且风险明显\n"
                    "- confidence: 0 到 0.95 的数字，表示多头论证置信度\n"
                    "- thesis: 中文多头核心论点\n"
                    "- key_points: 字符串数组，只列出输入报告中已有的多头证据\n"
                    "- concerns: 字符串数组，列出输入报告中削弱多头观点的风险或不足\n\n"
                    "重要约束：\n"
                    "1. 只能基于已有报告分析，不能编造新事实、新数据、新闻、财务指标或技术指标。\n"
                    "2. 不能把 bearish 报告强行改写成利多；bearish 证据应放入 concerns。\n"
                    "3. 如果多头证据不足，应输出 neutral，并说明证据不足。\n"
                    "4. 输出必须为中文 thesis、key_points 和 concerns。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"股票代码: {state.symbol}\n"
                    f"分析日期: {state.trade_date}\n\n"
                    f"已有报告: {reports}\n\n"
                    "规则基线多头研究观点:\n"
                    "{\n"
                    f"  \"stance\": \"{rule_report.stance.value}\",\n"
                    f"  \"confidence\": {rule_report.confidence},\n"
                    f"  \"thesis\": \"{rule_report.thesis}\",\n"
                    f"  \"key_points\": {rule_report.key_points},\n"
                    f"  \"concerns\": {rule_report.concerns}\n"
                    "}\n\n"
                    "请返回 JSON：\n"
                    "{\n"
                    "  \"stance\": \"bullish|neutral|bearish\",\n"
                    "  \"confidence\": 0.0-0.95,\n"
                    "  \"thesis\": \"中文多头核心论点\",\n"
                    "  \"key_points\": [\"只来自已有报告的多头证据\"],\n"
                    "  \"concerns\": [\"只来自已有报告的风险或不足\"]\n"
                    "}"
                ),
            },
        ]


class BearishResearchAgent(BaseAgent):
    name = "bearish_research_agent"
    role = "空头研究员 Agent"

    def run(self, state: AgentState) -> AgentState:
        rule_report = self._make_rule_report(state)
        if not self._collect_report_evidence(state):
            state.bearish_research_report = rule_report
            return state

        if settings.llm_provider != "deepseek":
            state.bearish_research_report = rule_report
            return state

        if not settings.has_llm_api_key:
            state.bearish_research_report = rule_report
            return state

        try:
            payload = DeepSeekChatClient().chat_json(self._build_deepseek_messages(state, rule_report))
            state.bearish_research_report = parse_research_perspective_report_payload(payload)
        except (LLMError, ValueError, TypeError):
            state.bearish_research_report = rule_report
        return state

    def _make_rule_report(self, state: AgentState) -> ResearchPerspectiveReport:
        evidence = self._collect_report_evidence(state)
        if not evidence:
            return ResearchPerspectiveReport(
                stance=Signal.NEUTRAL,
                confidence=0.35,
                thesis=NO_BEARISH_EVIDENCE_SUMMARY,
                key_points=[],
                concerns=["technical/news/fundamental/sentiment 报告均缺失，不能构造空头论据。"],
            )

        key_points: list[str] = []
        concerns: list[str] = []
        bearish_strength = 0
        bullish_pressure = 0

        for item in evidence:
            label = item["label"]
            signal = item["signal"]
            score = item["score"]
            summary = item["summary"]
            if signal == Signal.BEARISH:
                bearish_strength += 2
                key_points.append(f"{label}偏空：{summary}")
            elif signal == Signal.NEUTRAL and score <= 42:
                bearish_strength += 1
                key_points.append(f"{label}偏弱或观望：{summary}")
            elif signal == Signal.BULLISH:
                bullish_pressure += 2
                concerns.append(f"{label}偏多，削弱空头论证：{summary}")
            else:
                concerns.append(f"{label}未形成明确空头信号：{summary}")

        if not key_points:
            return ResearchPerspectiveReport(
                stance=Signal.NEUTRAL,
                confidence=0.4,
                thesis=NO_BEARISH_EVIDENCE_SUMMARY,
                key_points=[],
                concerns=concerns or ["现有报告没有可引用的风险、下跌或观望理由。"],
            )

        net_strength = bearish_strength - bullish_pressure
        if net_strength >= 3:
            stance = Signal.BEARISH
            confidence = min(0.55 + net_strength * 0.08, 0.85)
            thesis = "空头研究员认为现有报告中存在较一致的风险或下跌证据，可以形成偏空研究观点。"
        elif net_strength >= 1:
            stance = Signal.BEARISH
            confidence = min(0.5 + net_strength * 0.06, 0.68)
            thesis = "空头研究员认为现有报告中存在一定风险或观望理由，但仍需关注反向证据。"
        else:
            stance = Signal.NEUTRAL
            confidence = 0.45
            thesis = "空头研究员能找到部分风险或观望理由，但反向或中性证据较多，暂不形成强空头结论。"

        return ResearchPerspectiveReport(
            stance=stance,
            confidence=round(confidence, 2),
            thesis=thesis,
            key_points=key_points[:5],
            concerns=concerns[:5],
        )

    def _collect_report_evidence(self, state: AgentState) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        if state.technical_report is not None:
            evidence.append(
                {
                    "label": "技术面",
                    "signal": state.technical_report.signal,
                    "score": state.technical_report.score,
                    "summary": state.technical_report.summary,
                }
            )
        if state.news_report is not None:
            evidence.append(
                {
                    "label": "新闻面",
                    "signal": state.news_report.sentiment,
                    "score": state.news_report.score,
                    "summary": state.news_report.summary,
                }
            )
        if state.fundamental_report is not None:
            evidence.append(
                {
                    "label": "基本面",
                    "signal": state.fundamental_report.signal,
                    "score": state.fundamental_report.score,
                    "summary": state.fundamental_report.summary,
                }
            )
        if state.sentiment_report is not None:
            evidence.append(
                {
                    "label": "舆情面",
                    "signal": state.sentiment_report.sentiment,
                    "score": state.sentiment_report.score,
                    "summary": state.sentiment_report.summary,
                }
            )
        return evidence

    def _build_deepseek_messages(
        self,
        state: AgentState,
        rule_report: ResearchPerspectiveReport,
    ) -> list[dict[str, str]]:
        reports = {
            "technical_report": asdict(state.technical_report) if state.technical_report else None,
            "news_report": asdict(state.news_report) if state.news_report else None,
            "fundamental_report": asdict(state.fundamental_report) if state.fundamental_report else None,
            "sentiment_report": asdict(state.sentiment_report) if state.sentiment_report else None,
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是 QuantMind 的空头研究员 Agent。你的任务是只站在空头角度，"
                    "从用户提供的 technical_report、news_report、fundamental_report、sentiment_report 中寻找风险、下跌或观望理由。\n\n"
                    "请输出严格 JSON 对象，不要输出 Markdown，不要输出解释性前后缀。\n"
                    "JSON 字段必须包含：\n"
                    "- stance: 只能是 bullish、neutral、bearish；空头研究员通常只能输出 bearish 或 neutral，除非完全找不到空头证据且利多明显\n"
                    "- confidence: 0 到 0.95 的数字，表示空头论证置信度\n"
                    "- thesis: 中文空头核心论点\n"
                    "- key_points: 字符串数组，只列出输入报告中已有的空头或风险证据\n"
                    "- concerns: 字符串数组，列出输入报告中削弱空头观点的利多证据或不足\n\n"
                    "重要约束：\n"
                    "1. 只能基于已有报告分析，不能编造新事实、新数据、新闻、财务指标或技术指标。\n"
                    "2. 不能把 bullish 报告强行改写成利空；bullish 证据应放入 concerns。\n"
                    "3. 如果空头证据不足，应输出 neutral，并说明证据不足。\n"
                    "4. 输出必须为中文 thesis、key_points 和 concerns。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"股票代码: {state.symbol}\n"
                    f"分析日期: {state.trade_date}\n\n"
                    f"已有报告: {reports}\n\n"
                    "规则基线空头研究观点:\n"
                    "{\n"
                    f"  \"stance\": \"{rule_report.stance.value}\",\n"
                    f"  \"confidence\": {rule_report.confidence},\n"
                    f"  \"thesis\": \"{rule_report.thesis}\",\n"
                    f"  \"key_points\": {rule_report.key_points},\n"
                    f"  \"concerns\": {rule_report.concerns}\n"
                    "}\n\n"
                    "请返回 JSON：\n"
                    "{\n"
                    "  \"stance\": \"bullish|neutral|bearish\",\n"
                    "  \"confidence\": 0.0-0.95,\n"
                    "  \"thesis\": \"中文空头核心论点\",\n"
                    "  \"key_points\": [\"只来自已有报告的空头或风险证据\"],\n"
                    "  \"concerns\": [\"只来自已有报告的利多证据或不足\"]\n"
                    "}"
                ),
            },
        ]


class ResearchManagerAgent(BaseAgent):
    name = "research_manager_agent"
    role = "研究经理 Agent"

    def run(self, state: AgentState) -> AgentState:
        rule_report = self._make_rule_report(state)
        if not self._has_research_or_analyst_evidence(state):
            state.research_debate_report = rule_report
            return state

        if settings.llm_provider != "deepseek":
            state.research_debate_report = rule_report
            return state

        if not settings.has_llm_api_key:
            state.research_debate_report = rule_report
            return state

        try:
            payload = DeepSeekChatClient().chat_json(self._build_deepseek_messages(state, rule_report))
            state.research_debate_report = parse_research_debate_report_payload(payload)
        except (LLMError, ValueError, TypeError):
            state.research_debate_report = rule_report
        return state

    def _make_rule_report(self, state: AgentState) -> ResearchDebateReport:
        bullish_report = state.bullish_research_report
        bearish_report = state.bearish_research_report

        if not self._has_research_or_analyst_evidence(state):
            return ResearchDebateReport(
                conclusion=Signal.NEUTRAL,
                confidence=0.35,
                bullish_summary="多头研究报告缺失。",
                bearish_summary="空头研究报告缺失。",
                final_summary=NO_RESEARCH_DEBATE_SUMMARY,
                key_evidence=[],
            )

        bullish_score = self._stance_score(bullish_report, positive_signal=Signal.BULLISH)
        bearish_score = self._stance_score(bearish_report, positive_signal=Signal.BEARISH)
        analyst_evidence = self._collect_analyst_evidence(state)

        for item in analyst_evidence:
            signal = item["signal"]
            if signal == Signal.BULLISH:
                bullish_score += 0.25
            elif signal == Signal.BEARISH:
                bearish_score += 0.25

        diff = bullish_score - bearish_score
        if diff >= 0.35:
            conclusion = Signal.BULLISH
            confidence = min(0.5 + abs(diff) * 0.18, 0.85)
            final_summary = "研究经理认为多头证据相对更有说服力，形成偏多研究结论。"
        elif diff <= -0.35:
            conclusion = Signal.BEARISH
            confidence = min(0.5 + abs(diff) * 0.18, 0.85)
            final_summary = "研究经理认为空头风险证据相对更有说服力，形成偏空研究结论。"
        else:
            conclusion = Signal.NEUTRAL
            confidence = 0.45 if (bullish_score or bearish_score) else 0.35
            final_summary = "研究经理认为多空证据较为均衡或信息不足，暂时形成中性研究结论。"

        key_evidence = self._build_key_evidence(state, analyst_evidence)

        return ResearchDebateReport(
            conclusion=conclusion,
            confidence=round(confidence, 2),
            bullish_summary=self._summarize_perspective(bullish_report, "多头研究报告缺失。"),
            bearish_summary=self._summarize_perspective(bearish_report, "空头研究报告缺失。"),
            final_summary=final_summary,
            key_evidence=key_evidence[:8],
        )

    def _has_research_or_analyst_evidence(self, state: AgentState) -> bool:
        return any(
            report is not None
            for report in (
                state.bullish_research_report,
                state.bearish_research_report,
                state.technical_report,
                state.news_report,
                state.fundamental_report,
                state.sentiment_report,
            )
        )

    def _stance_score(
        self,
        report: ResearchPerspectiveReport | None,
        *,
        positive_signal: Signal,
    ) -> float:
        if report is None:
            return 0.0
        if report.stance == positive_signal:
            return max(0.2, report.confidence)
        if report.stance == Signal.NEUTRAL:
            return max(0.0, report.confidence * 0.25)
        return -max(0.1, report.confidence * 0.5)

    def _collect_analyst_evidence(self, state: AgentState) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        if state.technical_report is not None:
            evidence.append({"label": "技术面", "signal": state.technical_report.signal, "summary": state.technical_report.summary})
        if state.news_report is not None:
            evidence.append({"label": "新闻面", "signal": state.news_report.sentiment, "summary": state.news_report.summary})
        if state.fundamental_report is not None:
            evidence.append({"label": "基本面", "signal": state.fundamental_report.signal, "summary": state.fundamental_report.summary})
        if state.sentiment_report is not None:
            evidence.append({"label": "舆情面", "signal": state.sentiment_report.sentiment, "summary": state.sentiment_report.summary})
        return evidence

    def _build_key_evidence(self, state: AgentState, analyst_evidence: list[dict[str, Any]]) -> list[str]:
        key_evidence: list[str] = []
        if state.bullish_research_report is not None:
            key_evidence.extend(f"多头观点：{item}" for item in state.bullish_research_report.key_points[:3])
            key_evidence.extend(f"多头顾虑：{item}" for item in state.bullish_research_report.concerns[:2])
        if state.bearish_research_report is not None:
            key_evidence.extend(f"空头观点：{item}" for item in state.bearish_research_report.key_points[:3])
            key_evidence.extend(f"空头顾虑：{item}" for item in state.bearish_research_report.concerns[:2])
        for item in analyst_evidence:
            key_evidence.append(f"{item['label']} {item['signal'].value}：{item['summary']}")
        return key_evidence

    def _summarize_perspective(self, report: ResearchPerspectiveReport | None, fallback: str) -> str:
        if report is None:
            return fallback
        return f"{report.stance.value} / confidence {report.confidence:.2f}：{report.thesis}"

    def _build_deepseek_messages(
        self,
        state: AgentState,
        rule_report: ResearchDebateReport,
    ) -> list[dict[str, str]]:
        reports = {
            "bullish_research_report": asdict(state.bullish_research_report) if state.bullish_research_report else None,
            "bearish_research_report": asdict(state.bearish_research_report) if state.bearish_research_report else None,
            "technical_report": asdict(state.technical_report) if state.technical_report else None,
            "news_report": asdict(state.news_report) if state.news_report else None,
            "fundamental_report": asdict(state.fundamental_report) if state.fundamental_report else None,
            "sentiment_report": asdict(state.sentiment_report) if state.sentiment_report else None,
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是 QuantMind 的研究经理 Agent。你的任务是汇总多头研究员和空头研究员观点，"
                    "并结合已有 technical_report、news_report、fundamental_report、sentiment_report，判断哪一方更有说服力。\n\n"
                    "请输出严格 JSON 对象，不要输出 Markdown，不要输出解释性前后缀。\n"
                    "JSON 字段必须包含：\n"
                    "- conclusion: 只能是 bullish、neutral、bearish\n"
                    "- confidence: 0 到 0.95 的数字，表示研究经理结论置信度\n"
                    "- bullish_summary: 中文总结多头观点\n"
                    "- bearish_summary: 中文总结空头观点\n"
                    "- final_summary: 中文最终研究经理结论\n"
                    "- key_evidence: 字符串数组，只列出输入报告中已有的关键证据\n\n"
                    "重要约束：\n"
                    "1. 只能基于已有报告和多空研究观点分析，不能编造新事实、新数据、新闻、财务指标或技术指标。\n"
                    "2. conclusion 为 bullish 表示多头证据更强；neutral 表示多空均衡或信息不足；bearish 表示空头证据更强。\n"
                    "3. 如果多空研究报告缺失或证据不足，应输出 neutral，并说明信息不足。\n"
                    "4. 输出必须为中文 summary 和 key_evidence。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"股票代码: {state.symbol}\n"
                    f"分析日期: {state.trade_date}\n\n"
                    f"已有报告: {reports}\n\n"
                    "规则基线研究经理结论:\n"
                    "{\n"
                    f"  \"conclusion\": \"{rule_report.conclusion.value}\",\n"
                    f"  \"confidence\": {rule_report.confidence},\n"
                    f"  \"bullish_summary\": \"{rule_report.bullish_summary}\",\n"
                    f"  \"bearish_summary\": \"{rule_report.bearish_summary}\",\n"
                    f"  \"final_summary\": \"{rule_report.final_summary}\",\n"
                    f"  \"key_evidence\": {rule_report.key_evidence}\n"
                    "}\n\n"
                    "请返回 JSON：\n"
                    "{\n"
                    "  \"conclusion\": \"bullish|neutral|bearish\",\n"
                    "  \"confidence\": 0.0-0.95,\n"
                    "  \"bullish_summary\": \"中文多头观点总结\",\n"
                    "  \"bearish_summary\": \"中文空头观点总结\",\n"
                    "  \"final_summary\": \"中文研究经理最终结论\",\n"
                    "  \"key_evidence\": [\"只来自已有报告的关键证据\"]\n"
                    "}"
                ),
            },
        ]