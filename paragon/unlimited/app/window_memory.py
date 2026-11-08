"""Paragon Unlimited: remember the size of editor windows (and splitter positions).

Sizes are kept in paragon.json (Configuration.pu_window_sizes) and saved when Paragon closes.
"""
import logging
from typing import Optional

from PySide6.QtCore import QObject, QEvent, QTimer
from PySide6.QtGui import QGuiApplication

_config = None


def set_config(config):
    global _config
    _config = config


def _store():
    if _config is None:
        return None
    if getattr(_config, "pu_window_sizes", None) is None:
        try:
            _config.pu_window_sizes = {}
        except Exception:
            return None
    return _config.pu_window_sizes


def saved(key: str) -> Optional[list]:
    store = _store()
    return list(store[key]) if store and key in store else None


def save(key: str, value):
    store = _store()
    if store is not None:
        store[key] = list(value)


class _Watcher(QObject):
    def __init__(self, widget, key):
        super().__init__(widget)
        self.key = key
        self.widget = widget
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._save)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.Move) and obj.isVisible() and not obj.isMaximized():
            self.timer.start()
        return False

    def _save(self):
        w = self.widget
        g = w.geometry()
        save(self.key, [g.width(), g.height(), g.x(), g.y()])


def remember_window(widget, key: str):
    """Restore the last size/position of this window and keep it up to date."""
    key = "window:" + key
    try:
        value = saved(key)
        if value and len(value) >= 2:
            w, h = max(300, int(value[0])), max(200, int(value[1]))
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                w, h = min(w, avail.width()), min(h, avail.height())
            widget.resize(w, h)
            if len(value) >= 4 and screen is not None:
                x, y = int(value[2]), int(value[3])
                if any(s.availableGeometry().contains(x + 40, y + 40) for s in QGuiApplication.screens()):
                    widget.move(x, y)
        watcher = _Watcher(widget, key)
        widget.installEventFilter(watcher)
        widget._pu_window_watcher = watcher
    except Exception:
        logging.exception("Could not restore the window size.")


def remember_splitter(splitter, key: str):
    key = "splitter:" + key
    try:
        value = saved(key)
        if value and len(value) == splitter.count() and sum(value) > 0:
            splitter.setSizes([int(v) for v in value])
        splitter.splitterMoved.connect(lambda *_: save(key, splitter.sizes()))
    except Exception:
        logging.exception("Could not restore the splitter position.")
