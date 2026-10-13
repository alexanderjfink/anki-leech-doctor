"""Theming for Leech Doctor.

Follows the surrounding app so the window matches the rest of Anki — including
add-ons that restyle it (notably Onigiri, which ships its own palette engine).

Resolution order:
  1. ``ui.theme.mode == "custom"``  -> explicit colours from this add-on's config
  2. ``"onigiri"`` / ``"auto"``     -> Onigiri's *live* resolved palette, read from
                                       its config on disk (its own engine decides
                                       light/dark and the active palette)
  3. fallback                       -> Anki's own Qt palette (tracks light/dark)

No Anki/Qt imports at module level, so the colour maths below is unit-testable.
"""
import glob
import json
import os
import re

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# AnkiWeb id of Onigiri; also matched by manifest name below.
ONIGIRI_ADDON_ID = "1011095603"


# --------------------------------------------------------------------- colour
def norm_hex(v):
    """Normalise '#abc' / 'abc' / '#AABBCC' to '#aabbcc', or '' if invalid."""
    m = _HEX_RE.match(str(v or "").strip())
    if not m:
        return ""
    h = m.group(1).lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def rgb(h):
    h = norm_hex(h) or "#000000"
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def mix(a, b, t):
    """Linear blend, t toward b."""
    a, b = norm_hex(a) or "#000000", norm_hex(b) or "#ffffff"
    t = max(0.0, min(1.0, float(t)))
    ar, ag, ab = rgb(a)
    br, bg, bb = rgb(b)
    return "#%02x%02x%02x" % (round(ar + (br - ar) * t),
                              round(ag + (bg - ag) * t),
                              round(ab + (bb - ab) * t))


def luminance(h):
    r, g, b = rgb(h)
    return (r * 299 + g * 587 + b * 114) / 1000.0 / 255.0


def rgba(h, alpha):
    r, g, b = rgb(h)
    return "rgba(%d,%d,%d,%g)" % (r, g, b, alpha)


class Theme:
    def __init__(self, paper="", panel="", ink="", ink_dim="", accent="",
                 border="", dark=False, source="?"):
        self.dark = bool(dark)
        self.source = source
        self.paper = norm_hex(paper) or ("#171717" if self.dark else "#eeeeee")
        self.panel = norm_hex(panel) or mix(self.paper, "#ffffff" if self.dark else "#000000", 0.06)
        self.ink = norm_hex(ink) or ("#e0e0e0" if self.dark else "#212121")
        self.ink_dim = norm_hex(ink_dim) or mix(self.ink, self.paper, 0.45)
        self.accent = norm_hex(accent) or "#0077c8"
        self.border = norm_hex(border) or mix(self.ink, self.paper, 0.75)
        self.danger = "#ff8a8a" if self.dark else "#b3261e"

    # -- helpers ---------------------------------------------------------
    def on(self, bg):
        """Black or white text for maximum contrast on `bg`."""
        return "#000000" if luminance(bg) > 0.55 else "#ffffff"

    def tint(self, color, alpha):
        return rgba(color, alpha)

    def surface(self, alpha=0.55):
        """A subtle raised surface over `paper`."""
        return self.tint(self.panel, alpha) if self.dark else self.tint(self.ink, 0.06)

    def line(self, alpha=0.18):
        return self.tint(self.ink, alpha)

    def describe(self):
        return (f"source: {self.source} · {'dark' if self.dark else 'light'} · "
                f"paper {self.paper} · panel {self.panel} · ink {self.ink} · "
                f"dim {self.ink_dim} · accent {self.accent}")


def build_from_tokens(tokens, dark, source="onigiri", accent_fallback=""):
    """Build a Theme from a CSS-custom-property token map (Onigiri's `colors`)."""
    t = tokens if isinstance(tokens, dict) else {}

    def g(*names, default=""):
        for n in names:
            v = norm_hex(t.get(n))
            if v:
                return v
        return default

    return Theme(
        paper=g("--bg"),
        panel=g("--canvas-inset", "--highlight-bg", "--button-primary-bg"),
        ink=g("--fg", "--font-small-title-color", "--icon-color"),
        ink_dim=g("--fg-subtle", "--icon-color"),
        accent=g("--accent-color", default=norm_hex(accent_fallback)),
        border=g("--border"),
        dark=dark,
        source=source,
    )


# ------------------------------------------------------------------ detection
def _night_mode():
    try:
        from aqt.theme import theme_manager
        nm = getattr(theme_manager, "night_mode", None)
        if isinstance(nm, bool):
            return nm
        get = getattr(theme_manager, "get_night_mode", None)
        if callable(get):
            return bool(get())
    except Exception:
        pass
    return False


def _addons_dir():
    try:
        from aqt import mw
        return mw.addonManager.addonsFolder()
    except Exception:
        return os.path.expanduser("~/Library/Application Support/Anki2/addons21")


def find_onigiri():
    """Locate Onigiri's add-on folder, by id or by manifest name."""
    base = _addons_dir()
    direct = os.path.join(base, ONIGIRI_ADDON_ID)
    if os.path.isdir(direct):
        return direct
    try:
        for d in sorted(glob.glob(os.path.join(base, "*"))):
            mf = os.path.join(d, "manifest.json")
            if not os.path.isfile(mf):
                continue
            try:
                with open(mf, encoding="utf-8") as f:
                    name = str(json.load(f).get("name", "")).lower()
            except Exception:
                continue
            if "onigiri" in name:
                return d
    except Exception:
        pass
    return None


def _profile_name():
    try:
        from aqt import mw
        return mw.pm.name or ""
    except Exception:
        return ""


def read_onigiri():
    """Return a Theme from Onigiri's live config, or None."""
    d = find_onigiri()
    if not d:
        return None

    data = {}
    files = glob.glob(os.path.join(d, "user_files", "settings_*.json"))
    prof = _profile_name()
    chosen = None
    if prof:
        for f in files:
            if prof in os.path.basename(f):
                chosen = f
                break
    if chosen is None and files:
        chosen = sorted(files)[0]
    if chosen:
        try:
            with open(chosen, encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}

    mode = str(data.get("onigiriThemeMode", "system")).lower()
    dark = _night_mode()
    if mode in ("dark", "night", "night_mode"):
        dark = True
    elif mode in ("light", "day", "day_mode"):
        dark = False

    colors = data.get("colors")
    tokens = {}
    if isinstance(colors, dict):
        tokens = colors.get("dark" if dark else "light") or {}

    accent = ""
    try:
        with open(os.path.join(d, "things_theme", "config.json"), encoding="utf-8") as f:
            accent = (json.load(f) or {}).get("accent", "")
    except Exception:
        pass

    if not tokens and not accent:
        return None
    label = data.get("onigiri_ui_theme", "?")
    return build_from_tokens(tokens, dark, source=f"onigiri ({label})",
                             accent_fallback=accent)


def _qt_theme(dark=None):
    from aqt.qt import QApplication, QPalette
    pal = QApplication.palette()

    def c(role):
        try:
            return pal.color(role).name()
        except Exception:
            return ""

    paper = c(QPalette.ColorRole.Window)
    ink = c(QPalette.ColorRole.WindowText)
    if dark is None:
        dark = luminance(paper) < 0.5
    return Theme(
        paper=paper,
        panel=c(QPalette.ColorRole.Base),
        ink=ink,
        ink_dim=mix(ink, paper, 0.45),
        accent=c(QPalette.ColorRole.Highlight),
        border=c(QPalette.ColorRole.Mid),
        dark=dark,
        source="anki palette",
    )


def resolve(cfg):
    """Pick a Theme for the current config. Always returns a usable Theme."""
    ui = (cfg or {}).get("ui", {}) or {}
    th = ui.get("theme", {}) or {}
    mode = str(th.get("mode", "auto")).lower()

    if mode == "custom":
        dark = th.get("dark")
        dark = _night_mode() if dark is None else bool(dark)
        return Theme(th.get("bg", ""), th.get("panel", ""), th.get("fg", ""),
                     th.get("fg_dim", ""), th.get("accent", ""), th.get("border", ""),
                     dark, "custom")

    if mode in ("onigiri", "auto"):
        theme = read_onigiri()
        if theme is not None:
            return theme

    try:
        return _qt_theme()
    except Exception:
        return Theme(dark=_night_mode(), source="fallback")
