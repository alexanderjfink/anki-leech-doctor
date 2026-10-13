"""Provider base types.

HTTP headers matter: some gateways sit behind Cloudflare, whose "error 1010"
rule blocks the default `Python-urllib/…` signature. We therefore send a
browser-style User-Agent by default (overridable per provider).
"""
import json
import urllib.request
import urllib.error

# Cloudflare bans known bot signatures (Python-urllib -> HTTP 403 / error 1010).
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class LLMError(Exception):
    pass


class Provider:
    kind = "base"

    def __init__(self, label, base_url, model, api_key,
                 user_agent=None, headers=None,
                 chat_path="/chat/completions", models_path="/models"):
        self.label = label
        self.base_url = (base_url or "").strip().rstrip("/")
        # be forgiving: "localhost:11434/v1" -> "http://localhost:11434/v1"
        if self.base_url and "://" not in self.base_url:
            self.base_url = "http://" + self.base_url
        self.model = model or ""
        self.api_key = api_key or ""
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.extra_headers = dict(headers or {})
        self.chat_path = chat_path
        self.models_path = models_path
        # tolerate a pasted full endpoint, e.g. ".../v1/chat/completions"
        if self.base_url.endswith(self.chat_path):
            self.base_url = self.base_url[: -len(self.chat_path)]

    # -- headers ---------------------------------------------------------
    def base_headers(self):
        h = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }
        h.update(self.extra_headers)
        return h

    # -- transport -------------------------------------------------------
    def _request(self, url, headers, payload=None, timeout=30):
        merged = self.base_headers()
        merged.update(headers or {})
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        method = "POST" if payload is not None else "GET"
        req = urllib.request.Request(url, data=data, headers=merged, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:400]
            except Exception:
                pass
            hint = ""
            if e.code == 403 and "1010" in body:
                hint = ("  [Cloudflare blocked the request signature. "
                        "Set a browser-style 'user_agent' for this provider in settings.]")
            raise LLMError(f"HTTP {e.code} from {self.label}: {body}{hint}")
        except urllib.error.URLError as e:
            raise LLMError(f"Cannot reach {self.label} at {self.base_url}: {e.reason}")
        except Exception as e:
            raise LLMError(f"{self.label} error: {e}")

    def chat(self, system, user, temperature=0.2, max_tokens=1200, timeout=90):
        raise NotImplementedError

    def list_models(self, timeout=10):
        raise NotImplementedError

    def describe(self):
        return f"{self.label} [{self.model or 'no model'} @ {self.base_url or 'no url'}]"
