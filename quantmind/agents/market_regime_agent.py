from __future__ import annotations

from statistics import pstdev

from quantmind.agents.base import BaseAgent
from quantmind.schemas import AgentState, MarketRegime, MarketRegimeReport


class MarketRegimeAgent(BaseAgent):
    name = "market_regime_agent"
    role = "市场状态识别 Agent"

    def run(self, state: AgentState) -> AgentState:
        market_data = state.market_data or {}
        prices = self._normalize_prices(market_data.get("close_prices", market_data.get("close", [])))

        if len(prices) < 10 or self._uses_mock_or_fallback_data(market_data):
            state.market_regime_report = MarketRegimeReport(
                regime=MarketRegime.INSUFFICIENT_DATA,
                volatility=0.0,
                trend_strength=0.0,
                max_drawdown=0.0,
                summary="行情数据不足或来自 mock/fallback 数据源，暂无法可靠识别市场状态。",
            )
            return state

        returns = [(prices[index] / prices[index - 1]) - 1 for index in range(1, len(prices)) if prices[index - 1] != 0]
        volatility = pstdev(returns) if len(returns) > 1 else 0.0
        trend_strength = (prices[-1] - prices[0]) / prices[0] if prices[0] else 0.0
        max_drawdown = self._calculate_max_drawdown(prices)
        regime = self._classify_regime(volatility, trend_strength, max_drawdown)

        state.market_regime_report = MarketRegimeReport(
            regime=regime,
            volatility=round(volatility, 6),
            trend_strength=round(trend_strength, 6),
            max_drawdown=round(max_drawdown, 6),
            summary=self._build_summary(regime, volatility, trend_strength, max_drawdown),
        )
        return state

    @staticmethod
    def _normalize_prices(values: object) -> list[float]:
        if not isinstance(values, list):
            return []
        prices: list[float] = []
        for value in values:
            try:
                price = float(value)
            except (TypeError, ValueError):
                continue
            if price > 0:
                prices.append(price)
        return prices

    @staticmethod
    def _uses_mock_or_fallback_data(market_data: dict[str, object]) -> bool:
        source = str(market_data.get("source", "")).lower()
        return "mock" in source or market_data.get("fallback_type") is not None

    @staticmethod
    def _calculate_max_drawdown(prices: list[float]) -> float:
        peak = prices[0]
        max_drawdown = 0.0
        for price in prices:
            peak = max(peak, price)
            if peak > 0:
                max_drawdown = min(max_drawdown, (price - peak) / peak)
        return max_drawdown

    @staticmethod
    def _classify_regime(volatility: float, trend_strength: float, max_drawdown: float) -> MarketRegime:
        if volatility >= 0.035 or max_drawdown <= -0.12:
            return MarketRegime.HIGH_VOLATILITY
        if trend_strength >= 0.06:
            return MarketRegime.UPTREND
        if trend_strength <= -0.06:
            return MarketRegime.DOWNTREND
        return MarketRegime.SIDEWAYS

    @staticmethod
    def _build_summary(regime: MarketRegime, volatility: float, trend_strength: float, max_drawdown: float) -> str:
        volatility_text = f"{volatility:.2%}"
        trend_text = f"{trend_strength:.2%}"
        drawdown_text = f"{max_drawdown:.2%}"
        if regime == MarketRegime.UPTREND:
            return f"近期价格呈上行趋势，趋势强度为 {trend_text}，波动率为 {volatility_text}。"
        if regime == MarketRegime.DOWNTREND:
            return f"近期价格呈下行趋势，趋势强度为 {trend_text}，最大回撤为 {drawdown_text}。"
        if regime == MarketRegime.HIGH_VOLATILITY:
            return f"近期波动较高或回撤较大，波动率为 {volatility_text}，最大回撤为 {drawdown_text}，系统应提高风险控制权重。"
        return f"近期价格以震荡为主，趋势强度为 {trend_text}，波动率为 {volatility_text}。"