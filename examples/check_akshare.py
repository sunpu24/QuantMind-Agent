from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quantmind.config import settings  # noqa: E402
from quantmind.data.market_data import MarketDataProvider  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AkShare A 股日线行情最小诊断脚本")
    parser.add_argument("--symbol", required=True, help="A股股票代码，例如 600519")
    parser.add_argument("--date", required=True, help="诊断日期，例如 2024-06-05")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider = MarketDataProvider()

    print("=" * 60)
    print("QuantMind AkShare Diagnostic")
    print("=" * 60)
    print(f"股票代码: {args.symbol}")
    print(f"诊断日期: {args.date}")
    print(f"AKSHARE_ENABLED: {settings.akshare_enabled}")
    print(f"AKSHARE_TIMEOUT: {settings.akshare_timeout}")

    if not settings.akshare_enabled:
        print("诊断结果: skipped")
        print("失败类型: disabled")
        print("失败原因: AkShare 已禁用")
        return

    try:
        import akshare as ak
    except ImportError as exc:
        print("诊断结果: failed")
        print("失败类型: import_error")
        print(f"失败原因: {provider._truncate_text(str(exc))}")
        return

    supports_timeout = provider._supports_timeout(ak.stock_zh_a_hist)
    print(f"stock_zh_a_hist 支持 timeout: {supports_timeout}")
    print(f"尝试窗口: {', '.join(str(days) for days in provider.RETRY_LOOKBACK_DAYS)} 天")

    last_exc: Exception | None = None
    for lookback_days in provider.RETRY_LOOKBACK_DAYS:
        print("-" * 60)
        print(f"开始尝试: {lookback_days} 天窗口")
        try:
            df = provider._fetch_akshare_daily_bars(ak, args.symbol, args.date, lookback_days)
            result = provider._normalize_akshare_daily_bars(args.symbol, args.date, df)
        except Exception as exc:
            last_exc = exc
            print("状态: failed")
            print(f"失败类型: {provider._classify_fallback_type(exc)}")
            print(f"失败原因: {provider._truncate_text(str(exc))}")
            continue

        print("状态: success")
        print(f"数据源: {result['source']}")
        print(f"返回条数: {len(result['dates'])}")
        print(f"首日: {result['dates'][0]}")
        print(f"末日: {result['dates'][-1]}")
        print(f"最新收盘价: {result['close_prices'][-1]}")
        return

    print("=" * 60)
    print("诊断结果: failed")
    print(f"失败类型: {provider._classify_fallback_type(last_exc)}")
    print(f"失败原因: {provider._build_fallback_reason(last_exc)}")


if __name__ == "__main__":
    main()