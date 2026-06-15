from __future__ import annotations

from quantmind.agents import (
    BearishResearchAgent,
    BullishResearchAgent,
    FundamentalAnalysisAgent,
    NewsAnalysisAgent,
    ResearchManagerAgent,
    RiskControlAgent,
    SentimentAnalysisAgent,
    TechnicalAnalysisAgent,
    TradingDecisionAgent,
)
from quantmind.data import FundamentalDataProvider, MarketDataProvider, NewsDataProvider
from quantmind.schemas import AgentState


WorkflowProgressEvent = dict[str, object]


OPTIONAL_ANALYSIS_AGENTS = frozenset({"technical", "news", "fundamental", "sentiment"})
DEFAULT_ANALYSIS_AGENTS = tuple(OPTIONAL_ANALYSIS_AGENTS)


class QuantMindWorkflow:
    """固定串行工作流，后续可升级为 LangGraph StateGraph。"""

    def __init__(self) -> None:
        self.market_provider = MarketDataProvider()
        self.news_provider = NewsDataProvider()
        self.fundamental_provider = FundamentalDataProvider()
        self.technical_agent = TechnicalAnalysisAgent()
        self.news_agent = NewsAnalysisAgent()
        self.fundamental_agent = FundamentalAnalysisAgent()
        self.sentiment_agent = SentimentAnalysisAgent()
        self.bullish_research_agent = BullishResearchAgent()
        self.bearish_research_agent = BearishResearchAgent()
        self.research_manager_agent = ResearchManagerAgent()
        self.risk_agent = RiskControlAgent()
        self.decision_agent = TradingDecisionAgent()

    def run(self, symbol: str, trade_date: str, selected_agents: list[str] | None = None) -> AgentState:
        enabled_agents = self._normalize_selected_agents(selected_agents)
        state = AgentState(
            symbol=symbol,
            trade_date=trade_date,
            market_data=self.market_provider.get_daily_bars(symbol, trade_date),
            news_data=self.news_provider.get_stock_news(symbol, trade_date),
            fundamental_data=self.fundamental_provider.get_fundamentals(symbol, trade_date),
        )
        if "technical" in enabled_agents:
            state = self.technical_agent.run(state)
        if "news" in enabled_agents:
            state = self.news_agent.run(state)
        if "fundamental" in enabled_agents:
            state = self.fundamental_agent.run(state)
        if "sentiment" in enabled_agents:
            state = self.sentiment_agent.run(state)
        state = self.bullish_research_agent.run(state)
        state = self.bearish_research_agent.run(state)
        state = self.research_manager_agent.run(state)
        state = self.risk_agent.run(state)
        state = self.decision_agent.run(state)
        return state

    def run_with_progress(self, symbol: str, trade_date: str, selected_agents: list[str] | None = None):
        """逐步运行工作流，供 Web SSE 展示 Agent 进度。"""

        enabled_agents = self._normalize_selected_agents(selected_agents)

        state = AgentState(
            symbol=symbol,
            trade_date=trade_date,
            market_data=self.market_provider.get_daily_bars(symbol, trade_date),
            news_data=self.news_provider.get_stock_news(symbol, trade_date),
            fundamental_data=self.fundamental_provider.get_fundamentals(symbol, trade_date),
        )
        steps = [
            *(step for step in ("technical", "news", "fundamental", "sentiment") if step in enabled_agents),
            "bullish_research",
            "bearish_research",
            "research_manager",
            "risk",
            "decision",
        ]
        total_steps = len(steps) + 1

        yield self._progress_event("prepared", self._progress_percent(1, total_steps), "已识别股票并获取行情、新闻与基本面基础数据", state)

        completed_steps = 1

        if "technical" in enabled_agents:
            state = self.technical_agent.run(state)
            completed_steps += 1
            yield self._progress_event("technical", self._progress_percent(completed_steps, total_steps), "技术分析 Agent 已完成", state)

        if "news" in enabled_agents:
            state = self.news_agent.run(state)
            completed_steps += 1
            yield self._progress_event("news", self._progress_percent(completed_steps, total_steps), "新闻分析 Agent 已完成", state)

        if "fundamental" in enabled_agents:
            state = self.fundamental_agent.run(state)
            completed_steps += 1
            yield self._progress_event("fundamental", self._progress_percent(completed_steps, total_steps), "基本面分析 Agent 已完成", state)

        if "sentiment" in enabled_agents:
            state = self.sentiment_agent.run(state)
            completed_steps += 1
            yield self._progress_event("sentiment", self._progress_percent(completed_steps, total_steps), "舆情分析 Agent 已完成", state)

        state = self.bullish_research_agent.run(state)
        completed_steps += 1
        yield self._progress_event("bullish_research", self._progress_percent(completed_steps, total_steps), "多头研究员 Agent 已完成", state)

        state = self.bearish_research_agent.run(state)
        completed_steps += 1
        yield self._progress_event("bearish_research", self._progress_percent(completed_steps, total_steps), "空头研究员 Agent 已完成", state)

        state = self.research_manager_agent.run(state)
        completed_steps += 1
        yield self._progress_event("research_manager", self._progress_percent(completed_steps, total_steps), "研究经理 Agent 已完成", state)

        state = self.risk_agent.run(state)
        completed_steps += 1
        yield self._progress_event("risk", self._progress_percent(completed_steps, total_steps), "风险控制 Agent 已完成", state)

        state = self.decision_agent.run(state)
        completed_steps += 1
        yield self._progress_event("decision", 100, "交易决策 Agent 已生成最终结论", state)

    @staticmethod
    def _normalize_selected_agents(selected_agents: list[str] | None) -> set[str]:
        if selected_agents is None:
            return set(DEFAULT_ANALYSIS_AGENTS)
        return {agent for agent in selected_agents if agent in OPTIONAL_ANALYSIS_AGENTS}

    @staticmethod
    def _progress_percent(completed_steps: int, total_steps: int) -> int:
        return min(99, round(completed_steps / total_steps * 100))

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
