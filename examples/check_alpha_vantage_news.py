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
    parser = argparse.ArgumentParser(description="Alpha Vantage 新闻最小诊断脚本")
    parser.add_argument("--symbol", required=True, help="股票代码，例如 600519 或 IBM")
    parser.add_argument("--date", required=True, help="诊断日期，例如 2024-06-05")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider = NewsDataProvider()

    print("=" * 60)
    print("QuantMind Alpha Vantage News Diagnostic")
    print("=" * 60)
    print(f"股票代码: {args.symbol}")
    print(f"诊断日期: {args.date}")
    print(f"QUANTMIND_NEWS_PROVIDER: {settings.news_provider}")
    print(f"ALPHA_VANTAGE_API_KEY: {settings.masked_alpha_vantage_api_key}")
    print(f"ALPHA_VANTAGE_TIMEOUT: {settings.alpha_vantage_timeout}")
    print(f"Alpha Vantage ticker: {provider._to_alpha_vantage_ticker(args.symbol)}")

    if not settings.has_alpha_vantage_api_key:
        print("诊断结果: failed")
        print("失败类型: missing_api_key")
        print("失败原因: 未配置 ALPHA_VANTAGE_API_KEY")
        return

    try:
        payload = provider._fetch_alpha_vantage_news(args.symbol)
        news = provider._normalize_alpha_vantage_news(args.symbol, args.date, payload)
    except Exception as exc:
        print("诊断结果: failed")
        print("失败类型: alpha_vantage_error")
        print(f"失败原因: {exc}")
        return

    print("诊断结果: success")
    print(f"返回新闻数: {len(news)}")
    for item in news:
        print(f"- [{item.get('date')}] {item.get('title')}")


if __name__ == "__main__":
    main()