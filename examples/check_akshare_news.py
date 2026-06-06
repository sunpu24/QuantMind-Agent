from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quantmind.config import settings  # noqa: E402
from quantmind.data.news_data import NewsDataProvider  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AkShare A 股个股新闻最小诊断脚本")
    parser.add_argument("--symbol", required=True, help="A股股票代码，例如 600519 或 600519.SH")
    parser.add_argument("--date", required=True, help="诊断日期，例如 2026-06-05")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider = NewsDataProvider()

    print("=" * 60)
    print("QuantMind AkShare News Diagnostic")
    print("=" * 60)
    print(f"股票代码: {args.symbol}")
    print(f"AkShare symbol: {provider._to_akshare_symbol(args.symbol)}")
    print(f"诊断日期: {args.date}")
    print(f"QUANTMIND_NEWS_PROVIDER: {settings.news_provider}")
    print(f"AKSHARE_ENABLED: {settings.akshare_enabled}")
    print(f"AKSHARE_TIMEOUT: {settings.akshare_timeout}")
    print("AkShare 接口: stock_news_em")

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

    try:
        df = provider._fetch_akshare_stock_news(ak, args.symbol)
        news = provider._normalize_akshare_stock_news(args.symbol, args.date, df)
    except Exception as exc:
        print("诊断结果: failed")
        print(f"失败类型: {provider._classify_akshare_fallback_type(exc)}")
        print(f"失败原因: {provider._truncate_text(str(exc))}")
        return

    if not news:
        print("诊断结果: failed")
        print("失败类型: empty_data")
        print(f"失败原因: AkShare 未返回 {args.date} 前的可用新闻")
        return

    print("诊断结果: success")
    print(f"返回新闻数: {len(news)}")
    for item in news:
        print(f"- [{item.get('date')}] {item.get('title')}")
        if item.get("publisher"):
            print(f"  来源: {item.get('publisher')}")
        if item.get("url"):
            print(f"  链接: {item.get('url')}")


if __name__ == "__main__":
    main()