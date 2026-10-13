"""Build a request from a note, call the selected provider, parse a strict-JSON proposal."""
import json
import re

from ..engine.query import strip_html


SYSTEM_PROMPT = (
    "You repair Anki flashcards a learner keeps forgetting. You receive one note's "
    "fields, which fields show on the question, and the learner's performance. "
    "Reply with ONLY minified JSON, no prose, shaped exactly like:\n"
    '{"failure_mode":"no_discriminator|wordy_front|wall_of_text|ambiguous|shallow|other",'
    '"rationale":"one short sentence",'
    '"edits":[{"field":"<existing field name>","new_value":"<full new value>","reason":"short"}]}\n'
    "Rules:\n"
    "- Only edit existing fields; never invent fields or change the note type.\n"
    "- Make the SMALLEST change that makes the answer derivable from the question.\n"
    "- Preserve cloze syntax {{c1::...}} exactly when present.\n"
    "- Keep carried-over facts intact; never delete source URLs.\n"
    "- Put a discriminating cue in an existing supporting field or cloze hint.\n"
    "- If the card is already fine, return edits: []."
)


def build_request_text(note, field_names, front_names, deck, metrics, diag):
    fields = []
    for i, nm in enumerate(field_names):
        val = note.fields[i] if i < len(note.fields) else ""
        fields.append({
            "name": nm,
            "value": strip_html(val)[:1500],
            "on_front": nm in front_names,
        })
    obj = {
        "deck": deck,
        "note_type": _model_name(note),
        "fields": fields,
        "performance": metrics,
        "diagnosis_hint": diag.get("hint", ""),
    }
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _model_name(note):
    try:
        return note.model()["name"]
    except Exception:
        return ""


def extract_json(text):
    if not text or not text.strip():
        raise ValueError("empty model response")
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        s, e = t.find("{"), t.rfind("}")
        if s != -1 and e != -1 and e > s:
            t = t[s:e + 1]
    return json.loads(t)


def validate_edits(field_names, edits):
    out = []
    for e in edits or []:
        if not isinstance(e, dict):
            continue
        f = e.get("field")
        v = e.get("new_value")
        if f in field_names and isinstance(v, str):
            out.append({"field": f, "new_value": v, "reason": e.get("reason", "")})
    return out


def generate(note, field_names, front_names, deck, metrics, diag, cfg, provider):
    """Return {"failure_mode","rationale","edits","raw"}. Raises LLMError on transport failure."""
    g = cfg["generation"]
    user = build_request_text(note, field_names, front_names, deck, metrics, diag)
    raw = provider.chat(
        SYSTEM_PROMPT, user,
        temperature=g.get("temperature", 0.2),
        max_tokens=g.get("max_tokens", 1200),
        timeout=g.get("timeout_s", 90),
    )
    data = extract_json(raw)
    edits = validate_edits(field_names, data.get("edits", []))
    return {
        "failure_mode": data.get("failure_mode", "other"),
        "rationale": data.get("rationale", ""),
        "edits": edits,
        "raw": raw,
    }
