"""Leech Doctor — find cards you keep forgetting, let an LLM propose repairs, apply safely.

Entry points:
  Tools -> Leech Doctor            (main window)
  Tools -> Leech Doctor: Preferences
  Browser right-click -> Send to Leech Doctor
"""
from aqt import mw, gui_hooks
from aqt.qt import QAction


def _open_editor(nids=None):
    from .gui.dialog import LeechDoctorDialog
    dlg = LeechDoctorDialog(mw)
    dlg.exec()


def _open_prefs():
    from .gui.prefs import show_preferences
    show_preferences(mw)


def _browser_menu(browser, menu):
    act = QAction("Send to Leech Doctor", browser)
    act.triggered.connect(lambda: _open_editor())
    menu.addAction(act)


def _setup():
    a1 = QAction("Leech Doctor…", mw)
    a1.triggered.connect(lambda: _open_editor())
    mw.form.menuTools.addAction(a1)

    a2 = QAction("Leech Doctor: Preferences…", mw)
    a2.triggered.connect(_open_prefs)
    mw.form.menuTools.addAction(a2)

    gui_hooks.browser_will_show_context_menu.append(_browser_menu)


gui_hooks.main_window_did_init.append(_setup)
