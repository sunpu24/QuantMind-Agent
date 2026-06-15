from __future__ import annotations

import json
import math
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from quantmind.config import settings


class FundamentalDataProvider:
    """基本面数据 Provider。外部数据不可用时返回空 metrics，避免编造财务数据。"""

    ALPHA_VANTAGE_OVERVIEW_URL = "https://www.alphavantage.co/query"
    FALLBACK_REASON_MAX_LENGTH = 240

    def get_fundamentals(self, symbol: str, trade_date: str) -> dict[str, Any]:
        if self._is_us_symbol(symbol):
            return self._get_from_alpha_vantage(symbol, trade_date)
        if self._is_a_share_symbol(symbol):
            return self._get_from_akshare(symbol, trade_date)
        return self._empty_result(
            symbol,
            trade_date,
            requested_provider="auto",
            source="fundamental_fallback_empty",
            fallback_type="unknown_market",
            fallback_reason=f"无法自动识别股票市场: {symbol}",
        )

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

    def _empty_result(
        self,
        symbol: str,
        trade_date: str,
        *,
        requested_provider: str,
        source: str,
        fallback_type: str,
        fallback_reason: str,
    ) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "trade_date": trade_date,
            "metrics": {},
            "source": source,
            "requested_provider": requested_provider,
            "fallback_type": fallback_type,
            "fallback_reason": self._truncate_text(fallback_reason),
        }

    def _get_from_alpha_vantage(self, symbol: str, trade_date: str) -> dict[str, Any]:
        if not settings.has_alpha_vantage_api_key:
            return self._empty_result(
                symbol,
                trade_date,
                requested_provider="alpha_vantage",
                source="alpha_vantage_fundamental_fallback_empty",
                fallback_type="missing_api_key",
                fallback_reason="未配置 ALPHA_VANTAGE_API_KEY",
            )

        try:
            payload = self._fetch_alpha_vantage_overview(symbol)
            return self._normalize_alpha_vantage_overview(symbol, trade_date, payload)
        except Exception as exc:
            return self._empty_result(
                symbol,
                trade_date,
                requested_provider="alpha_vantage",
                source="alpha_vantage_fundamental_fallback_empty",
                fallback_type=self._classify_fallback_type(exc),
                fallback_reason=f"Alpha Vantage 基本面获取失败: {exc}",
            )

    def _fetch_alpha_vantage_overview(self, symbol: str) -> dict[str, Any]:
        params = {
            "function": "OVERVIEW",
            "symbol": symbol.strip().upper(),
            "apikey": settings.alpha_vantage_api_key,
        }
        url = f"{self.ALPHA_VANTAGE_OVERVIEW_URL}?{urlencode(params)}"
        with urlopen(url, timeout=settings.alpha_vantage_timeout) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw)

    def _normalize_alpha_vantage_overview(
        self,
        symbol: str,
        trade_date: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not payload or "Symbol" not in payload:
            raise ValueError("Alpha Vantage OVERVIEW 返回空基本面数据")
        if "Note" in payload or "Information" in payload or "Error Message" in payload:
            raise ValueError(payload.get("Note") or payload.get("Information") or payload.get("Error Message"))

        metrics = {
            "pe_ratio": self._to_float_or_none(payload.get("PERatio")),
            "roe": self._to_float_or_none(payload.get("ReturnOnEquityTTM")),
            "profit_margin": self._to_float_or_none(payload.get("ProfitMargin")),
            "revenue_growth_yoy": self._to_float_or_none(payload.get("QuarterlyRevenueGrowthYOY")),
            "earnings_growth_yoy": self._to_float_or_none(payload.get("QuarterlyEarningsGrowthYOY")),
            "debt_to_equity": self._to_float_or_none(payload.get("DebtToEquityRatio")),
            "market_cap": self._to_float_or_none(payload.get("MarketCapitalization")),
        }
        metrics = {key: value for key, value in metrics.items() if value is not None}
        if not metrics:
            raise ValueError("Alpha Vantage OVERVIEW 未包含可用财务指标")
        return {
            "symbol": symbol,
            "trade_date": trade_date,
            "metrics": metrics,
            "source": "alpha_vantage_overview",
            "requested_provider": "alpha_vantage",
            "fallback_type": None,
            "fallback_reason": None,
        }

    def _get_from_akshare(self, symbol: str, trade_date: str) -> dict[str, Any]:
        if not settings.akshare_enabled:
            return self._empty_result(
                symbol,
                trade_date,
                requested_provider="akshare",
                source="akshare_fundamental_fallback_empty",
                fallback_type="disabled",
                fallback_reason="AkShare 已禁用",
            )

        try:
            import akshare as ak
        except ImportError:
            return self._empty_result(
                symbol,
                trade_date,
                requested_provider="akshare",
                source="akshare_fundamental_fallback_empty",
                fallback_type="import_error",
                fallback_reason="未安装 AkShare",
            )

        try:
            df = self._fetch_akshare_indicator(ak, symbol)
            return self._normalize_akshare_indicator(symbol, trade_date, df)
        except Exception as exc:
            return self._empty_result(
                symbol,
                trade_date,
                requested_provider="akshare",
                source="akshare_fundamental_fallback_empty",
                fallback_type=self._classify_fallback_type(exc),
                fallback_reason=f"AkShare 基本面获取失败: {exc}",
            )

    def _fetch_akshare_indicator(self, ak: Any, symbol: str) -> Any:
        normalized_symbol = self._to_akshare_symbol(symbol)
        if hasattr(ak, "stock_a_indicator_lg"):
            return ak.stock_a_indicator_lg(symbol=normalized_symbol)
        if hasattr(ak, "stock_financial_analysis_indicator"):
            return ak.stock_financial_analysis_indicator(symbol=normalized_symbol, start_year="2020")
        raise AttributeError("当前 AkShare 版本缺少可用的 A 股基本面接口")

    def _normalize_akshare_indicator(self, symbol: str, trade_date: str, df: Any) -> dict[str, Any]:
        if df is None or getattr(df, "empty", True):
            raise ValueError("AkShare 返回空基本面数据")

        row = self._select_latest_akshare_row(df, trade_date)
        metrics = {
            "pe_ratio": self._first_numeric(row, ["pe", "PE", "市盈率"]),
            "pb_ratio": self._first_numeric(row, ["pb", "PB", "市净率"]),
            "ps_ratio": self._first_numeric(row, ["ps", "PS", "市销率"]),
            "dividend_yield": self._first_numeric(row, ["dv_ratio", "股息率"]),
            "roe": self._first_percent_or_numeric(row, ["净资产收益率(%)", "加权净资产收益率(%)", "ROE", "roe"]),
            "profit_margin": self._first_percent_or_numeric(row, ["销售净利率(%)", "销售净利率", "净利率", "profit_margin"]),
            "gross_margin": self._first_percent_or_numeric(row, ["销售毛利率(%)", "销售毛利率", "毛利率"]),
            "revenue_growth_yoy": self._first_percent_or_numeric(row, ["主营业务收入增长率(%)", "营业收入增长率(%)", "营收增长率", "revenue_growth_yoy"]),
            "earnings_growth_yoy": self._first_percent_or_numeric(row, ["净利润增长率(%)", "净利润同比增长率", "earnings_growth_yoy"]),
            "debt_ratio": self._first_percent_or_numeric(row, ["资产负债率(%)", "资产负债率", "debt_ratio"]),
            "debt_to_equity": self._first_percent_or_numeric(row, ["产权比率(%)", "产权比率", "debt_to_equity"]),
            "total_assets": self._first_numeric(row, ["总资产(元)", "总资产"]),
        }
        metrics = {key: value for key, value in metrics.items() if value is not None}
        if not metrics:
            raise ValueError(f"AkShare 基本面字段不包含可用指标，当前字段: {list(df.columns)}")
        return {
            "symbol": symbol,
            "trade_date": trade_date,
            "metrics": metrics,
            "source": "akshare_indicator",
            "requested_provider": "akshare",
            "fallback_type": None,
            "fallback_reason": None,
        }

    def _select_latest_akshare_row(self, df: Any, trade_date: str) -> Any:
        if "日期" not in df.columns:
            return df.iloc[-1]

        comparable = df.copy()
        comparable["__date"] = comparable["日期"].astype(str)
        eligible = comparable[comparable["__date"] <= trade_date]
        if eligible.empty:
            return df.iloc[-1]
        return eligible.sort_values("__date").iloc[-1]

    @staticmethod
    def _to_akshare_symbol(symbol: str) -> str:
        value = symbol.strip().upper()
        if value.endswith((".SH", ".SZ", ".BJ")):
            return value.split(".", maxsplit=1)[0]
        return value

    @staticmethod
    def _to_float_or_none(value: Any) -> float | None:
        try:
            if value in (None, "", "None", "-"):
                return None
            parsed = float(value)
            if not math.isfinite(parsed):
                return None
            return parsed
        except (TypeError, ValueError):
            return None

    def _first_numeric(self, row: Any, candidates: list[str]) -> float | None:
        for key in candidates:
            if key in row.index:
                value = self._to_float_or_none(row.get(key))
                if value is not None:
                    return value
        return None

    def _first_percent_or_numeric(self, row: Any, candidates: list[str]) -> float | None:
        value = self._first_numeric(row, candidates)
        if value is None:
            return None
        if abs(value) > 1:
            return value / 100
        return value

    @classmethod
    def _truncate_text(cls, text: str) -> str:
        if len(text) <= cls.FALLBACK_REASON_MAX_LENGTH:
            return text
        return f"{text[: cls.FALLBACK_REASON_MAX_LENGTH - 3]}..."

    @staticmethod
    def _classify_fallback_type(exc: Exception | None) -> str:
        if exc is None:
            return "fundamental_error"
        exc_text = f"{exc.__class__.__module__}.{exc.__class__.__name__}: {exc}".lower()
        message = str(exc).lower()
        if "timeout" in exc_text or "timed out" in exc_text:
            return "timeout"
        if "token" in exc_text or "api key" in message or "apikey" in message:
            return "missing_api_key"
        if "rate" in message or "frequency" in message:
            return "rate_limit"
        if "空" in str(exc) or "empty" in message:
            return "empty_data"
        if "字段" in str(exc) or "column" in exc_text or "schema" in exc_text:
            return "schema_mismatch"
        return "fundamental_error"