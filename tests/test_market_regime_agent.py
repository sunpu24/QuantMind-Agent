from __future__ import annotations

import unittest

from quantmind.agents.market_regime_agent import MarketRegimeAgent
from quantmind.schemas import AgentState, MarketRegime


class MarketRegimeAgentTest(unittest.TestCase):
    def test_uptrend_prices_are_identified_as_uptrend(self) -> None:
        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            market_data={"source": "unit_test", "close_prices": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]},
        )

        result = MarketRegimeAgent().run(state)

        self.assertEqual(result.market_regime_report.regime, MarketRegime.UPTREND)
        self.assertGreater(result.market_regime_report.trend_strength, 0.06)
        self.assertIn("上行趋势", result.market_regime_report.summary)

    def test_high_volatility_or_large_drawdown_is_identified(self) -> None:
        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            market_data={"source": "unit_test", "close_prices": [100, 108, 95, 112, 90, 115, 88, 116, 91, 114, 89]},
        )

        result = MarketRegimeAgent().run(state)

        self.assertEqual(result.market_regime_report.regime, MarketRegime.HIGH_VOLATILITY)
        self.assertLessEqual(result.market_regime_report.max_drawdown, -0.12)
        self.assertIn("风险控制权重", result.market_regime_report.summary)

    def test_mock_or_fallback_market_data_is_insufficient(self) -> None:
        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            market_data={
                "source": "unit_test_fallback_mock",
                "fallback_type": "missing_token",
                "close_prices": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
            },
        )

        result = MarketRegimeAgent().run(state)

        self.assertEqual(result.market_regime_report.regime, MarketRegime.INSUFFICIENT_DATA)
        self.assertIn("mock/fallback", result.market_regime_report.summary)


if __name__ == "__main__":
    unittest.main()