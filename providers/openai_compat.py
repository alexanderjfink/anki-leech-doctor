"""OpenAI-compatible client (OpenAI, Ollama, vLLM, OpenCode, LM Studio, LiteLLM…)."""
from .base import Provider, LLMError, is_opencode, opencode_session


class OpenAICompatProvider(Provider):
    kind = "openai_compat"

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _chat_headers(self):
        """Headers for an inference request.

        OpenCode's relay requires a stable ``x-opencode-session`` id here (and only
        here — their ``GET /models`` deliberately omits it). An explicit header in
        the provider config always wins.
        """
        h = self._headers()
        if is_opencode(self.base_url) and not self.has_header("x-opencode-session"):
            h["x-opencode-session"] = opencode_session()
        return h

    def chat(self, system, user, temperature=0.2, max_tokens=1200, timeout=90):
        if not self.base_url:
            raise LLMError(f"{self.label}: base_url is not set (open Preferences).")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        data = self._request(f"{self.base_url}{self.chat_path}", self._chat_headers(), payload, timeout)
        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            raise LLMError(f"{self.label}: unexpected response shape: {str(data)[:300]}")

    def list_models(self, timeout=10):
        if not self.base_url:
            raise LLMError(f"{self.label}: base_url is not set.")
        data = self._request(f"{self.base_url}{self.models_path}", self._headers(), None, timeout)
        ids = []
        items = data.get("data", []) if isinstance(data, dict) else (data or [])
        for m in items:
            if isinstance(m, dict) and m.get("id"):
                ids.append(m["id"])
            elif isinstance(m, str):
                ids.append(m)
        return sorted(set(ids))
