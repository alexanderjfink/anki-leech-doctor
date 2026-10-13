"""Heuristic failure-mode diagnosis + front/back field detection from card templates."""
import re
from .query import strip_html


def template_of(card):
    try:
        t = card.template()
        return t.get("qfmt", ""), t.get("afmt", "")
    except Exception:
        return "", ""


def front_field_names(card, field_names):
    """Which fields appear on the question template."""
    qfmt, _ = template_of(card)
    if not qfmt:
        return []
    found = []
    for name in field_names:
        pat = r"\{\{[^{}]*\b" + re.escape(name) + r"\b[^{}]*\}\}"
        try:
            if re.search(pat, qfmt):
                found.append(name)
        except Exception:
            continue
    return found


def diagnose(card, note, field_names, cfg, front_names=None):
    d = cfg["diagnosis"]
    qfmt, afmt = template_of(card)
    if front_names is None:
        front_names = front_field_names(card, field_names)

    front_text_parts, back_text_parts = [], []
    for i, nm in enumerate(field_names):
        val = note.fields[i] if i < len(note.fields) else ""
        (front_text_parts if nm in front_names else back_text_parts).append(strip_html(val))
    front_text = " ".join(p for p in front_text_parts if p)
    back_text = " ".join(p for p in back_text_parts if p)

    modes = []
    if len(front_text) > d["wordy_front_threshold"]:
        modes.append("wordy front")
    if len(back_text) > d["wall_of_text_threshold"]:
        modes.append("wall of text on answer side")
    if "<img" in qfmt or "<img" in afmt:
        modes.append("image prompt (needs a discriminating cue)")

    empty_support = []
    for nm in d.get("support_fields", []):
        if nm in field_names:
            ix = field_names.index(nm)
            if not strip_html(note.fields[ix]).strip():
                empty_support.append(nm)
    if empty_support:
        modes.append("empty support field: " + ", ".join(empty_support))

    if re.search(r"\b(and|or)\b", front_text) and "," in front_text:
        modes.append("possible multi-response")

    all_text = " ".join(note.fields)
    if re.search(r"'[^']{2,}'", all_text):
        modes.append("arbitrary label (cultivar / quoted name)")

    return {
        "modes": modes,
        "hint": "; ".join(modes) if modes else "no obvious structural problem",
        "front_fields": front_names,
        "empty_support": empty_support,
    }
