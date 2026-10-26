"""Runtime settings loaded from environment variables / `.env`.

All variables use the `DART_` prefix (see `.env.example`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DART_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Open DART
    api_key: str = ""
    api_base_url: str = "https://opendart.fss.or.kr/api"
    http_timeout: float = 30.0

    # Fallback SLM (OpenAI-compatible endpoint: Ollama / vLLM / OpenAI)
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_timeout: float = 120.0
    llm_enabled: bool = True
    llm_max_retries: int = 2

    # Local cache
    cache_dir: Path = Path(".cache")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
