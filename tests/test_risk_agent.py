from __future__ import annotations

import unittest
from unittest.mock import patch

from quantmind.agents.risk_agent import RiskControlAgent
from quantmind.llm.client import LLMError
from quantmind.schemas import AgentState, NewsReport, RiskLevel, Signal, TechnicalReport


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


if __name__ == "__main__":
    unittest.main()