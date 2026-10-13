"""Provider base types.

Two headers matter in practice:

* **User-Agent** — Cloudflare's "error 1010" rule blocks the default
  ``Python-urllib/…`` signature. OpenCode also asks clients to *self-identify*
  with their own agent string rather than a generic library name, so we send an
  honest one (verified to pass their Cloudflare). Overridable per provider.
* **x-opencode-session** — OpenCode Go requires a stable session id on inference
  requests ("any stable UUID works"); without it the relay returns HTTP 400
  ``MissingSessionID``. Their ``GET /models`` deliberately does not carry it.
"""
import json
import os
import urllib.error
import urllib.request
import uuid

OPENCODE_HOST = "opencode.ai"

_SESSION = None


def _manifest():
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "manifest.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def default_user_agent():
    m = _manifest()
    version = m.get("version", "0")
    home = m.get("homepage", "") or "https://github.com/alexanderjfink/anki-leech-doctor"
    return f"LeechDoctor/{version} (+{home})"


def is_opencode(base_url):
    """True when the endpoint is the OpenCode relay (Zen or Go)."""
    return OPENCODE_HOST in (base_url or "").lower()


def opencode_session():
    """A stable, opaque session id for this run (128-bit hex).

    OpenCode only requires that it be stable per conversation; one id per
    add-on process keeps routing and prompt caching consistent.
    """
    global _SESSION
    if _SESSION is None:
        _SESSION = uuid.uuid4().hex
    return _SESSION


DEFAULT_USER_AGENT = default_user_agent()


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

    def has_header(self, name):
        return any(k.lower() == name.lower() for k in self.extra_headers)

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
            elif "x-opencode-session" in body or "MissingSessionID" in body:
                hint = ("  [OpenCode requires an x-opencode-session header on inference "
                        "requests; Leech Doctor sends one automatically. If you overrode "
                        "'headers', make sure you didn't remove it.]")
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
