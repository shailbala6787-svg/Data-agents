"""Provider factory — resolves provider + model from settings.

``auto`` picks whichever key is set. With no key at all we raise a clear,
actionable error: the real provider is the default and the only gated path —
there is no silent stub fallback (harness/rules/ai-agents.md rule 7).
"""
from __future__ import annotations

from src.config.settings import get_settings
from src.llm.providers.anthropic import AnthropicProvider
from src.llm.providers.base import LLMError, LLMProvider
from src.llm.providers.gemini import GeminiProvider
from src.llm.providers.openrouter import OpenRouterProvider


def create_llm_provider() -> LLMProvider:
 s = get_settings()
 provider = s.resolve_provider()
 model = s.resolve_model()

 if provider == "anthropic":
  return AnthropicProvider(api_key=s.anthropic_api_key, model=model)
 if provider == "gemini":
  return GeminiProvider(api_key=s.gemini_api_key, model=model)
 if provider == "openrouter":
  return OpenRouterProvider(
   api_key=s.openrouter_api_key, model=model, base_url=s.openrouter_base_url
  )
 if provider == "ollama":
  return OllamaProvider(
   base_url=s.ollama_base_url or "http://localhost:11434",
   model=model or s.ollama_model or "llama3.2:3b",
  )
 raise LLMError(
 "No LLM provider configured. Set AGENT_LLM_PROVIDER=ollama and provide "
 "a running local Ollama instance (http://localhost:11434), or set a cloud "
 "provider key in .env."
 )
