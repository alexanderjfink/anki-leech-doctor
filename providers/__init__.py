"""Provider clients. Two shapes cover all five targets:

  openai_compat -> OpenAI, Ollama, vLLM, OpenCode, LM Studio, LiteLLM, ...
  anthropic     -> Claude native Messages API
"""
from .base import Provider, LLMError
from .router import (
    pick_provider, make_provider, probe, route_info, resolve, is_configured,
)

__all__ = [
    "Provider", "LLMError", "pick_provider", "make_provider", "probe",
    "route_info", "resolve", "is_configured",
]
