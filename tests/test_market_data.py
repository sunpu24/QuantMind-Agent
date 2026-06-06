from __future__ import annotations

import types
import unittest
from unittest.mock import patch

import pandas as pd

from quantmind.data.market_data import MarketDataProvider


class MarketDataProviderTest(unittest.TestCase):
    def test_symbol_market_detection(self) -> None:
        provider = MarketDataProvider()

        self.assertTrue(provider._is_a_share_symbol("600519"))
        self.assertTrue(provider._is_a_share_symbol("000001.SZ"))
        self.assertFalse(provider._is_a_share_symbol("AAPL"))
        self.assertTrue(provider._is_us_symbol("AAPL"))
        self.assertTrue(provider._is_us_symbol("BRK.B"))
        self.assertFalse(provider._is_us_symbol("600519"))

    def test_auto_provider_routes_us_symbol_to_alpha_vantage(self) -> None:
        provider = MarketDataProvider()

        with patch("quantmind.data.market_data.settings") as mock_settings:
            mock_settings.data_provider = "auto"
            with patch.object(provider, "_get_from_alpha_vantage") as mock_alpha:
                mock_alpha.return_value = {"source": "alpha_vantage"}
                result = provider.get_daily_bars("AAPL", "2026-05-14")

        self.assertEqual(result["source"], "alpha_vantage")
        mock_alpha.assert_called_once_with("AAPL", "2026-05-14")

    def test_auto_provider_routes_a_share_symbol_to_tushare(self) -> None:
        provider = MarketDataProvider()

        with patch("quantmind.data.market_data.settings") as mock_settings:
            mock_settings.data_provider = "auto"
            with patch.object(provider, "_get_from_tushare") as mock_tushare:
                mock_tushare.return_value = {"source": "tushare"}
                result = provider.get_daily_bars("600519", "2026-05-14")

        self.assertEqual(result["source"], "tushare")
        mock_tushare.assert_called_once_with("600519", "2026-05-14")

    def test_normalize_alpha_vantage_daily_bars_keeps_latest_20_before_trade_date(self) -> None:
        payload = {
            "Time Series (Daily)": {
                date: {"4. close": str(100 + index + 0.123), "5. volume": str(10_000 + index)}
                for index, date in enumerate(
                    pd.date_range("2026-04-20", periods=25, freq="D").strftime("%Y-%m-%d")
                )
            }
        }
        provider = MarketDataProvider()

        result = provider._normalize_alpha_vantage_daily_bars("aapl", "2026-05-14", payload)

        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(result["source"], "alpha_vantage")
        self.assertEqual(result["requested_provider"], "alpha_vantage")
        self.assertEqual(result["market"], "US")
        self.assertEqual(len(result["dates"]), 20)
        self.assertEqual(result["dates"][0], "2026-04-25")
        self.assertEqual(result["dates"][-1], "2026-05-14")
        self.assertEqual(result["close_prices"][0], 105.12)
        self.assertEqual(result["volumes"][-1], 10_024)

    def test_get_from_alpha_vantage_falls_back_when_api_key_missing(self) -> None:
        provider = MarketDataProvider()

        with patch("quantmind.data.market_data.settings") as mock_settings:
            mock_settings.has_alpha_vantage_api_key = False
            result = provider._get_from_alpha_vantage("AAPL", "2026-05-14")

        self.assertEqual(result["source"], "alpha_vantage_fallback_mock")
        self.assertEqual(result["requested_provider"], "alpha_vantage")
        self.assertEqual(result["fallback_type"], "missing_api_key")

    def test_alpha_vantage_rate_limit_falls_back_to_mock(self) -> None:
        provider = MarketDataProvider()

        with patch("quantmind.data.market_data.settings") as mock_settings:
            mock_settings.has_alpha_vantage_api_key = True
            with patch.object(
                provider,
                "_fetch_alpha_vantage_daily_bars",
                return_value={"Note": "Thank you for using Alpha Vantage! Our standard API call frequency is limited."},
            ):
                result = provider._get_from_alpha_vantage("AAPL", "2026-05-14")

        self.assertEqual(result["source"], "alpha_vantage_fallback_mock")
        self.assertEqual(result["fallback_type"], "rate_limit")

    def test_normalize_akshare_daily_bars_keeps_latest_20_before_trade_date(self) -> None:
        df = pd.DataFrame(
            {
                "日期": pd.date_range("2026-04-20", periods=25, freq="D").strftime("%Y-%m-%d"),
                "收盘": [100 + i + 0.123 for i in range(25)],
                "成交量": [10_000 + i for i in range(25)],
                "其他字段": ["ignored"] * 25,
            }
        )
        provider = MarketDataProvider()

        result = provider._normalize_akshare_daily_bars("600519", "2026-05-14", df)

        self.assertEqual(result["symbol"], "600519")
        self.assertEqual(len(result["dates"]), 20)
        self.assertEqual(len(result["close_prices"]), 20)
        self.assertEqual(len(result["volumes"]), 20)
        self.assertEqual(result["dates"][0], "2026-04-25")
        self.assertEqual(result["dates"][-1], "2026-05-14")
        self.assertEqual(result["close_prices"][0], 105.12)
        self.assertEqual(result["close_prices"][-1], 124.12)
        self.assertEqual(result["volumes"][0], 10_005)
        self.assertEqual(result["volumes"][-1], 10_024)
        self.assertEqual(result["source"], "akshare")
        self.assertEqual(result["requested_provider"], "akshare")
        self.assertIsNone(result["fallback_reason"])
        self.assertIsNone(result["fallback_type"])

    def test_mock_data_contains_observability_metadata(self) -> None:
        provider = MarketDataProvider()

        result = provider._get_mock_data("600519", "2026-05-14")

        self.assertEqual(result["symbol"], "600519")
        self.assertEqual(len(result["close_prices"]), 20)
        self.assertEqual(len(result["volumes"]), 20)
        self.assertEqual(result["source"], "mock")
        self.assertEqual(result["requested_provider"], "mock")
        self.assertIsNone(result["fallback_reason"])

    def test_mock_data_can_mark_akshare_fallback(self) -> None:
        provider = MarketDataProvider()

        result = provider._get_mock_data(
            "600519",
            "2026-05-14",
            requested_provider="akshare",
            source="akshare_fallback_mock",
            fallback_reason="network unavailable",
        )

        self.assertEqual(result["source"], "akshare_fallback_mock")
        self.assertEqual(result["requested_provider"], "akshare")
        self.assertEqual(result["fallback_reason"], "network unavailable")
        self.assertIsNone(result["fallback_type"])

    def test_normalize_akshare_daily_bars_rejects_missing_required_columns(self) -> None:
        df = pd.DataFrame({"日期": ["2026-05-14"], "收盘": [100.0]})
        provider = MarketDataProvider()

        with self.assertRaises(ValueError):
            provider._normalize_akshare_daily_bars("600519", "2026-05-14", df)

    def test_fetch_akshare_daily_bars_passes_timeout_when_supported(self) -> None:
        captured_kwargs = {}

        def stock_zh_a_hist(
            symbol,
            period,
            start_date,
            end_date,
            adjust,
            timeout=None,
        ):
            kwargs = {
                "symbol": symbol,
                "period": period,
                "start_date": start_date,
                "end_date": end_date,
                "adjust": adjust,
                "timeout": timeout,
            }
            captured_kwargs.update(kwargs)
            return pd.DataFrame({"日期": ["2026-05-14"], "收盘": [100.0], "成交量": [10_000]})

        provider = MarketDataProvider()
        ak = types.SimpleNamespace(stock_zh_a_hist=stock_zh_a_hist)

        provider._fetch_akshare_daily_bars(ak, "600519", "2026-05-14", 30)

        self.assertEqual(captured_kwargs["symbol"], "600519")
        self.assertEqual(captured_kwargs["start_date"], "20260414")
        self.assertEqual(captured_kwargs["end_date"], "20260514")
        self.assertIn("timeout", captured_kwargs)

    def test_akshare_retries_shorter_windows_then_succeeds(self) -> None:
        provider = MarketDataProvider()
        calls = []

        def fake_fetch(_ak, symbol, trade_date, lookback_days):
            calls.append((symbol, trade_date, lookback_days))
            if lookback_days == 60:
                raise RuntimeError("network temporarily unavailable")
            return pd.DataFrame({"日期": ["2026-05-14"], "收盘": [100.0], "成交量": [10_000]})

        with patch.object(provider, "_fetch_akshare_daily_bars", side_effect=fake_fetch):
            result = provider._get_from_akshare("600519", "2026-05-14")

        self.assertEqual([call[2] for call in calls], [60, 30])
        self.assertEqual(result["source"], "akshare")
        self.assertEqual(result["akshare_lookback_days"], 30)
        self.assertEqual(result["akshare_attempts"][0]["status"], "failed")
        self.assertEqual(result["akshare_attempts"][1]["status"], "success")

    def test_akshare_fallback_reason_is_classified_and_truncated(self) -> None:
        provider = MarketDataProvider()

        class ProxyError(Exception):
            pass

        with patch.object(
            provider,
            "_fetch_akshare_daily_bars",
            side_effect=ProxyError("proxy failed " + "x" * 400),
        ):
            result = provider._get_from_akshare("600519", "2026-05-14")

        self.assertEqual(result["source"], "akshare_fallback_mock")
        self.assertEqual(result["fallback_type"], "proxy_error")
        self.assertLessEqual(len(result["fallback_reason"]), provider.FALLBACK_REASON_MAX_LENGTH)
        self.assertEqual([item["lookback_days"] for item in result["akshare_attempts"]], [60, 30, 20])

    def test_to_tushare_ts_code_infers_exchange(self) -> None:
        provider = MarketDataProvider()

        self.assertEqual(provider._to_tushare_ts_code("600519"), "600519.SH")
        self.assertEqual(provider._to_tushare_ts_code("000001"), "000001.SZ")
        self.assertEqual(provider._to_tushare_ts_code("300750"), "300750.SZ")
        self.assertEqual(provider._to_tushare_ts_code("688001"), "688001.SH")
        self.assertEqual(provider._to_tushare_ts_code("600519.SH"), "600519.SH")

    def test_normalize_tushare_daily_bars_sorts_and_keeps_latest_20(self) -> None:
        df = pd.DataFrame(
            {
                "trade_date": pd.date_range("2026-04-20", periods=25, freq="D")
                .strftime("%Y%m%d")
                .tolist()[::-1],
                "close": [100 + i + 0.123 for i in range(25)],
                "vol": [10_000 + i for i in range(25)],
                "ignored": ["x"] * 25,
            }
        )
        provider = MarketDataProvider()

        result = provider._normalize_tushare_daily_bars("600519", "2026-05-14", df)

        self.assertEqual(result["symbol"], "600519")
        self.assertEqual(result["source"], "tushare")
        self.assertEqual(result["requested_provider"], "tushare")
        self.assertEqual(result["tushare_ts_code"], "600519.SH")
        self.assertEqual(len(result["dates"]), 20)
        self.assertEqual(result["dates"][0], "2026-04-25")
        self.assertEqual(result["dates"][-1], "2026-05-14")

    def test_normalize_tushare_daily_bars_rejects_missing_required_columns(self) -> None:
        df = pd.DataFrame({"trade_date": ["20260514"], "close": [100.0]})
        provider = MarketDataProvider()

        with self.assertRaises(ValueError):
            provider._normalize_tushare_daily_bars("600519", "2026-05-14", df)

    def test_get_from_tushare_falls_back_when_token_missing(self) -> None:
        provider = MarketDataProvider()

        with patch("quantmind.data.market_data.settings") as mock_settings:
            mock_settings.has_tushare_token = False
            result = provider._get_from_tushare("600519", "2026-05-14")

        self.assertEqual(result["source"], "tushare_fallback_mock")
        self.assertEqual(result["requested_provider"], "tushare")
        self.assertEqual(result["fallback_type"], "missing_token")


if __name__ == "__main__":
    unittest.main()