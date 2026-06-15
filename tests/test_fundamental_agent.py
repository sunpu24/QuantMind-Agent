from __future__ import annotations

import unittest
from unittest.mock import patch

from quantmind.agents.fundamental_agent import (
    NO_FUNDAMENTAL_DATA_SUMMARY,
    FundamentalAnalysisAgent,
)
from quantmind.llm.client import LLMError
from quantmind.schemas import AgentState, Signal


def _state(metrics: dict[str, object] | None = None, source: str = "unit_test") -> AgentState:
    return AgentState(
        symbol="600519",
        trade_date="2024-06-05",
        fundamental_data={
            "metrics": metrics or {},
            "source": source,
            "requested_provider": "unit_test",
            "fallback_type": None,
            "fallback_reason": None,
        },
    )


class FundamentalAnalysisAgentTest(unittest.TestCase):
    def test_empty_data_returns_neutral_without_llm(self) -> None:
        agent = FundamentalAnalysisAgent()

        with patch("quantmind.agents.fundamental_agent.DeepSeekChatClient") as mock_client_cls:
            result = agent.run(_state({}))

        self.assertEqual(result.fundamental_report.signal, Signal.NEUTRAL)
        self.assertEqual(result.fundamental_report.score, 50)
        self.assertEqual(result.fundamental_report.summary, NO_FUNDAMENTAL_DATA_SUMMARY)
        self.assertEqual(result.fundamental_report.metrics, {})
        mock_client_cls.assert_not_called()

    def test_rule_report_bullish(self) -> None:
        agent = FundamentalAnalysisAgent()

        with patch("quantmind.agents.fundamental_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(
                _state(
                    {
                        "roe": 0.22,
                        "earnings_growth_yoy": 0.18,
                        "debt_ratio": 0.32,
                        "pe_ratio": 28,
                    }
                )
            )

        self.assertEqual(result.fundamental_report.signal, Signal.BULLISH)
        self.assertGreater(result.fundamental_report.score, 60)

    def test_rule_report_bearish(self) -> None:
        agent = FundamentalAnalysisAgent()

        with patch("quantmind.agents.fundamental_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(
                _state(
                    {
                        "roe": 0.02,
                        "earnings_growth_yoy": -0.2,
                        "debt_ratio": 0.78,
                        "pe_ratio": 95,
                    }
                )
            )

        self.assertEqual(result.fundamental_report.signal, Signal.BEARISH)
        self.assertLess(result.fundamental_report.score, 40)

    def test_deepseek_success_outputs_structured_fundamental_report(self) -> None:
        agent = FundamentalAnalysisAgent()
        payload = {
            "signal": "bullish",
            "score": 82,
            "summary": "DeepSeek 判断基本面偏强。",
            "metrics": {"roe": 999},
        }

        with patch("quantmind.agents.fundamental_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.fundamental_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.return_value = payload
                result = agent.run(_state({"roe": 0.2, "earnings_growth_yoy": 0.1}))

        self.assertEqual(result.fundamental_report.signal, Signal.BULLISH)
        self.assertEqual(result.fundamental_report.score, 82)
        self.assertEqual(result.fundamental_report.summary, "DeepSeek 判断基本面偏强。")
        self.assertEqual(result.fundamental_report.metrics, {"roe": 0.2, "earnings_growth_yoy": 0.1})
        self.assertEqual(result.fundamental_report.data_source, "deepseek_guardrailed")

    def test_deepseek_error_falls_back_to_rule_report(self) -> None:
        agent = FundamentalAnalysisAgent()

        with patch("quantmind.agents.fundamental_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.fundamental_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.side_effect = LLMError("bad response")
                result = agent.run(_state({"roe": 0.22, "earnings_growth_yoy": 0.18, "debt_ratio": 0.32}))

        self.assertEqual(result.fundamental_report.signal, Signal.BULLISH)
        self.assertEqual(result.fundamental_report.data_source, "unit_test")

    def test_deepseek_prompt_forbids_fabricating_financial_data(self) -> None:
        agent = FundamentalAnalysisAgent()
        state = _state({"roe": 0.2, "pe_ratio": 30})
        rule_report = agent._make_rule_report(state.fundamental_data["metrics"], data_source="unit_test")
        messages = agent._build_deepseek_messages(state, state.fundamental_data["metrics"], rule_report)
        combined = "\n".join(message["content"] for message in messages)

        self.assertIn("只能基于用户提供的财务字段分析", combined)
        self.assertIn("不得编造财报数据", combined)
        self.assertIn("严格 JSON", combined)


if __name__ == "__main__":
    unittest.main()