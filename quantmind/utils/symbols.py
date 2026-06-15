from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from quantmind.config import settings


@dataclass(frozen=True)
class ResolvedSymbol:
    """用户输入解析后的股票标识。"""

    query: str
    symbol: str
    display_name: str
    market: str
    input_type: str


COMMON_SYMBOL_ALIASES: dict[str, tuple[str, str, str]] = {
    "贵州茅台": ("600519", "贵州茅台", "A_SHARE"),
    "茅台": ("600519", "贵州茅台", "A_SHARE"),
    "平安银行": ("000001", "平安银行", "A_SHARE"),
    "伊利股份": ("600887", "伊利股份", "A_SHARE"),
    "伊利": ("600887", "伊利股份", "A_SHARE"),
    "格力电器": ("000651", "格力电器", "A_SHARE"),
    "格力": ("000651", "格力电器", "A_SHARE"),
    "宁德时代": ("300750", "宁德时代", "A_SHARE"),
    "比亚迪": ("002594", "比亚迪", "A_SHARE"),
    "招商银行": ("600036", "招商银行", "A_SHARE"),
    "中国平安": ("601318", "中国平安", "A_SHARE"),
    "apple": ("AAPL", "Apple", "US"),
    "苹果": ("AAPL", "Apple", "US"),
    "aapl": ("AAPL", "Apple", "US"),
    "tesla": ("TSLA", "Tesla", "US"),
    "特斯拉": ("TSLA", "Tesla", "US"),
    "tsla": ("TSLA", "Tesla", "US"),
    "microsoft": ("MSFT", "Microsoft", "US"),
    "微软": ("MSFT", "Microsoft", "US"),
    "msft": ("MSFT", "Microsoft", "US"),
    "nvidia": ("NVDA", "NVIDIA", "US"),
    "英伟达": ("NVDA", "NVIDIA", "US"),
    "nvda": ("NVDA", "NVIDIA", "US"),
    "amazon": ("AMZN", "Amazon", "US"),
    "亚马逊": ("AMZN", "Amazon", "US"),
    "amzn": ("AMZN", "Amazon", "US"),
    "google": ("GOOGL", "Alphabet", "US"),
    "谷歌": ("GOOGL", "Alphabet", "US"),
    "googl": ("GOOGL", "Alphabet", "US"),
    "meta": ("META", "Meta", "US"),
}


COMMON_SYMBOLS_BY_CODE: dict[str, tuple[str, str]] = {
    symbol.upper(): (display_name, market)
    for symbol, display_name, market in COMMON_SYMBOL_ALIASES.values()
}


def resolve_symbol(query: str) -> ResolvedSymbol:
    """解析首页输入的股票名称、A 股代码或美股 ticker。

    第一版 intentionally 保持轻量：常见名称走本地映射，代码/ticker 走格式识别。
    后续可以替换为 AkShare 股票列表或 Alpha Vantage Symbol Search。
    """

    raw = query.strip()
    if not raw:
        raise ValueError("请输入股票名称或代码")

    key = raw.lower()
    if key in COMMON_SYMBOL_ALIASES:
        symbol, display_name, market = COMMON_SYMBOL_ALIASES[key]
        return ResolvedSymbol(
            query=raw,
            symbol=symbol,
            display_name=display_name,
            market=market,
            input_type="alias",
        )

    a_share_match = _resolve_a_share_name_from_akshare(raw)
    if a_share_match is not None:
        symbol, display_name = a_share_match
        return ResolvedSymbol(
            query=raw,
            symbol=symbol,
            display_name=display_name,
            market="A_SHARE",
            input_type="a_share_name",
        )

    normalized = raw.upper()
    if _is_a_share_symbol(normalized):
        symbol = normalized.split(".", maxsplit=1)[0]
        display_name, market = COMMON_SYMBOLS_BY_CODE.get(symbol, (symbol, "A_SHARE"))
        return ResolvedSymbol(
            query=raw,
            symbol=symbol,
            display_name=display_name,
            market=market,
            input_type="a_share_code",
        )

    if _is_us_symbol(normalized):
        display_name, market = COMMON_SYMBOLS_BY_CODE.get(normalized, (normalized, "US"))
        return ResolvedSymbol(
            query=raw,
            symbol=normalized,
            display_name=display_name,
            market=market,
            input_type="us_ticker",
        )

    raise ValueError("当前仅支持 A 股和美股，输入内容不可查询。中文名称未能从 A 股列表解析时，请输入股票代码或美股 ticker。")


def _resolve_a_share_name_from_akshare(query: str) -> tuple[str, str] | None:
    """通过 AkShare 全量 A 股代码名称表解析中文股票名称。

    本地常用别名只作为快速路径；这里用于从根本上支持绝大多数 A 股中文名称。
    为避免单元测试或离线环境因网络/依赖失败而中断，任何 AkShare 异常都回退为未命中。
    """

    if not settings.akshare_enabled or not _contains_cjk(query):
        return None

    key = _normalize_name_key(query)
    if not key:
        return None

    try:
        aliases = _load_a_share_aliases_from_akshare()
    except Exception:
        return None
    return aliases.get(key)


@lru_cache(maxsize=1)
def _load_a_share_aliases_from_akshare() -> dict[str, tuple[str, str]]:
    import akshare as ak

    if not hasattr(ak, "stock_info_a_code_name"):
        return {}

    df = ak.stock_info_a_code_name()
    if df is None or getattr(df, "empty", True):
        return {}

    code_column = _first_existing_column(df, ["code", "代码", "证券代码", "股票代码"])
    name_column = _first_existing_column(df, ["name", "名称", "证券简称", "股票简称"])
    if code_column is None or name_column is None:
        return {}

    aliases: dict[str, tuple[str, str]] = {}
    for _, row in df.iterrows():
        code = _normalize_a_share_code(row.get(code_column))
        name = str(row.get(name_column) or "").strip()
        if code is None or not name:
            continue
        aliases[_normalize_name_key(name)] = (code, name)
    return aliases


def _first_existing_column(df: Any, candidates: list[str]) -> str | None:
    columns = {str(column): column for column in getattr(df, "columns", [])}
    for candidate in candidates:
        if candidate in columns:
            return columns[candidate]
    return None


def _normalize_a_share_code(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    code = text.split(".", maxsplit=1)[0]
    if code.isdigit():
        code = code.zfill(6)
    if code.isdigit() and len(code) == 6:
        return code
    return None


def _normalize_name_key(value: str) -> str:
    return "".join(str(value).strip().lower().split())


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _is_a_share_symbol(value: str) -> bool:
    if value.endswith((".SH", ".SZ", ".BJ")):
        code = value.split(".", maxsplit=1)[0]
        return code.isdigit() and len(code) == 6
    return value.isdigit() and len(value) == 6


def _is_us_symbol(value: str) -> bool:
    if not value or value.isdigit():
        return False
    if value.endswith((".SH", ".SZ", ".BJ")):
        return False
    normalized = value.replace(".", "").replace("-", "")
    return normalized.isascii() and normalized.isalpha() and 1 <= len(normalized) <= 8