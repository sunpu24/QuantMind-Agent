from __future__ import annotations

from typing import Any

from quantmind.schemas import NewsReport, RiskLevel, RiskReport, Signal, TechnicalReport, TradeAction, TradeDecision


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