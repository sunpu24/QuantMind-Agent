from __future__ import annotations

import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quantmind.config import settings  # noqa: E402
from quantmind.llm.client import DeepSeekChatClient  # noqa: E402


def main() -> None:
    print("=" * 60)
    print("QuantMind DeepSeek Diagnostic")
    print("=" * 60)
    print(f"QUANTMIND_LLM_PROVIDER: {settings.llm_provider}")
    print(f"QUANTMIND_LLM_MODEL: {settings.llm_model}")
    print(f"QUANTMIND_LLM_BASE_URL: {settings.llm_base_url}")
    print(f"QUANTMIND_LLM_TIMEOUT: {settings.llm_timeout}")
    print(f"LLM API KEY: {settings.masked_llm_api_key}")

    if settings.llm_provider != "deepseek":
        print("诊断结果: skipped")
        print("原因: QUANTMIND_LLM_PROVIDER 不是 deepseek")
        return
    if not settings.has_llm_api_key:
        print("诊断结果: failed")
        print("失败类型: missing_api_key")
        return

    try:
        started_at = time.perf_counter()
        result = DeepSeekChatClient().chat_json([
            {"role": "system", "content": "你只输出 JSON。"},
            {"role": "user", "content": "返回 {\"status\": \"ok\", \"message\": \"连接成功\"}"},
        ])
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    except Exception as exc:
        print("诊断结果: failed")
        print("失败类型: deepseek_error")
        print(f"失败原因: {exc}")
        return

    print("诊断结果: success")
    print(f"调用耗时: {elapsed_ms} ms")
    print(f"响应: {result}")


if __name__ == "__main__":
    main()