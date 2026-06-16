from __future__ import annotations

import unittest
from unittest.mock import patch

from quantmind.agents.decision_agent import TradingDecisionAgent
from quantmind.schemas import (
    AgentState,
    FundamentalReport,
    MarketRegime,
    MarketRegimeReport,
    NewsReport,
    ResearchDebateReport,
    RiskLevel,
    RiskReport,
    SentimentReport,
    Signal,
    TechnicalReport,
    TradeAction,
)


def _state() -> AgentState:
    return AgentState(
        symbol="600519",
        trade_date="2024-06-05",
        market_data={"source": "tushare"},
        news_data=[{"news_source": "alpha_vantage", "news_fallback_type": None}],
        market_regime_report=MarketRegimeReport(
            regime=MarketRegime.UPTREND,
            volatility=0.012,
            trend_strength=0.08,
            max_drawdown=-0.02,
            summary="近期价格呈上行趋势。",
        ),
        technical_report=TechnicalReport(
            signal=Signal.BULLISH,
            score=78,
            summary="技术面偏强。",
            indicators={"latest": 1644.0, "ma5": 1630.0},
        ),
        news_report=NewsReport(
            sentiment=Signal.NEUTRAL,
            score=55,
            summary="新闻中性。",
            headlines=["新闻标题"],
        ),
        fundamental_report=FundamentalReport(
            signal=Signal.BULLISH,
            score=72,
            summary="基本面偏多。",
            metrics={"roe": 0.2},
        ),
        risk_report=RiskReport(
            level=RiskLevel.MEDIUM,
            score=50,
            suggested_position=0.3,
            stop_loss_pct=0.05,
            summary="风险中等。",
        ),
    )


class TradingDecisionAgentTest(unittest.TestCase):
    def test_rule_decision_when_llm_provider_is_mock(self) -> None:
        agent = TradingDecisionAgent()

        with patch("quantmind.agents.decision_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            mock_settings.llm_model = "deepseek-chat"
            result = agent.run(_state())

        self.assertEqual(result.final_decision.action, TradeAction.BUY)
        self.assertEqual(result.final_decision.decision_source, "rule")
        self.assertGreater(result.final_decision.weighted_score, 0.25)

    def test_deepseek_decision_uses_structured_payload_and_guardrails(self) -> None:
        agent = TradingDecisionAgent()
        payload = {
            "action": "BUY",
            "confidence": 0.88,
            "position_size": 0.9,
            "summary": "DeepSeek 认为可小仓位参与。",
            "reasoning": "技术偏强，但风险中等，因此仓位受限。",
            "risk_notes": "严格止损。",
        }

        with patch("quantmind.agents.decision_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.llm_model = "deepseek-chat"
            mock_settings.has_llm_api_key = True
            mock_settings.max_position_size = 0.5
            with patch("quantmind.agents.decision_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.return_value = payload
                result = agent.run(_state())

        decision = result.final_decision
        self.assertEqual(decision.action, TradeAction.BUY)
        self.assertEqual(decision.decision_source, "deepseek")
        self.assertEqual(decision.position_size, 0.3)
        self.assertEqual(decision.llm_reasoning, "技术偏强，但风险中等，因此仓位受限。")
        self.assertIsNotNone(decision.llm_elapsed_ms)
        self.assertIn("symbol=600519", decision.llm_prompt_summary)
        self.assertIn("tech=bullish/78", decision.llm_prompt_summary)
        self.assertIn("market_regime=uptrend", decision.llm_prompt_summary)
        self.assertIn("weighted_score=", decision.llm_prompt_summary)
        self.assertIn("action=BUY", decision.llm_response_summary)
        self.assertIn("position_size=0.9", decision.llm_response_summary)
        self.assertIn("technical", decision.contribution_breakdown)

    def test_deepseek_missing_key_falls_back_to_rule(self) -> None:
        agent = TradingDecisionAgent()

        with patch("quantmind.agents.decision_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.llm_model = "deepseek-chat"
            mock_settings.has_llm_api_key = False
            result = agent.run(_state())

        self.assertEqual(result.final_decision.decision_source, "rule_fallback")
        self.assertIn("未配置 DeepSeek API Key", result.final_decision.llm_fallback_reason)
        self.assertEqual(result.final_decision.llm_fallback_type, "missing_api_key")
        self.assertIn("symbol=600519", result.final_decision.llm_prompt_summary)

    def test_deepseek_error_falls_back_to_rule(self) -> None:
        agent = TradingDecisionAgent()

        with patch("quantmind.agents.decision_agent.settings") as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.llm_model = "deepseek-chat"
            mock_settings.has_llm_api_key = True
            mock_settings.max_position_size = 0.5
            with patch("quantmind.agents.decision_agent.DeepSeekChatClient") as mock_client_cls:
                mock_client_cls.return_value.chat_json.side_effect = ValueError("bad json")
                result = agent.run(_state())

        self.assertEqual(result.final_decision.decision_source, "rule_fallback")
        self.assertIn("bad json", result.final_decision.llm_fallback_reason)
        self.assertEqual(result.final_decision.llm_fallback_type, "invalid_response")
        self.assertIsNotNone(result.final_decision.llm_elapsed_ms)
        self.assertIn("symbol=600519", result.final_decision.llm_prompt_summary)

    def test_mock_market_data_guardrail_downgrades_buy_to_wait(self) -> None:
        agent = TradingDecisionAgent()
        state = _state()
        state.market_data = {"source": "tushare_fallback_mock", "fallback_type": "missing_token"}

        with patch("quantmind.agents.decision_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            mock_settings.llm_model = "deepseek-chat"
            result = agent.run(state)

        self.assertEqual(result.final_decision.action, TradeAction.WAIT)
        self.assertEqual(result.final_decision.position_size, 0.0)
        self.assertLessEqual(result.final_decision.confidence, 0.55)
        self.assertIn("未找到可用行情数据", result.final_decision.summary)
        self.assertNotIn("占位", result.final_decision.summary)
        self.assertIn("强制覆盖为 WAIT", result.final_decision.regime_adjustment)

    def test_rule_decision_uses_wait_for_conflicting_or_insufficient_signals(self) -> None:
        agent = TradingDecisionAgent()
        state = _state()
        state.technical_report.signal = Signal.NEUTRAL
        state.news_report.sentiment = Signal.NEUTRAL

        with patch("quantmind.agents.decision_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            mock_settings.llm_model = "deepseek-chat"
            result = agent.run(state)

        self.assertEqual(result.final_decision.action, TradeAction.WAIT)
        self.assertEqual(result.final_decision.position_size, 0.0)
        self.assertLess(result.final_decision.weighted_score, 0.25)

    def test_deepseek_prompt_contains_wait_action_rules(self) -> None:
        agent = TradingDecisionAgent()
        messages = agent._build_deepseek_messages(_state(), agent._make_rule_decision(_state()))

        self.assertIn("BUY/HOLD/WAIT/SELL", messages[1]["content"])
        self.assertIn("WAIT=观望等待", messages[1]["content"])
        self.assertIn("market_regime", messages[1]["content"])
        self.assertIn("contribution_breakdown", messages[1]["content"])

    def test_deepseek_prompt_treats_missing_news_as_neutral_and_forbids_fabrication(self) -> None:
        agent = TradingDecisionAgent()
        state = _state()
        state.news_data = []
        state.news_report.summary = "没有找到相关的新闻"
        state.news_report.sentiment = Signal.NEUTRAL
        messages = agent._build_deepseek_messages(state, agent._make_rule_decision(state))
        combined = "\n".join(message["content"] for message in messages)

        self.assertIn("只能依赖技术分析、新闻分析和风险控制报告", combined)
        self.assertIn("没有找到相关的新闻", combined)
        self.assertIn("不得编造新闻", combined)
        self.assertIn("不要给出激进 BUY", combined)

    def test_rule_decision_uses_research_debate_as_important_signal(self) -> None:
        agent = TradingDecisionAgent()
        state = _state()
        state.technical_report.signal = Signal.NEUTRAL
        state.news_report.sentiment = Signal.NEUTRAL
        state.fundamental_report = FundamentalReport(
            signal=Signal.NEUTRAL,
            score=50,
            summary="基本面中性。",
            metrics={},
        )
        state.sentiment_report = SentimentReport(
            sentiment=Signal.BULLISH,
            score=65,
            buzz_score=20,
            disagreement_score=20,
            summary="舆情偏多。",
            sources=[],
        )
        state.research_debate_report = ResearchDebateReport(
            conclusion=Signal.BULLISH,
            confidence=0.75,
            bullish_summary="多头证据更充分。",
            bearish_summary="空头证据有限。",
            final_summary="研究经理认为偏多。",
            key_evidence=["研究经理 bullish"],
        )

        with patch("quantmind.agents.decision_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            mock_settings.llm_model = "deepseek-chat"
            result = agent.run(state)

        self.assertEqual(result.final_decision.action, TradeAction.BUY)
        self.assertIn("研究结论", result.final_decision.regime_adjustment)

    def test_high_risk_blocks_bullish_research_buy(self) -> None:
        agent = TradingDecisionAgent()
        state = _state()
        state.research_debate_report = ResearchDebateReport(
            conclusion=Signal.BULLISH,
            confidence=0.82,
            bullish_summary="多头证据更充分。",
            bearish_summary="空头证据有限。",
            final_summary="研究经理认为偏多。",
            key_evidence=["研究经理 bullish"],
        )
        state.risk_report = RiskReport(
            level=RiskLevel.HIGH,
            score=82,
            suggested_position=0.15,
            stop_loss_pct=0.05,
            summary="综合风险较高。",
        )

        with patch("quantmind.agents.decision_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            mock_settings.llm_model = "deepseek-chat"
            result = agent.run(state)

        self.assertNotEqual(result.final_decision.action, TradeAction.BUY)
        self.assertEqual(result.final_decision.position_size, 0.0)

    def test_high_volatility_raises_risk_weight_and_caps_buy_position(self) -> None:
        agent = TradingDecisionAgent()
        state = _state()
        state.market_regime_report = MarketRegimeReport(
            regime=MarketRegime.HIGH_VOLATILITY,
            volatility=0.041,
            trend_strength=0.03,
            max_drawdown=-0.13,
            summary="近期波动较高或回撤较大。",
        )
        state.news_report.sentiment = Signal.BULLISH
        state.fundamental_report = FundamentalReport(signal=Signal.BULLISH, score=80, summary="基本面偏多。", metrics={})
        state.sentiment_report = SentimentReport(
            sentiment=Signal.BULLISH,
            score=70,
            buzz_score=60,
            disagreement_score=10,
            summary="舆情偏多。",
            sources=[],
        )
        state.research_debate_report = ResearchDebateReport(
            conclusion=Signal.BULLISH,
            confidence=0.78,
            bullish_summary="多头证据充分。",
            bearish_summary="空头证据较弱。",
            final_summary="研究经理偏多。",
            key_evidence=[],
        )
        state.risk_report.level = RiskLevel.LOW
        state.risk_report.suggested_position = 0.35

        with patch("quantmind.agents.decision_agent.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            mock_settings.llm_model = "deepseek-chat"
            result = agent.run(state)

        self.assertEqual(result.final_decision.action, TradeAction.BUY)
        self.assertLessEqual(result.final_decision.position_size, 0.15)
        self.assertAlmostEqual(result.final_decision.contribution_breakdown["risk_penalty"], -0.034)
        self.assertIn("风险控制权重至 34%", result.final_decision.regime_adjustment)

    def test_contribution_breakdown_contains_all_expected_keys(self) -> None:
        agent = TradingDecisionAgent()
        decision = agent._make_rule_decision(_state())

        self.assertEqual(
            set(decision.contribution_breakdown),
            {"technical", "news", "fundamental", "sentiment", "research", "risk_penalty"},
        )


if __name__ == "__main__":
    unittest.main()