from __future__ import annotations

import unittest
from unittest.mock import patch

from quantmind.graph.workflow import QuantMindWorkflow
from quantmind.schemas import Signal, TradeAction


class QuantMindWorkflowTest(unittest.TestCase):
    def test_workflow_runs_all_nine_agents_with_mock_fallback_guardrail(self) -> None:
        workflow = QuantMindWorkflow()
        workflow.market_provider.get_daily_bars = lambda symbol, trade_date: {
            "source": "unit_test_fallback_mock",
            "fallback_type": "unit_test",
            "latest": 100.0,
            "close": [98.0, 99.0, 100.0, 101.0, 102.0],
            "volume": [1000, 1100, 1200, 1300, 1400],
        }
        workflow.news_provider.get_stock_news = lambda symbol, trade_date: [
            {
                "title": "公司增长超预期，机构看好后续盈利改善",
                "summary": "市场关注度提升。",
                "source": "unit_test",
                "news_source": "unit_test",
            }
        ]
        workflow.fundamental_provider.get_fundamentals = lambda symbol, trade_date: {
            "source": "unit_test",
            "requested_provider": "unit_test",
            "metrics": {
                "roe": 0.22,
                "earnings_growth_yoy": 0.18,
                "debt_ratio": 0.32,
                "pe_ratio": 28,
            },
        }

        with patch("quantmind.agents.technical_agent.settings") as tech_settings, \
            patch("quantmind.agents.news_agent.settings") as news_settings, \
            patch("quantmind.agents.fundamental_agent.settings") as fundamental_settings, \
            patch("quantmind.agents.sentiment_agent.settings") as sentiment_settings, \
            patch("quantmind.agents.research_agent.settings") as research_settings, \
            patch("quantmind.agents.risk_agent.settings") as risk_settings, \
            patch("quantmind.agents.decision_agent.settings") as decision_settings:
            for mock_settings in (
                tech_settings,
                news_settings,
                fundamental_settings,
                sentiment_settings,
                research_settings,
                risk_settings,
                decision_settings,
            ):
                mock_settings.llm_provider = "mock"
                mock_settings.llm_model = "deepseek-chat"
                mock_settings.has_llm_api_key = False
                mock_settings.default_position_size = 0.3
                mock_settings.max_position_size = 0.5
                mock_settings.stop_loss_pct = 0.05

            state = workflow.run("600519", "2024-06-05")

        self.assertIsNotNone(state.technical_report)
        self.assertIsNotNone(state.news_report)
        self.assertIsNotNone(state.fundamental_report)
        self.assertIsNotNone(state.sentiment_report)
        self.assertIsNotNone(state.bullish_research_report)
        self.assertIsNotNone(state.bearish_research_report)
        self.assertIsNotNone(state.research_debate_report)
        self.assertIsNotNone(state.risk_report)
        self.assertIsNotNone(state.final_decision)
        self.assertEqual(state.fundamental_report.signal, Signal.BULLISH)
        self.assertEqual(state.final_decision.action, TradeAction.WAIT)
        self.assertEqual(state.final_decision.position_size, 0.0)
        self.assertIn("未找到可用行情数据", state.final_decision.summary)

    def test_run_with_progress_emits_new_agent_steps(self) -> None:
        workflow = QuantMindWorkflow()
        workflow.market_provider.get_daily_bars = lambda symbol, trade_date: {"source": "mock"}
        workflow.news_provider.get_stock_news = lambda symbol, trade_date: []
        workflow.fundamental_provider.get_fundamentals = lambda symbol, trade_date: {"source": "unit_test", "metrics": {}}

        with patch("quantmind.agents.technical_agent.settings") as tech_settings, \
            patch("quantmind.agents.news_agent.settings") as news_settings, \
            patch("quantmind.agents.fundamental_agent.settings") as fundamental_settings, \
            patch("quantmind.agents.sentiment_agent.settings") as sentiment_settings, \
            patch("quantmind.agents.research_agent.settings") as research_settings, \
            patch("quantmind.agents.risk_agent.settings") as risk_settings, \
            patch("quantmind.agents.decision_agent.settings") as decision_settings:
            for mock_settings in (
                tech_settings,
                news_settings,
                fundamental_settings,
                sentiment_settings,
                research_settings,
                risk_settings,
                decision_settings,
            ):
                mock_settings.llm_provider = "mock"
                mock_settings.llm_model = "deepseek-chat"
                mock_settings.has_llm_api_key = False
                mock_settings.default_position_size = 0.3
                mock_settings.max_position_size = 0.5
                mock_settings.stop_loss_pct = 0.05

            events = list(workflow.run_with_progress("600519", "2024-06-05"))

        self.assertEqual(
            [event["step"] for event in events],
            [
                "prepared",
                "technical",
                "news",
                "fundamental",
                "sentiment",
                "bullish_research",
                "bearish_research",
                "research_manager",
                "risk",
                "decision",
            ],
        )
        self.assertEqual(events[-1]["percent"], 100)

    def test_selected_analysis_agents_skip_unselected_basic_reports(self) -> None:
        workflow = QuantMindWorkflow()
        workflow.market_provider.get_daily_bars = lambda symbol, trade_date: {
            "source": "unit_test_fallback_mock",
            "fallback_type": "unit_test",
            "close_prices": [98.0, 99.0, 100.0, 101.0, 102.0],
            "volumes": [1000, 1100, 1200, 1300, 1400],
        }
        workflow.news_provider.get_stock_news = lambda symbol, trade_date: [
            {
                "title": "公司增长超预期，机构看好后续盈利改善",
                "summary": "市场关注度提升。",
                "source": "unit_test",
                "news_source": "unit_test",
            }
        ]
        workflow.fundamental_provider.get_fundamentals = lambda symbol, trade_date: {
            "source": "unit_test",
            "metrics": {"roe": 0.22, "earnings_growth_yoy": 0.18, "debt_ratio": 0.32},
        }

        with patch("quantmind.agents.technical_agent.settings") as tech_settings, \
            patch("quantmind.agents.news_agent.settings") as news_settings, \
            patch("quantmind.agents.fundamental_agent.settings") as fundamental_settings, \
            patch("quantmind.agents.sentiment_agent.settings") as sentiment_settings, \
            patch("quantmind.agents.research_agent.settings") as research_settings, \
            patch("quantmind.agents.risk_agent.settings") as risk_settings, \
            patch("quantmind.agents.decision_agent.settings") as decision_settings:
            for mock_settings in (
                tech_settings,
                news_settings,
                fundamental_settings,
                sentiment_settings,
                research_settings,
                risk_settings,
                decision_settings,
            ):
                mock_settings.llm_provider = "mock"
                mock_settings.llm_model = "deepseek-chat"
                mock_settings.has_llm_api_key = False
                mock_settings.default_position_size = 0.3
                mock_settings.max_position_size = 0.5
                mock_settings.stop_loss_pct = 0.05

            state = workflow.run("600519", "2024-06-05", selected_agents=["technical", "news"])

        self.assertIsNotNone(state.technical_report)
        self.assertIsNotNone(state.news_report)
        self.assertIsNone(state.fundamental_report)
        self.assertIsNone(state.sentiment_report)
        self.assertIsNotNone(state.bullish_research_report)
        self.assertIsNotNone(state.bearish_research_report)
        self.assertIsNotNone(state.research_debate_report)
        self.assertIsNotNone(state.risk_report)
        self.assertIsNotNone(state.final_decision)

    def test_run_with_progress_omits_unselected_basic_agent_steps(self) -> None:
        workflow = QuantMindWorkflow()
        workflow.market_provider.get_daily_bars = lambda symbol, trade_date: {"source": "mock"}
        workflow.news_provider.get_stock_news = lambda symbol, trade_date: []
        workflow.fundamental_provider.get_fundamentals = lambda symbol, trade_date: {"source": "unit_test", "metrics": {}}

        with patch("quantmind.agents.technical_agent.settings") as tech_settings, \
            patch("quantmind.agents.news_agent.settings") as news_settings, \
            patch("quantmind.agents.fundamental_agent.settings") as fundamental_settings, \
            patch("quantmind.agents.sentiment_agent.settings") as sentiment_settings, \
            patch("quantmind.agents.research_agent.settings") as research_settings, \
            patch("quantmind.agents.risk_agent.settings") as risk_settings, \
            patch("quantmind.agents.decision_agent.settings") as decision_settings:
            for mock_settings in (
                tech_settings,
                news_settings,
                fundamental_settings,
                sentiment_settings,
                research_settings,
                risk_settings,
                decision_settings,
            ):
                mock_settings.llm_provider = "mock"
                mock_settings.llm_model = "deepseek-chat"
                mock_settings.has_llm_api_key = False
                mock_settings.default_position_size = 0.3
                mock_settings.max_position_size = 0.5
                mock_settings.stop_loss_pct = 0.05

            events = list(workflow.run_with_progress("600519", "2024-06-05", selected_agents=["technical", "news"]))

        self.assertEqual(
            [event["step"] for event in events],
            [
                "prepared",
                "technical",
                "news",
                "bullish_research",
                "bearish_research",
                "research_manager",
                "risk",
                "decision",
            ],
        )
        self.assertEqual(events[-1]["percent"], 100)


if __name__ == "__main__":
    unittest.main()