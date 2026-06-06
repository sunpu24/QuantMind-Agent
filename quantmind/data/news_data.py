from __future__ import annotations

import random
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from quantmind.config import settings


class NewsDataProvider:
    """新闻数据 Provider。默认 Mock，可接入 A 股 AkShare 与美股 Alpha Vantage 新闻源。"""

    ALPHA_VANTAGE_NEWS_URL = "https://www.alphavantage.co/query"
    NEWS_LIMIT = 3
    FALLBACK_REASON_MAX_LENGTH = 240

    def get_stock_news(self, symbol: str, trade_date: str) -> list[dict[str, Any]]:
        if settings.news_provider == "auto":
            if self._is_us_symbol(symbol):
                return self._get_from_alpha_vantage(symbol, trade_date)
            if self._is_a_share_symbol(symbol):
                return self._get_from_akshare(symbol, trade_date)
            print(f"无法自动识别股票市场: {symbol}，没有找到相关的新闻。")
            return []
        if settings.news_provider == "akshare":
            return self._get_from_akshare(symbol, trade_date)
        if settings.news_provider == "alpha_vantage":
            return self._get_from_alpha_vantage(symbol, trade_date)
        return self._get_mock_news(symbol, trade_date)

    @staticmethod
    def _is_a_share_symbol(symbol: str) -> bool:
        value = symbol.strip().upper()
        if value.endswith((".SH", ".SZ", ".BJ")):
            return value.split(".", maxsplit=1)[0].isdigit()
        return value.isdigit() and len(value) == 6

    @staticmethod
    def _is_us_symbol(symbol: str) -> bool:
        value = symbol.strip().upper()
        if not value or value.isdigit():
            return False
        if value.endswith((".SH", ".SZ", ".BJ")):
            return False
        normalized = value.replace(".", "").replace("-", "")
        return normalized.isalpha()

    def _get_mock_news(
        self,
        symbol: str,
        trade_date: str,
        *,
        requested_news_provider: str | None = None,
        news_source: str = "mock",
        news_fallback_reason: str | None = None,
        news_fallback_type: str | None = None,
    ) -> list[dict[str, Any]]:
        random.seed(f"news-{symbol}-{trade_date}")
        templates = [
            "公司核心业务保持稳定增长，机构关注度提升",
            "行业政策预期改善，板块情绪有所回暖",
            "市场成交活跃度一般，短期资金仍偏谨慎",
            "公司发布风险提示，提醒投资者注意波动风险",
            "部分股东增持股份，释放长期信心",
        ]
        return [
            {
                "title": f"{symbol}: {title}",
                "date": trade_date,
                "source": news_source,
                "news_source": news_source,
                "requested_news_provider": requested_news_provider or settings.news_provider,
                "news_fallback_reason": news_fallback_reason,
                "news_fallback_type": news_fallback_type,
            }
            for title in random.sample(templates, k=3)
        ]

    def _get_from_alpha_vantage(self, symbol: str, trade_date: str) -> list[dict[str, Any]]:
        if not settings.has_alpha_vantage_api_key:
            print("未配置 ALPHA_VANTAGE_API_KEY，没有找到相关的新闻。")
            return []

        try:
            payload = self._fetch_alpha_vantage_news(symbol)
            news = self._normalize_alpha_vantage_news(symbol, trade_date, payload)
        except Exception as exc:
            print(f"Alpha Vantage 新闻获取失败，没有找到相关的新闻。原因: {exc}")
            return []

        if not news:
            print("Alpha Vantage 未返回与目标股票相关的可用新闻，没有找到相关的新闻。")
            return []
        return news

    def _get_alpha_vantage_fallback_mock(
        self,
        symbol: str,
        trade_date: str,
        *,
        news_fallback_type: str,
        news_fallback_reason: str,
    ) -> list[dict[str, Any]]:
        return self._get_mock_news(
            symbol,
            trade_date,
            requested_news_provider="alpha_vantage",
            news_source="alpha_vantage_fallback_mock",
            news_fallback_reason=news_fallback_reason,
            news_fallback_type=news_fallback_type,
        )

    def _get_from_akshare(self, symbol: str, trade_date: str) -> list[dict[str, Any]]:
        if not settings.akshare_enabled:
            reason = "AkShare 已禁用"
            print(f"{reason}，没有找到相关的新闻。")
            return []

        try:
            import akshare as ak
        except ImportError:
            reason = "未安装 AkShare"
            print(f"{reason}，没有找到相关的新闻。")
            return []

        try:
            df = self._fetch_akshare_stock_news(ak, symbol)
            news = self._normalize_akshare_stock_news(symbol, trade_date, df)
        except Exception as exc:
            reason = self._truncate_text(f"AkShare 新闻获取失败: {exc}")
            print(f"AkShare 新闻获取失败，没有找到相关的新闻。原因: {reason}")
            return []

        if not news:
            reason = "AkShare 未返回与目标股票相关的可用新闻"
            print(f"{reason}，没有找到相关的新闻。")
            return []
        return news

    def _get_akshare_fallback_mock(
        self,
        symbol: str,
        trade_date: str,
        *,
        news_fallback_type: str,
        news_fallback_reason: str,
    ) -> list[dict[str, Any]]:
        return self._get_mock_news(
            symbol,
            trade_date,
            requested_news_provider="akshare",
            news_source="akshare_fallback_mock",
            news_fallback_reason=news_fallback_reason,
            news_fallback_type=news_fallback_type,
        )

    def _fetch_akshare_stock_news(self, ak: Any, symbol: str) -> Any:
        return ak.stock_news_em(symbol=self._to_akshare_symbol(symbol))

    def _normalize_akshare_stock_news(
        self,
        symbol: str,
        trade_date: str,
        df: Any,
    ) -> list[dict[str, Any]]:
        required_columns = {"新闻标题", "发布时间"}
        if df is None or getattr(df, "empty", True):
            raise ValueError("AkShare 返回空新闻数据")
        if not required_columns.issubset(set(df.columns)):
            raise ValueError(f"AkShare 返回字段不完整，当前字段: {list(df.columns)}")

        rows = []
        for _, row in df.iterrows():
            published_at = self._format_akshare_time(str(row.get("发布时间", "")))
            if published_at and published_at > trade_date:
                continue
            title = str(row.get("新闻标题", "")).strip()
            if not title:
                continue
            rows.append(
                {
                    "title": title,
                    "date": published_at or trade_date,
                    "source": "akshare",
                    "news_source": "akshare",
                    "requested_news_provider": "akshare",
                    "news_fallback_reason": None,
                    "news_fallback_type": None,
                    "provider": "akshare",
                    "url": str(row.get("新闻链接", "") or ""),
                    "summary": str(row.get("新闻内容", "") or ""),
                    "publisher": str(row.get("文章来源", "") or ""),
                    "keyword": str(row.get("关键词", "") or ""),
                    "ticker": self._to_akshare_symbol(symbol),
                }
            )

        return self._filter_relevant_news(symbol, rows)[: self.NEWS_LIMIT]

    @staticmethod
    def _to_akshare_symbol(symbol: str) -> str:
        value = symbol.strip().upper()
        if value.endswith((".SH", ".SZ", ".BJ")):
            return value.split(".", maxsplit=1)[0]
        return value

    @staticmethod
    def _format_akshare_time(value: str) -> str | None:
        value = value.strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
            try:
                candidate = value[:19] if "%H" in fmt else value[:10]
                return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        if len(value) >= 8 and value[:8].isdigit():
            return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
        return None

    @classmethod
    def _truncate_text(cls, text: str) -> str:
        if len(text) <= cls.FALLBACK_REASON_MAX_LENGTH:
            return text
        return f"{text[: cls.FALLBACK_REASON_MAX_LENGTH - 3]}..."

    @staticmethod
    def _classify_akshare_fallback_type(exc: Exception | None) -> str:
        if exc is None:
            return "akshare_error"
        exc_text = f"{exc.__class__.__module__}.{exc.__class__.__name__}: {exc}".lower()
        message = str(exc)
        if "proxyerror" in exc_text or "proxy" in exc_text:
            return "proxy_error"
        if "timeout" in exc_text or "timed out" in exc_text:
            return "timeout"
        if "空新闻" in message or "未返回可用新闻" in message:
            return "empty_data"
        if "字段" in message or "column" in exc_text or "schema" in exc_text:
            return "schema_mismatch"
        return "akshare_error"

    def _fetch_alpha_vantage_news(self, symbol: str) -> dict[str, Any]:
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": self._to_alpha_vantage_ticker(symbol),
            "apikey": settings.alpha_vantage_api_key,
            "limit": str(self.NEWS_LIMIT),
        }
        url = f"{self.ALPHA_VANTAGE_NEWS_URL}?{urlencode(params)}"
        with urlopen(url, timeout=settings.alpha_vantage_timeout) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw)

    def _normalize_alpha_vantage_news(
        self,
        symbol: str,
        trade_date: str,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if "Error Message" in payload:
            raise ValueError(payload["Error Message"])
        if "Note" in payload:
            raise ValueError(payload["Note"])
        if "Information" in payload:
            raise ValueError(payload["Information"])

        feed = payload.get("feed", [])
        if not isinstance(feed, list):
            raise ValueError("Alpha Vantage 返回 feed 字段格式异常")

        news_items: list[dict[str, Any]] = []
        for item in feed:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            if not title:
                continue
            ticker_sentiment = item.get("ticker_sentiment", [])
            published_at = str(item.get("time_published", ""))
            news_items.append(
                {
                    "title": title,
                    "date": self._format_alpha_vantage_time(published_at) or trade_date,
                    "source": "alpha_vantage",
                    "news_source": "alpha_vantage",
                    "requested_news_provider": "alpha_vantage",
                    "news_fallback_reason": None,
                    "news_fallback_type": None,
                    "provider": "alpha_vantage",
                    "url": item.get("url", ""),
                    "summary": item.get("summary", ""),
                    "ticker": self._to_alpha_vantage_ticker(symbol),
                    "ticker_sentiment": ticker_sentiment,
                }
            )
        return self._filter_relevant_news(symbol, news_items)[: self.NEWS_LIMIT]

    def _filter_relevant_news(self, symbol: str, news_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        relevant_items = []
        for item in news_items:
            if self._is_relevant_news_item(symbol, item):
                item["news_relevance"] = "matched"
                relevant_items.append(item)
        return relevant_items

    def _is_relevant_news_item(self, symbol: str, item: dict[str, Any]) -> bool:
        target_tokens = self._news_relevance_tokens(symbol)
        ticker_sentiment = item.get("ticker_sentiment")
        if isinstance(ticker_sentiment, list):
            target_ticker = self._to_alpha_vantage_ticker(symbol).upper()
            for entry in ticker_sentiment:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("ticker", "")).strip().upper() == target_ticker:
                    return True

        searchable = " ".join(
            str(item.get(key, ""))
            for key in ("title", "summary", "keyword", "publisher")
        ).upper()
        return any(token and token in searchable for token in target_tokens)

    def _news_relevance_tokens(self, symbol: str) -> set[str]:
        value = symbol.strip().upper()
        tokens = {value}
        if "." in value:
            tokens.add(value.split(".", maxsplit=1)[0])
        if self._is_a_share_symbol(value):
            tokens.add(self._to_akshare_symbol(value))
        if self._is_us_symbol(value):
            tokens.add(self._to_alpha_vantage_ticker(value))
        return {token for token in tokens if token}

    @staticmethod
    def _to_alpha_vantage_ticker(symbol: str) -> str:
        value = symbol.strip().upper()
        if value.endswith((".SH", ".SZ", ".SHH", ".SHZ", ".SSH")):
            return value.split(".", maxsplit=1)[0]
        if value.isdigit():
            return value
        return value

    @staticmethod
    def _format_alpha_vantage_time(value: str) -> str | None:
        if len(value) >= 8 and value[:8].isdigit():
            return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
        return None
