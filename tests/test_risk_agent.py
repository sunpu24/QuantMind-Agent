from __future__ import annotations

import unittest
from unittest.mock import patch

from quantmind.agents.risk_agent import RiskControlAgent
from quantmind.llm.client import LLMError
from quantmind.schemas import (
    AgentState,
    FundamentalReport,
    NewsReport,
    ResearchDebateReport,
    RiskLevel,
    SentimentReport,
    Signal,
    TechnicalReport,
)


def _state() -> AgentState:
    return AgentState(
        symbol="600519",
        trade_date="2024-06-05",
        technical_report=TechnicalReport(
            signal=Signal.BULLISH,
            score=82,
            summary="技术面偏强。",
            indicators={"ma5": 10, "ma10": 9, "latest": 11, "volume_change": 0.2},
        ),
        news_report=NewsReport(
            sentiment=Signal.NEUTRAL,
            score=55,
            summary="新闻中性。",
            headlines=[],
        ),
    )


class RiskControlAgentTest(unittest.TestCase):
    def test_deepseek_guardrails_clip_position_and_rule_stop_loss(self) -> None:
        agent = RiskControlAgent()
        payload = {
            "level": "low",
            "score": 20,
            "suggested_position": 0.8,
            "stop_loss_pct": 0.3,
            "summary": "DeepSeek 认为风险较低，可积极参与。",
        }

        with patch("quantmind.agents.risk_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            mock_settings.default_position_size = 0.3
            mock_settings.max_position_size = 0.5
            mock_settings.stop_loss_pct = 0.05
            with patch("quantmind.agents.risk_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.return_value = payload
                result = agent.run(_state())

        self.assertEqual(result.risk_report.risk_source, "deepseek_guardrailed")
        self.assertEqual(result.risk_report.level, RiskLevel.LOW)
        self.assertEqual(result.risk_report.score, 20)
        self.assertEqual(result.risk_report.suggested_position, 0.5)
        self.assertEqual(result.risk_report.stop_loss_pct, 0.05)
        self.assertIn("裁剪到 50%", result.risk_report.summary)

    def test_deepseek_error_falls_back_to_rule_report(self) -> None:
        agent = RiskControlAgent()

        with patch("quantmind.agents.risk_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            mock_settings.default_position_size = 0.3
            mock_settings.max_position_size = 0.5
            mock_settings.stop_loss_pct = 0.05
            with patch("quantmind.agents.risk_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.side_effect = LLMError("bad response")
                result = agent.run(_state())

        self.assertEqual(result.risk_report.risk_source, "rule")
        self.assertEqual(result.risk_report.level, RiskLevel.MEDIUM)
        self.assertEqual(result.risk_report.suggested_position, 0.3)

    def test_non_deepseek_provider_uses_rule_report(self) -> None:
        agent = RiskControlAgent()

        with patch("quantmind.agents.risk_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            mock_settings.default_position_size = 0.3
            mock_settings.max_position_size = 0.5
            mock_settings.stop_loss_pct = 0.05
            result = agent.run(_state())

        self.assertEqual(result.risk_report.risk_source, "rule")
        self.assertEqual(result.risk_report.level, RiskLevel.MEDIUM)

    def test_rule_report_uses_new_reports_to_increase_risk(self) -> None:
        agent = RiskControlAgent()
        state = _state()
        state.technical_report.signal = Signal.NEUTRAL
        state.news_report.sentiment = Signal.NEUTRAL
        state.fundamental_report = FundamentalReport(
            signal=Signal.BEARISH,
            score=28,
            summary="利润增长为负且负债率偏高。",
            metrics={"profit_growth_yoy": -0.2, "debt_ratio": 0.75},
        )
        state.sentiment_report = SentimentReport(
            sentiment=Signal.BEARISH,
            score=32,
            buzz_score=70,
            disagreement_score=78,
            summary="负面情绪较多且分歧较高。",
            sources=["unit_test"],
        )
        state.research_debate_report = ResearchDebateReport(
            conclusion=Signal.BEARISH,
            confidence=0.76,
            bullish_summary="多头证据不足。",
            bearish_summary="空头风险更充分。",
            final_summary="研究经理认为偏空。",
            key_evidence=["基本面 bearish", "舆情 bearish"],
        )

        with patch("quantmind.agents.risk_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            mock_settings.default_position_size = 0.3
            mock_settings.max_position_size = 0.5
            mock_settings.stop_loss_pct = 0.05
            result = agent.run(state)

        self.assertEqual(result.risk_report.level, RiskLevel.HIGH)
        self.assertGreaterEqual(result.risk_report.score, 80)
        self.assertLessEqual(result.risk_report.suggested_position, 0.15)

    def test_rule_report_bullish_research_lowers_risk_without_exceeding_max_position(self) -> None:
        agent = RiskControlAgent()
        state = _state()
        state.fundamental_report = FundamentalReport(
            signal=Signal.BULLISH,
            score=78,
            summary="ROE 较高且利润增长为正。",
            metrics={"roe": 0.2},
        )
        state.sentiment_report = SentimentReport(
            sentiment=Signal.BULLISH,
            score=72,
            buzz_score=55,
            disagreement_score=15,
            summary="正面情绪较多。",
            sources=["unit_test"],
        )
        state.research_debate_report = ResearchDebateReport(
            conclusion=Signal.BULLISH,
            confidence=0.74,
            bullish_summary="多头证据更充分。",
            bearish_summary="空头证据有限。",
            final_summary="研究经理认为偏多。",
            key_evidence=["技术面 bullish", "基本面 bullish"],
        )

        with patch("quantmind.agents.risk_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            mock_settings.default_position_size = 0.3
            mock_settings.max_position_size = 0.35
            mock_settings.stop_loss_pct = 0.05
            result = agent.run(state)

        self.assertEqual(result.risk_report.level, RiskLevel.LOW)
        self.assertLessEqual(result.risk_report.suggested_position, 0.35)


if __name__ == "__main__":
    unittest.main()