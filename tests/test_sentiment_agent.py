from __future__ import annotations

import unittest
from unittest.mock import patch

from quantmind.agents.sentiment_agent import NO_SENTIMENT_DATA_SUMMARY, SentimentAnalysisAgent
from quantmind.llm.client import LLMError
from quantmind.schemas import AgentState, Signal


def _state(items: list[dict[str, object]] | None = None) -> AgentState:
    return AgentState(
        symbol="600519",
        trade_date="2024-06-05",
        news_data=items
        if items is not None
        else [
            {
                "title": "公司核心业务增长超预期，机构继续看好",
                "summary": "市场关注度提升。",
                "source": "unit_test",
                "news_source": "unit_test",
            }
        ],
    )


class SentimentAnalysisAgentTest(unittest.TestCase):
    def test_empty_news_returns_neutral_without_llm(self) -> None:
        agent = SentimentAnalysisAgent()
        state = AgentState(symbol="600519", trade_date="2024-06-05", news_data=[])

        with patch("quantmind.agents.sentiment_agent.DeepSeekChatClient") as mock_client_cls:
            result = agent.run(state)

        self.assertEqual(result.sentiment_report.sentiment, Signal.NEUTRAL)
        self.assertEqual(result.sentiment_report.score, 50)
        self.assertEqual(result.sentiment_report.buzz_score, 5)
        self.assertEqual(result.sentiment_report.disagreement_score, 5)
        self.assertEqual(result.sentiment_report.summary, NO_SENTIMENT_DATA_SUMMARY)
        self.assertEqual(result.sentiment_report.sources, [])
        mock_client_cls.assert_not_called()

    def test_rule_report_bullish(self) -> None:
        agent = SentimentAnalysisAgent()

        with patch("quantmind.agents.sentiment_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(_state())

        self.assertEqual(result.sentiment_report.sentiment, Signal.BULLISH)
        self.assertGreater(result.sentiment_report.score, 50)
        self.assertGreater(result.sentiment_report.buzz_score, 10)
        self.assertEqual(result.sentiment_report.sources, ["unit_test"])

    def test_rule_report_bearish(self) -> None:
        agent = SentimentAnalysisAgent()
        items = [
            {
                "title": "公司业绩下滑且不及预期",
                "summary": "投资者担忧风险继续释放。",
                "source": "unit_test",
            }
        ]

        with patch("quantmind.agents.sentiment_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(_state(items))

        self.assertEqual(result.sentiment_report.sentiment, Signal.BEARISH)
        self.assertLess(result.sentiment_report.score, 50)

    def test_rule_report_detects_disagreement(self) -> None:
        agent = SentimentAnalysisAgent()
        items = [
            {"title": "公司增长超预期但估值风险引发担忧", "summary": "多空分歧升温。", "source": "source_a"},
            {"title": "机构看好盈利改善，同时提示业绩下滑风险", "summary": "市场观点分化。", "source": "source_b"},
        ]

        with patch("quantmind.agents.sentiment_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(_state(items))

        self.assertGreaterEqual(result.sentiment_report.disagreement_score, 60)
        self.assertIn("分歧", result.sentiment_report.summary)

    def test_deepseek_success_outputs_structured_sentiment_report(self) -> None:
        agent = SentimentAnalysisAgent()
        payload = {
            "sentiment": "bullish",
            "score": 78,
            "buzz_score": 70,
            "disagreement_score": 25,
            "summary": "DeepSeek 判断市场情绪偏正面。",
            "sources": ["unit_test"],
        }

        with patch("quantmind.agents.sentiment_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.sentiment_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.return_value = payload
                result = agent.run(_state())

        self.assertEqual(result.sentiment_report.sentiment, Signal.BULLISH)
        self.assertEqual(result.sentiment_report.score, 78)
        self.assertEqual(result.sentiment_report.buzz_score, 70)
        self.assertEqual(result.sentiment_report.disagreement_score, 25)
        self.assertEqual(result.sentiment_report.summary, "DeepSeek 判断市场情绪偏正面。")
        self.assertEqual(result.sentiment_report.sources, ["unit_test"])
        mock_client_cls.return_value.chat_json.assert_called_once()

    def test_deepseek_error_falls_back_to_rule_report(self) -> None:
        agent = SentimentAnalysisAgent()

        with patch("quantmind.agents.sentiment_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.sentiment_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.side_effect = LLMError("bad response")
                result = agent.run(_state())

        self.assertEqual(result.sentiment_report.sentiment, Signal.BULLISH)
        self.assertGreater(result.sentiment_report.score, 50)

    def test_deepseek_prompt_contains_sentiment_constraints(self) -> None:
        agent = SentimentAnalysisAgent()
        state = _state()
        rule_report = agent._make_rule_report(state)
        messages = agent._build_deepseek_messages(state, rule_report)
        combined = "\n".join(message["content"] for message in messages)

        self.assertIn("市场情绪", combined)
        self.assertIn("关注热度", combined)
        self.assertIn("分歧程度", combined)
        self.assertIn("不要编造", combined)
        self.assertIn("严格 JSON", combined)


if __name__ == "__main__":
    unittest.main()