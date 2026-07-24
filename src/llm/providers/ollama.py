"""Ollama local LLM provider (OpenAI-compatible api/generate endpoint)."""
from __future__ import annotations

import httpx

from src.llm.providers.base import LLMError, LLMProvider
from src.llm.retry import with_retries

_DEFAULT_URL = "http://localhost:11434"


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = (base_url or _DEFAULT_URL).rstrip("/")
        self.model = model or "llama3.2:3b"

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        def _call() -> str:
            resp = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": f"SYSTEM:\n{system}\n\nUSER:\n{user}",
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("response") or "").strip()
            if not text:
                raise LLMError("ollama returned an empty completion")
            return text

        return with_retries(_call, provider=self.name)
