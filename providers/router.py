"""Provider router: power-aware selection of local vs cloud, with reachability
and configuration fallbacks so an unconfigured provider is never chosen silently."""
import urllib.request
import urllib.error

from .base import Provider, LLMError, DEFAULT_USER_AGENT
from .openai_compat import OpenAICompatProvider
from .anthropic import AnthropicProvider
from . import power as _power


def make_provider(entry):
    """Build a Provider from a catalog entry. Honours optional per-provider
    overrides: user_agent, headers (dict), chat_path, models_path."""
    entry = entry or {}
    kind = entry.get("kind", "openai_compat")
    common = dict(
        label=entry.get("label", kind),
        base_url=entry.get("base_url"),
        model=entry.get("model"),
        api_key=entry.get("api_key"),
        user_agent=entry.get("user_agent"),
        headers=entry.get("headers"),
    )
    if kind == "anthropic":
        return AnthropicProvider(
            chat_path=entry.get("chat_path", "/v1/messages"),
            models_path=entry.get("models_path", "/v1/models"),
            **common,
        )
    return OpenAICompatProvider(
        chat_path=entry.get("chat_path", "/chat/completions"),
        models_path=entry.get("models_path", "/models"),
        **common,
    )


def is_configured(entry):
    """A provider is usable if it has a base_url (and a key, for Anthropic)."""
    if not entry:
        return False
    if not (entry.get("base_url") or "").strip():
        return False
    if entry.get("kind") == "anthropic" and not (entry.get("api_key") or "").strip():
        return False
    return True


def _slot_entry(cfg, slot):
    catalog = cfg["providers"]["catalog"]
    name = cfg["providers"]["slots"].get(slot)
    return name, catalog.get(name)


def other_slot(slot):
    return "cloud" if slot == "local" else "local"


def route_info(cfg, force=None):
    """Return (slot, reason_string) without building a client."""
    r = cfg["routing"]
    mode = force or r.get("mode", "auto")
    if mode in ("local", "cloud"):
        return mode, f"manual override: {mode}"

    if not _power.is_online(timeout=r.get("probe_timeout_s", 1.5)):
        return r.get("offline", "local"), "offline -> local"

    pwr = _power.detect_power()
    key = {"ac": "on_ac", "battery": "on_battery", "desktop": "on_desktop", "unknown": "on_desktop"}[pwr]
    slot = r.get(key, "local")
    where = {"ac": "on AC power", "battery": "on battery", "desktop": "desktop", "unknown": "power unknown"}[pwr]
    return slot, f"{where} -> {slot}"


def resolve(cfg, force=None):
    """Pick the provider, skipping an unconfigured slot in auto mode.

    Returns (slot, name, entry, reason).
    """
    slot, reason = route_info(cfg, force)
    name, entry = _slot_entry(cfg, slot)
    mode = force or cfg["routing"].get("mode", "auto")

    if mode == "auto" and not is_configured(entry):
        o = other_slot(slot)
        oname, oentry = _slot_entry(cfg, o)
        if is_configured(oentry):
            return (o, oname, oentry,
                    f"{reason}; slot '{slot}' -> '{name}' is not configured, using '{o}' -> '{oname}'")
    return slot, name, entry, reason


def pick_provider(cfg, force=None):
    """Resolve to a usable Provider, or raise a precise configuration error."""
    slot, name, entry, reason = resolve(cfg, force=force)

    if not entry:
        raise LLMError("No provider configured. Open Leech Doctor: Preferences.")
    if not is_configured(entry):
        need = "a base_url"
        if entry.get("kind") == "anthropic":
            need += " and an API key"
        raise LLMError(
            f"The '{slot}' slot points to '{name}', which is not ready (needs {need}).\n"
            f"Open Preferences → Routing to point the '{slot}' slot at a configured provider, "
            f"or fill in '{name}' on the Providers tab."
        )

    provider = make_provider(entry)

    mode = force or cfg["routing"].get("mode", "auto")
    timeout = cfg["routing"].get("probe_timeout_s", 1.5)
    if mode == "auto" and provider.base_url and not probe(provider.base_url, timeout, provider.api_key):
        for fb in (cfg["routing"].get("fallback"), other_slot(slot)):
            if not fb or fb == slot:
                continue
            _s, fbname, fbentry, _r = resolve(cfg, fb)
            if is_configured(fbentry):
                reason += f" (unreachable; using {fb} -> {fbname})"
                return make_provider(fbentry), reason
    return provider, reason


def probe(url, timeout=1.5, api_key=None):
    """Best-effort reachability check. True if the host answers at all."""
    if not url:
        return False
    base = url.rstrip("/")
    for target in (f"{base}/models", base):
        try:
            req = urllib.request.Request(target, method="GET")
            req.add_header("User-Agent", DEFAULT_USER_AGENT)
            if api_key:
                req.add_header("Authorization", f"Bearer {api_key}")
            urllib.request.urlopen(req, timeout=timeout)
            return True
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404, 405):   # host is up, just gated
                return True
            continue
        except Exception:
            continue
    return False
