from __future__ import annotations

from dataclasses import dataclass


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

    normalized = raw.upper()
    if _is_a_share_symbol(normalized):
        symbol = normalized.split(".", maxsplit=1)[0]
        return ResolvedSymbol(
            query=raw,
            symbol=symbol,
            display_name=symbol,
            market="A_SHARE",
            input_type="a_share_code",
        )

    if _is_us_symbol(normalized):
        return ResolvedSymbol(
            query=raw,
            symbol=normalized,
            display_name=normalized,
            market="US",
            input_type="us_ticker",
        )

    raise ValueError("当前仅支持 A 股和美股，输入内容不可查询。中文名称暂未收录时，请输入股票代码或美股 ticker。")


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