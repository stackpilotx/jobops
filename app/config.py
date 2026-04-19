"""Centralized configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # AI
    openai_api_key: str = ""
    grok_api_key: str = ""
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""  # Google AI Studio / Generative Language API
    default_ai_provider: str = "openai"  # openai | grok | groq | claude | gemini
    openai_model: str = "gpt-4o-mini"
    grok_model: str = "grok-2-latest"
    groq_model: str = "llama-3.3-70b-versatile"
    anthropic_model: str = "claude-sonnet-4-20250514"
    gemini_model: str = "gemini-1.5-pro"

    # HTTP
    request_timeout_s: int = 20
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )

    # Server
    host: str = "127.0.0.1"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
