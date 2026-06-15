from __future__ import annotations

import json
import random
import inspect
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from quantmind.config import settings


class MarketDataProvider:
    """行情数据 Provider。默认 Mock，可接入 A 股 AkShare/Tushare 与美股 Alpha Vantage 日线行情。"""

    LOOKBACK_DAYS = 60
    RETRY_LOOKBACK_DAYS = (60, 30, 20)
    BAR_LIMIT = 20
    FALLBACK_REASON_MAX_LENGTH = 240
    ALPHA_VANTAGE_DAILY_URL = "https://www.alphavantage.co/query"

    def get_daily_bars(self, symbol: str, trade_date: str) -> dict[str, Any]:
        if settings.data_provider == "auto":
            if self._is_us_symbol(symbol):
                return self._get_from_alpha_vantage(symbol, trade_date)
            if self._is_a_share_symbol(symbol):
                return self._get_from_tushare(symbol, trade_date)
            return self._get_mock_data(
                symbol,
                trade_date,
                requested_provider="auto",
                source="auto_fallback_mock",
                fallback_reason=f"无法自动识别股票市场: {symbol}",
                fallback_type="unknown_market",
            )
        if settings.data_provider == "alpha_vantage":
            return self._get_from_alpha_vantage(symbol, trade_date)
        if settings.data_provider == "akshare":
            return self._get_from_akshare(symbol, trade_date)
        if settings.data_provider == "tushare":
            return self._get_from_tushare(symbol, trade_date)
        return self._get_mock_data(symbol, trade_date, requested_provider=settings.data_provider)

    def _get_mock_data(
        self,
        symbol: str,
        trade_date: str,
        *,
        requested_provider: str = "mock",
        source: str = "mock",
        fallback_reason: str | None = None,
        fallback_type: str | None = None,
        akshare_attempts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        random.seed(f"{symbol}-{trade_date}")
        base = random.uniform(20, 180)
        closes = []
        volumes = []
        price = base
        for _ in range(20):
            price *= 1 + random.uniform(-0.025, 0.03)
            closes.append(round(price, 2))
            volumes.append(random.randint(80_000, 260_000))

        end = datetime.strptime(trade_date, "%Y-%m-%d")
        dates = [(end - timedelta(days=19 - i)).strftime("%Y-%m-%d") for i in range(20)]
        return {
            "symbol": symbol,
            "dates": dates,
            "close_prices": closes,
            "volumes": volumes,
            "source": source,
            "requested_provider": requested_provider,
            "fallback_reason": fallback_reason,
            "fallback_type": fallback_type,
            "akshare_attempts": akshare_attempts,
        }

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

    def _get_from_alpha_vantage(self, symbol: str, trade_date: str) -> dict[str, Any]:
        if not settings.has_alpha_vantage_api_key:
            reason = "未配置 ALPHA_VANTAGE_API_KEY"
            print(f"{reason}，回退到 Mock 行情数据。")
            return self._get_mock_data(
                symbol,
                trade_date,
                requested_provider="alpha_vantage",
                source="alpha_vantage_fallback_mock",
                fallback_reason=reason,
                fallback_type="missing_api_key",
            )

        try:
            payload = self._fetch_alpha_vantage_daily_bars(symbol)
            return self._normalize_alpha_vantage_daily_bars(symbol, trade_date, payload)
        except Exception as exc:
            fallback_type = self._classify_alpha_vantage_fallback_type(exc)
            reason = self._truncate_text(f"Alpha Vantage 行情获取失败: {exc}")
            print(f"Alpha Vantage 行情获取失败，回退到 Mock 行情数据。原因: {reason}")
            return self._get_mock_data(
                symbol,
                trade_date,
                requested_provider="alpha_vantage",
                source="alpha_vantage_fallback_mock",
                fallback_reason=reason,
                fallback_type=fallback_type,
            )

    def _fetch_alpha_vantage_daily_bars(self, symbol: str) -> dict[str, Any]:
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": self._to_alpha_vantage_symbol(symbol),
            "outputsize": "compact",
            "apikey": settings.alpha_vantage_api_key,
        }
        url = f"{self.ALPHA_VANTAGE_DAILY_URL}?{urlencode(params)}"
        with urlopen(url, timeout=settings.alpha_vantage_timeout) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw)

    def _normalize_alpha_vantage_daily_bars(
        self,
        symbol: str,
        trade_date: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if "Error Message" in payload:
            raise ValueError(payload["Error Message"])
        if "Note" in payload:
            raise ValueError(payload["Note"])
        if "Information" in payload:
            raise ValueError(payload["Information"])

        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict) or not series:
            raise ValueError("Alpha Vantage 返回空行情数据")

        rows = []
        for date, values in series.items():
            if not isinstance(values, dict):
                continue
            if date > trade_date:
                continue
            close = values.get("4. close")
            volume = values.get("5. volume")
            if close is None or volume is None:
                continue
            rows.append((date, round(float(close), 2), int(float(volume))))

        rows = sorted(rows, key=lambda item: item[0])[-self.BAR_LIMIT :]
        if not rows:
            raise ValueError(f"未获取到 {trade_date} 前的可用 Alpha Vantage 行情数据")
        actual_trade_date = rows[-1][0]

        return {
            "symbol": self._to_alpha_vantage_symbol(symbol),
            "dates": [item[0] for item in rows],
            "close_prices": [item[1] for item in rows],
            "volumes": [item[2] for item in rows],
            "source": "alpha_vantage",
            "requested_provider": "alpha_vantage",
            "fallback_reason": None,
            "fallback_type": None,
            "market": "US",
            "requested_trade_date": trade_date,
            "actual_trade_date": actual_trade_date,
            "date_adjusted": actual_trade_date != trade_date,
            "date_adjust_reason": self._build_date_adjust_reason(trade_date, actual_trade_date),
        }

    @staticmethod
    def _to_alpha_vantage_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    @staticmethod
    def _classify_alpha_vantage_fallback_type(exc: Exception | None) -> str:
        if exc is None:
            return "alpha_vantage_error"
        exc_text = f"{exc.__class__.__module__}.{exc.__class__.__name__}: {exc}".lower()
        message = str(exc).lower()
        if "timeout" in exc_text or "timed out" in exc_text:
            return "timeout"
        if "frequency" in message or "rate" in message or "call frequency" in message:
            return "rate_limit"
        if "invalid api call" in message or "error message" in message:
            return "api_error"
        if "空行情" in str(exc) or "未获取到" in str(exc):
            return "empty_data"
        return "alpha_vantage_error"

    def _get_from_akshare(self, symbol: str, trade_date: str) -> dict[str, Any]:
        if not settings.akshare_enabled:
            reason = "AkShare 已禁用"
            print(f"{reason}，回退到 Mock 行情数据。")
            return self._get_mock_data(
                symbol,
                trade_date,
                requested_provider="akshare",
                source="akshare_fallback_mock",
                fallback_reason=reason,
                fallback_type="disabled",
            )

        try:
            import akshare as ak
        except ImportError:
            reason = "未安装 AkShare"
            print(f"{reason}，回退到 Mock 行情数据。")
            return self._get_mock_data(
                symbol,
                trade_date,
                requested_provider="akshare",
                source="akshare_fallback_mock",
                fallback_reason=reason,
                fallback_type="import_error",
            )

        attempts: list[dict[str, Any]] = []
        last_exc: Exception | None = None
        for lookback_days in self.RETRY_LOOKBACK_DAYS:
            try:
                df = self._fetch_akshare_daily_bars(ak, symbol, trade_date, lookback_days)
                result = self._normalize_akshare_daily_bars(symbol, trade_date, df)
                result["akshare_lookback_days"] = lookback_days
                result["akshare_attempts"] = attempts + [
                    {"lookback_days": lookback_days, "status": "success"}
                ]
                return result
            except Exception as exc:
                last_exc = exc
                attempts.append(
                    {
                        "lookback_days": lookback_days,
                        "status": "failed",
                        "fallback_type": self._classify_fallback_type(exc),
                        "reason": self._truncate_text(str(exc)),
                    }
                )
                print(
                    "AkShare 行情获取失败，准备尝试更短窗口。"
                    f"窗口: {lookback_days} 天，原因: {self._truncate_text(str(exc))}"
                )

        fallback_type = self._classify_fallback_type(last_exc)
        reason = self._build_fallback_reason(last_exc)
        print(f"AkShare 行情获取失败，回退到 Mock 行情数据。原因: {reason}")
        return self._get_mock_data(
            symbol,
            trade_date,
            requested_provider="akshare",
            source="akshare_fallback_mock",
            fallback_reason=reason,
            fallback_type=fallback_type,
            akshare_attempts=attempts,
        )

    def _fetch_akshare_daily_bars(
        self,
        ak: Any,
        symbol: str,
        trade_date: str,
        lookback_days: int,
    ) -> Any:
        end = datetime.strptime(trade_date, "%Y-%m-%d")
        start = end - timedelta(days=lookback_days)
        kwargs: dict[str, Any] = {
            "symbol": symbol,
            "period": "daily",
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
            "adjust": "",
        }
        if self._supports_timeout(ak.stock_zh_a_hist):
            kwargs["timeout"] = settings.akshare_timeout
        return ak.stock_zh_a_hist(**kwargs)

    def _normalize_akshare_daily_bars(
        self,
        symbol: str,
        trade_date: str,
        df: Any,
    ) -> dict[str, Any]:
        required_columns = {"日期", "收盘", "成交量"}
        if df is None or getattr(df, "empty", True):
            raise ValueError("AkShare 返回空行情数据")
        if not required_columns.issubset(set(df.columns)):
            raise ValueError(f"AkShare 返回字段不完整，当前字段: {list(df.columns)}")

        data = df.loc[:, ["日期", "收盘", "成交量"]].copy()
        data["日期"] = data["日期"].astype(str)
        data = data[data["日期"] <= trade_date]
        data = data.tail(self.BAR_LIMIT)

        if data.empty:
            raise ValueError(f"未获取到 {trade_date} 前的可用行情数据")
        actual_trade_date = self._format_akshare_date(str(data["日期"].iloc[-1]))

        return {
            "symbol": symbol,
            "dates": [self._format_akshare_date(value) for value in data["日期"].tolist()],
            "close_prices": [round(float(value), 2) for value in data["收盘"].tolist()],
            "volumes": [int(value) for value in data["成交量"].tolist()],
            "source": "akshare",
            "requested_provider": "akshare",
            "fallback_reason": None,
            "fallback_type": None,
            "requested_trade_date": trade_date,
            "actual_trade_date": actual_trade_date,
            "date_adjusted": actual_trade_date != trade_date,
            "date_adjust_reason": self._build_date_adjust_reason(trade_date, actual_trade_date),
        }

    @staticmethod
    def _format_akshare_date(value: str) -> str:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")

    @staticmethod
    def _supports_timeout(func: Any) -> bool:
        try:
            return "timeout" in inspect.signature(func).parameters
        except (TypeError, ValueError):
            return False

    @classmethod
    def _build_fallback_reason(cls, exc: Exception | None) -> str:
        if exc is None:
            return "AkShare 行情获取失败"
        return cls._truncate_text(f"AkShare 行情获取失败: {exc}")

    @classmethod
    def _truncate_text(cls, text: str) -> str:
        if len(text) <= cls.FALLBACK_REASON_MAX_LENGTH:
            return text
        return f"{text[: cls.FALLBACK_REASON_MAX_LENGTH - 3]}..."

    @staticmethod
    def _classify_fallback_type(exc: Exception | None) -> str:
        if exc is None:
            return "akshare_error"
        exc_text = f"{exc.__class__.__module__}.{exc.__class__.__name__}: {exc}".lower()
        if "proxyerror" in exc_text or "proxy" in exc_text:
            return "proxy_error"
        if "timeout" in exc_text or "timed out" in exc_text:
            return "timeout"
        if "空行情" in str(exc) or "未获取到" in str(exc):
            return "empty_data"
        if "字段" in str(exc) or "column" in exc_text or "schema" in exc_text:
            return "schema_mismatch"
        return "akshare_error"

    def _get_from_tushare(self, symbol: str, trade_date: str) -> dict[str, Any]:
        if not settings.has_tushare_token:
            reason = "未配置 TUSHARE_TOKEN"
            print(f"{reason}，回退到 Mock 行情数据。")
            return self._get_mock_data(
                symbol,
                trade_date,
                requested_provider="tushare",
                source="tushare_fallback_mock",
                fallback_reason=reason,
                fallback_type="missing_token",
            )

        try:
            import tushare as ts
        except ImportError:
            reason = "未安装 Tushare"
            print(f"{reason}，回退到 Mock 行情数据。")
            return self._get_mock_data(
                symbol,
                trade_date,
                requested_provider="tushare",
                source="tushare_fallback_mock",
                fallback_reason=reason,
                fallback_type="import_error",
            )

        try:
            df = self._fetch_tushare_daily_bars(ts, symbol, trade_date)
            return self._normalize_tushare_daily_bars(symbol, trade_date, df)
        except Exception as exc:
            fallback_type = self._classify_tushare_fallback_type(exc)
            reason = self._truncate_text(f"Tushare 行情获取失败: {exc}")
            print(f"Tushare 行情获取失败，回退到 Mock 行情数据。原因: {reason}")
            return self._get_mock_data(
                symbol,
                trade_date,
                requested_provider="tushare",
                source="tushare_fallback_mock",
                fallback_reason=reason,
                fallback_type=fallback_type,
            )

    def _fetch_tushare_daily_bars(self, ts: Any, symbol: str, trade_date: str) -> Any:
        pro = ts.pro_api(settings.tushare_token)
        end = datetime.strptime(trade_date, "%Y-%m-%d")
        start = end - timedelta(days=self.LOOKBACK_DAYS)
        return pro.daily(
            ts_code=self._to_tushare_ts_code(symbol),
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )

    def _normalize_tushare_daily_bars(
        self,
        symbol: str,
        trade_date: str,
        df: Any,
    ) -> dict[str, Any]:
        required_columns = {"trade_date", "close", "vol"}
        if df is None or getattr(df, "empty", True):
            raise ValueError("Tushare 返回空行情数据")
        if not required_columns.issubset(set(df.columns)):
            raise ValueError(f"Tushare 返回字段不完整，当前字段: {list(df.columns)}")

        data = df.loc[:, ["trade_date", "close", "vol"]].copy()
        data["trade_date"] = data["trade_date"].astype(str)
        max_trade_date = trade_date.replace("-", "")
        data = data[data["trade_date"] <= max_trade_date]
        data = data.sort_values("trade_date").tail(self.BAR_LIMIT)

        if data.empty:
            raise ValueError(f"未获取到 {trade_date} 前的可用 Tushare 行情数据")
        actual_trade_date = self._format_tushare_date(str(data["trade_date"].iloc[-1]))

        return {
            "symbol": symbol,
            "dates": [self._format_tushare_date(value) for value in data["trade_date"].tolist()],
            "close_prices": [round(float(value), 2) for value in data["close"].tolist()],
            "volumes": [int(float(value)) for value in data["vol"].tolist()],
            "source": "tushare",
            "requested_provider": "tushare",
            "fallback_reason": None,
            "fallback_type": None,
            "tushare_ts_code": self._to_tushare_ts_code(symbol),
            "requested_trade_date": trade_date,
            "actual_trade_date": actual_trade_date,
            "date_adjusted": actual_trade_date != trade_date,
            "date_adjust_reason": self._build_date_adjust_reason(trade_date, actual_trade_date),
        }

    @staticmethod
    def _build_date_adjust_reason(requested_trade_date: str, actual_trade_date: str) -> str | None:
        if actual_trade_date == requested_trade_date:
            return None
        return f"目标日期 {requested_trade_date} 无可用行情，已自动使用最近可用交易日 {actual_trade_date}。"

    @staticmethod
    def _to_tushare_ts_code(symbol: str) -> str:
        value = symbol.strip().upper()
        if value.endswith((".SH", ".SZ", ".BJ")):
            return value
        if value.startswith(("6", "9")):
            return f"{value}.SH"
        if value.startswith(("0", "2", "3")):
            return f"{value}.SZ"
        if value.startswith(("4", "8")):
            return f"{value}.BJ"
        raise ValueError(f"无法识别 A 股代码所属交易所: {symbol}")

    @staticmethod
    def _format_tushare_date(value: str) -> str:
        return datetime.strptime(value, "%Y%m%d").strftime("%Y-%m-%d")

    @staticmethod
    def _classify_tushare_fallback_type(exc: Exception | None) -> str:
        if exc is None:
            return "tushare_error"
        exc_text = f"{exc.__class__.__module__}.{exc.__class__.__name__}: {exc}".lower()
        message = str(exc)
        if "token" in exc_text or "权限" in message or "积分" in message:
            return "token_error"
        if "timeout" in exc_text or "timed out" in exc_text:
            return "timeout"
        if "空行情" in message or "未获取到" in message:
            return "empty_data"
        if "字段" in message or "column" in exc_text or "schema" in exc_text:
            return "schema_mismatch"
        return "tushare_error"
