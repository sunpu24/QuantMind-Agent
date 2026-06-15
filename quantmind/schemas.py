from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Signal(str, Enum):
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TradeAction(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    WAIT = "WAIT"
    SELL = "SELL"


@dataclass
class TechnicalReport:
    signal: Signal
    score: int
    summary: str
    indicators: dict[str, Any] = field(default_factory=dict)


@dataclass
class NewsReport:
    sentiment: Signal
    score: int
    summary: str
    headlines: list[str] = field(default_factory=list)


@dataclass
class FundamentalReport:
    signal: Signal
    score: int
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
    data_source: str = "rule"


@dataclass
class SentimentReport:
    sentiment: Signal
    score: int
    buzz_score: int
    disagreement_score: int
    summary: str
    sources: list[str] = field(default_factory=list)


@dataclass
class ResearchPerspectiveReport:
    stance: Signal
    confidence: float
    thesis: str
    key_points: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)


@dataclass
class ResearchDebateReport:
    conclusion: Signal
    confidence: float
    bullish_summary: str
    bearish_summary: str
    final_summary: str
    key_evidence: list[str] = field(default_factory=list)


@dataclass
class RiskReport:
    level: RiskLevel
    score: int
    suggested_position: float
    stop_loss_pct: float
    summary: str
    risk_source: str = "rule"


@dataclass
class TradeDecision:
    action: TradeAction
    confidence: float
    position_size: float
    summary: str
    risk_notes: str
    decision_source: str = "rule"
    llm_provider: str = "mock"
    llm_model: str = "mock-model"
    llm_fallback_reason: Optional[str] = None
    llm_reasoning: str = ""
    llm_elapsed_ms: Optional[int] = None
    llm_fallback_type: Optional[str] = None
    llm_prompt_summary: str = ""
    llm_response_summary: str = ""


@dataclass
class AgentState:
    symbol: str
    trade_date: str
    market_data: dict[str, Any] = field(default_factory=dict)
    news_data: list[dict[str, Any]] = field(default_factory=list)
    fundamental_data: dict[str, Any] = field(default_factory=dict)
    sentiment_data: dict[str, Any] = field(default_factory=dict)
    technical_report: Optional[TechnicalReport] = None
    news_report: Optional[NewsReport] = None
    fundamental_report: Optional[FundamentalReport] = None
    sentiment_report: Optional[SentimentReport] = None
    bullish_research_report: Optional[ResearchPerspectiveReport] = None
    bearish_research_report: Optional[ResearchPerspectiveReport] = None
    research_debate_report: Optional[ResearchDebateReport] = None
    risk_report: Optional[RiskReport] = None
    final_decision: Optional[TradeDecision] = None
