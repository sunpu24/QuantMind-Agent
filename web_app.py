from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from quantmind.graph.workflow import QuantMindWorkflow
from quantmind.schemas import AgentState
from quantmind.utils.symbols import ResolvedSymbol, resolve_symbol


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="QuantMind Agent Web", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/analysis")
def analysis() -> FileResponse:
    return FileResponse(STATIC_DIR / "analysis.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/validate")
def validate_symbol(q: str = Query(..., min_length=1)) -> JSONResponse:
    try:
        resolved = resolve_symbol(q)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": str(exc)},
        )
    return JSONResponse({"ok": True, "data": _resolved_symbol_to_dict(resolved)})


@app.get("/api/analyze/stream")
def analyze_stream(q: str = Query(..., min_length=1)) -> StreamingResponse:
    def event_generator():
        try:
            resolved = resolve_symbol(q)
            yield _sse(
                {
                    "type": "progress",
                    "step": "resolved",
                    "percent": 5,
                    "message": f"已识别为 {resolved.display_name}（{resolved.symbol}）",
                    "symbol": _resolved_symbol_to_dict(resolved),
                }
            )

            workflow = QuantMindWorkflow()
            trade_date = date.today().strftime("%Y-%m-%d")
            for event in workflow.run_with_progress(resolved.symbol, trade_date):
                state = event["state"]
                payload = {
                    "type": "progress",
                    "step": event["step"],
                    "percent": event["percent"],
                    "message": event["message"],
                    "symbol": _resolved_symbol_to_dict(resolved),
                }
                if event["step"] == "decision":
                    payload = {
                        "type": "result",
                        "step": "done",
                        "percent": 100,
                        "message": "分析完成",
                        "symbol": _resolved_symbol_to_dict(resolved),
                        "data": _state_to_response(state),
                    }
                yield _sse(payload)
        except Exception as exc:  # noqa: BLE001 - Web 层需要将异常转成前端可读事件
            yield _sse(
                {
                    "type": "error",
                    "step": "error",
                    "percent": 100,
                    "message": f"分析失败: {exc}",
                }
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _resolved_symbol_to_dict(resolved: ResolvedSymbol) -> dict[str, str]:
    return asdict(resolved)


def _state_to_response(state: AgentState) -> dict[str, Any]:
    return {
        "symbol": state.symbol,
        "trade_date": state.trade_date,
        "market_data": state.market_data,
        "news_data": state.news_data,
        "technical_report": _serialize(state.technical_report),
        "news_report": _serialize(state.news_report),
        "risk_report": _serialize(state.risk_report),
        "final_decision": _serialize(state.final_decision),
        "disclaimer": "本报告仅用于研究和学习，不构成任何投资建议；数据可能延迟、不完整或受第三方源影响，交易有风险，决策需谨慎。",
    }


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("web_app:app", host="0.0.0.0", port=port, reload=True)