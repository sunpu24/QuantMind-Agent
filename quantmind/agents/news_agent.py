from __future__ import annotations

from quantmind.agents.base import BaseAgent
from quantmind.config import settings
from quantmind.llm.client import DeepSeekChatClient, LLMError
from quantmind.llm.parsing import parse_news_report_payload
from quantmind.schemas import AgentState, NewsReport, Signal


FALLBACK_MOCK_WARNING = (
    "重要提示：当前新闻为 mock fallback，不能当作真实新闻证据。"
    "请在 summary 中明确说明这一点，并降低对新闻情绪的确信度。"
)

NO_RELEVANT_NEWS_SUMMARY = "没有找到相关的新闻"


class NewsAnalysisAgent(BaseAgent):
    name = "news_analysis_agent"
    role = "新闻分析 Agent"

    def run(self, state: AgentState) -> AgentState:
        if not state.news_data:
            state.news_report = self._make_no_news_report()
            return state

        rule_report = self._make_rule_report(state)
        if settings.llm_provider != "deepseek":
            state.news_report = rule_report
            return state

        if not settings.has_llm_api_key:
            state.news_report = rule_report
            return state

        try:
            payload = DeepSeekChatClient().chat_json(self._build_deepseek_messages(state))
            state.news_report = parse_news_report_payload(payload)
        except (LLMError, ValueError, TypeError):
            state.news_report = rule_report
        return state

    def _make_no_news_report(self) -> NewsReport:
        return NewsReport(
            sentiment=Signal.NEUTRAL,
            score=50,
            summary=NO_RELEVANT_NEWS_SUMMARY,
            headlines=[],
        )

    def _make_rule_report(self, state: AgentState) -> NewsReport:
        news_items = state.news_data
        headlines = [item.get("title", "") for item in news_items]
        joined = " ".join(headlines)

        positive_words = ["增长", "利好", "突破", "回购", "增持", "盈利", "创新高"]
        negative_words = ["下滑", "利空", "处罚", "减持", "亏损", "风险", "调查"]

        pos = sum(word in joined for word in positive_words)
        neg = sum(word in joined for word in negative_words)

        if pos > neg:
            sentiment = Signal.BULLISH
            score = min(60 + (pos - neg) * 8, 90)
            summary = "新闻关键词偏正面，市场情绪对股价有一定支撑。"
        elif neg > pos:
            sentiment = Signal.BEARISH
            score = max(40 - (neg - pos) * 8, 10)
            summary = "新闻关键词偏负面，需要警惕事件冲击。"
        else:
            sentiment = Signal.NEUTRAL
            score = 55
            summary = "近期新闻整体偏中性，暂无明显单边情绪。"

        return NewsReport(
            sentiment=sentiment,
            score=score,
            summary=summary,
            headlines=headlines,
        )

    def _build_deepseek_messages(self, state: AgentState) -> list[dict[str, str]]:
        news_items = state.news_data
        first_item = news_items[0] if news_items else {}
        news_source = first_item.get("news_source", first_item.get("source", "unknown"))
        news_fallback_type = first_item.get("news_fallback_type")
        fallback_warning = FALLBACK_MOCK_WARNING if news_source.endswith("_fallback_mock") else ""
        news_lines = []
        for index, item in enumerate(news_items, start=1):
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
                    "你是 QuantMind 的新闻分析 Agent。你的任务是只基于用户提供的新闻标题、新闻摘要和新闻源 metadata，判断新闻情绪。\n\n"
                    "请输出严格 JSON 对象，不要输出 Markdown，不要输出解释性前后缀。\n"
                    "JSON 字段必须包含：\n"
                    "- sentiment: 只能是 bullish、neutral、bearish\n"
                    "- score: 0 到 100 的整数，数值越高表示越偏正面\n"
                    "- summary: 中文摘要，说明新闻情绪判断依据\n"
                    "- headlines: 字符串数组，保留或筛选输入中的关键新闻标题\n\n"
                    "重要约束：\n"
                    "1. 不要编造用户未提供的新闻事实。\n"
                    "2. 不要把 mock 新闻当作真实新闻证据。\n"
                    "3. 如果没有输入新闻，必须直接说明没有找到相关的新闻，不要编造新闻。\n"
                    "4. 输出必须为中文 summary。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"股票代码: {state.symbol}\n"
                    f"分析日期: {state.trade_date}\n"
                    f"新闻数据源: {news_source}\n"
                    f"新闻回退类型: {news_fallback_type}\n\n"
                    f"{fallback_warning}\n\n"
                    "新闻列表:\n"
                    f"{chr(10).join(news_lines)}\n\n"
                    "请返回 JSON：\n"
                    "{\n"
                    "  \"sentiment\": \"bullish|neutral|bearish\",\n"
                    "  \"score\": 0-100,\n"
                    "  \"summary\": \"中文新闻情绪分析结论\",\n"
                    "  \"headlines\": [\"新闻标题1\", \"新闻标题2\"]\n"
                    "}"
                ),
            },
        ]
