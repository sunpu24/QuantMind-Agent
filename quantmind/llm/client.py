from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from quantmind.config import settings


class LLMError(RuntimeError):
    """LLM 调用或响应格式异常。"""


class DeepSeekChatClient:
    """轻量 DeepSeek OpenAI-compatible Chat Completions client。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.effective_llm_api_key
        self.model = model or settings.llm_model or "deepseek-chat"
        self.base_url = (base_url or settings.llm_base_url or "https://api.deepseek.com").rstrip("/")
        self.timeout = timeout or settings.llm_timeout

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        if not self.api_key:
            raise LLMError("未配置 DeepSeek API Key")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:300]
            raise LLMError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise LLMError(f"DeepSeek 网络请求失败: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError("DeepSeek 请求超时") from exc

        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except Exception as exc:
            raise LLMError("DeepSeek 响应不是可解析的 JSON 对象") from exc
        if not isinstance(parsed, dict):
            raise LLMError("DeepSeek 响应 JSON 顶层不是对象")
        return parsed