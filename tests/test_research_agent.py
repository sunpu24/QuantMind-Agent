from __future__ import annotations

import unittest
from unittest.mock import patch

from quantmind.agents.research_agent import (
    NO_BEARISH_EVIDENCE_SUMMARY,
    NO_BULLISH_EVIDENCE_SUMMARY,
    NO_RESEARCH_DEBATE_SUMMARY,
    BearishResearchAgent,
    BullishResearchAgent,
    ResearchManagerAgent,
)
from quantmind.llm.client import LLMError
from quantmind.schemas import (
    AgentState,
    FundamentalReport,
    NewsReport,
    ResearchPerspectiveReport,
    SentimentReport,
    Signal,
    TechnicalReport,
)


def _state() -> AgentState:
    return AgentState(symbol="600519", trade_date="2024-06-05")


class BullishResearchAgentTest(unittest.TestCase):
    def test_missing_reports_returns_neutral_without_llm(self) -> None:
        agent = BullishResearchAgent()

        with patch("quantmind.agents.research_agent.DeepSeekChatClient") as mock_client_cls:
            result = agent.run(_state())

        self.assertEqual(result.bullish_research_report.stance, Signal.NEUTRAL)
        self.assertEqual(result.bullish_research_report.thesis, NO_BULLISH_EVIDENCE_SUMMARY)
        self.assertEqual(result.bullish_research_report.key_points, [])
        mock_client_cls.assert_not_called()

    def test_rule_report_collects_bullish_points(self) -> None:
        agent = BullishResearchAgent()
        state = _state()
        state.technical_report = TechnicalReport(
            signal=Signal.BULLISH,
            score=78,
            summary="最新价格站上均线，趋势偏强。",
        )
        state.news_report = NewsReport(
            sentiment=Signal.BULLISH,
            score=72,
            summary="新闻关键词偏正面。",
            headlines=["业务增长超预期"],
        )
        state.fundamental_report = FundamentalReport(
            signal=Signal.BULLISH,
            score=80,
            summary="ROE 较高且利润增长为正。",
            metrics={"roe": 0.2},
        )

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(state)

        self.assertEqual(result.bullish_research_report.stance, Signal.BULLISH)
        self.assertGreater(result.bullish_research_report.confidence, 0.55)
        self.assertGreaterEqual(len(result.bullish_research_report.key_points), 3)
        self.assertIn("技术面偏多", result.bullish_research_report.key_points[0])

    def test_bearish_reports_become_concerns_not_bullish_points(self) -> None:
        agent = BullishResearchAgent()
        state = _state()
        state.technical_report = TechnicalReport(
            signal=Signal.BEARISH,
            score=30,
            summary="最新价格跌破均线，趋势偏弱。",
        )
        state.sentiment_report = SentimentReport(
            sentiment=Signal.BEARISH,
            score=35,
            buzz_score=60,
            disagreement_score=70,
            summary="负面情绪词更多，分歧较高。",
            sources=["unit_test"],
        )

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(state)

        self.assertEqual(result.bullish_research_report.stance, Signal.NEUTRAL)
        self.assertEqual(result.bullish_research_report.key_points, [])
        self.assertTrue(any("偏空" in item for item in result.bullish_research_report.concerns))

    def test_deepseek_success_outputs_structured_report(self) -> None:
        agent = BullishResearchAgent()
        state = _state()
        state.technical_report = TechnicalReport(
            signal=Signal.BULLISH,
            score=78,
            summary="趋势偏强。",
        )
        payload = {
            "stance": "bullish",
            "confidence": 0.72,
            "thesis": "DeepSeek 认为多头证据较充分。",
            "key_points": ["技术面趋势偏强。"],
            "concerns": ["仍需关注新闻不足。"],
        }

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.research_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.return_value = payload
                result = agent.run(state)

        self.assertEqual(result.bullish_research_report.stance, Signal.BULLISH)
        self.assertEqual(result.bullish_research_report.confidence, 0.72)
        self.assertEqual(result.bullish_research_report.thesis, "DeepSeek 认为多头证据较充分。")
        self.assertEqual(result.bullish_research_report.key_points, ["技术面趋势偏强。"])
        mock_client_cls.return_value.chat_json.assert_called_once()

    def test_deepseek_error_falls_back_to_rule_report(self) -> None:
        agent = BullishResearchAgent()
        state = _state()
        state.news_report = NewsReport(
            sentiment=Signal.BULLISH,
            score=70,
            summary="新闻关键词偏正面。",
            headlines=["增长"],
        )

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.research_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.side_effect = LLMError("bad response")
                result = agent.run(state)

        self.assertEqual(result.bullish_research_report.stance, Signal.BULLISH)
        self.assertGreater(len(result.bullish_research_report.key_points), 0)

    def test_deepseek_prompt_contains_research_constraints(self) -> None:
        agent = BullishResearchAgent()
        state = _state()
        state.technical_report = TechnicalReport(
            signal=Signal.BULLISH,
            score=78,
            summary="趋势偏强。",
        )
        rule_report = agent._make_rule_report(state)
        messages = agent._build_deepseek_messages(state, rule_report)
        combined = "\n".join(message["content"] for message in messages)

        self.assertIn("多头研究员", combined)
        self.assertIn("只能基于已有报告", combined)
        self.assertIn("不能编造新事实", combined)
        self.assertIn("严格 JSON", combined)


class BearishResearchAgentTest(unittest.TestCase):
    def test_missing_reports_returns_neutral_without_llm(self) -> None:
        agent = BearishResearchAgent()

        with patch("quantmind.agents.research_agent.DeepSeekChatClient") as mock_client_cls:
            result = agent.run(_state())

        self.assertEqual(result.bearish_research_report.stance, Signal.NEUTRAL)
        self.assertEqual(result.bearish_research_report.thesis, NO_BEARISH_EVIDENCE_SUMMARY)
        self.assertEqual(result.bearish_research_report.key_points, [])
        mock_client_cls.assert_not_called()

    def test_rule_report_collects_bearish_points(self) -> None:
        agent = BearishResearchAgent()
        state = _state()
        state.technical_report = TechnicalReport(
            signal=Signal.BEARISH,
            score=28,
            summary="最新价格跌破均线，趋势偏弱。",
        )
        state.news_report = NewsReport(
            sentiment=Signal.BEARISH,
            score=32,
            summary="新闻关键词偏负面。",
            headlines=["需求低于预期"],
        )
        state.fundamental_report = FundamentalReport(
            signal=Signal.BEARISH,
            score=30,
            summary="利润增长为负且负债率较高。",
            metrics={"profit_growth": -0.12},
        )

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(state)

        self.assertEqual(result.bearish_research_report.stance, Signal.BEARISH)
        self.assertGreater(result.bearish_research_report.confidence, 0.55)
        self.assertGreaterEqual(len(result.bearish_research_report.key_points), 3)
        self.assertIn("技术面偏空", result.bearish_research_report.key_points[0])

    def test_bullish_reports_become_concerns_not_bearish_points(self) -> None:
        agent = BearishResearchAgent()
        state = _state()
        state.technical_report = TechnicalReport(
            signal=Signal.BULLISH,
            score=78,
            summary="最新价格站上均线，趋势偏强。",
        )
        state.sentiment_report = SentimentReport(
            sentiment=Signal.BULLISH,
            score=70,
            buzz_score=60,
            disagreement_score=20,
            summary="正面情绪词更多，分歧较低。",
            sources=["unit_test"],
        )

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(state)

        self.assertEqual(result.bearish_research_report.stance, Signal.NEUTRAL)
        self.assertEqual(result.bearish_research_report.key_points, [])
        self.assertTrue(any("偏多" in item for item in result.bearish_research_report.concerns))

    def test_deepseek_success_outputs_structured_report(self) -> None:
        agent = BearishResearchAgent()
        state = _state()
        state.technical_report = TechnicalReport(
            signal=Signal.BEARISH,
            score=28,
            summary="趋势偏弱。",
        )
        payload = {
            "stance": "bearish",
            "confidence": 0.72,
            "thesis": "DeepSeek 认为空头证据较充分。",
            "key_points": ["技术面趋势偏弱。"],
            "concerns": ["仍需关注新闻不足。"],
        }

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.research_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.return_value = payload
                result = agent.run(state)

        self.assertEqual(result.bearish_research_report.stance, Signal.BEARISH)
        self.assertEqual(result.bearish_research_report.confidence, 0.72)
        self.assertEqual(result.bearish_research_report.thesis, "DeepSeek 认为空头证据较充分。")
        self.assertEqual(result.bearish_research_report.key_points, ["技术面趋势偏弱。"])
        mock_client_cls.return_value.chat_json.assert_called_once()

    def test_deepseek_error_falls_back_to_rule_report(self) -> None:
        agent = BearishResearchAgent()
        state = _state()
        state.news_report = NewsReport(
            sentiment=Signal.BEARISH,
            score=30,
            summary="新闻关键词偏负面。",
            headlines=["下滑"],
        )

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.research_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.side_effect = LLMError("bad response")
                result = agent.run(state)

        self.assertEqual(result.bearish_research_report.stance, Signal.BEARISH)
        self.assertGreater(len(result.bearish_research_report.key_points), 0)

    def test_deepseek_prompt_contains_research_constraints(self) -> None:
        agent = BearishResearchAgent()
        state = _state()
        state.technical_report = TechnicalReport(
            signal=Signal.BEARISH,
            score=28,
            summary="趋势偏弱。",
        )
        rule_report = agent._make_rule_report(state)
        messages = agent._build_deepseek_messages(state, rule_report)
        combined = "\n".join(message["content"] for message in messages)

        self.assertIn("空头研究员", combined)
        self.assertIn("只能基于已有报告", combined)
        self.assertIn("不能编造新事实", combined)
        self.assertIn("严格 JSON", combined)


class ResearchManagerAgentTest(unittest.TestCase):
    def test_missing_reports_returns_neutral_without_llm(self) -> None:
        agent = ResearchManagerAgent()

        with patch("quantmind.agents.research_agent.DeepSeekChatClient") as mock_client_cls:
            result = agent.run(_state())

        self.assertEqual(result.research_debate_report.conclusion, Signal.NEUTRAL)
        self.assertEqual(result.research_debate_report.final_summary, NO_RESEARCH_DEBATE_SUMMARY)
        self.assertEqual(result.research_debate_report.key_evidence, [])
        mock_client_cls.assert_not_called()

    def test_rule_report_prefers_stronger_bullish_research(self) -> None:
        agent = ResearchManagerAgent()
        state = _state()
        state.bullish_research_report = ResearchPerspectiveReport(
            stance=Signal.BULLISH,
            confidence=0.76,
            thesis="多头证据较一致。",
            key_points=["技术面偏多", "基本面偏多"],
            concerns=["新闻样本有限"],
        )
        state.bearish_research_report = ResearchPerspectiveReport(
            stance=Signal.NEUTRAL,
            confidence=0.42,
            thesis="空头证据不足。",
            key_points=[],
            concerns=["缺少明确利空"],
        )
        state.technical_report = TechnicalReport(
            signal=Signal.BULLISH,
            score=78,
            summary="价格站上均线。",
        )

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(state)

        self.assertEqual(result.research_debate_report.conclusion, Signal.BULLISH)
        self.assertGreater(result.research_debate_report.confidence, 0.5)
        self.assertIn("多头证据", result.research_debate_report.final_summary)
        self.assertTrue(any("多头观点" in item for item in result.research_debate_report.key_evidence))

    def test_rule_report_prefers_stronger_bearish_research(self) -> None:
        agent = ResearchManagerAgent()
        state = _state()
        state.bullish_research_report = ResearchPerspectiveReport(
            stance=Signal.NEUTRAL,
            confidence=0.4,
            thesis="多头证据不足。",
            key_points=[],
            concerns=["趋势偏弱"],
        )
        state.bearish_research_report = ResearchPerspectiveReport(
            stance=Signal.BEARISH,
            confidence=0.74,
            thesis="空头风险较一致。",
            key_points=["技术面偏空", "舆情偏空"],
            concerns=["基本面数据有限"],
        )
        state.sentiment_report = SentimentReport(
            sentiment=Signal.BEARISH,
            score=35,
            buzz_score=60,
            disagreement_score=72,
            summary="负面情绪较多且分歧较高。",
            sources=["unit_test"],
        )

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(state)

        self.assertEqual(result.research_debate_report.conclusion, Signal.BEARISH)
        self.assertGreater(result.research_debate_report.confidence, 0.5)
        self.assertIn("空头风险", result.research_debate_report.final_summary)
        self.assertTrue(any("空头观点" in item for item in result.research_debate_report.key_evidence))

    def test_balanced_research_returns_neutral(self) -> None:
        agent = ResearchManagerAgent()
        state = _state()
        state.bullish_research_report = ResearchPerspectiveReport(
            stance=Signal.BULLISH,
            confidence=0.6,
            thesis="多头有一定证据。",
            key_points=["新闻偏多"],
            concerns=[],
        )
        state.bearish_research_report = ResearchPerspectiveReport(
            stance=Signal.BEARISH,
            confidence=0.58,
            thesis="空头也有一定证据。",
            key_points=["估值压力"],
            concerns=[],
        )

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            result = agent.run(state)

        self.assertEqual(result.research_debate_report.conclusion, Signal.NEUTRAL)
        self.assertIn("多空证据较为均衡", result.research_debate_report.final_summary)

    def test_deepseek_success_outputs_structured_debate_report(self) -> None:
        agent = ResearchManagerAgent()
        state = _state()
        state.bullish_research_report = ResearchPerspectiveReport(
            stance=Signal.BULLISH,
            confidence=0.7,
            thesis="多头证据较多。",
            key_points=["技术偏强"],
            concerns=[],
        )
        payload = {
            "conclusion": "bullish",
            "confidence": 0.73,
            "bullish_summary": "DeepSeek 总结多头更强。",
            "bearish_summary": "DeepSeek 总结空头较弱。",
            "final_summary": "研究经理认为偏多。",
            "key_evidence": ["技术偏强"],
        }

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.research_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.return_value = payload
                result = agent.run(state)

        self.assertEqual(result.research_debate_report.conclusion, Signal.BULLISH)
        self.assertEqual(result.research_debate_report.confidence, 0.73)
        self.assertEqual(result.research_debate_report.final_summary, "研究经理认为偏多。")
        self.assertEqual(result.research_debate_report.key_evidence, ["技术偏强"])
        mock_client_cls.return_value.chat_json.assert_called_once()

    def test_deepseek_error_falls_back_to_rule_report(self) -> None:
        agent = ResearchManagerAgent()
        state = _state()
        state.bearish_research_report = ResearchPerspectiveReport(
            stance=Signal.BEARISH,
            confidence=0.72,
            thesis="空头证据较充分。",
            key_points=["技术面偏空"],
            concerns=[],
        )

        with patch("quantmind.agents.research_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.has_llm_api_key = True
            with patch("quantmind.agents.research_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.side_effect = LLMError("bad response")
                result = agent.run(state)

        self.assertEqual(result.research_debate_report.conclusion, Signal.BEARISH)
        self.assertGreater(len(result.research_debate_report.key_evidence), 0)

    def test_deepseek_prompt_contains_manager_constraints(self) -> None:
        agent = ResearchManagerAgent()
        state = _state()
        state.bullish_research_report = ResearchPerspectiveReport(
            stance=Signal.BULLISH,
            confidence=0.7,
            thesis="多头证据较多。",
            key_points=["技术偏强"],
            concerns=[],
        )
        rule_report = agent._make_rule_report(state)
        messages = agent._build_deepseek_messages(state, rule_report)
        combined = "\n".join(message["content"] for message in messages)

        self.assertIn("研究经理", combined)
        self.assertIn("判断哪一方更有说服力", combined)
        self.assertIn("只能基于已有报告", combined)
        self.assertIn("严格 JSON", combined)


if __name__ == "__main__":
    unittest.main()