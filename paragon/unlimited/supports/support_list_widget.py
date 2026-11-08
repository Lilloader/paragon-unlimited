"""Paragon Unlimited: the Supports tab of the FE13 character editor.

One row per support partner with its support type, its ranks and whether anything the game
needs is missing. Add a support with any character, remove one, change its type or open its
conversations. Every change updates the support slots of both characters, the support
conversation list (RelianceList) and the conversation text file (see support_list.py).
"""
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from paragon.unlimited.supports import extra_slots
from paragon.unlimited.supports import support_list as sl
from paragon.unlimited.supports import support_tools as st
from paragon.ui.controllers.auto.abstract_auto_widget import AbstractAutoWidget

TYPES = [  # (name, thresholds); None = the game's choice for the pair
    ("Automatic", None),
    ("Non-romantic (C/B/A)", st.TYPE_NON_ROMANTIC),
    ("Slow (C/B/A/S)", st.TYPE_SLOW),
    ("Medium (C/B/A/S)", 336464132),
    ("Fast (C/B/A/S)", 302843907),
]
COL_PARTNER, COL_TYPE, COL_RANKS, COL_STATUS, COL_ACTIONS = range(5)


class FE13SupportListWidget(AbstractAutoWidget, QWidget):
    def __init__(self, state):
        AbstractAutoWidget.__init__(self, state)
        QWidget.__init__(self)
        self.rid = None
        self.editors = {}
        self._loading = False

        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setWordWrap(True)
        layout.addWidget(self.title)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Partner", "Support type", "Ranks", "In game", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(COL_PARTNER, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(COL_RANKS, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(COL_STATUS, QHeaderView.Stretch)
        head.setSectionResizeMode(COL_ACTIONS, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("Add a support with"))
        self.partner_box = QComboBox()
        self.partner_box.setEditable(True)
        self.partner_box.setInsertPolicy(QComboBox.NoInsert)
        self.partner_box.setMinimumWidth(220)
        add_row.addWidget(self.partner_box, 1)
        self.type_box = QComboBox()
        for name, value in TYPES:
            self.type_box.addItem(name, value)
        self.type_box.setToolTip(
            "Automatic: Non-romantic for two men or two women, Slow for a man and a woman\n"
            "(as in the game). Non-romantic supports stop at A; the others have an S rank."
        )
        add_row.addWidget(self.type_box)
        self.add_button = QPushButton("Add")
        self.add_button.setToolTip(
            "Adds the support to both characters, the support conversations C/B/A (and S)\n"
            "and the conversation file, so it works in the game."
        )
        self.add_button.clicked.connect(self._on_add)
        add_row.addWidget(self.add_button)
        layout.addLayout(add_row)

        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.setEnabled(False)

    # ------------------------------------------------------------------ helpers
    def _name(self, rid):
        try:
            return self.data.display(rid) or self.data.key(rid) or "?"
        except Exception:
            return "?"

    def _fill_partners(self):
        current = self.partner_box.currentData()
        self.partner_box.blockSignals(True)
        self.partner_box.clear()
        for rid in sl._characters(self.data):
            if rid == self.rid:
                continue
            key = self.data.key(rid)
            if not key or not key.startswith("PID_"):
                continue
            self.partner_box.addItem(f"{self._name(rid)}  ({key})", rid)
        completer = QCompleter([self.partner_box.itemText(i) for i in range(self.partner_box.count())], self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.partner_box.setCompleter(completer)
        if current is not None:
            i = self.partner_box.findData(current)
            if i >= 0:
                self.partner_box.setCurrentIndex(i)
        self.partner_box.blockSignals(False)

    def _status(self, s: sl.Support):
        missing = []
        if not s.partner_lists_owner:
            missing.append(f"{self._name(s.partner)} does not list {self._name(self.rid)}")
        if st.is_none(s.thresholds):
            missing.append("support type None")
        want = sl.levels_for(s.thresholds) if not st.is_none(s.thresholds) else []
        lack = [sl.LEVELS[x] for x in want if x not in s.conversations]
        if lack:
            missing.append("no conversation record for " + "/".join(lack))
        if sl.find_archive(self.data, self.rid, s.partner) is None:
            missing.append("no conversation file")
        return missing

    def _refresh_editor(self):
        """Show the change in the rest of the character editor (the support slots)."""
        top, p = None, self.parentWidget()
        while p is not None:
            if isinstance(p, AbstractAutoWidget) and hasattr(p, "set_target"):
                top = p
            p = p.parentWidget()
        if top is not None:
            try:
                top.set_target(self.rid)
                return
            except Exception:
                logging.exception("Could not refresh the character editor.")
        self.set_target(self.rid)

    # ------------------------------------------------------------------ view
    def set_target(self, rid):
        self.rid = rid
        self.setEnabled(rid is not None)
        self._loading = True
        try:
            self._fill_partners()
            self._fill_table()
        finally:
            self._loading = False

    def _fill_table(self):
        self.table.setRowCount(0)
        if not self.rid:
            self.title.setText("")
            self.note.setText("")
            return
        supports = sl.supports_of(self.data, self.rid)
        used = extra_slots.TOTAL_SLOTS - sl.free_slots(self.data, self.rid)
        self.title.setText(
            f"<b>{self._name(self.rid)}</b> has {len(supports)} support partner(s) "
            f"({used} of {extra_slots.TOTAL_SLOTS} slots used)."
        )
        self.table.setRowCount(len(supports))
        for row, s in enumerate(supports):
            item = QTableWidgetItem(self._name(s.partner))
            item.setToolTip(f"{self.data.key(s.partner)}, slot(s) " + ", ".join(f"#{k:03}" for k in s.slots))
            self.table.setItem(row, COL_PARTNER, item)

            box = QComboBox()
            for name, value in TYPES[1:]:
                box.addItem(name, value)
            i = box.findData(s.thresholds & 0xFFFFFFFF if s.thresholds is not None else None)
            if i < 0:
                box.addItem(st.type_name(s.thresholds), s.thresholds)
                i = box.count() - 1
            box.setCurrentIndex(i)
            box.currentIndexChanged.connect(lambda _i, p=s.partner, b=box: self._on_type(p, b.currentData()))
            self.table.setCellWidget(row, COL_TYPE, box)

            ranks = " ".join(sl.LEVELS[x] for x in sorted(s.conversations)) or "-"
            self.table.setItem(row, COL_RANKS, QTableWidgetItem(ranks))

            missing = self._status(s)
            status = QTableWidgetItem("OK" if not missing else "Missing: " + "; ".join(missing))
            status.setToolTip(status.text())
            if missing:
                status.setForeground(QColor(210, 70, 70))
            self.table.setItem(row, COL_STATUS, status)

            actions = QWidget()
            h = QHBoxLayout(actions)
            h.setContentsMargins(2, 0, 2, 0)
            if missing:
                fix = QPushButton("Fix")
                fix.setToolTip("Add what is missing so the support works in the game.")
                fix.clicked.connect(lambda _c=False, p=s.partner: self._on_fix(p))
                h.addWidget(fix)
            talk = QPushButton("Conversations")
            talk.clicked.connect(lambda _c=False, p=s.partner: self._on_open(p))
            h.addWidget(talk)
            remove = QPushButton("Remove")
            remove.clicked.connect(lambda _c=False, p=s.partner: self._on_remove(p))
            h.addWidget(remove)
            self.table.setCellWidget(row, COL_ACTIONS, actions)
        self.note.setText(
            "Adding or removing a support changes both characters, the support conversation list "
            "and the conversation file. Removing keeps the conversation text, in case you add the "
            "support again. Slots #052-#059 need the game code patch."
        )

    # ------------------------------------------------------------------ actions
    def _run(self, title, fn):
        try:
            result = fn()
        except Exception:
            logging.exception("%s failed.", title)
            QMessageBox.warning(self, title, f"{title} failed (see paragon.log). Nothing was saved yet.")
            self._refresh_editor()
            return None
        if result is not None and not result.ok:
            QMessageBox.information(self, title, result.message)
        self._refresh_editor()
        return result

    def _on_add(self):
        if not self.rid:
            return
        partner = self.partner_box.currentData()
        text = self.partner_box.currentText()
        if partner is None or self.partner_box.itemText(self.partner_box.currentIndex()) != text:
            i = self.partner_box.findText(text, Qt.MatchContains)
            partner = self.partner_box.itemData(i) if i >= 0 else None
        if partner is None:
            QMessageBox.information(self, "Add support", "Pick a character from the list.")
            return
        if any(s.partner == partner for s in sl.supports_of(self.data, self.rid)):
            QMessageBox.information(
                self, "Add support",
                f"{self._name(self.rid)} already supports {self._name(partner)}. "
                "Use Fix in the list if something is missing.",
            )
            return
        self._run("Add support", lambda: sl.add_support(self.data, self.rid, partner, self.type_box.currentData()))

    def _on_fix(self, partner):
        self._run("Fix support", lambda: sl.repair_support(self.data, self.rid, partner))

    def _on_type(self, partner, thresholds):
        if self._loading or thresholds is None:
            return
        self._run("Support type", lambda: sl.set_type(self.data, self.rid, partner, thresholds))

    def _on_remove(self, partner):
        answer = QMessageBox.question(
            self,
            "Remove support",
            f"Remove the support between {self._name(self.rid)} and {self._name(partner)}?\n\n"
            "Both characters lose it and its conversations are taken out of the support list. "
            "The conversation text is kept.",
        )
        if answer != QMessageBox.Yes:
            return
        self._run("Remove support", lambda: sl.remove_support(self.data, self.rid, partner))

    def _on_open(self, partner):
        try:
            thresholds = sl.current_type(self.data, self.rid, partner)
            path = sl.ensure_archive(self.data, self.rid, partner, sl.levels_for(thresholds))
            if not path:
                QMessageBox.information(self, "Conversations", "Both characters need a PID (PID_name).")
                return
            st.fill_new_conversations(self.data, path, True)
            if path in self.editors:
                self.editors[path].show()
                return
            from paragon.model.game import Game
            from paragon.ui.controllers.dialogue_editor import DialogueEditor

            editor = DialogueEditor(self.data, self.gs.dialogue, self.gs.sprite_animation, Game.FE13)
            editor.set_archive(path, True)
            self.editors[path] = editor
            editor.show()
        except Exception:
            logging.exception("Could not open the support conversations.")
            QMessageBox.warning(self, "Conversations", "Could not open the conversations (see paragon.log).")
