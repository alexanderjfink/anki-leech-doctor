#!/usr/bin/env python3
"""Build an .ankiaddon package for manual install / AnkiWeb upload.

Usage:
    python3 build.py

Produces leech_doctor-<version>.ankiaddon in the repo root. The archive contains
the add-on files at the top level (manifest.json + __init__.py at the root), which
is what Anki's "Install from file…" and the AnkiWeb add-on uploader expect.
"""
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
EXCLUDE_DIRS = {"__pycache__", ".git", "docs", ".github"}
EXCLUDE_FILES = {
    "meta.json", "revert_log.json", "build.py",
    ".gitignore", "README.md", "CHANGELOG.md", "LICENSE",
}


def main():
    with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    name = manifest.get("package", "addon")
    version = manifest.get("version", "0.0.0")
    out = os.path.join(ROOT, f"{name}-{version}.ankiaddon")

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn in EXCLUDE_FILES or fn.endswith((".ankiaddon", ".pyc")):
                    continue
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.relpath(full, ROOT))

    print(f"built {os.path.basename(out)} ({os.path.getsize(out):,} bytes)")


if __name__ == "__main__":
    main()
