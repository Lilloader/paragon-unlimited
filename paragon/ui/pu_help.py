"""Paragon Unlimited: in-app help.

Topics live in Data/<game>/PU_Help.yml. F1 in any window (or a Help button) opens the topic
for that window; Help -> Help Topics lists everything; the Acknowledgments tab holds the
credits that used to be the About box.
"""
import html
import json
import logging
import os
import re
from typing import Dict, Optional

import yaml
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QTextBrowser,
    QTabWidget,
    QWidget,
    QLabel,
    QPushButton,
    QToolBar,
)

_TOPICS: Dict[str, dict] = {}
_LOADED_FOR = None


def _game_dir(game) -> str:
    name = getattr(game, "value", None) or str(game or "FE13")
    return os.path.join("Data", name)


def load_topics(game="FE13") -> Dict[str, dict]:
    global _TOPICS, _LOADED_FOR
    if _LOADED_FOR == str(game) and _TOPICS:
        return _TOPICS
    topics = {}
    for path in (os.path.join(_game_dir(game), "PU_Help.yml"), os.path.join("Data", "FE13", "PU_Help.yml")):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    topics = (yaml.safe_load(f) or {}).get("topics", {})
                break
            except Exception:
                logging.exception(f"Could not read help topics from {path}")
    _TOPICS, _LOADED_FOR = topics, str(game)
    return topics


def _commands_html() -> str:
    try:
        with open(os.path.join("resources", "misc", "DialogueCommands.json"), "r", encoding="utf-8") as f:
            commands = json.load(f)
    except Exception:
        return "<p>(The command list could not be loaded.)</p>"
    rows = []
    for c in commands:
        hint = c.get("Hint") or html.escape(c.get("Command", ""))
        rows.append(f"<li>{hint}</li>")
    return "<ul>" + "".join(rows) + "</ul>"


def _emotions_html(game) -> str:
    try:
        with open(os.path.join(_game_dir(game), "Emotions.json"), "r", encoding="utf-8") as f:
            emotions = json.load(f)
    except Exception:
        return ""
    cells = "".join(
        f"<tr><td>{html.escape(en)}</td><td>{html.escape(jp)}</td></tr>" for en, jp in emotions.items()
    )
    return (
        "<p>Use the English name in the editor (it is converted for the game). A character only has "
        "the expressions in their portrait file; most have Standard, Happy, Angry, Suffering and Posed. "
        "Blush and Sweat are overlays: <i>$Emotions(Happy,Blush)</i>.</p>"
        f"<table border='1' cellspacing='0' cellpadding='3'><tr><th>Editor</th><th>Game</th></tr>{cells}</table>"
    )


def topic_html(topic_id: str, game="FE13") -> str:
    topics = load_topics(game)
    t = topics.get(topic_id) or topics.get("main") or {"title": "Help", "body": "<p>No help yet.</p>"}
    body = t.get("body", "")
    if "{{dialogue_commands}}" in body:
        body = body.replace("{{dialogue_commands}}", _commands_html())
    if "{{emotions}}" in body:
        body = body.replace("{{emotions}}", _emotions_html(game))
    nav = ""
    if t.get("tutorial"):
        lessons = sorted((v.get("tutorial"), k) for k, v in topics.items() if v.get("tutorial"))
        ids = [k for _n, k in lessons]
        i = ids.index(topic_id) if topic_id in ids else -1
        links = []
        if i > 0:
            links.append(f"<a href='topic:{ids[i - 1]}'>&larr; {html.escape(topics[ids[i - 1]].get('title', ''))}</a>")
        if 0 <= i < len(ids) - 1:
            links.append(f"<a href='topic:{ids[i + 1]}'>Next lesson: {html.escape(topics[ids[i + 1]].get('title', ''))} &rarr;</a>")
        if links:
            nav = "<hr><p>" + " &nbsp; | &nbsp; ".join(links) + "</p>"
        title = f"Lesson {t['tutorial']}: {t.get('title', topic_id)}"
    else:
        title = t.get("title", topic_id)
    return f"<h2>{html.escape(title)}</h2>{body}{nav}"


def topic_for_window(widget) -> str:
    """Topic id for a window (or any widget inside it)."""
    topics = load_topics(_LOADED_FOR or "FE13")
    w = widget.window() if widget is not None else None
    if w is None:
        return "main"
    keys = []
    explicit = getattr(w, "_pu_help_topic", None)
    if explicit:
        keys.append(explicit)
    keys += list(getattr(w, "_pu_help_keys", []) or [])
    keys += [cls.__name__ for cls in type(w).__mro__]
    for key in keys:
        if key in topics:
            return key
        for tid, t in topics.items():
            if key in (t.get("windows") or []):
                return tid
    return "main"


ACKNOWLEDGMENTS = """
<h2>Paragon Unlimited</h2>
<p>A toolkit for making Fire Emblem Awakening mods: Map Maker, Sprite Workshop, 60 support slots,
portrait and model previews, voices, DLC maps, Check My Mod, Copy to Azahar, Share My Mod and more.
It also opens Fates and Echoes projects.</p>
<h3>Thanks</h3>
<ul><li>Albinopelican</li><li>lilloader</li></ul>
<h3>Credits carried over from Paragon</h3>
<ul><li>Moonling</li><li>Lazy</li><li>muhmuhten</li><li>DeathChaos</li><li>TildeHat</li>
<li>AmbiguousPresence</li><li>SciresM</li><li>jespoketheepic</li></ul>
<h3>Also used</h3>
<ul>
<li>mila and exalt-rs: file formats and the script compiler</li>
<li>3dbrew.org: notes on the CGFX, CTPK and sound formats</li>
<li>Qt / PySide6, Pillow, PyYAML, pydantic</li>
</ul>
<h3>License</h3>
<p>Paragon Unlimited is free software under the GNU General Public License, version 3 (LICENSE.txt).
It is based on Paragon, copyright thane98, also GPL-3.0. Source code:
<a href="https://github.com/Lilloader/paragon-unlimited">github.com/Lilloader/paragon-unlimited</a>.</p>
<p>Fire Emblem is a trademark of Nintendo / Intelligent Systems. Paragon Unlimited is a fan tool and
does not include any game files.</p>
"""


class HelpDialog(QDialog):
    def __init__(self, game="FE13", parent=None):
        super().__init__(parent)
        self.game = game
        self.setWindowTitle("Paragon Unlimited - Help")
        self.setWindowIcon(QIcon("paragon.ico"))
        self.resize(1000, 700)
        self.list = QListWidget()
        self.list.setMaximumWidth(290)
        self.text = QTextBrowser()
        help_page = QWidget()
        h = QHBoxLayout()
        h.addWidget(self.list)
        h.addWidget(self.text, 1)
        help_page.setLayout(h)
        thanks = QTextBrowser()
        thanks.setOpenExternalLinks(True)
        thanks.setHtml(ACKNOWLEDGMENTS)
        self.tabs = QTabWidget()
        self.tabs.addTab(help_page, "Help")
        self.tabs.addTab(thanks, "Acknowledgments")
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        layout = QVBoxLayout()
        layout.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Tip: press F1 in any window for help about it."))
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
        self.setLayout(layout)
        topics = load_topics(game)
        tutorials = [(tid, t) for tid, t in topics.items() if t.get("tutorial")]
        reference = [(tid, t) for tid, t in topics.items() if not t.get("tutorial")]
        for header, group in (("Tutorials - start here", tutorials), ("Reference", reference)):
            if not group:
                continue
            head = QListWidgetItem(header)
            head.setFlags(Qt.NoItemFlags)
            f = head.font()
            f.setBold(True)
            head.setFont(f)
            self.list.addItem(head)
            for tid, t in group:
                label = t.get("title", tid)
                if t.get("tutorial"):
                    label = f"{t['tutorial']}. {label}"
                item = QListWidgetItem("   " + label)
                item.setData(Qt.UserRole, tid)
                self.list.addItem(item)
        self.list.currentItemChanged.connect(self._on_item)
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self._on_link)
        try:
            from paragon.ui import pu_window_memory

            pu_window_memory.remember_window(self, "help")
        except Exception:
            pass

    def _on_item(self, item, _prev=None):
        if item is not None and item.data(Qt.UserRole):
            self.text.setHtml(topic_html(item.data(Qt.UserRole), self.game))

    def _on_link(self, url):
        """Links in help pages: topic:<id> opens another page, anything else the web browser."""
        target = url.toString()
        if target.startswith("topic:"):
            self.show_topic(target[len("topic:"):])
            return
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(url)

    def show_topic(self, topic_id):
        self.tabs.setCurrentIndex(0)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == topic_id:
                self.list.setCurrentRow(i)
                break
        else:
            self.text.setHtml(topic_html(topic_id, self.game))
        self.show()
        self.raise_()
        self.activateWindow()

    def show_acknowledgments(self):
        self.tabs.setCurrentIndex(1)
        self.show()
        self.raise_()
        self.activateWindow()


class HelpManager(QObject):
    """F1 anywhere opens the help for the active window; remembers the last editor used."""

    def __init__(self, game="FE13", main_window=None):
        super().__init__(main_window)
        self.game = game
        self.main_window = main_window
        self.dialog: Optional[HelpDialog] = None
        self.last_window = None
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            app.focusChanged.connect(self._on_focus)

    def _on_focus(self, _old, new):
        if new is None:
            return
        w = new.window()
        if w is None or isinstance(w, HelpDialog) or w is self.main_window:
            return
        self.last_window = w

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_F1:
            target = QApplication.activeWindow()
            if not isinstance(target, HelpDialog):
                self.show_for(target)
                return True
        return False

    def _dialog(self) -> HelpDialog:
        if self.dialog is None:
            self.dialog = HelpDialog(self.game)
        return self.dialog

    def show_for(self, window):
        self._dialog().show_topic(topic_for_window(window) if window is not None else "main")

    def show_for_last(self):
        """Help menu of the main window: the editor you used last, if it is still open."""
        w = self.last_window
        if w is not None and w.isVisible():
            self.show_for(w)
        else:
            self.show_for(self.main_window)

    def show_topics(self):
        self._dialog().show_topic("main")

    def show_acknowledgments(self):
        self._dialog().show_acknowledgments()


_manager: Optional[HelpManager] = None


def install(game, main_window) -> HelpManager:
    global _manager
    load_topics(game)
    if _manager is not None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(_manager)
        try:
            if _manager.dialog is not None:
                _manager.dialog.close()
        except Exception:
            pass
    _manager = HelpManager(game, main_window)
    return _manager


def manager() -> Optional[HelpManager]:
    return _manager


def show_help(widget):
    """For Help buttons inside windows."""
    m = _manager
    if m is not None:
        m.show_for(widget)
    else:
        dlg = HelpDialog()
        dlg.show_topic(topic_for_window(widget))
        widget._pu_help_dialog = dlg


def add_help_action(window, topic: Optional[str] = None, *more_keys):
    """Give a window a Help entry: a toolbar action when it has a toolbar."""
    if topic:
        window._pu_help_topic = topic
    if more_keys:
        window._pu_help_keys = [k for k in more_keys if k]
    try:
        bar = window.findChild(QToolBar)
        if bar is not None:
            act = bar.addAction("Help")
            act.setToolTip("Help about this window (F1)")
            act.triggered.connect(lambda: show_help(window))
            return act
    except Exception:
        logging.exception("Could not add a Help button.")
    return None
