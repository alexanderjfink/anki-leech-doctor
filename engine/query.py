"""Find, score and group struggled cards. Pure-ish: everything takes an Anki `col`."""
import re

DISP_PREFS = ("Text", "Front", "Country", "Botanical Name", "Artist", "Word", "Expression", "Question")


def build_search(min_lapses, include_leeches, include_suspended):
    if include_leeches:
        base = f"(prop:lapses>={int(min_lapses)} or tag:leech)"
    else:
        base = f"prop:lapses>={int(min_lapses)}"
    if not include_suspended:
        base += " -is:suspended"
    return base


def strip_html(s):
    s = s or ""
    s = re.sub(r"\[sound:[^\]]*\]", " ", s)
    s = re.sub(r"<img[^>]*>", "[image]", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&")
           .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'"))
    return re.sub(r"\s+", " ", s).strip()


def note_field_names(note):
    try:
        return [f["name"] for f in note.model()["flds"]]
    except Exception:
        try:
            return list(note.keys())
        except Exception:
            return []


def model_name(note):
    try:
        return note.model()["name"]
    except Exception:
        return ""


def representative_text(note, field_names, front_names=None):
    values = list(note.fields)
    order = []
    if front_names:
        order += [n for n in front_names if n in field_names]
    order += [n for n in DISP_PREFS if n in field_names]
    order += list(field_names)
    seen = set()
    for n in order:
        if n in seen:
            continue
        seen.add(n)
        try:
            t = strip_html(values[field_names.index(n)])
        except Exception:
            t = ""
        if t:
            return t
    return "(empty)"


def collect(col, cfg, limit=None):
    """Return a list of per-card rows for struggled cards, sorted worst-first."""
    f = cfg["filters"]
    q = build_search(f.get("min_lapses", 3), f.get("include_leeches", True), f.get("include_suspended", False))
    cids = col.find_cards(q)
    ceiling = f.get("ease_ceiling")
    rows = []
    for cid in cids:
        try:
            c = col.get_card(cid)
        except Exception:
            continue
        ease = (c.factor or 0) / 1000.0
        if ceiling and ease > float(ceiling):
            continue
        try:
            n = col.get_note(c.nid)
        except Exception:
            continue
        names = note_field_names(n)
        rows.append({
            "cid": cid, "nid": c.nid, "did": c.did,
            "deck": col.decks.name(c.did),
            "model": model_name(n),
            "lapses": c.lapses, "reps": c.reps,
            "fail_rate": (c.lapses / c.reps) if c.reps else 0.0,
            "ease": ease, "ivl": c.ivl, "type": c.type, "queue": c.queue,
            "text": representative_text(n, names),
        })
    rows.sort(key=lambda r: (-r["lapses"], r["ease"], -r["fail_rate"]))
    if limit:
        rows = rows[:limit]
    return rows


def group_notes(rows):
    """Collapse card rows to one entry per note (editing is note-level)."""
    by_nid = {}
    for r in rows:
        e = by_nid.get(r["nid"])
        if e is None:
            e = dict(r)
            e["cards"] = 1
            e["cids"] = [r["cid"]]
            by_nid[r["nid"]] = e
        else:
            e["cards"] += 1
            e["cids"].append(r["cid"])
            e["lapses"] = max(e["lapses"], r["lapses"])
            e["ease"] = min(e["ease"], r["ease"])
    out = list(by_nid.values())
    out.sort(key=lambda e: (-e["lapses"], e["ease"]))
    return out


def group_by_deck(notes):
    decks = {}
    for n in notes:
        decks.setdefault(n["deck"], []).append(n)
    for d in decks:
        decks[d].sort(key=lambda e: (-e["lapses"], e["ease"]))
    return dict(sorted(decks.items(), key=lambda kv: -sum(x["lapses"] for x in kv[1])))
