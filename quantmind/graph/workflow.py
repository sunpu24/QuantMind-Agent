from __future__ import annotations

from quantmind.agents import (
    NewsAnalysisAgent,
    RiskControlAgent,
    TechnicalAnalysisAgent,
    TradingDecisionAgent,
)
from quantmind.data import MarketDataProvider, NewsDataProvider
from quantmind.schemas import AgentState


WorkflowProgressEvent = dict[str, object]


class QuantMindWorkflow:
    """固定串行工作流，后续可升级为 LangGraph StateGraph。"""

    def __init__(self) -> None:
        self.market_provider = MarketDataProvider()
        self.news_provider = NewsDataProvider()
        self.technical_agent = TechnicalAnalysisAgent()
        self.news_agent = NewsAnalysisAgent()
        self.risk_agent = RiskControlAgent()
        self.decision_agent = TradingDecisionAgent()

    def run(self, symbol: str, trade_date: str) -> AgentState:
        state = AgentState(
            symbol=symbol,
            trade_date=trade_date,
            market_data=self.market_provider.get_daily_bars(symbol, trade_date),
            news_data=self.news_provider.get_stock_news(symbol, trade_date),
        )
        state = self.technical_agent.run(state)
        state = self.news_agent.run(state)
        state = self.risk_agent.run(state)
        state = self.decision_agent.run(state)
        return state

    def run_with_progress(self, symbol: str, trade_date: str):
        """逐步运行工作流，供 Web SSE 展示 Agent 进度。"""

        state = AgentState(
            symbol=symbol,
            trade_date=trade_date,
            market_data=self.market_provider.get_daily_bars(symbol, trade_date),
            news_data=self.news_provider.get_stock_news(symbol, trade_date),
        )
        yield self._progress_event("prepared", 15, "已识别股票并获取基础数据", state)

        state = self.technical_agent.run(state)
        yield self._progress_event("technical", 35, "技术分析 Agent 已完成", state)

        state = self.news_agent.run(state)
        yield self._progress_event("news", 55, "新闻分析 Agent 已完成", state)

        state = self.risk_agent.run(state)
        yield self._progress_event("risk", 75, "风险控制 Agent 已完成", state)

        state = self.decision_agent.run(state)
        yield self._progress_event("decision", 100, "交易决策 Agent 已生成最终结论", state)

    @staticmethod
    def _progress_event(
        step: str,
        percent: int,
        message: str,
        state: AgentState,
    ) -> WorkflowProgressEvent:
        return {
            "step": step,
            "percent": percent,
            "message": message,
            "state": state,
        }
