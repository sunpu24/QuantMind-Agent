from __future__ import annotations

from datetime import date, datetime

from quantmind.schemas import AgentState


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _pct_precise(value: float) -> str:
    return f"{value * 100:.2f}%"


def _format_generated_at() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _format_date_note(trade_date: str) -> str | None:
    try:
        parsed_trade_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
    except ValueError:
        return "日期提示: 分析日期格式异常，无法判断数据完整性。"

    today = date.today()
    if parsed_trade_date > today:
        return "日期提示: 分析日期晚于当前日期，真实行情/新闻可能不可得，报告仅可作为流程演示。"
    if parsed_trade_date == today:
        return "日期提示: 分析日期为当前日期，盘中/盘后数据可能尚未完整。"
    if (today - parsed_trade_date).days <= 3:
        return "日期提示: 分析日期接近当前日期，请留意行情、财报和新闻数据可能存在更新滞后。"
    return None


def _format_indicator_lines(indicators: dict[str, object]) -> list[str]:
    if not indicators:
        return ["指标: {}"]

    labels = {
        "latest": "最新价",
        "ma5": "MA5",
        "ma10": "MA10",
        "volume_change": "成交量变化",
    }
    lines = ["指标:"]
    for key in ("latest", "ma5", "ma10", "volume_change"):
        if key not in indicators:
            continue
        value = indicators[key]
        if key == "volume_change":
            try:
                formatted = _pct_precise(float(value))
            except (TypeError, ValueError):
                formatted = str(value)
        else:
            formatted = str(value)
        lines.append(f"- {labels[key]}: {formatted}")

    remaining = {key: value for key, value in indicators.items() if key not in labels}
    for key, value in remaining.items():
        lines.append(f"- {key}: {value}")
    return lines


def _format_mapping_lines(title: str, values: dict[str, object]) -> list[str]:
    if not values:
        return [f"{title}: {{}}"]
    lines = [f"{title}:"]
    for key, value in values.items():
        lines.append(f"- {key}: {value}")
    return lines


def _format_list_lines(title: str, values: list[str]) -> list[str]:
    if not values:
        return [f"{title}: []"]
    lines = [f"{title}:"]
    for value in values:
        lines.append(f"- {value}")
    return lines


def _clean_news_title(title: str) -> str:
    # 上游新闻偶尔会出现 “公司600519.SH)：” 这类缺少左括号的格式瑕疵。
    for suffix in (".SH)：", ".SZ)：", ".BJ)："):
        idx = title.find(suffix)
        if idx <= 0:
            continue
        prefix = title[:idx]
        digit_start = idx - 6
        if digit_start >= 0 and prefix[digit_start:idx].isdigit() and "(" not in prefix[digit_start - 1 : idx]:
            title = f"{title[:digit_start]}({title[digit_start:]}"
    return title


def _format_news_line(title: str, news_data: list[dict[str, object]]) -> str:
    metadata = next((item for item in news_data if str(item.get("title", "")) == title), {})
    cleaned_title = _clean_news_title(title)
    published_date = metadata.get("date")
    publisher = metadata.get("publisher") or metadata.get("source") or metadata.get("news_source")
    suffix_parts = []
    if publisher:
        suffix_parts.append(str(publisher))
    if metadata.get("url"):
        suffix_parts.append("含链接")

    prefix = f"[{published_date}] " if published_date else ""
    suffix = f"（{' / '.join(suffix_parts)}）" if suffix_parts else ""
    return f"- {prefix}{cleaned_title}{suffix}"


def _format_action_note(action: object) -> str | None:
    value = getattr(action, "value", action)
    if value == "SELL":
        return "动作解释: SELL 在无持仓上下文下不表示做空；可理解为有持仓则减仓/卖出，无持仓则不建议新开仓。"
    if value == "HOLD":
        return "动作解释: HOLD 需要结合既有持仓理解；当前系统无持仓上下文时不代表新增买入。"
    return None


def _format_akshare_attempts(attempts: object) -> str | None:
    if not isinstance(attempts, list) or not attempts:
        return None

    parts = []
    for item in attempts:
        if not isinstance(item, dict):
            continue
        lookback_days = item.get("lookback_days")
        status = item.get("status", "unknown")
        if lookback_days is None:
            parts.append(str(status))
        else:
            parts.append(f"{lookback_days}天 {status}")

    if not parts:
        return None
    return ", ".join(parts)


def _get_news_metadata(news_data: object) -> dict[str, object]:
    if not isinstance(news_data, list) or not news_data:
        return {}
    first_item = news_data[0]
    if not isinstance(first_item, dict):
        return {}
    return first_item


def _is_placeholder_market_data(market_data: dict[str, object]) -> bool:
    source = str(market_data.get("source", "")).lower()
    return "mock" in source or market_data.get("fallback_type") is not None


ACTION_RULES = (
    "动作规则: BUY=买入/加仓且仓位>0；HOLD=已有仓位继续持有、不新增买入；"
    "WAIT=观望等待、不买不卖、仓位0%；SELL=卖出/减仓、仓位0%。"
)


def render_text_report(state: AgentState) -> str:
    tech = state.technical_report
    market_data = state.market_data or {}
    data_source = market_data.get("source", "unknown")
    requested_provider = market_data.get("requested_provider", "unknown")
    requested_trade_date = market_data.get("requested_trade_date")
    actual_trade_date = market_data.get("actual_trade_date")
    date_adjust_reason = market_data.get("date_adjust_reason")
    fallback_reason = market_data.get("fallback_reason")
    fallback_type = market_data.get("fallback_type")
    akshare_attempts = _format_akshare_attempts(market_data.get("akshare_attempts"))
    news_metadata = _get_news_metadata(state.news_data)
    news_source = news_metadata.get("news_source", news_metadata.get("source", "unknown"))
    requested_news_provider = news_metadata.get("requested_news_provider", "unknown")
    news_fallback_reason = news_metadata.get("news_fallback_reason")
    news_fallback_type = news_metadata.get("news_fallback_type")
    news = state.news_report
    fundamental = state.fundamental_report
    sentiment = state.sentiment_report
    bullish_research = state.bullish_research_report
    bearish_research = state.bearish_research_report
    research_debate = state.research_debate_report
    risk = state.risk_report
    decision = state.final_decision

    lines = [
        "=" * 60,
        "QuantMind Agent Report",
        "=" * 60,
        f"报告生成时间: {_format_generated_at()}",
        f"股票代码: {state.symbol}",
        f"分析日期: {state.trade_date}",
        f"行情数据源: {data_source}",
        f"请求 Provider: {requested_provider}",
        f"新闻数据源: {news_source}",
        f"请求新闻 Provider: {requested_news_provider}",
        "数据口径: 报告仅基于当前可用行情、新闻与模型输出；新闻按分析日期做时间边界过滤。",
    ]
    date_note = _format_date_note(state.trade_date)
    if date_note:
        lines.append(date_note)
    if requested_trade_date and actual_trade_date:
        lines.append(f"请求行情日期: {requested_trade_date}")
        lines.append(f"实际行情日期: {actual_trade_date}")
    if date_adjust_reason:
        lines.append(f"行情日期调整: {date_adjust_reason}")
    if _is_placeholder_market_data(market_data):
        lines.extend(
            [
                "⚠ 行情数据提示: 未找到可用行情数据，无法基于真实行情给出买入或卖出判断。",
                "⚠ 最终交易决策为 WAIT，不能作为真实投资建议。",
            ]
        )
    if fallback_reason:
        lines.append(f"回退原因: {fallback_reason}")
    if fallback_type:
        lines.append(f"回退类型: {fallback_type}")
    if akshare_attempts:
        lines.append(f"AkShare 尝试: {akshare_attempts}")
    if news_fallback_reason:
        lines.append(f"新闻回退原因: {news_fallback_reason}")
    if news_fallback_type:
        lines.append(f"新闻回退类型: {news_fallback_type}")
    lines.extend([
        "",
        "[技术分析]",
        f"趋势: {tech.signal.value if tech else 'N/A'}",
        f"评分: {tech.score if tech else 'N/A'}",
        f"理由: {tech.summary if tech else 'N/A'}",
    ])
    lines.extend(_format_indicator_lines(tech.indicators if tech else {}))
    lines.extend([
        "",
        "[新闻分析]",
        f"情绪: {news.sentiment.value if news else 'N/A'}",
        f"评分: {news.score if news else 'N/A'}",
        f"理由: {news.summary if news else 'N/A'}",
        "新闻标题（含发布日期/来源，若上游提供）:",
    ])
    for title in news.headlines if news else []:
        lines.append(_format_news_line(title, state.news_data))

    lines.extend([
        "",
        "[基本面分析]",
        f"信号: {fundamental.signal.value if fundamental else 'N/A'}",
        f"评分: {fundamental.score if fundamental else 'N/A'}",
        f"数据来源: {fundamental.data_source if fundamental else 'N/A'}",
        f"理由: {fundamental.summary if fundamental else 'N/A'}",
    ])
    lines.extend(_format_mapping_lines("财务指标", fundamental.metrics if fundamental else {}))

    lines.extend([
        "",
        "[舆情分析]",
        f"情绪: {sentiment.sentiment.value if sentiment else 'N/A'}",
        f"评分: {sentiment.score if sentiment else 'N/A'}",
        f"关注热度: {sentiment.buzz_score if sentiment else 'N/A'}",
        f"分歧程度: {sentiment.disagreement_score if sentiment else 'N/A'}",
        f"理由: {sentiment.summary if sentiment else 'N/A'}",
    ])
    lines.extend(_format_list_lines("舆情来源", sentiment.sources if sentiment else []))

    lines.extend([
        "",
        "[多头研究员观点]",
        f"立场: {bullish_research.stance.value if bullish_research else 'N/A'}",
        f"置信度: {bullish_research.confidence if bullish_research else 'N/A'}",
        f"核心论点: {bullish_research.thesis if bullish_research else 'N/A'}",
    ])
    lines.extend(_format_list_lines("多头要点", bullish_research.key_points if bullish_research else []))
    lines.extend(_format_list_lines("多头关注风险", bullish_research.concerns if bullish_research else []))

    lines.extend([
        "",
        "[空头研究员观点]",
        f"立场: {bearish_research.stance.value if bearish_research else 'N/A'}",
        f"置信度: {bearish_research.confidence if bearish_research else 'N/A'}",
        f"核心论点: {bearish_research.thesis if bearish_research else 'N/A'}",
    ])
    lines.extend(_format_list_lines("空头要点", bearish_research.key_points if bearish_research else []))
    lines.extend(_format_list_lines("空头关注风险", bearish_research.concerns if bearish_research else []))

    lines.extend([
        "",
        "[研究经理结论]",
        f"结论: {research_debate.conclusion.value if research_debate else 'N/A'}",
        f"置信度: {research_debate.confidence if research_debate else 'N/A'}",
        f"多头摘要: {research_debate.bullish_summary if research_debate else 'N/A'}",
        f"空头摘要: {research_debate.bearish_summary if research_debate else 'N/A'}",
        f"最终摘要: {research_debate.final_summary if research_debate else 'N/A'}",
    ])
    lines.extend(_format_list_lines("关键证据", research_debate.key_evidence if research_debate else []))

    lines.extend([
        "",
        "[风险控制]",
        f"风险控制来源: {risk.risk_source if risk else 'N/A'}",
        f"风险等级: {risk.level.value if risk else 'N/A'}",
        f"风险评分: {risk.score if risk else 'N/A'}",
        f"建议仓位: {_pct(risk.suggested_position) if risk else 'N/A'}",
        f"止损建议: {_pct(risk.stop_loss_pct) if risk else 'N/A'}",
        f"理由: {risk.summary if risk else 'N/A'}",
        "",
        "[最终交易决策]",
        ACTION_RULES,
        f"LLM Provider: {decision.llm_provider if decision else 'N/A'}",
        f"LLM Model: {decision.llm_model if decision else 'N/A'}",
        f"LLM 耗时: {f'{decision.llm_elapsed_ms} ms' if decision and decision.llm_elapsed_ms is not None else 'N/A'}",
        f"LLM 回退类型: {decision.llm_fallback_type if decision and decision.llm_fallback_type else 'N/A'}",
        f"LLM 输入摘要: {decision.llm_prompt_summary if decision and decision.llm_prompt_summary else 'N/A'}",
        f"LLM 输出摘要: {decision.llm_response_summary if decision and decision.llm_response_summary else 'N/A'}",
        f"交易决策来源: {decision.decision_source if decision else 'N/A'}",
        f"动作: {decision.action.value if decision else 'N/A'}",
        f"置信度: {decision.confidence if decision else 'N/A'}",
        "置信度说明: 置信度表示模型/规则综合信号强弱，不代表收益概率、胜率或确定性承诺。",
        f"建议仓位: {_pct(decision.position_size) if decision else 'N/A'}",
        f"理由: {decision.summary if decision else 'N/A'}",
        f"依据: {decision.llm_reasoning if decision and decision.llm_reasoning else 'N/A'}",
        f"风险提示: {decision.risk_notes if decision else 'N/A'}",
    ])
    action_note = _format_action_note(decision.action if decision else None)
    if action_note:
        lines.append(action_note)
    if decision and decision.llm_fallback_reason:
        lines.append(f"LLM 回退原因: {decision.llm_fallback_reason}")
    lines.extend(
        [
            "",
            "免责声明: 本报告仅用于研究和学习，不构成任何投资建议；数据可能延迟、不完整或受第三方源影响，交易有风险，决策需谨慎。",
        ]
    )
    lines.append("=" * 60)
    return "\n".join(lines)
