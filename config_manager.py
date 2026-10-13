"""Config loading with deep-merge defaults so missing keys never crash the add-on."""
import json
import os

ADDON_PACKAGE = "leech_doctor"
_DEFAULTS = None


def _defaults():
    global _DEFAULTS
    if _DEFAULTS is None:
        try:
            with open(os.path.join(os.path.dirname(__file__), "config.json")) as f:
                _DEFAULTS = json.load(f)
        except Exception:
            _DEFAULTS = {}
    return _DEFAULTS


def _deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get_config():
    from aqt import mw
    user = {}
    try:
        user = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    except Exception:
        user = {}
    return _deep_merge(_defaults(), user)


def write_config(cfg):
    from aqt import mw
    mw.addonManager.writeConfig(ADDON_PACKAGE, cfg)
