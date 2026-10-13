"""Detect power source / machine class for the routing policy (macOS-aware)."""
import platform
import subprocess
import time

_CACHE = {"t": 0.0, "value": None}
_TTL = 10.0  # seconds


def detect_power(force=False):
    """Return 'ac' | 'battery' | 'desktop' | 'unknown'."""
    if not force and _CACHE["value"] is not None and (time.time() - _CACHE["t"]) < _TTL:
        return _CACHE["value"]

    value = _detect_uncached()
    _CACHE["t"] = time.time()
    _CACHE["value"] = value
    return value


def _detect_uncached():
    if platform.system() != "Darwin":
        # Non-mac: assume always-on power unless we can tell otherwise.
        return "desktop"
    try:
        out = subprocess.run(
            ["pmset", "-g", "batt"],
            capture_output=True, text=True, timeout=3,
        ).stdout
    except Exception:
        return "unknown"
    if "InternalBattery" not in out:
        return "desktop"          # desktop Mac: no battery -> treated as AC
    if "AC Power" in out:
        return "ac"
    if "Battery Power" in out:
        return "battery"
    return "unknown"


def is_online(timeout=1.5):
    """Cheap connectivity check (used only to force local when offline)."""
    import socket
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            s = socket.create_connection((host, 53), timeout=timeout)
            s.close()
            return True
        except Exception:
            continue
    return False
