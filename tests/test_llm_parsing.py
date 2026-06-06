from __future__ import annotations

import unittest

from quantmind.llm.parsing import (
    parse_news_report_payload,
    parse_risk_report_payload,
    parse_technical_report_payload,
    parse_trade_decision_payload,
)
from quantmind.schemas import RiskLevel, RiskReport, Signal, TradeAction


class LLMParsingTest(unittest.TestCase):
    def test_parse_news_report_payload(self) -> None:
        report = parse_news_report_payload(
            {
                "sentiment": "bullish",
                "score": 88,
                "summary": "新闻偏正面。",
                "headlines": ["标题1", "标题2"],
            }
        )

        self.assertEqual(report.sentiment, Signal.BULLISH)
        self.assertEqual(report.score, 88)
        self.assertEqual(report.summary, "新闻偏正面。")
        self.assertEqual(report.headlines, ["标题1", "标题2"])

    def test_parse_news_report_clamps_and_defaults(self) -> None:
        report = parse_news_report_payload(
            {
                "sentiment": "optimistic",
                "score": 150,
                "headlines": "单条标题",
            }
        )

        self.assertEqual(report.sentiment, Signal.NEUTRAL)
        self.assertEqual(report.score, 100)
        self.assertEqual(report.summary, "DeepSeek 给出新闻情绪分析。")
        self.assertEqual(report.headlines, ["单条标题"])

    def test_parse_technical_report_payload_uses_python_indicators(self) -> None:
        indicators = {"ma5": 17.0, "ma10": 14.5, "latest": 19, "volume_change": 0.2222}
        report = parse_technical_report_payload(
            {
                "signal": "bearish",
                "score": 120,
                "summary": "LLM 技术解释。",
                "indicators": {"ma5": 999999},
            },
            indicators=indicators,
        )

        self.assertEqual(report.signal, Signal.BEARISH)
        self.assertEqual(report.score, 100)
        self.assertEqual(report.summary, "LLM 技术解释。")
        self.assertEqual(report.indicators, indicators)

    def test_parse_technical_report_defaults_invalid_signal(self) -> None:
        report = parse_technical_report_payload(
            {"signal": "optimistic", "score": -10},
            indicators={"ma5": 1, "ma10": 2, "latest": 3, "volume_change": 0},
        )

        self.assertEqual(report.signal, Signal.NEUTRAL)
        self.assertEqual(report.score, 0)
        self.assertEqual(report.summary, "DeepSeek 给出技术结构分析。")

    def test_parse_risk_report_guardrails_position_and_stop_loss(self) -> None:
        rule_report = RiskReport(
            level=RiskLevel.MEDIUM,
            score=50,
            suggested_position=0.3,
            stop_loss_pct=0.05,
            summary="规则风险中等。",
        )

        report = parse_risk_report_payload(
            {
                "level": "low",
                "score": 18,
                "suggested_position": 0.8,
                "stop_loss_pct": 0.3,
                "summary": "LLM 风险解释。",
            },
            rule_report=rule_report,
            max_position_size=0.5,
            stop_loss_pct=0.05,
        )

        self.assertEqual(report.level, RiskLevel.LOW)
        self.assertEqual(report.score, 18)
        self.assertEqual(report.suggested_position, 0.5)
        self.assertEqual(report.stop_loss_pct, 0.05)
        self.assertEqual(report.risk_source, "deepseek_guardrailed")

    def test_parse_trade_decision_clamps_confidence_and_position(self) -> None:
        decision = parse_trade_decision_payload(
            {
                "action": "BUY",
                "confidence": 1.5,
                "position_size": 0.8,
                "summary": "结论",
                "reasoning": "依据",
                "risk_notes": "风险",
            },
            max_position_size=0.5,
            risk_position_size=0.3,
            llm_provider="deepseek",
            llm_model="deepseek-chat",
            llm_elapsed_ms=1234,
            llm_prompt_summary="symbol=600519, tech=bullish/78",
            llm_response_summary="action=BUY, confidence=1.5",
        )

        self.assertEqual(decision.action, TradeAction.BUY)
        self.assertEqual(decision.confidence, 0.95)
        self.assertEqual(decision.position_size, 0.3)
        self.assertEqual(decision.decision_source, "deepseek")
        self.assertEqual(decision.llm_elapsed_ms, 1234)
        self.assertEqual(decision.llm_prompt_summary, "symbol=600519, tech=bullish/78")
        self.assertEqual(decision.llm_response_summary, "action=BUY, confidence=1.5")

    def test_non_buy_position_is_zero(self) -> None:
        decision = parse_trade_decision_payload(
            {"action": "SELL", "position_size": 0.3},
            max_position_size=0.5,
            risk_position_size=0.3,
            llm_provider="deepseek",
            llm_model="deepseek-chat",
        )

        self.assertEqual(decision.action, TradeAction.SELL)
        self.assertEqual(decision.position_size, 0.0)

    def test_wait_action_is_supported_and_position_is_zero(self) -> None:
        decision = parse_trade_decision_payload(
            {"action": "WAIT", "position_size": 0.3},
            max_position_size=0.5,
            risk_position_size=0.3,
            llm_provider="deepseek",
            llm_model="deepseek-chat",
        )

        self.assertEqual(decision.action, TradeAction.WAIT)
        self.assertEqual(decision.position_size, 0.0)

    def test_invalid_action_defaults_to_wait(self) -> None:
        decision = parse_trade_decision_payload(
            {"action": "WATCH", "position_size": 0.3},
            max_position_size=0.5,
            risk_position_size=0.3,
            llm_provider="deepseek",
            llm_model="deepseek-chat",
        )

        self.assertEqual(decision.action, TradeAction.WAIT)
        self.assertEqual(decision.position_size, 0.0)


if __name__ == "__main__":
    unittest.main()