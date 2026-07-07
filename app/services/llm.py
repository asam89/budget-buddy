"""LLM provider abstraction — all AI call sites use this interface."""

import json
import logging
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import requests

logger = logging.getLogger(__name__)


@dataclass
class LLMHealth:
    reachable: bool
    model_available: bool
    latency_ms: float
    error: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    def complete_json(self, prompt: str, schema: dict | None = None,
                      max_tokens: int = 4096) -> dict | list:
        ...

    def name(self) -> str:
        ...

    def health(self) -> LLMHealth:
        ...


class OllamaProvider:
    """Local LLM via Ollama HTTP API."""

    def __init__(self, base_url: str = "http://localhost:11434",
                 model: str = "gemma3:12b", timeout: int = 120):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def name(self) -> str:
        return f"ollama:{self._model}"

    def complete_json(self, prompt: str, schema: dict | None = None,
                      max_tokens: int = 4096) -> dict | list:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if schema:
            payload["format"] = schema

        resp = requests.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"].strip()

        # Strip markdown fencing if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Retry once with validation error appended
            retry_prompt = (
                f"{prompt}\n\nYour previous response was not valid JSON. "
                f"Please return ONLY valid JSON. Previous response:\n{content[:500]}"
            )
            payload["messages"] = [{"role": "user", "content": retry_prompt}]
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(content)

    def health(self) -> LLMHealth:
        start = time.time()
        try:
            resp = requests.get(f"{self._base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            latency = (time.time() - start) * 1000
            models = [m["name"] for m in resp.json().get("models", [])]
            model_ok = any(self._model in m for m in models)
            return LLMHealth(
                reachable=True,
                model_available=model_ok,
                latency_ms=round(latency, 1),
                error=None if model_ok else f"Model {self._model} not found. Available: {models}",
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return LLMHealth(
                reachable=False,
                model_available=False,
                latency_ms=round(latency, 1),
                error=str(e),
            )

    def list_models(self) -> list[str]:
        try:
            resp = requests.get(f"{self._base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []


class AnthropicProvider:
    """Cloud LLM via Anthropic API — opt-in only."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514",
                 timeout: int = 60):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def name(self) -> str:
        return f"anthropic:{self._model}"

    def complete_json(self, prompt: str, schema: dict | None = None,
                      max_tokens: int = 4096) -> dict | list:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text.strip()

        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        return json.loads(content)

    def health(self) -> LLMHealth:
        start = time.time()
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._api_key)
            # Minimal call to verify credentials
            client.messages.create(
                model=self._model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            latency = (time.time() - start) * 1000
            return LLMHealth(reachable=True, model_available=True, latency_ms=round(latency, 1))
        except Exception as e:
            latency = (time.time() - start) * 1000
            return LLMHealth(
                reachable=False, model_available=False,
                latency_ms=round(latency, 1), error=str(e),
            )


def get_provider(
    provider_name: str | None = None,
    ollama_base_url: str = "http://localhost:11434",
    ollama_model: str = "gemma3:12b",
    anthropic_api_key: str = "",
    llm_timeout: int = 120,
) -> LLMProvider | None:
    """Factory: build the active LLM provider from config values."""
    provider = (provider_name or "ollama").lower()

    if provider == "anthropic":
        if not anthropic_api_key:
            return None
        return AnthropicProvider(api_key=anthropic_api_key, timeout=llm_timeout)
    else:
        return OllamaProvider(
            base_url=ollama_base_url,
            model=ollama_model,
            timeout=llm_timeout,
        )
