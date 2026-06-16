from __future__ import annotations

import unittest

from quantmind.schemas import (
    AgentState,
    FundamentalReport,
    MarketRegime,
    MarketRegimeReport,
    ResearchDebateReport,
    ResearchPerspectiveReport,
    SentimentReport,
    Signal,
)
from web_app import _state_to_response


class WebResponseTest(unittest.TestCase):
    def test_state_to_response_serializes_new_reports(self) -> None:
        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            fundamental_data={"metrics": {"roe": 0.2}},
            sentiment_data={"source": "news_data"},
            market_regime_report=MarketRegimeReport(
                regime=MarketRegime.SIDEWAYS,
                volatility=0.01,
                trend_strength=0.02,
                max_drawdown=-0.03,
                summary="近期震荡。",
            ),
            fundamental_report=FundamentalReport(
                signal=Signal.BULLISH,
                score=78,
                summary="基本面偏多。",
                metrics={"roe": 0.2},
                data_source="unit_test",
            ),
            sentiment_report=SentimentReport(
                sentiment=Signal.NEUTRAL,
                score=50,
                buzz_score=20,
                disagreement_score=10,
                summary="舆情中性。",
                sources=["unit_test"],
            ),
            bullish_research_report=ResearchPerspectiveReport(
                stance=Signal.BULLISH,
                confidence=0.7,
                thesis="多头证据较充分。",
                key_points=["基本面偏多"],
                concerns=[],
            ),
            bearish_research_report=ResearchPerspectiveReport(
                stance=Signal.NEUTRAL,
                confidence=0.4,
                thesis="空头证据不足。",
                key_points=[],
                concerns=["缺少明确利空"],
            ),
            research_debate_report=ResearchDebateReport(
                conclusion=Signal.BULLISH,
                confidence=0.72,
                bullish_summary="多头更强。",
                bearish_summary="空头较弱。",
                final_summary="研究经理认为偏多。",
                key_evidence=["基本面偏多"],
            ),
        )

        payload = _state_to_response(state)

        self.assertEqual(payload["fundamental_data"], {"metrics": {"roe": 0.2}})
        self.assertEqual(payload["sentiment_data"], {"source": "news_data"})
        self.assertEqual(payload["fundamental_report"]["signal"], "bullish")
        self.assertEqual(payload["sentiment_report"]["sentiment"], "neutral")
        self.assertEqual(payload["market_regime_report"]["regime"], "sideways")
        self.assertEqual(payload["bullish_research_report"]["stance"], "bullish")
        self.assertEqual(payload["bearish_research_report"]["stance"], "neutral")
        self.assertEqual(payload["research_debate_report"]["conclusion"], "bullish")


if __name__ == "__main__":
    unittest.main()