from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # 允许未安装依赖时仍用默认配置运行
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

if load_dotenv is not None:
    load_dotenv(ENV_PATH)


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    env: str = os.getenv("QUANTMIND_ENV", "development")
    output_language: str = os.getenv("QUANTMIND_OUTPUT_LANGUAGE", "zh-CN")

    data_provider: str = os.getenv("QUANTMIND_DATA_PROVIDER", "mock")
    news_provider: str = os.getenv("QUANTMIND_NEWS_PROVIDER", "mock")
    tushare_token: str = os.getenv("TUSHARE_TOKEN", "")
    alpha_vantage_api_key: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    alpha_vantage_timeout: int = _get_int("ALPHA_VANTAGE_TIMEOUT", 15)
    akshare_enabled: bool = _get_bool("AKSHARE_ENABLED", True)
    akshare_timeout: int = _get_int("AKSHARE_TIMEOUT", 15)

    llm_provider: str = os.getenv("QUANTMIND_LLM_PROVIDER", "mock")
    llm_model: str = os.getenv("QUANTMIND_LLM_MODEL", "deepseek-chat")
    llm_base_url: str = os.getenv("QUANTMIND_LLM_BASE_URL", "https://api.deepseek.com")
    llm_api_key: str = os.getenv("QUANTMIND_LLM_API_KEY", "")
    llm_timeout: int = _get_int("QUANTMIND_LLM_TIMEOUT", 30)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY", "")

    default_position_size: float = _get_float("QUANTMIND_DEFAULT_POSITION_SIZE", 0.3)
    max_position_size: float = _get_float("QUANTMIND_MAX_POSITION_SIZE", 0.5)
    stop_loss_pct: float = _get_float("QUANTMIND_STOP_LOSS_PCT", 0.05)
    take_profit_pct: float = _get_float("QUANTMIND_TAKE_PROFIT_PCT", 0.1)

    @property
    def has_tushare_token(self) -> bool:
        token = self.tushare_token.strip()
        return bool(token) and token != "your_tushare_token_here"

    @property
    def masked_tushare_token(self) -> str:
        if not self.has_tushare_token:
            return "未配置"
        token = self.tushare_token.strip()
        if len(token) <= 8:
            return "***"
        return f"{token[:4]}...{token[-4:]}"

    @property
    def has_alpha_vantage_api_key(self) -> bool:
        key = self.alpha_vantage_api_key.strip()
        return bool(key) and key != "your_alpha_vantage_api_key_here"

    @property
    def masked_alpha_vantage_api_key(self) -> str:
        if not self.has_alpha_vantage_api_key:
            return "未配置"
        key = self.alpha_vantage_api_key.strip()
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    @property
    def effective_llm_api_key(self) -> str:
        if self.llm_provider == "deepseek":
            return self.deepseek_api_key.strip() or self.llm_api_key.strip()
        return self.llm_api_key.strip()

    @property
    def has_llm_api_key(self) -> bool:
        key = self.effective_llm_api_key
        return bool(key) and key not in {"your_llm_api_key_here", "your_deepseek_api_key_here"}

    @property
    def masked_llm_api_key(self) -> str:
        if not self.has_llm_api_key:
            return "未配置"
        key = self.effective_llm_api_key
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"


settings = Settings()
