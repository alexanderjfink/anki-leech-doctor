"""Safe, field-only edits with Anki undo attempt + a persistent revert log.

Rule: NEVER change a note's model/type, and NEVER touch ivl/factor/due/queue.
Only note field text is modified, which preserves all scheduling.
"""
import json
import os
import time
from collections import defaultdict

REVERT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "revert_log.json")


def _read_log():
    try:
        with open(REVERT_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _write_log(log):
    try:
        with open(REVERT_FILE, "w") as f:
            json.dump(log, f, indent=1, ensure_ascii=False)
    except Exception:
        pass


def log_size():
    return len(_read_log())


def apply_edits(col, note, edits, provider_label=""):
    """Apply {field,new_value} edits to one note. Returns list of change records."""
    try:
        field_names = [f["name"] for f in note.model()["flds"]]
    except Exception:
        field_names = list(note.keys())

    changes = []
    undo_id = None
    try:
        undo_id = col.add_custom_undo_entry("Leech Doctor")
    except Exception:
        undo_id = None

    for e in edits or []:
        name = e.get("field")
        new = e.get("new_value", "")
        if name not in field_names or not isinstance(new, str):
            continue
        ix = field_names.index(name)
        old = note.fields[ix]
        if old == new:
            continue
        note.fields[ix] = new
        changes.append({"nid": note.id, "field": name, "old": old, "new": new})

    if changes:
        col.update_note(note)

    if undo_id is not None:
        try:
            col.merge_undo_entries(undo_id)
        except Exception:
            pass

    if changes:
        append_changes(changes, provider_label)

    return changes


def append_changes(records, provider_label=""):
    """Record already-made changes (e.g. by Anki's own editor) so Revert can undo them."""
    if not records:
        return
    log = _read_log()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    for c in records:
        log.append({"ts": ts, "provider": provider_label, **c})
    _write_log(log)


def _restore(col, records):
    by_nid = defaultdict(list)
    for r in records:
        by_nid[r["nid"]].append(r)
    restored = 0
    for nid, recs in by_nid.items():
        try:
            note = col.get_note(nid)
        except Exception:
            continue
        try:
            names = [f["name"] for f in note.model()["flds"]]
        except Exception:
            names = list(note.keys())
        changed = False
        for r in recs:
            if r["field"] in names:
                note.fields[names.index(r["field"])] = r["old"]
                changed = True
                restored += 1
        if changed:
            col.update_note(note)
    return restored


def revert_last(col):
    log = _read_log()
    if not log:
        return 0, "revert log is empty"
    last_ts = log[-1]["ts"]
    batch = [c for c in log if c["ts"] == last_ts]
    n = _restore(col, batch)
    _write_log([c for c in log if c["ts"] != last_ts])
    return n, f"reverted {n} field(s) from {last_ts}"


def revert_all(col):
    log = _read_log()
    if not log:
        return 0, "revert log is empty"
    n = _restore(col, log)
    _write_log([])
    return n, f"reverted {n} field(s) across {len(log)} change(s)"
