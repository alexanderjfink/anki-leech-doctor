"""Preferences dialog: providers (with model discovery), routing, generation, filters, apply."""
from aqt.qt import *
from aqt import mw
from aqt.utils import showInfo

from ..config_manager import get_config, write_config
from ..providers import make_provider, pick_provider, LLMError

ROUTE_SLOTS = ["local", "cloud"]


def _grow(form):
    """Make form fields actually expand (macOS default keeps them at size-hint → narrow boxes)."""
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
    return form


def _wide(w, minimum=260):
    w.setMinimumWidth(minimum)
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return w


class PreferencesDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Leech Doctor — Preferences")
        self.setMinimumSize(760, 560)
        self.resize(920, 720)
        self.cfg = get_config()
        self.provider_rows = {}   # key -> dict of widgets
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        cat = self.cfg["providers"]["catalog"]

        tabs.addTab(self._scroll(self._providers_tab(cat)), "Providers")
        tabs.addTab(self._scroll(self._routing_tab(cat)), "Routing")
        tabs.addTab(self._scroll(self._generation_tab()), "Generation")
        tabs.addTab(self._scroll(self._filters_tab()), "Filters & Apply")
        tabs.addTab(self._scroll(self._theme_tab()), "Theme")

        btns = QHBoxLayout()
        test = QPushButton("Test connection")
        test.clicked.connect(self._test)
        btns.addWidget(test)
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        root.addLayout(btns)

    def _scroll(self, widget):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setWidget(widget)
        return sa

    # --------------------------------------------------------- Providers tab
    def _providers_tab(self, cat):
        prov = QWidget()
        pl = QVBoxLayout(prov)

        info = QLabel(
            "Enter a base URL and API key, then click <b>Load models</b> to populate the dropdown "
            "(type a model name directly if the endpoint can't be listed). "
            "Local endpoints usually need no key: Ollama <code>http://localhost:11434/v1</code>, "
            "vLLM / gateway <code>http://localhost:8000/v1</code>."
        )
        info.setWordWrap(True)
        pl.addWidget(info)

        for key, entry in cat.items():
            box = QGroupBox(f"{entry.get('label', key)}   ·   {key}  [{entry.get('kind')}]")
            form = _grow(QFormLayout(box))

            e_url = _wide(QLineEdit(entry.get("base_url", "")), 360)
            form.addRow("base URL", e_url)

            # key + reveal toggle
            key_row = QWidget()
            kh = QHBoxLayout(key_row)
            kh.setContentsMargins(0, 0, 0, 0)
            e_key = _wide(QLineEdit(entry.get("api_key", "")), 300)
            e_key.setEchoMode(QLineEdit.EchoMode.Password)
            reveal = QCheckBox("show")
            def _toggle(state, w=e_key):
                w.setEchoMode(QLineEdit.EchoMode.Normal if state else QLineEdit.EchoMode.Password)
            reveal.stateChanged.connect(_toggle)
            kh.addWidget(e_key, 1)
            kh.addWidget(reveal)
            form.addRow("API key", key_row)

            # model combo + load button
            model_row = QWidget()
            mh = QHBoxLayout(model_row)
            mh.setContentsMargins(0, 0, 0, 0)
            combo = _wide(QComboBox(), 300)
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            if entry.get("model"):
                combo.addItem(entry["model"])
                combo.setCurrentText(entry["model"])
            load = QPushButton("Load models")
            status = QLabel("")
            status.setMinimumWidth(120)
            mh.addWidget(combo, 1)
            mh.addWidget(load)
            form.addRow("model", model_row)
            form.addRow("", status)

            use_row = QWidget()
            uh = QHBoxLayout(use_row)
            uh.setContentsMargins(0, 0, 0, 0)
            b_local = QPushButton("Use as LOCAL slot")
            b_cloud = QPushButton("Use as CLOUD slot")
            b_local.clicked.connect(lambda _, k=key: self._use_slot("local", k))
            b_cloud.clicked.connect(lambda _, k=key: self._use_slot("cloud", k))
            uh.addWidget(b_local); uh.addWidget(b_cloud); uh.addStretch(1)
            form.addRow("routing", use_row)

            self.provider_rows[key] = {
                "kind": entry.get("kind", "openai_compat"),
                "label": entry.get("label", key),
                "url": e_url, "key": e_key, "combo": combo, "status": status,
            }
            load.clicked.connect(self._make_loader(key))
            pl.addWidget(box)

        pl.addStretch(1)
        return prov

    def _make_loader(self, key):
        def go():
            row = self.provider_rows[key]
            provider = make_provider({
                "kind": row["kind"], "label": row["label"],
                "base_url": row["url"].text().strip(),
                "model": row["combo"].currentText().strip(),
                "api_key": row["key"].text().strip(),
            })
            row["status"].setText("loading…")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                models = provider.list_models(timeout=10)
                err = None
            except LLMError as e:
                models, err = [], str(e)
            except Exception as e:
                models, err = [], str(e)
            finally:
                QApplication.restoreOverrideCursor()

            if models:
                cur = row["combo"].currentText().strip()
                row["combo"].clear()
                row["combo"].addItems(models)
                if cur in models:
                    row["combo"].setCurrentText(cur)
                elif not cur:
                    row["combo"].setCurrentText(models[0])
                row["status"].setText(f"<span style='color:#2a2'>{len(models)} models</span>")
            elif err:
                row["status"].setText(f"<span style='color:#c00'>✗ {err[:90]}</span>")
            else:
                row["status"].setText("<span style='color:#888'>no models returned</span>")
        return go

    # ----------------------------------------------------------- Routing tab
    def _routing_tab(self, cat):
        rw = QWidget()
        form = _grow(QFormLayout(rw))

        self.mode_combo = _wide(QComboBox(), 200)
        self.mode_combo.addItems(["auto", "local", "cloud"])
        self.mode_combo.setCurrentText(self.cfg["routing"].get("mode", "auto"))
        form.addRow("mode", self.mode_combo)

        self.slot_local = _wide(QComboBox(), 200)
        self.slot_cloud = _wide(QComboBox(), 200)
        for c in (self.slot_local, self.slot_cloud):
            c.addItems(list(cat.keys()))
        self.slot_local.setCurrentText(self.cfg["providers"]["slots"].get("local", "ollama"))
        self.slot_cloud.setCurrentText(self.cfg["providers"]["slots"].get("cloud", "claude"))
        form.addRow("local slot provider", self.slot_local)
        form.addRow("cloud slot provider", self.slot_cloud)

        self.route_summary = QLabel("")
        self.route_summary.setWordWrap(True)
        form.addRow("current slots", self.route_summary)
        for c in (self.slot_local, self.slot_cloud):
            c.currentIndexChanged.connect(self._refresh_routing_summary)
        self._refresh_routing_summary()

        self.situation = {}
        for k in ("on_ac", "on_battery", "on_desktop", "offline", "fallback"):
            c = _wide(QComboBox(), 200)
            c.addItems(ROUTE_SLOTS)
            c.setCurrentText(self.cfg["routing"].get(k, "local"))
            self.situation[k] = c
            form.addRow(k.replace("_", " "), c)

        note = QLabel("auto → AC:local, battery:cloud, desktop:local, offline:local, "
                      "and falls back when the chosen provider is unreachable. Manual mode overrides.")
        note.setWordWrap(True)
        form.addRow("", note)
        return rw

    # -------------------------------------------------------- Generation tab
    def _generation_tab(self):
        gw = QWidget()
        form = _grow(QFormLayout(gw))
        g = self.cfg["generation"]
        self.temp = _wide(QDoubleSpinBox(), 160)
        self.temp.setRange(0.0, 2.0); self.temp.setSingleStep(0.1)
        self.temp.setValue(float(g.get("temperature", 0.2)))
        self.max_tokens = _wide(QSpinBox(), 160)
        self.max_tokens.setRange(64, 32000); self.max_tokens.setValue(int(g.get("max_tokens", 1200)))
        self.timeout = _wide(QSpinBox(), 160)
        self.timeout.setRange(5, 600); self.timeout.setValue(int(g.get("timeout_s", 90)))
        self.batch = _wide(QSpinBox(), 160)
        self.batch.setRange(1, 1000); self.batch.setValue(int(g.get("max_cards_per_batch", 50)))
        self.conc = _wide(QSpinBox(), 160)
        self.conc.setRange(1, 16); self.conc.setValue(int(g.get("concurrency", 3)))
        form.addRow("temperature", self.temp)
        form.addRow("max_tokens", self.max_tokens)
        form.addRow("timeout (s)", self.timeout)
        form.addRow("max cards per batch", self.batch)
        form.addRow("concurrency", self.conc)
        return gw

    # ----------------------------------------------------- Filters/Apply tab
    def _filters_tab(self):
        fw = QWidget()
        form = _grow(QFormLayout(fw))
        f = self.cfg["filters"]; a = self.cfg["apply"]
        self.min_lapses = _wide(QSpinBox(), 160)
        self.min_lapses.setRange(1, 200); self.min_lapses.setValue(int(f.get("min_lapses", 3)))
        self.inc_leech = QCheckBox(); self.inc_leech.setChecked(bool(f.get("include_leeches", True)))
        self.inc_susp = QCheckBox(); self.inc_susp.setChecked(bool(f.get("include_suspended", False)))
        self.ease_ceil = _wide(QLineEdit("" if f.get("ease_ceiling") in (None, "") else str(f.get("ease_ceiling"))), 160)
        self.confirm_over = _wide(QSpinBox(), 160)
        self.confirm_over.setRange(1, 10000); self.confirm_over.setValue(int(a.get("confirm_apply_over", 25)))
        self.keep_log = QCheckBox(); self.keep_log.setChecked(bool(a.get("keep_revert_log", True)))
        form.addRow("min lapses", self.min_lapses)
        form.addRow("include leeches", self.inc_leech)
        form.addRow("include suspended", self.inc_susp)
        form.addRow("ease ceiling (blank = off)", self.ease_ceil)
        form.addRow("confirm apply over", self.confirm_over)
        form.addRow("keep revert log", self.keep_log)
        return fw

    # -------------------------------------------------------------- gather
    def _gather(self):
        cfg = get_config()
        for key, row in self.provider_rows.items():
            cfg["providers"]["catalog"][key]["base_url"] = row["url"].text().strip()
            cfg["providers"]["catalog"][key]["model"] = row["combo"].currentText().strip()
            cfg["providers"]["catalog"][key]["api_key"] = row["key"].text().strip()
        cfg["providers"]["slots"]["local"] = self.slot_local.currentText()
        cfg["providers"]["slots"]["cloud"] = self.slot_cloud.currentText()
        cfg["routing"]["mode"] = self.mode_combo.currentText()
        for k, c in self.situation.items():
            cfg["routing"][k] = c.currentText()
        cfg["generation"].update({
            "temperature": float(self.temp.value()),
            "max_tokens": int(self.max_tokens.value()),
            "timeout_s": int(self.timeout.value()),
            "max_cards_per_batch": int(self.batch.value()),
            "concurrency": int(self.conc.value()),
        })
        ceil = self.ease_ceil.text().strip()
        cfg["filters"].update({
            "min_lapses": int(self.min_lapses.value()),
            "include_leeches": bool(self.inc_leech.isChecked()),
            "include_suspended": bool(self.inc_susp.isChecked()),
            "ease_ceiling": float(ceil) if ceil else None,
        })
        cfg["apply"].update({
            "confirm_apply_over": int(self.confirm_over.value()),
            "keep_revert_log": bool(self.keep_log.isChecked()),
        })
        dk = self.theme_dark.currentText()
        cfg.setdefault("ui", {})
        cfg["ui"]["theme"] = {
            "mode": self.theme_mode.currentText(),
            "dark": None if dk == "auto" else (dk == "dark"),
            "accent": self.theme_edits["accent"].text().strip(),
            "bg": self.theme_edits["bg"].text().strip(),
            "panel": self.theme_edits["panel"].text().strip(),
            "fg": self.theme_edits["fg"].text().strip(),
            "fg_dim": self.theme_edits["fg_dim"].text().strip(),
            "border": self.theme_edits["border"].text().strip(),
        }
        return cfg

    def _use_slot(self, slot, key):
        combo = self.slot_local if slot == "local" else self.slot_cloud
        combo.setCurrentText(key)
        self._refresh_routing_summary()
        showInfo(f"'{key}' is now the {slot.upper()} slot.\nClick Save to keep it.")

    def _refresh_routing_summary(self, *_):
        if not hasattr(self, "route_summary"):
            return
        cat = self.cfg["providers"]["catalog"]

        def desc(k):
            e = cat.get(k, {})
            url = e.get("base_url") or "(no URL set)"
            return f"{e.get('label', k)} [{url}]"

        self.route_summary.setText(
            f"<b>local</b> → {desc(self.slot_local.currentText())}<br>"
            f"<b>cloud</b> → {desc(self.slot_cloud.currentText())}"
        )

    # ------------------------------------------------------------ Theme tab
    def _theme_tab(self):
        tw = QWidget()
        form = _grow(QFormLayout(tw))
        th = (self.cfg.get("ui", {}) or {}).get("theme", {}) or {}

        self.theme_mode = _wide(QComboBox(), 200)
        self.theme_mode.addItems(["auto", "onigiri", "anki", "custom"])
        self.theme_mode.setCurrentText(str(th.get("mode", "auto")))
        form.addRow("mode", self.theme_mode)

        note = QLabel(
            "<b>auto</b> / <b>onigiri</b> follow Onigiri's active palette when it is installed "
            "(reading its own light/dark choice, else Anki's). <b>anki</b> uses Anki's Qt colours. "
            "<b>custom</b> uses the fields below."
        )
        note.setWordWrap(True)
        form.addRow("", note)

        self.theme_dark = _wide(QComboBox(), 200)
        self.theme_dark.addItems(["auto", "light", "dark"])
        d = th.get("dark")
        self.theme_dark.setCurrentText("auto" if d is None else ("dark" if d else "light"))
        form.addRow("custom: mode", self.theme_dark)

        self.theme_edits = {}
        for key, label in (("accent", "accent"), ("bg", "background"),
                           ("panel", "panel"), ("fg", "text"),
                           ("fg_dim", "muted text"), ("border", "border")):
            e = _wide(QLineEdit(str(th.get(key, "") or "")), 200)
            e.setPlaceholderText("#rrggbb")
            self.theme_edits[key] = e
            form.addRow(f"custom: {label}", e)

        show = QPushButton("Show resolved theme")
        show.clicked.connect(self._show_theme)
        form.addRow("", show)
        return tw

    def _show_theme(self):
        from .theme import resolve as resolve_theme
        try:
            showInfo(resolve_theme(self._gather()).describe())
        except Exception as e:
            showInfo(f"Could not resolve theme: {e}")

    def _test(self):
        cfg = self._gather()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            provider, reason = pick_provider(cfg, force=None)
            reply = provider.chat("You are a test.", "Reply with the single word: ok",
                                  temperature=0.0, max_tokens=16,
                                  timeout=cfg["generation"]["timeout_s"])
        except LLMError as e:
            QApplication.restoreOverrideCursor()
            showInfo(f"Test failed:\n{e}")
            return
        except Exception as e:
            QApplication.restoreOverrideCursor()
            showInfo(f"Test error:\n{e}")
            return
        QApplication.restoreOverrideCursor()
        showInfo(f"Route: {reason}\nProvider: {provider.describe()}\nReply: {reply.strip()[:200]}")

    def _save(self):
        write_config(self._gather())
        showInfo("Saved. Reopen the Leech Doctor to use the new settings.")
        self.accept()


def show_preferences(parent):
    dlg = PreferencesDialog(parent)
    dlg.exec()
