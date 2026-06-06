from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from quantmind.data.news_data import NewsDataProvider


class NewsDataProviderTest(unittest.TestCase):
    def test_auto_provider_routes_a_share_to_akshare(self) -> None:
        provider = NewsDataProvider()

        with patch("quantmind.data.news_data.settings") as mock_settings:
            mock_settings.news_provider = "auto"
            with patch.object(provider, "_get_from_akshare", return_value=[]) as mock_akshare:
                provider.get_stock_news("600519", "2026-06-05")

        mock_akshare.assert_called_once_with("600519", "2026-06-05")

    def test_auto_provider_routes_us_symbol_to_alpha_vantage(self) -> None:
        provider = NewsDataProvider()

        with patch("quantmind.data.news_data.settings") as mock_settings:
            mock_settings.news_provider = "auto"
            with patch.object(provider, "_get_from_alpha_vantage", return_value=[]) as mock_alpha:
                provider.get_stock_news("IBM", "2026-06-05")

        mock_alpha.assert_called_once_with("IBM", "2026-06-05")

    def test_to_akshare_symbol_maps_a_share_suffixes(self) -> None:
        provider = NewsDataProvider()

        self.assertEqual(provider._to_akshare_symbol("600519"), "600519")
        self.assertEqual(provider._to_akshare_symbol("600519.SH"), "600519")
        self.assertEqual(provider._to_akshare_symbol("000001.SZ"), "000001")
        self.assertEqual(provider._to_akshare_symbol("430047.BJ"), "430047")

    def test_normalize_akshare_stock_news_converts_dataframe(self) -> None:
        provider = NewsDataProvider()
        df = pd.DataFrame(
            [
                {
                    "关键词": "600519",
                    "新闻标题": "贵州茅台发布分红方案",
                    "新闻内容": "公司公告分红方案。",
                    "发布时间": "2026-06-02 20:38:44",
                    "文章来源": "财联社",
                    "新闻链接": "https://example.com/1",
                },
                {
                    "关键词": "600519",
                    "新闻标题": "未来日期新闻应过滤",
                    "新闻内容": "future",
                    "发布时间": "2026-06-06 09:00:00",
                    "文章来源": "测试",
                    "新闻链接": "https://example.com/2",
                },
            ]
        )

        result = provider._normalize_akshare_stock_news("600519.SH", "2026-06-05", df)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "贵州茅台发布分红方案")
        self.assertEqual(result[0]["date"], "2026-06-02")
        self.assertEqual(result[0]["source"], "akshare")
        self.assertEqual(result[0]["news_source"], "akshare")
        self.assertEqual(result[0]["requested_news_provider"], "akshare")
        self.assertEqual(result[0]["summary"], "公司公告分红方案。")
        self.assertEqual(result[0]["publisher"], "财联社")
        self.assertEqual(result[0]["keyword"], "600519")
        self.assertEqual(result[0]["news_relevance"], "matched")
        self.assertEqual(result[0]["url"], "https://example.com/1")
        self.assertEqual(result[0]["ticker"], "600519")

    def test_akshare_filters_irrelevant_stock_news(self) -> None:
        provider = NewsDataProvider()
        df = pd.DataFrame(
            [
                {
                    "关键词": "000001",
                    "新闻标题": "其他公司发布公告",
                    "新闻内容": "与目标股票无关。",
                    "发布时间": "2026-06-02 20:38:44",
                }
            ]
        )

        result = provider._normalize_akshare_stock_news("600519", "2026-06-05", df)

        self.assertEqual(result, [])

    def test_akshare_empty_data_returns_no_news(self) -> None:
        provider = NewsDataProvider()

        with patch("quantmind.data.news_data.settings") as mock_settings:
            mock_settings.news_provider = "akshare"
            mock_settings.akshare_enabled = True
            with patch.object(provider, "_fetch_akshare_stock_news", return_value=pd.DataFrame()):
                result = provider._get_from_akshare("600519", "2026-06-05")

        self.assertEqual(result, [])

    def test_akshare_schema_mismatch_returns_no_news(self) -> None:
        provider = NewsDataProvider()

        with patch("quantmind.data.news_data.settings") as mock_settings:
            mock_settings.news_provider = "akshare"
            mock_settings.akshare_enabled = True
            with patch.object(
                provider,
                "_fetch_akshare_stock_news",
                return_value=pd.DataFrame({"标题": ["字段不匹配"]}),
            ):
                result = provider._get_from_akshare("600519", "2026-06-05")

        self.assertEqual(result, [])

    def test_to_alpha_vantage_ticker_maps_a_share_symbols(self) -> None:
        provider = NewsDataProvider()

        self.assertEqual(provider._to_alpha_vantage_ticker("600519"), "600519")
        self.assertEqual(provider._to_alpha_vantage_ticker("000001"), "000001")
        self.assertEqual(provider._to_alpha_vantage_ticker("600519.SH"), "600519")
        self.assertEqual(provider._to_alpha_vantage_ticker("000001.SZ"), "000001")
        self.assertEqual(provider._to_alpha_vantage_ticker("IBM"), "IBM")

    def test_normalize_alpha_vantage_news_converts_feed(self) -> None:
        provider = NewsDataProvider()
        payload = {
            "feed": [
                {
                    "title": "Company reports growth",
                    "time_published": "20240605123000",
                    "url": "https://example.com/news",
                    "summary": "summary text",
                    "ticker_sentiment": [{"ticker": "600519"}],
                }
            ]
        }

        result = provider._normalize_alpha_vantage_news("600519", "2024-06-05", payload)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Company reports growth")
        self.assertEqual(result[0]["date"], "2024-06-05")
        self.assertEqual(result[0]["source"], "alpha_vantage")
        self.assertEqual(result[0]["news_source"], "alpha_vantage")
        self.assertEqual(result[0]["requested_news_provider"], "alpha_vantage")
        self.assertIsNone(result[0]["news_fallback_reason"])
        self.assertIsNone(result[0]["news_fallback_type"])
        self.assertEqual(result[0]["ticker"], "600519")
        self.assertEqual(result[0]["news_relevance"], "matched")

    def test_alpha_vantage_filters_irrelevant_ticker_sentiment(self) -> None:
        provider = NewsDataProvider()
        payload = {
            "feed": [
                {
                    "title": "Macro market update",
                    "time_published": "20240605123000",
                    "summary": "No target ticker here.",
                    "ticker_sentiment": [{"ticker": "MSFT"}],
                }
            ]
        }

        result = provider._normalize_alpha_vantage_news("IBM", "2024-06-05", payload)

        self.assertEqual(result, [])

    def test_alpha_vantage_keeps_matching_ticker_sentiment(self) -> None:
        provider = NewsDataProvider()
        payload = {
            "feed": [
                {
                    "title": "Enterprise AI demand rises",
                    "time_published": "20240605123000",
                    "summary": "Sector note.",
                    "ticker_sentiment": [{"ticker": "IBM"}],
                }
            ]
        }

        result = provider._normalize_alpha_vantage_news("IBM", "2024-06-05", payload)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ticker"], "IBM")
        self.assertEqual(result[0]["news_relevance"], "matched")

    def test_alpha_vantage_missing_key_returns_no_news(self) -> None:
        provider = NewsDataProvider()

        with patch("quantmind.data.news_data.settings") as mock_settings:
            mock_settings.news_provider = "alpha_vantage"
            mock_settings.has_alpha_vantage_api_key = False
            result = provider._get_from_alpha_vantage("600519", "2024-06-05")

        self.assertEqual(result, [])

    def test_alpha_vantage_empty_data_returns_no_news(self) -> None:
        provider = NewsDataProvider()

        with patch("quantmind.data.news_data.settings") as mock_settings:
            mock_settings.news_provider = "alpha_vantage"
            mock_settings.has_alpha_vantage_api_key = True
            with patch.object(provider, "_fetch_alpha_vantage_news", return_value={"feed": []}):
                result = provider._get_from_alpha_vantage("600519", "2024-06-05")

        self.assertEqual(result, [])

    def test_normalize_alpha_vantage_news_rejects_error_message(self) -> None:
        provider = NewsDataProvider()

        with self.assertRaises(ValueError):
            provider._normalize_alpha_vantage_news(
                "600519",
                "2024-06-05",
                {"Error Message": "invalid api call"},
            )


if __name__ == "__main__":
    unittest.main()