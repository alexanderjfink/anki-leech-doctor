"""Anthropic Claude native Messages API client."""
from .base import Provider, LLMError


class AnthropicProvider(Provider):
    kind = "anthropic"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("chat_path", "/v1/messages")
        kwargs.setdefault("models_path", "/v1/models")
        super().__init__(*args, **kwargs)

    def _headers(self):
        if not self.api_key:
            raise LLMError(f"{self.label}: API key is not set (open Preferences).")
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def chat(self, system, user, temperature=0.2, max_tokens=1200, timeout=90):
        if not self.base_url:
            raise LLMError(f"{self.label}: base_url is not set.")
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = self._request(f"{self.base_url}{self.chat_path}", self._headers(), payload, timeout)
        try:
            parts = [b.get("text", "") for b in data["content"] if b.get("type") == "text"]
            return "".join(parts)
        except Exception:
            raise LLMError(f"{self.label}: unexpected response shape: {str(data)[:300]}")

    def list_models(self, timeout=10):
        if not self.base_url:
            raise LLMError(f"{self.label}: base_url is not set.")
        data = self._request(f"{self.base_url}{self.models_path}", self._headers(), None, timeout)
        ids = [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
        return sorted(set(ids))
