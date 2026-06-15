from __future__ import annotations

from typing import Any

from quantmind.schemas import (
    FundamentalReport,
    NewsReport,
    ResearchDebateReport,
    ResearchPerspectiveReport,
    RiskLevel,
    RiskReport,
    SentimentReport,
    Signal,
    TechnicalReport,
    TradeAction,
    TradeDecision,
)


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_news_report_payload(payload: dict[str, Any]) -> NewsReport:
    sentiment_raw = str(payload.get("sentiment", Signal.NEUTRAL.value)).lower()
    if sentiment_raw not in {item.value for item in Signal}:
        sentiment_raw = Signal.NEUTRAL.value

    score = max(0, min(_to_int(payload.get("score"), 55), 100))
    summary = str(payload.get("summary") or "DeepSeek 给出新闻情绪分析。")
    headlines_raw = payload.get("headlines", [])
    if isinstance(headlines_raw, list):
        headlines = [str(item) for item in headlines_raw if str(item).strip()]
    elif headlines_raw:
        headlines = [str(headlines_raw)]
    else:
        headlines = []

    return NewsReport(
        sentiment=Signal(sentiment_raw),
        score=score,
        summary=summary,
        headlines=headlines,
    )


def parse_technical_report_payload(
    payload: dict[str, Any],
    *,
    indicators: dict[str, Any],
) -> TechnicalReport:
    signal_raw = str(payload.get("signal", Signal.NEUTRAL.value)).lower()
    if signal_raw not in {item.value for item in Signal}:
        signal_raw = Signal.NEUTRAL.value

    score = max(0, min(_to_int(payload.get("score"), 55), 100))
    summary = str(payload.get("summary") or "DeepSeek 给出技术结构分析。")

    return TechnicalReport(
        signal=Signal(signal_raw),
        score=score,
        summary=summary,
        indicators=dict(indicators),
    )


def parse_fundamental_report_payload(
    payload: dict[str, Any],
    *,
    metrics: dict[str, Any],
    data_source: str,
) -> FundamentalReport:
    signal_raw = str(payload.get("signal", Signal.NEUTRAL.value)).lower()
    if signal_raw not in {item.value for item in Signal}:
        signal_raw = Signal.NEUTRAL.value

    score = max(0, min(_to_int(payload.get("score"), 50), 100))
    summary = str(payload.get("summary") or "DeepSeek 给出基本面分析。")

    return FundamentalReport(
        signal=Signal(signal_raw),
        score=score,
        summary=summary,
        metrics=dict(metrics),
        data_source=data_source,
    )


def parse_sentiment_report_payload(payload: dict[str, Any]) -> SentimentReport:
    sentiment_raw = str(payload.get("sentiment", Signal.NEUTRAL.value)).lower()
    if sentiment_raw not in {item.value for item in Signal}:
        sentiment_raw = Signal.NEUTRAL.value

    score = max(0, min(_to_int(payload.get("score"), 50), 100))
    buzz_score = max(0, min(_to_int(payload.get("buzz_score"), 10), 100))
    disagreement_score = max(0, min(_to_int(payload.get("disagreement_score"), 10), 100))
    summary = str(payload.get("summary") or "DeepSeek 给出市场情绪分析。")
    sources_raw = payload.get("sources", [])
    if isinstance(sources_raw, list):
        sources = [str(item) for item in sources_raw if str(item).strip()]
    elif sources_raw:
        sources = [str(sources_raw)]
    else:
        sources = []

    return SentimentReport(
        sentiment=Signal(sentiment_raw),
        score=score,
        buzz_score=buzz_score,
        disagreement_score=disagreement_score,
        summary=summary,
        sources=sources,
    )


def parse_research_perspective_report_payload(payload: dict[str, Any]) -> ResearchPerspectiveReport:
    stance_raw = str(payload.get("stance", Signal.NEUTRAL.value)).lower()
    if stance_raw not in {item.value for item in Signal}:
        stance_raw = Signal.NEUTRAL.value

    confidence = max(0.0, min(_to_float(payload.get("confidence"), 0.5), 0.95))
    thesis = str(payload.get("thesis") or "多头研究员基于已有报告给出谨慎观点。")

    key_points_raw = payload.get("key_points", [])
    if isinstance(key_points_raw, list):
        key_points = [str(item) for item in key_points_raw if str(item).strip()]
    elif key_points_raw:
        key_points = [str(key_points_raw)]
    else:
        key_points = []

    concerns_raw = payload.get("concerns", [])
    if isinstance(concerns_raw, list):
        concerns = [str(item) for item in concerns_raw if str(item).strip()]
    elif concerns_raw:
        concerns = [str(concerns_raw)]
    else:
        concerns = []

    return ResearchPerspectiveReport(
        stance=Signal(stance_raw),
        confidence=round(confidence, 2),
        thesis=thesis,
        key_points=key_points,
        concerns=concerns,
    )


def parse_research_debate_report_payload(payload: dict[str, Any]) -> ResearchDebateReport:
    conclusion_raw = str(payload.get("conclusion", Signal.NEUTRAL.value)).lower()
    if conclusion_raw not in {item.value for item in Signal}:
        conclusion_raw = Signal.NEUTRAL.value

    confidence = max(0.0, min(_to_float(payload.get("confidence"), 0.5), 0.95))
    bullish_summary = str(payload.get("bullish_summary") or "多头观点证据不足或未提供。")
    bearish_summary = str(payload.get("bearish_summary") or "空头观点证据不足或未提供。")
    final_summary = str(payload.get("final_summary") or "研究经理基于已有报告给出中性结论。")

    key_evidence_raw = payload.get("key_evidence", [])
    if isinstance(key_evidence_raw, list):
        key_evidence = [str(item) for item in key_evidence_raw if str(item).strip()]
    elif key_evidence_raw:
        key_evidence = [str(key_evidence_raw)]
    else:
        key_evidence = []

    return ResearchDebateReport(
        conclusion=Signal(conclusion_raw),
        confidence=round(confidence, 2),
        bullish_summary=bullish_summary,
        bearish_summary=bearish_summary,
        final_summary=final_summary,
        key_evidence=key_evidence,
    )


def parse_risk_report_payload(
    payload: dict[str, Any],
    *,
    rule_report: RiskReport,
    max_position_size: float,
    stop_loss_pct: float,
) -> RiskReport:
    level_raw = str(payload.get("level", rule_report.level.value)).lower()
    if level_raw not in {item.value for item in RiskLevel}:
        level_raw = rule_report.level.value

    score = max(0, min(_to_int(payload.get("score"), rule_report.score), 100))
    requested_position = max(0.0, _to_float(payload.get("suggested_position"), rule_report.suggested_position))
    guarded_position = min(requested_position, max_position_size)
    summary = str(payload.get("summary") or "DeepSeek 给出风险解释，仓位与止损已按规则约束。")
    if requested_position > guarded_position:
        summary += f" DeepSeek 建议仓位 {requested_position:.0%}，已按最大仓位约束裁剪到 {guarded_position:.0%}。"

    return RiskReport(
        level=RiskLevel(level_raw),
        score=score,
        suggested_position=round(guarded_position, 2),
        stop_loss_pct=stop_loss_pct,
        summary=summary,
        risk_source="deepseek_guardrailed",
    )


def parse_trade_decision_payload(
    payload: dict[str, Any],
    *,
    max_position_size: float,
    risk_position_size: float,
    llm_provider: str,
    llm_model: str,
    llm_elapsed_ms: int | None = None,
    llm_prompt_summary: str = "",
    llm_response_summary: str = "",
) -> TradeDecision:
    action_raw = str(payload.get("action", "WAIT")).upper()
    if action_raw not in {item.value for item in TradeAction}:
        action_raw = TradeAction.WAIT.value
    action = TradeAction(action_raw)

    confidence = max(0.0, min(_to_float(payload.get("confidence"), 0.5), 0.95))
    position_size = max(0.0, _to_float(payload.get("position_size"), 0.0))
    position_size = min(position_size, max_position_size, risk_position_size)
    if action != TradeAction.BUY:
        position_size = 0.0

    summary = str(payload.get("summary") or "DeepSeek 给出交易决策。")
    risk_notes = str(payload.get("risk_notes") or "请结合风险控制报告执行。")
    llm_reasoning = str(payload.get("reasoning") or payload.get("llm_reasoning") or summary)

    return TradeDecision(
        action=action,
        confidence=round(confidence, 2),
        position_size=round(position_size, 2),
        summary=summary,
        risk_notes=risk_notes,
        decision_source="deepseek",
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_reasoning=llm_reasoning,
        llm_elapsed_ms=llm_elapsed_ms,
        llm_prompt_summary=llm_prompt_summary,
        llm_response_summary=llm_response_summary,
    )