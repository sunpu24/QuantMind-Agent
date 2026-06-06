from __future__ import annotations

import argparse
from datetime import datetime

from quantmind.graph.workflow import QuantMindWorkflow
from quantmind.utils.report import render_text_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QuantMind Agent 多 Agent A股分析框架")
    parser.add_argument("--symbol", required=True, help="A股股票代码，例如 600519")
    parser.add_argument("--date", required=True, help="分析日期，例如 2026-06-05")
    return parser.parse_args()


def validate_trade_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("分析日期必须使用 YYYY-MM-DD 格式，例如 2024-06-05") from exc
    return value


def main() -> None:
    args = parse_args()
    try:
        trade_date = validate_trade_date(args.date)
    except argparse.ArgumentTypeError as exc:
        raise SystemExit(f"参数错误: {exc}") from exc
    workflow = QuantMindWorkflow()
    state = workflow.run(symbol=args.symbol, trade_date=trade_date)
    print(render_text_report(state))


if __name__ == "__main__":
    main()
