"""Field-text helpers (pure — no Anki/Qt imports, so they are unit-testable)."""
import re


def sanitize_qt_html(h):
    """Convert a Qt `QTextEdit.toHtml()` document back to Anki-style field HTML.

    Qt wraps content in <html><head><style>…<body> and adds <p style="…"> around
    every line. We keep the text, cloze markers, links and <img> tags; drop the
    wrapper, style/class attributes and span/div scaffolding; and turn paragraph
    breaks into <br>.
    """
    if not h:
        return h or ""
    m = re.search(r"<body[^>]*>(.*?)</body>", h, re.S | re.I)
    body = m.group(1) if m else h
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    # drop empty paragraphs (Qt emits these for blank lines)
    body = re.sub(r"<p[^>]*>\s*(?:<br\s*/?>)?\s*</p>", "", body, flags=re.I)
    # paragraph / div boundaries -> <br>
    body = re.sub(r"</p\s*>\s*<p[^>]*>", "<br>", body, flags=re.I)
    body = re.sub(r"</div\s*>\s*<div[^>]*>", "<br>", body, flags=re.I)
    body = re.sub(r"</?(?:p|div)[^>]*>", "", body, flags=re.I)
    # drop Qt scaffolding
    body = re.sub(r"</?span[^>]*>", "", body, flags=re.I)
    body = re.sub(r'\s+(?:style|class|dir|lang)="[^"]*"', "", body)
    body = re.sub(r"<br\s*/?>", "<br>", body, flags=re.I)
    body = body.replace("&nbsp;", " ")
    return body.strip()


def next_cloze_number(text):
    """Next free cloze index for a field (1 if it has none yet)."""
    nums = [int(n) for n in re.findall(r"\{\{c(\d+)::", text or "")]
    return (max(nums) + 1) if nums else 1


def cloze_inner(sel):
    """If `sel` is exactly one cloze deletion, return its inner text, else None."""
    m = re.fullmatch(r"\{\{c\d+::(.*)\}\}", sel or "", re.S)
    return m.group(1) if m else None
