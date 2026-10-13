"""Leech Doctor main window: rank struggled notes, propose LLM repairs, edit ANY field, apply safely."""
import html
import os
import re

from aqt.qt import *
from aqt import mw
from aqt.utils import showInfo

from ..config_manager import get_config, write_config
from ..engine import query as Q
from ..engine import diagnose as D
from ..engine import apply as A
from ..engine.text import sanitize_qt_html, next_cloze_number, cloze_inner
from ..proposals import generate as G
from ..providers import pick_provider, route_info, resolve, is_configured, LLMError

PROV_MODES = ["Auto", "Local", "Cloud"]


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
        else:
            ch = item.layout()
            if ch is not None:
                _clear_layout(ch)


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


class _AutoHeight:
    """Mixin: grow a text/document widget to fit its content, scroll past `cap` px."""

    def _init_auto(self, cap):
        self._cap = int(cap)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(3)
        self.document().contentsChanged.connect(self._adjust)
        self._adjust()
        # the true wrap width isn't known until layout/show — re-measure once settled
        QTimer.singleShot(0, self._adjust)

    def _adjust(self):
        w = self.viewport().width() or self.width()
        if w <= 0:
            return                          # not laid out yet; keep current height
        doc = self.document()
        doc.setTextWidth(w)
        try:
            content_h = int(doc.documentLayout().documentSize().height())
        except Exception:
            content_h = int(doc.size().height())
        line = self.fontMetrics().height() + 10
        h = min(max(content_h + 10, line), self._cap)
        if h != self.height():
            self.setFixedHeight(h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._adjust()

    def showEvent(self, e):
        super().showEvent(e)
        self._adjust()

    def set_cap(self, cap):
        self._cap = int(cap)
        self._adjust()


class AutoTextEdit(_AutoHeight, QPlainTextEdit):
    """Raw HTML/text editor that auto-sizes."""

    def __init__(self, cap=140, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._init_auto(cap)


class AutoRichEdit(_AutoHeight, QTextEdit):
    """Rich-text editor that auto-sizes (WYSIWYG; use only for touched fields)."""

    def __init__(self, cap=200, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self._init_auto(cap)


class FieldPreview(QTextBrowser):
    """Read-only renderer that resolves Anki media (e.g. <img src="ug-map-niue.png">)."""

    def __init__(self, media_dir=None, cap=220, parent=None):
        super().__init__(parent)
        self._cap = int(cap)
        if media_dir:
            self.setSearchPaths([media_dir])
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._adjust()

    def set_html(self, text):
        self.setHtml(text or "")
        self._adjust()

    def _adjust(self):
        doc = self.document()
        doc.setDocumentMargin(4)
        w = self.viewport().width() or self.width()
        if w > 0:
            doc.setTextWidth(w)
        h = int(doc.size().height()) + 10
        h = min(max(h, 20), self._cap)
        if h != self.height():
            self.setFixedHeight(h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._adjust()


class LeechDoctorDialog(QDialog):
    def __init__(self, parent, preselect_nids=None):
        super().__init__(parent)
        self.setWindowTitle("Leech Doctor")
        self.setMinimumSize(680, 460)
        self.cfg = get_config()
        self._night = _night_mode()
        self._amber_text = "#FFD966" if self._night else "#7A5B00"
        self._red_text = "#FF9A9A" if self._night else "#B00020"
        self.rows = []
        self.notes = []
        self.proposals = {}
        self.current = None
        self.editors = {}
        self.rich_editors = {}
        self.proposed_fields = set()
        self.rich_mode = False
        self.previews = {}
        self.originals = {}
        self._shortcuts = []
        self._loading = False
        try:
            self.media_dir = mw.col.media.dir()
        except Exception:
            self.media_dir = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._refresh_previews)
        self._build_ui()
        self._reload()
        self._update_status()
        self._fit_to_screen()

    # ------------------------------------------------ keep the window on screen
    def _fit_to_screen(self, want_w=1200, want_h=820):
        scr = None
        try:
            if self.parent() is not None:
                scr = self.parent().screen()
        except Exception:
            scr = None
        if scr is None:
            try:
                scr = QApplication.screenAt(QCursor.pos())
            except Exception:
                scr = None
        if scr is None:
            scr = QApplication.primaryScreen()
        geo = scr.availableGeometry()
        w = max(self.minimumWidth(), min(want_w, int(geo.width() * 0.92)))
        h = max(self.minimumHeight(), min(want_h, int(geo.height() * 0.92)))
        self.resize(w, h)
        self.move(geo.x() + (geo.width() - w) // 2, geo.y() + (geo.height() - h) // 2)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Deck:"))
        self.deck_combo = QComboBox()
        self.deck_combo.currentIndexChanged.connect(self._populate_tree)
        bar.addWidget(self.deck_combo, 1)

        bar.addWidget(QLabel("Sort:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Longest struggle", "Fail rate", "Lowest ease", "Longest interval"])
        self.sort_combo.currentIndexChanged.connect(self._populate_tree)
        bar.addWidget(self.sort_combo)

        bar.addWidget(QLabel("min lapses:"))
        self.lapses_spin = QSpinBox()
        self.lapses_spin.setRange(1, 200)
        self.lapses_spin.setValue(int(self.cfg["filters"].get("min_lapses", 3)))
        self.lapses_spin.valueChanged.connect(self._reload)
        bar.addWidget(self.lapses_spin)

        self.leech_chk = QCheckBox("leeches only")
        self.leech_chk.stateChanged.connect(self._populate_tree)
        bar.addWidget(self.leech_chk)

        self.preview_chk = QCheckBox("previews")
        self.preview_chk.setChecked(True)
        self.preview_chk.setToolTip("Render HTML/images in fields below the raw editor")
        self.preview_chk.stateChanged.connect(self._rerender_current)
        bar.addWidget(self.preview_chk)

        self.rich_chk = QCheckBox("rich edit")
        self.rich_chk.setChecked(bool(self.cfg.get("ui", {}).get("rich_edit", False)))
        self.rich_chk.setToolTip("Edit fields as rich text (bold/italic/images). Only fields you "
                                 "actually change are rewritten, and Qt's markup is stripped back "
                                 "to Anki-style HTML. Best for prose fields.")
        self.rich_chk.stateChanged.connect(self._rerender_current)
        bar.addWidget(self.rich_chk)

        bar.addWidget(QLabel("field height:"))
        self.fh_spin = QSpinBox()
        self.fh_spin.setRange(40, 5000)
        self.fh_spin.setSingleStep(20)
        self.fh_spin.setValue(int(self.cfg.get("ui", {}).get("field_max_height", 260)))
        self.fh_spin.setToolTip("Max height (px) of each field box before it scrolls internally. "
                                "Set high (e.g. 2000) to always fit the whole text.")
        self.fh_spin.valueChanged.connect(self._on_field_height)
        bar.addWidget(self.fh_spin)

        bar.addWidget(QLabel("Provider:"))
        self.prov_combo = QComboBox()
        self.prov_combo.addItems(PROV_MODES)
        self.prov_combo.currentIndexChanged.connect(self._update_status)
        bar.addWidget(self.prov_combo)

        self.rebuild_btn = QPushButton("Rebuild")
        self.rebuild_btn.clicked.connect(self._reload)
        bar.addWidget(self.rebuild_btn)
        root.addLayout(bar)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Struggled cards", "lapses"])
        self.tree.setColumnWidth(0, 300)
        self.tree.itemSelectionChanged.connect(self._on_select)
        split.addWidget(self.tree)

        right = QWidget()
        right_outer = QVBoxLayout(right)
        right_outer.setContentsMargins(0, 0, 0, 0)
        self.fields_scroll = QScrollArea()
        self.fields_scroll.setWidgetResizable(True)
        self.fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.fields_host = QWidget()
        self.right_layout = QVBoxLayout(self.fields_host)
        self.fields_scroll.setWidget(self.fields_host)
        right_outer.addWidget(self.fields_scroll)
        split.addWidget(right)

        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([340, 760])
        root.addWidget(split, 1)

        btns = QHBoxLayout()
        self.gen_btn = QPushButton("Generate proposal")
        self.gen_btn.clicked.connect(self._on_generate)
        self.gen_deck_btn = QPushButton("Generate for deck")
        self.gen_deck_btn.clicked.connect(self._on_generate_deck)
        self.reload_btn = QPushButton("Reload fields")
        self.reload_btn.clicked.connect(self._reload_fields)
        self.apply_card_btn = QPushButton("Apply card")
        self.apply_card_btn.clicked.connect(self._apply_current)
        self.apply_deck_btn = QPushButton("Apply deck")
        self.apply_deck_btn.clicked.connect(self._apply_deck)
        self.apply_all_btn = QPushButton("Apply all")
        self.apply_all_btn.clicked.connect(self._apply_all)
        self.revert_btn = QPushButton("Revert last")
        self.revert_btn.clicked.connect(self._revert_last)
        self.revert_all_btn = QPushButton("Revert all")
        self.revert_all_btn.clicked.connect(self._revert_all)
        for b in (self.gen_btn, self.gen_deck_btn, self.reload_btn, self.apply_card_btn,
                  self.apply_deck_btn, self.apply_all_btn, self.revert_btn, self.revert_all_btn):
            btns.addWidget(b)
        root.addLayout(btns)

        self._placeholder()

    # -------------------------------------------------------------- helpers
    def _force(self):
        i = self.prov_combo.currentIndex()
        return {0: None, 1: "local", 2: "cloud"}.get(i)

    def _update_status(self, *_):
        try:
            slot, name, entry, reason = resolve(self.cfg, force=self._force())
            label = (entry or {}).get("label", name or "—")
            model = (entry or {}).get("model") or "no model"
            ready = is_configured(entry)
        except Exception as e:
            slot, label, model, reason, ready = "?", "?", "?", f"routing error: {e}", False
        try:
            log_n = A.log_size()
        except Exception:
            log_n = 0
        warn = "" if ready else " <span style='color:#c00'>· NOT CONFIGURED (Preferences → Routing)</span>"
        self.status.setText(
            f"Provider: <b>{slot}</b> → {label} · {model} — {reason}{warn}"
            f"   ·   revert log: {log_n} change(s)"
        )

    def _current_deck(self):
        return self.deck_combo.currentData()

    def _field_cap(self):
        try:
            return int(self.cfg.get("ui", {}).get("field_max_height", 260))
        except Exception:
            return 260

    def _preview_cap(self):
        try:
            return int(self.cfg.get("ui", {}).get("preview_max_height", 220))
        except Exception:
            return 220

    def _on_field_height(self, *_):
        val = int(self.fh_spin.value())
        try:
            self.cfg.setdefault("ui", {})["field_max_height"] = val
            write_config(self.cfg)
        except Exception:
            pass
        for ed in list(self.editors.values()):     # live re-size, no full re-render
            try:
                ed.set_cap(val)
            except Exception:
                pass

    def _stat_chip(self, value, caption, tooltip, accent=False):
        w = QWidget()
        w.setObjectName("statChip")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(0)
        big = QLabel(str(value))
        f = big.font(); f.setPointSize(f.pointSize() + 6); f.setBold(True)
        big.setFont(f)
        big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if accent:
            big.setStyleSheet(f"color: {self._red_text};")
        cap = QLabel(caption)
        cf = cap.font(); cf.setPointSize(max(8, cf.pointSize() - 1))
        cap.setFont(cf)
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setStyleSheet("color: gray;")
        lay.addWidget(big)
        lay.addWidget(cap)
        w.setStyleSheet(
            "#statChip { background-color: rgba(128,128,128,30); "
            "border: 1px solid rgba(128,128,128,70); border-radius: 6px; }"
        )
        if accent:
            w.setStyleSheet(
                "#statChip { background-color: rgba(220,80,80,45); "
                "border: 1px solid rgba(220,80,80,140); border-radius: 6px; }"
            )
        w.setToolTip(tooltip)
        return w

    # -------------------------------------------------------------- loading
    def _reload(self, *_):
        self.cfg = get_config()
        self.cfg["filters"]["min_lapses"] = int(self.lapses_spin.value())
        self._loading = True
        try:
            self.rows = Q.collect(mw.col, self.cfg)
        except Exception as e:
            showInfo(f"Failed to read collection: {e}")
            self.rows = []
        self.notes = Q.group_notes(self.rows)

        self.deck_combo.blockSignals(True)
        prev = self.deck_combo.currentData()
        self.deck_combo.clear()
        self.deck_combo.addItem("All decks", None)
        for deck in Q.group_by_deck(self.notes).keys():
            self.deck_combo.addItem(deck, deck)
        idx = self.deck_combo.findData(prev)
        self.deck_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.deck_combo.blockSignals(False)

        self._loading = False
        self._populate_tree()
        self._update_status()

    def _sorted_notes(self):
        notes = list(self.notes)
        deck = self._current_deck()
        if deck:
            notes = [n for n in notes if n["deck"] == deck]
        if self.leech_chk.isChecked():
            notes = [n for n in notes if n["lapses"] >= 1]
        key = self.sort_combo.currentIndex()
        if key == 0:
            notes.sort(key=lambda n: (-n["lapses"], n["ease"]))
        elif key == 1:
            notes.sort(key=lambda n: (-n["fail_rate"], -n["lapses"]))
        elif key == 2:
            notes.sort(key=lambda n: (n["ease"], -n["lapses"]))
        elif key == 3:
            notes.sort(key=lambda n: (-n["ivl"], -n["lapses"]))
        return notes

    def _populate_tree(self, *_):
        if self._loading:
            return
        self._loading = True
        self.tree.clear()
        notes = self._sorted_notes()
        if self._current_deck():
            for n in notes[:500]:
                it = QTreeWidgetItem([f"{n['text'][:80]}", str(n['lapses'])])
                it.setData(0, Qt.ItemDataRole.UserRole, n["nid"])
                self.tree.addTopLevelItem(it)
        else:
            decks = {}
            for n in notes:
                decks.setdefault(n["deck"], []).append(n)
            for deck, items in sorted(decks.items(), key=lambda kv: -sum(x["lapses"] for x in kv[1])):
                top = QTreeWidgetItem([f"{deck}  ({len(items)})", str(sum(x["lapses"] for x in items))])
                top.setData(0, Qt.ItemDataRole.UserRole, None)
                self.tree.addTopLevelItem(top)
                for n in items[:80]:
                    ch = QTreeWidgetItem([f"{n['text'][:70]}", str(n['lapses'])])
                    ch.setData(0, Qt.ItemDataRole.UserRole, n["nid"])
                    top.addChild(ch)
                top.setExpanded(True)
        self._loading = False

    def _note_by_nid(self, nid):
        for n in self.notes:
            if n["nid"] == nid:
                return n
        return None

    # --------------------------------------------------------------- editor
    def _placeholder(self, msg="Select a card on the left, then Generate proposal "
                               "(or just edit its fields and Apply card)."):
        _clear_layout(self.right_layout)
        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        self.right_layout.addWidget(lbl)
        self.right_layout.addStretch(1)

    def _rerender_current(self, *_):
        if self.current:
            self._render_note(self.current)

    def _on_select(self, *_):
        if self._loading:
            return
        items = self.tree.selectedItems()
        if not items:
            return
        nid = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not nid:
            return
        entry = self._note_by_nid(nid)
        if entry:
            self.current = entry
            self._render_note(entry)

    def _render_note(self, entry):
        _clear_layout(self.right_layout)
        self.editors = {}
        self.rich_editors = {}
        self.previews = {}
        self.originals = {}
        self._shortcuts = []

        note = mw.col.get_note(entry["nid"])
        field_names = Q.note_field_names(note)
        card = mw.col.get_card(entry["cids"][0])
        front_names = D.front_field_names(card, field_names)
        diag = D.diagnose(card, note, field_names, self.cfg, front_names)
        prop = self.proposals.get(entry["nid"])

        is_cloze = False
        try:
            is_cloze = int(note.model()["type"]) == 1
        except Exception:
            try:
                is_cloze = int(note.model().get("type", 0)) == 1
            except Exception:
                is_cloze = False

        hdr = QLabel(f"<b>{entry['text'][:120]}</b>")
        hdr.setWordWrap(True)
        self.right_layout.addWidget(hdr)

        meta = QLabel(f"{entry['deck']} · note {entry['nid']} · affects {entry['cards']} card(s)")
        meta.setTextFormat(Qt.TextFormat.RichText)
        meta.setStyleSheet("color: gray;")
        self.right_layout.addWidget(meta)

        # ---- stats ---------------------------------------------------------
        stats = QHBoxLayout()
        stats.setSpacing(6)
        stats.addWidget(self._stat_chip(
            entry["lapses"], "lapses",
            "Times you forgot this card after learning it (answered Again). The main struggle signal.",
            accent=True))
        stats.addWidget(self._stat_chip(
            entry["reps"], "reps", "Total number of reviews of this card."))
        stats.addWidget(self._stat_chip(
            f"{int(entry['fail_rate'] * 100)}%", "fail %", "lapses ÷ reps — how often you forget it."))
        stats.addWidget(self._stat_chip(
            f"{entry['ease']:.2f}", "ease", "Anki's ease factor. 1.30 is the floor (hardest)."))
        stats.addWidget(self._stat_chip(
            f"{entry['ivl']}d", "interval", "Current interval, in days."))
        stats.addStretch(1)
        self.right_layout.addLayout(stats)

        explainer = QLabel("<span style='color:gray'>lapses = forgotten after learning · "
                           "reps = total reviews · fail % = lapses ÷ reps</span>")
        explainer.setTextFormat(Qt.TextFormat.RichText)
        self.right_layout.addWidget(explainer)

        # ---- diagnosis (highlighted) --------------------------------------
        banner = QLabel(f"<b>⚠ Diagnosis</b> &nbsp; {html.escape(diag['hint'])}")
        banner.setObjectName("diagBanner")
        banner.setWordWrap(True)
        banner.setTextFormat(Qt.TextFormat.RichText)
        bf = banner.font(); bf.setBold(True); banner.setFont(bf)
        banner.setStyleSheet(
            "#diagBanner { background-color: rgba(224,168,0,55); "
            "border: 1px solid rgba(224,168,0,150); border-left: 5px solid rgba(232,168,0,230); "
            f"border-radius: 6px; padding: 8px; color: {self._amber_text}; }}"
        )
        self.right_layout.addWidget(banner)

        if prop:
            rat = QLabel(f"<b>{html.escape(prop.get('failure_mode', '?'))}</b> — {html.escape(prop.get('rationale', ''))}")
            rat.setTextFormat(Qt.TextFormat.RichText)
            rat.setWordWrap(True)
            self.right_layout.addWidget(rat)

        use_rich = self.rich_chk.isChecked()
        self.rich_mode = use_rich
        if use_rich:
            hint_txt = ("Rich edit is ON — fields render as formatted text. Only fields you change "
                        "(or that carry an LLM proposal) are written back, and Qt's markup is "
                        "normalised to Anki-style HTML.")
        else:
            hint_txt = ("Fields show raw content (HTML, cloze and hints preserved). "
                        "<span style='color:#0a0'>Green labels</span> were filled from the LLM proposal.")
        hint = QLabel(hint_txt)
        hint.setWordWrap(True)
        self.right_layout.addWidget(hint)

        # ---- fields --------------------------------------------------------
        edits_by_field = {e["field"]: e for e in (prop["edits"] if prop else [])}
        self.proposed_fields = set(edits_by_field.keys())
        show_prev = self.preview_chk.isChecked() and not use_rich

        box = QGroupBox("Fields")
        box_lay = QVBoxLayout(box)
        box_lay.setSpacing(2)
        box_lay.setContentsMargins(6, 6, 6, 6)
        for i, nm in enumerate(field_names):
            raw = note.fields[i] if i < len(note.fields) else ""
            self.originals[nm] = raw
            proposed = edits_by_field.get(nm)
            value = proposed["new_value"] if proposed else raw

            flags = []
            if nm in front_names:
                flags.append("front")
            if proposed:
                flags.append("<span style='color:#0a0'>LLM proposed</span>")
            lbl = QLabel(f"<b>{nm}</b>" + (f"  ({' · '.join(flags)})" if flags else ""))
            lbl.setTextFormat(Qt.TextFormat.RichText)

            if use_rich:
                ed = AutoRichEdit(cap=self._field_cap())
                ed.setHtml(value)
                ed.document().setModified(False)
                self.rich_editors[nm] = ed
            else:
                ed = AutoTextEdit(cap=self._field_cap())
                ed.setPlainText(value)
                ed.textChanged.connect(self._schedule_preview_refresh)
            self.editors[nm] = ed
            self._add_shortcuts(ed, use_rich, is_cloze)

            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            head.setSpacing(2)
            head.addWidget(lbl)
            head.addStretch(1)
            for sym, tag in (("B", "b"), ("I", "i"), ("U", "u")):
                head.addWidget(self._fmt_button(sym, tag, ed))
            if is_cloze:
                head.addWidget(self._cloze_button(ed))
            box_lay.addLayout(head)
            box_lay.addWidget(ed)

            if show_prev and re.search(r"<[a-zA-Z/]", raw):
                pv = FieldPreview(media_dir=self.media_dir, cap=self._preview_cap())
                pv.set_html(value)
                self.previews[nm] = pv
                box_lay.addWidget(pv)
        self.right_layout.addWidget(box)
        self.right_layout.addStretch(1)

        self._refresh_previews()

    def _reload_fields(self):
        if self.current:
            self._render_note(self.current)

    # ------------------------------------------------------- inline formatting
    @staticmethod
    def _seq_text(seq):
        try:
            return QKeySequence(seq).toString(QKeySequence.SequenceFormat.NativeText)
        except Exception:
            return seq

    def _add_shortcuts(self, ed, use_rich, is_cloze):
        """⌘/Ctrl+B/I/U per field, plus ⌘⇧C for cloze. QTextEdit already implements
        B/I/U natively for rich text, so we only bind our own on raw editors."""
        bindings = []
        if not use_rich:
            bindings += [("Ctrl+B", lambda e=ed: self._apply_format(e, "b")),
                         ("Ctrl+I", lambda e=ed: self._apply_format(e, "i")),
                         ("Ctrl+U", lambda e=ed: self._apply_format(e, "u"))]
        if is_cloze:
            bindings.append(("Ctrl+Shift+C", lambda e=ed: self._toggle_cloze(e)))
        for seq, fn in bindings:
            try:
                sc = QShortcut(QKeySequence(seq), ed)
                sc.setContext(Qt.ShortcutContext.WidgetShortcut)
                sc.activated.connect(fn)
                self._shortcuts.append(sc)
            except Exception:
                pass

    def _fmt_button(self, sym, tag, editor):
        names = {"b": "Bold", "i": "Italic", "u": "Underline"}
        seqs = {"b": "Ctrl+B", "i": "Ctrl+I", "u": "Ctrl+U"}
        b = QToolButton()
        b.setText(sym)
        f = b.font()
        f.setBold(sym == "B")
        f.setItalic(sym == "I")
        f.setUnderline(sym == "U")
        b.setFont(f)
        b.setAutoRaise(True)
        b.setFixedSize(26, 22)
        b.setToolTip(f"{names.get(tag, tag)} ({self._seq_text(seqs.get(tag, ''))}) — "
                     f"wraps the selection in <{tag}>…</{tag}>")
        b.clicked.connect(lambda _=False, e=editor, t=tag: self._apply_format(e, t))
        return b

    def _cloze_button(self, editor):
        b = QToolButton()
        b.setText("{{c}}")
        b.setAutoRaise(True)
        b.setMinimumHeight(22)
        b.setToolTip(f"Cloze deletion ({self._seq_text('Ctrl+Shift+C')}) — wraps the selection in "
                     f"{{{{c1::…}}}} using the next free number")
        b.clicked.connect(lambda _=False, e=editor: self._toggle_cloze(e))
        return b

    @staticmethod
    def _toggle_cloze(ed):
        cur = ed.textCursor()
        if not cur.hasSelection():
            open_t, close_t = "{{c%d::" % next_cloze_number(ed.toPlainText()), "}}"
            pos = cur.position()
            cur.insertText(open_t + close_t)
            cur.setPosition(pos + len(open_t))
            ed.setTextCursor(cur)
            return
        start, end = cur.selectionStart(), cur.selectionEnd()
        sel = ed.toPlainText()[start:end]
        inner = cloze_inner(sel)
        if inner is not None:
            new, off = inner, 0
        else:
            inner = sel
            open_t, close_t = "{{c%d::" % next_cloze_number(ed.toPlainText()), "}}"
            new, off = open_t + sel + close_t, len(open_t)
        cur.beginEditBlock()
        cur.setPosition(start)
        cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(new)
        cur.endEditBlock()
        cur.setPosition(start + off)
        cur.setPosition(start + off + len(inner), QTextCursor.MoveMode.KeepAnchor)
        ed.setTextCursor(cur)

    def _apply_format(self, editor, tag):
        try:
            if isinstance(editor, QTextEdit):        # rich mode: real character formatting
                fmt = QTextCharFormat()
                cur = editor.currentCharFormat()
                if tag == "b":
                    on = int(cur.fontWeight()) >= 600
                    fmt.setFontWeight(QFont.Weight.Normal if on else QFont.Weight.Bold)
                elif tag == "i":
                    fmt.setFontItalic(not cur.fontItalic())
                elif tag == "u":
                    fmt.setFontUnderline(not cur.fontUnderline())
                editor.mergeCurrentCharFormat(fmt)
            else:                                    # raw mode: wrap/unwrap HTML tags
                self._toggle_tag(editor, tag)
            editor.setFocus()
        except Exception:
            pass

    @staticmethod
    def _toggle_tag(ed, tag):
        open_t, close_t = f"<{tag}>", f"</{tag}>"
        cur = ed.textCursor()
        if not cur.hasSelection():
            pos = cur.position()
            cur.insertText(open_t + close_t)
            cur.setPosition(pos + len(open_t))
            ed.setTextCursor(cur)
            return
        start, end = cur.selectionStart(), cur.selectionEnd()
        sel = ed.toPlainText()[start:end]
        if sel.startswith(open_t) and sel.endswith(close_t) and len(sel) >= len(open_t) + len(close_t):
            inner = sel[len(open_t):len(sel) - len(close_t)]
            new, off = inner, 0
        else:
            inner = sel
            new, off = open_t + sel + close_t, len(open_t)
        cur.beginEditBlock()
        cur.setPosition(start)
        cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(new)
        cur.endEditBlock()
        cur.setPosition(start + off)
        cur.setPosition(start + off + len(inner), QTextCursor.MoveMode.KeepAnchor)
        ed.setTextCursor(cur)

    # ------------------------------------------------------------- previews
    def _schedule_preview_refresh(self):
        self._preview_timer.start(250)

    def _refresh_previews(self):
        for nm, pv in self.previews.items():
            ed = self.editors.get(nm)
            if ed is not None:
                pv.set_html(ed.toPlainText())

    # ------------------------------------------------------------- generate
    def _generate_for(self, entry):
        note = mw.col.get_note(entry["nid"])
        field_names = Q.note_field_names(note)
        card = mw.col.get_card(entry["cids"][0])
        front_names = D.front_field_names(card, field_names)
        diag = D.diagnose(card, note, field_names, self.cfg, front_names)
        metrics = {"lapses": entry["lapses"], "reps": entry["reps"],
                   "fail_rate": round(entry["fail_rate"], 3),
                   "ease": round(entry["ease"], 2), "interval": entry["ivl"]}
        provider, reason = pick_provider(self.cfg, force=self._force())
        prop = G.generate(note, field_names, front_names, entry["deck"], metrics, diag, self.cfg, provider)
        prop["_provider"] = provider.label
        self.proposals[entry["nid"]] = prop
        return prop

    def _on_generate(self):
        if not self.current:
            showInfo("Select a card first.")
            return
        self.gen_btn.setEnabled(False)
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._generate_for(self.current)
        except LLMError as e:
            showInfo(f"Provider error:\n{e}")
            return
        except Exception as e:
            showInfo(f"Generation failed:\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.gen_btn.setEnabled(True)
        self._render_note(self.current)

    def _on_generate_deck(self):
        targets = self._sorted_notes()
        cap = int(self.cfg["generation"].get("max_cards_per_batch", 50))
        targets = targets[:cap]
        if not targets:
            showInfo("Nothing to generate for.")
            return
        prog = QProgressDialog("Generating proposals…", "Cancel", 0, len(targets), self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        errors = 0
        for i, entry in enumerate(targets):
            if prog.wasCanceled():
                break
            prog.setValue(i)
            prog.setLabelText(f"{i+1}/{len(targets)}: {entry['text'][:50]}")
            QApplication.processEvents()
            try:
                self._generate_for(entry)
            except Exception:
                errors += 1
        prog.setValue(len(targets))
        self._update_status()
        if self.current:
            self._render_note(self.current)
        showInfo(f"Generated {len(targets) - errors}/{len(targets)} proposal(s)."
                 + (f" {errors} failed." if errors else ""))

    # ---------------------------------------------------------------- apply
    def _collect_edits(self, entry):
        prop = self.proposals.get(entry["nid"])
        if entry is not self.current or not self.editors:
            if not prop:
                return prop, []
            return prop, [{"field": e["field"], "new_value": e.get("new_value", "")} for e in prop["edits"]]
        edits = []
        if self.rich_mode:
            for nm, ed in self.rich_editors.items():
                if ed.document().isModified() or nm in self.proposed_fields:
                    edits.append({"field": nm, "new_value": sanitize_qt_html(ed.toHtml())})
        else:
            for nm, ed in self.editors.items():
                txt = ed.toPlainText()
                if txt != self.originals.get(nm, ""):
                    edits.append({"field": nm, "new_value": txt})
        return prop, edits

    def _do_apply(self, entries, label):
        over = int(self.cfg["apply"].get("confirm_apply_over", 25))
        if len(entries) > over:
            if QMessageBox.question(
                self, "Confirm apply",
                f"Apply changes to {len(entries)} note(s) in your collection?",
            ) != QMessageBox.StandardButton.Yes:
                return
        applied_notes = applied_fields = 0
        for entry in entries:
            prop, edits = self._collect_edits(entry)
            if not edits:
                continue
            try:
                note = mw.col.get_note(entry["nid"])
                changes = A.apply_edits(mw.col, note, edits,
                                        provider_label=(prop or {}).get("_provider", ""))
                if changes:
                    applied_notes += 1
                    applied_fields += len(changes)
            except Exception:
                continue
        self._update_status()
        if self.current:
            self._render_note(self.current)
        showInfo(f"{label}: applied {applied_fields} field edit(s) across {applied_notes} note(s).\n"
                 f"Scheduling was not touched. Use Revert to undo.")

    def _apply_current(self):
        if not self.current:
            showInfo("Select a card first.")
            return
        self._do_apply([self.current], "Apply card")

    def _apply_deck(self):
        deck = self._current_deck()
        entries = [n for n in self.notes if (not deck or n["deck"] == deck)
                   and (n["nid"] in self.proposals or n is self.current)]
        if not entries:
            showInfo("No generated proposals in scope. Generate first.")
            return
        self._do_apply(entries, f"Apply deck ({deck or 'all'})")

    def _apply_all(self):
        entries = [n for n in self.notes if n["nid"] in self.proposals or n is self.current]
        if not entries:
            showInfo("No generated proposals yet.")
            return
        self._do_apply(entries, "Apply all")

    # --------------------------------------------------------------- revert
    def _revert_last(self):
        n, msg = A.revert_last(mw.col)
        self._update_status()
        if self.current:
            self._render_note(self.current)
        showInfo(msg)

    def _revert_all(self):
        if QMessageBox.question(self, "Revert all",
                                "Undo every change this add-on has logged?") != QMessageBox.StandardButton.Yes:
            return
        n, msg = A.revert_all(mw.col)
        self._update_status()
        if self.current:
            self._render_note(self.current)
        showInfo(msg)
