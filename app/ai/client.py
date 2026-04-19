"""Unified AI client helpers for OpenAI-compatible and Anthropic providers."""
from __future__ import annotations

import httpx
from openai import OpenAI
from openai import APIConnectionError, APIError, APITimeoutError, AuthenticationError, BadRequestError, RateLimitError

from app.config import get_settings
from app.schemas import AICredentials


OPENAI_BASE_URL = "https://api.openai.com/v1"
GROK_BASE_URL = "https://api.x.ai/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class AIClientError(Exception):
    """Raised when credentials are missing, unsupported, or invalid."""


def _infer_provider_from_api_key(api_key: str | None) -> str | None:
    key = (api_key or "").strip()
    if not key:
        return None
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("xai-"):
        return "grok"
    if key.startswith("sk-ant-"):
        return "claude"
    if key.startswith("AIza"):
        return "gemini"
    if key.startswith("sk-"):
        return "openai"
    return None


def _display_provider(provider: str) -> str:
    names = {
        "openai": "OpenAI",
        "grok": "Grok",
        "groq": "Groq",
        "claude": "Claude",
        "gemini": "Gemini",
    }
    return names.get(provider, provider.title())


def _normalize_provider(provider: str) -> str:
    value = (provider or "").lower().strip()
    if value == "anthropic":
        return "claude"
    if value in ("google", "googleai"):
        return "gemini"
    return value or "openai"


def _validate_provider_api_key_match(provider: str, api_key: str | None) -> None:
    inferred = _infer_provider_from_api_key(api_key)
    if inferred and inferred != provider:
        raise AIClientError(
            f"Provider/key mismatch: selected {_display_provider(provider)} "
            f"but the API key looks like {_display_provider(inferred)}. "
            f"Switch the provider or move the key to the matching .env variable."
        )


def _resolve_provider(creds: AICredentials) -> str:
    settings = get_settings()
    return _normalize_provider(creds.provider or settings.default_ai_provider or "openai")


def _build_openai_compatible_client(creds: AICredentials) -> tuple[OpenAI, str]:
    """Return (client, model) for OpenAI-compatible providers."""
    settings = get_settings()
    provider = _resolve_provider(creds)

    if provider == "grok":
        api_key = creds.api_key or settings.grok_api_key
        model = creds.model or settings.grok_model
        base_url = GROK_BASE_URL
    elif provider == "groq":
        api_key = creds.api_key or settings.groq_api_key
        model = creds.model or settings.groq_model
        base_url = GROQ_BASE_URL
    elif provider == "openai":
        api_key = creds.api_key or settings.openai_api_key
        model = creds.model or settings.openai_model
        base_url = OPENAI_BASE_URL
    else:
        raise AIClientError(f"Unsupported AI provider: {provider}")

    if not api_key:
        raise AIClientError(
            f"No API key provided for {provider}. "
            "Paste one in the UI or set it in .env."
        )

    _validate_provider_api_key_match(provider, api_key)
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
    return client, model


def _chat_openai_compatible(
    creds: AICredentials, system: str, user: str, *, json_mode: bool = False
) -> str:
    client, model = _build_openai_compatible_client(creds)
    base_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }

    def _create(**kwargs) -> str:
        try:
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except AuthenticationError as exc:
            raise AIClientError(f"{_resolve_provider(creds).title()} authentication failed: {exc}") from exc
        except RateLimitError as exc:
            raise AIClientError(f"{_resolve_provider(creds).title()} rate limit hit: {exc}") from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise AIClientError(f"{_resolve_provider(creds).title()} request failed: {exc}") from exc
        except APIError as exc:
            raise AIClientError(f"{_resolve_provider(creds).title()} API error: {exc}") from exc

    if json_mode:
        try:
            return _create(**base_kwargs, response_format={"type": "json_object"})
        except BadRequestError:
            # Some OpenAI-compatible providers reject response_format=json_object.
            # Retry with stronger textual instruction instead of failing ATS entirely.
            fallback_messages = [
                {
                    "role": "system",
                    "content": (
                        f"{system}\n\n"
                        "Return valid JSON only. Do not include markdown fences or commentary."
                    ),
                },
                {"role": "user", "content": user},
            ]
            return _create(**{**base_kwargs, "messages": fallback_messages})

    return _create(**base_kwargs)


def _chat_claude(creds: AICredentials, system: str, user: str, *, json_mode: bool = False) -> str:
    settings = get_settings()
    api_key = creds.api_key or settings.anthropic_api_key
    model = creds.model or settings.anthropic_model

    if not api_key:
        raise AIClientError(
            "No API key provided for claude. Paste one in the UI or set ANTHROPIC_API_KEY in .env."
        )

    _validate_provider_api_key_match("claude", api_key)
    body = {
        "model": model,
        "max_tokens": 2048,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if json_mode:
        body["system"] = (
            f"{system}\n\n"
            "Return valid JSON only. Do not include markdown fences or extra commentary."
        )

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    try:
        resp = httpx.post(ANTHROPIC_MESSAGES_URL, headers=headers, json=body, timeout=60.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise AIClientError(f"Claude request failed: {exc}") from exc

    data = resp.json()
    parts = data.get("content") or []
    text_chunks = [part.get("text", "") for part in parts if part.get("type") == "text"]
    return "".join(text_chunks).strip()


def _chat_gemini(
    creds: AICredentials, system: str, user: str, *, json_mode: bool = False
) -> str:
    """Call Google's Generative Language API (Gemini).

    Uses the ``generateContent`` REST endpoint with an ``X-goog-api-key``
    header so the API key never appears in logs or URLs.
    """
    settings = get_settings()
    api_key = creds.api_key or settings.gemini_api_key
    model = creds.model or settings.gemini_model

    if not api_key:
        raise AIClientError(
            "No API key provided for gemini. Paste one in the UI or set GEMINI_API_KEY in .env."
        )

    _validate_provider_api_key_match("gemini", api_key)
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"

    # Gemini has its own schema — system instruction + contents[].parts[].text
    effective_system = system
    if json_mode:
        effective_system = (
            f"{system}\n\n"
            "Return valid JSON only. Do not include markdown fences or extra commentary."
        )

    body: dict = {
        "systemInstruction": {"parts": [{"text": effective_system}]},
        "contents": [
            {"role": "user", "parts": [{"text": user}]},
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048,
        },
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    headers = {
        "x-goog-api-key": api_key,
        "content-type": "application/json",
    }

    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=60.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise AIClientError(f"Gemini request failed: {exc}") from exc

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts).strip()


def chat(creds: AICredentials, system: str, user: str, *, json_mode: bool = False) -> str:
    """One-shot chat call. Returns assistant text."""
    provider = _resolve_provider(creds)
    if provider == "claude":
        return _chat_claude(creds, system, user, json_mode=json_mode)
    if provider == "gemini":
        return _chat_gemini(creds, system, user, json_mode=json_mode)
    if provider in {"openai", "grok", "groq"}:
        return _chat_openai_compatible(creds, system, user, json_mode=json_mode)
    raise AIClientError(f"Unsupported AI provider: {provider}")
