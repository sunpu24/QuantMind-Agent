from __future__ import annotations

from quantmind.agents.base import BaseAgent
from quantmind.config import settings
from quantmind.llm.client import DeepSeekChatClient, LLMError
from quantmind.llm.parsing import parse_sentiment_report_payload
from quantmind.schemas import AgentState, SentimentReport, Signal


NO_SENTIMENT_DATA_SUMMARY = "没有可用新闻，市场情绪、关注热度和分歧程度暂时保持中性低热度判断。"


class SentimentAnalysisAgent(BaseAgent):
    name = "sentiment_analysis_agent"
    role = "舆情分析 Agent"

    def run(self, state: AgentState) -> AgentState:
        if not state.news_data:
            state.sentiment_report = self._make_no_news_report()
            return state

        rule_report = self._make_rule_report(state)
        if settings.llm_provider != "deepseek":
            state.sentiment_report = rule_report
            return state

        if not settings.has_llm_api_key:
            state.sentiment_report = rule_report
            return state

        try:
            payload = DeepSeekChatClient().chat_json(self._build_deepseek_messages(state, rule_report))
            state.sentiment_report = parse_sentiment_report_payload(payload)
        except (LLMError, ValueError, TypeError):
            state.sentiment_report = rule_report
        return state

    def _make_no_news_report(self) -> SentimentReport:
        return SentimentReport(
            sentiment=Signal.NEUTRAL,
            score=50,
            buzz_score=5,
            disagreement_score=5,
            summary=NO_SENTIMENT_DATA_SUMMARY,
            sources=[],
        )

    def _make_rule_report(self, state: AgentState) -> SentimentReport:
        news_items = state.news_data
        text_parts = []
        sources = []
        for item in news_items:
            text_parts.append(str(item.get("title", "")))
            text_parts.append(str(item.get("summary", "")))
            source = item.get("news_source", item.get("source"))
            if source:
                sources.append(str(source))

        joined = " ".join(text_parts)
        positive_words = ["增长", "利好", "突破", "回购", "增持", "盈利", "创新高", "看好", "改善", "超预期"]
        negative_words = ["下滑", "利空", "处罚", "减持", "亏损", "风险", "调查", "承压", "不及预期", "担忧"]

        pos = sum(joined.count(word) for word in positive_words)
        neg = sum(joined.count(word) for word in negative_words)
        news_count = len(news_items)
        buzz_score = min(10 + news_count * 15, 100)

        if pos and neg:
            disagreement_score = min(30 + min(pos, neg) * 20 + abs(pos - neg) * 5, 100)
        else:
            disagreement_score = 10 if pos or neg else 5

        if pos > neg:
            sentiment = Signal.BULLISH
            score = min(58 + (pos - neg) * 8 + min(news_count, 3) * 2, 90)
            summary = "舆情规则判断偏多：正面情绪词更多，市场关注度有所提升。"
        elif neg > pos:
            sentiment = Signal.BEARISH
            score = max(42 - (neg - pos) * 8 - min(news_count, 3) * 2, 10)
            summary = "舆情规则判断偏空：负面情绪词更多，需要警惕市场情绪压力。"
        else:
            sentiment = Signal.NEUTRAL
            score = 50
            summary = "舆情规则判断中性：正负情绪信号接近或有效情绪词不足。"

        if disagreement_score >= 60:
            summary += " 同时正负情绪并存，分歧程度较高。"

        return SentimentReport(
            sentiment=sentiment,
            score=score,
            buzz_score=buzz_score,
            disagreement_score=disagreement_score,
            summary=summary,
            sources=list(dict.fromkeys(sources)),
        )

    def _build_deepseek_messages(
        self,
        state: AgentState,
        rule_report: SentimentReport,
    ) -> list[dict[str, str]]:
        news_lines = []
        for index, item in enumerate(state.news_data, start=1):
            item_source = item.get("news_source", item.get("source", "unknown"))
            news_lines.append(
                f"{index}. title={item.get('title', '')}\n"
                f"   summary={item.get('summary', '')}\n"
                f"   news_source={item_source}\n"
                f"   fallback_type={item.get('news_fallback_type')}"
            )

        return [
            {
                "role": "system",
                "content": (
                    "你是 QuantMind 的舆情分析 Agent。你的任务是只基于用户提供的新闻标题、新闻摘要和新闻源 metadata，"
                    "判断市场情绪、关注热度 buzz_score 和分歧程度 disagreement_score。\n\n"
                    "注意：NewsAnalysisAgent 关注新闻事件本身利好或利空；你关注市场情绪、关注热度和分歧程度。\n\n"
                    "请输出严格 JSON 对象，不要输出 Markdown，不要输出解释性前后缀。\n"
                    "JSON 字段必须包含：\n"
                    "- sentiment: 只能是 bullish、neutral、bearish\n"
                    "- score: 0 到 100 的整数，数值越高表示市场情绪越正面\n"
                    "- buzz_score: 0 到 100 的整数，数值越高表示关注热度越高\n"
                    "- disagreement_score: 0 到 100 的整数，数值越高表示多空分歧越高\n"
                    "- summary: 中文摘要，说明情绪、热度和分歧判断依据\n"
                    "- sources: 字符串数组，来自输入的新闻源 metadata\n\n"
                    "重要约束：\n"
                    "1. 不要编造用户未提供的新闻、社交媒体、成交量或市场数据。\n"
                    "2. 只能基于输入新闻标题、摘要和来源 metadata 判断舆情。\n"
                    "3. 如果新闻不足，应输出 neutral、低 buzz_score、低 disagreement_score，并说明信息不足。\n"
                    "4. 输出必须为中文 summary。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"股票代码: {state.symbol}\n"
                    f"分析日期: {state.trade_date}\n\n"
                    "新闻列表:\n"
                    f"{chr(10).join(news_lines)}\n\n"
                    "规则基线舆情判断:\n"
                    "{\n"
                    f"  \"sentiment\": \"{rule_report.sentiment.value}\",\n"
                    f"  \"score\": {rule_report.score},\n"
                    f"  \"buzz_score\": {rule_report.buzz_score},\n"
                    f"  \"disagreement_score\": {rule_report.disagreement_score},\n"
                    f"  \"summary\": \"{rule_report.summary}\"\n"
                    "}\n\n"
                    "请返回 JSON：\n"
                    "{\n"
                    "  \"sentiment\": \"bullish|neutral|bearish\",\n"
                    "  \"score\": 0-100,\n"
                    "  \"buzz_score\": 0-100,\n"
                    "  \"disagreement_score\": 0-100,\n"
                    "  \"summary\": \"中文舆情分析结论\",\n"
                    "  \"sources\": [\"新闻源1\", \"新闻源2\"]\n"
                    "}"
                ),
            },
        ]