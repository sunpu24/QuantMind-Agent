from __future__ import annotations

import unittest
from unittest.mock import patch

from quantmind.agents.news_agent import FALLBACK_MOCK_WARNING, NO_RELEVANT_NEWS_SUMMARY, NewsAnalysisAgent
from quantmind.llm.client import LLMError
from quantmind.schemas import AgentState, Signal


def _state(news_source: str = "alpha_vantage", fallback_type: str | None = None) -> AgentState:
    return AgentState(
        symbol="600519",
        trade_date="2024-06-05",
        news_data=[
            {
                "title": "公司核心业务保持稳定增长",
                "summary": "机构关注度提升。",
                "source": news_source,
                "news_source": news_source,
                "news_fallback_type": fallback_type,
            }
        ],
    )


class NewsAnalysisAgentTest(unittest.TestCase):
    def test_empty_news_returns_no_relevant_news_report_without_llm(self) -> None:
        agent = NewsAnalysisAgent()
        state = AgentState(symbol="600519", trade_date="2024-06-05", news_data=[])

        with patch("quantmind.agents.news_agent.DeepSeekChatClient") as mock_client_cls:
            result = agent.run(state)

        self.assertEqual(result.news_report.sentiment, Signal.NEUTRAL)
        self.assertEqual(result.news_report.score, 50)
        self.assertEqual(result.news_report.summary, NO_RELEVANT_NEWS_SUMMARY)
        self.assertEqual(result.news_report.headlines, [])
        mock_client_cls.assert_not_called()

    def test_deepseek_success_outputs_structured_news_report(self) -> None:
        agent = NewsAnalysisAgent()
        payload = {
            "sentiment": "bullish",
            "score": 82,
            "summary": "DeepSeek 判断新闻偏正面。",
            "headlines": ["公司核心业务保持稳定增长"],
        }

        with patch("quantmind.agents.news_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.news_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.return_value = payload
                result = agent.run(_state())

        self.assertEqual(result.news_report.sentiment, Signal.BULLISH)
        self.assertEqual(result.news_report.score, 82)
        self.assertEqual(result.news_report.summary, "DeepSeek 判断新闻偏正面。")
        mock_client_cls.return_value.chat_json.assert_called_once()

    def test_fallback_mock_prompt_contains_warning(self) -> None:
        agent = NewsAnalysisAgent()
        messages = agent._build_deepseek_messages(
            _state(news_source="alpha_vantage_fallback_mock", fallback_type="empty_data")
        )

        self.assertIn(FALLBACK_MOCK_WARNING, messages[1]["content"])
        self.assertIn("新闻数据源: alpha_vantage_fallback_mock", messages[1]["content"])

    def test_akshare_fallback_mock_prompt_contains_warning(self) -> None:
        agent = NewsAnalysisAgent()
        messages = agent._build_deepseek_messages(
            _state(news_source="akshare_fallback_mock", fallback_type="proxy_error")
        )

        self.assertIn(FALLBACK_MOCK_WARNING, messages[1]["content"])
        self.assertIn("新闻数据源: akshare_fallback_mock", messages[1]["content"])

    def test_deepseek_error_falls_back_to_rule_report(self) -> None:
        agent = NewsAnalysisAgent()

        with patch("quantmind.agents.news_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.news_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.side_effect = LLMError("bad response")
                result = agent.run(_state())

        self.assertEqual(result.news_report.sentiment, Signal.BULLISH)
        self.assertEqual(result.news_report.score, 68)
        self.assertEqual(result.news_report.summary, "新闻关键词偏正面，市场情绪对股价有一定支撑。")

    def test_non_deepseek_provider_uses_rule_report(self) -> None:
        agent = NewsAnalysisAgent()

        with patch("quantmind.agents.news_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(_state())

        self.assertEqual(result.news_report.sentiment, Signal.BULLISH)
        self.assertEqual(result.news_report.score, 68)


if __name__ == "__main__":
    unittest.main()