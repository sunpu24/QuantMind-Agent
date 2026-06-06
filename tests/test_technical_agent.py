from __future__ import annotations

import unittest
from unittest.mock import patch

from quantmind.agents.technical_agent import FALLBACK_MOCK_WARNING, TechnicalAnalysisAgent
from quantmind.llm.client import LLMError
from quantmind.schemas import AgentState, Signal


def _state(source: str = "akshare", fallback_type: str | None = None) -> AgentState:
    return AgentState(
        symbol="600519",
        trade_date="2024-06-05",
        market_data={
            "close_prices": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
            "volumes": [100, 110, 120, 130, 140, 150, 160, 170, 180, 220],
            "source": source,
            "requested_provider": "akshare",
            "fallback_type": fallback_type,
            "fallback_reason": "network unavailable" if fallback_type else None,
        },
    )


class TechnicalAnalysisAgentTest(unittest.TestCase):
    def test_deepseek_success_outputs_structured_technical_report(self) -> None:
        agent = TechnicalAnalysisAgent()
        payload = {
            "signal": "bullish",
            "score": 86,
            "summary": "DeepSeek 判断均线结构偏强。",
            "indicators": {"ma5": 999999},
        }

        with patch("quantmind.agents.technical_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.technical_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.return_value = payload
                result = agent.run(_state())

        self.assertEqual(result.technical_report.signal, Signal.BULLISH)
        self.assertEqual(result.technical_report.score, 86)
        self.assertEqual(result.technical_report.summary, "DeepSeek 判断均线结构偏强。")
        self.assertEqual(
            result.technical_report.indicators,
            {"ma5": 17.0, "ma10": 14.5, "latest": 19, "volume_change": 0.2222},
        )
        mock_client_cls.return_value.chat_json.assert_called_once()

    def test_deepseek_error_falls_back_to_rule_report(self) -> None:
        agent = TechnicalAnalysisAgent()

        with patch("quantmind.agents.technical_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.technical_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.side_effect = LLMError("bad response")
                result = agent.run(_state())

        self.assertEqual(result.technical_report.signal, Signal.BULLISH)
        self.assertEqual(result.technical_report.score, 84)
        self.assertEqual(
            result.technical_report.summary,
            "最新价格站上短期与中期均线，趋势偏强。 同时成交量有所放大，强化上涨信号。",
        )

    def test_non_deepseek_provider_uses_rule_report(self) -> None:
        agent = TechnicalAnalysisAgent()

        with patch("quantmind.agents.technical_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(_state())

        self.assertEqual(result.technical_report.signal, Signal.BULLISH)
        self.assertEqual(result.technical_report.score, 84)

    def test_fallback_mock_prompt_contains_warning(self) -> None:
        agent = TechnicalAnalysisAgent()
        indicators = {"ma5": 17.0, "ma10": 14.5, "latest": 19, "volume_change": 0.2222}
        rule_report = agent._make_rule_report(indicators)

        messages = agent._build_deepseek_messages(
            _state(source="akshare_fallback_mock", fallback_type="proxy_error"),
            indicators,
            rule_report,
        )

        self.assertIn(FALLBACK_MOCK_WARNING, messages[1]["content"])
        self.assertIn("行情数据源: akshare_fallback_mock", messages[1]["content"])

    def test_insufficient_indicators_do_not_call_deepseek(self) -> None:
        agent = TechnicalAnalysisAgent()
        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            market_data={"close_prices": [10, 11, 12, 13], "volumes": [100, 110, 120, 130]},
        )

        with patch("quantmind.agents.technical_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.technical_agent.DeepSeekChatClient") as mock_client_cls:
                result = agent.run(state)

        self.assertEqual(result.technical_report.signal, Signal.NEUTRAL)
        self.assertEqual(result.technical_report.score, 50)
        self.assertEqual(result.technical_report.indicators, {})
        mock_client_cls.return_value.chat_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()