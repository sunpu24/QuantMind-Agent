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
    parser = argparse.ArgumentParser(description="Tushare A 股日线行情最小诊断脚本")
    parser.add_argument("--symbol", required=True, help="A股股票代码，例如 600519")
    parser.add_argument("--date", required=True, help="诊断日期，例如 2024-06-05")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider = MarketDataProvider()

    print("=" * 60)
    print("QuantMind Tushare Diagnostic")
    print("=" * 60)
    print(f"股票代码: {args.symbol}")
    print(f"诊断日期: {args.date}")
    print(f"TUSHARE_TOKEN: {settings.masked_tushare_token}")

    if not settings.has_tushare_token:
        print("诊断结果: failed")
        print("失败类型: missing_token")
        print("失败原因: 未配置 TUSHARE_TOKEN")
        return

    try:
        import tushare as ts
    except ImportError as exc:
        print("诊断结果: failed")
        print("失败类型: import_error")
        print(f"失败原因: {provider._truncate_text(str(exc))}")
        return

    try:
        ts_code = provider._to_tushare_ts_code(args.symbol)
        print(f"Tushare ts_code: {ts_code}")
        df = provider._fetch_tushare_daily_bars(ts, args.symbol, args.date)
        result = provider._normalize_tushare_daily_bars(args.symbol, args.date, df)
    except Exception as exc:
        print("诊断结果: failed")
        print(f"失败类型: {provider._classify_tushare_fallback_type(exc)}")
        print(f"失败原因: {provider._truncate_text(str(exc))}")
        return

    print("诊断结果: success")
    print(f"数据源: {result['source']}")
    print(f"返回条数: {len(result['dates'])}")
    print(f"首日: {result['dates'][0]}")
    print(f"末日: {result['dates'][-1]}")
    print(f"最新收盘价: {result['close_prices'][-1]}")


if __name__ == "__main__":
    main()