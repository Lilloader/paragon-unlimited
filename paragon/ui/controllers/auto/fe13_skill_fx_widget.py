"""Paragon Unlimited: the effect rules of one skill, inside the FE13 skill editor.

Rules are stored in GameData (PU_SkillFx) and only do something in game with the Paragon
Unlimited code.ips (exp04 or later). See paragon/core/services/fe13_skill_fx.py.
"""
import logging

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from paragon.core.services import fe13_skill_fx as fx
from paragon.ui.controllers.auto.abstract_auto_widget import AbstractAutoWidget


class FE13SkillFxWidget(AbstractAutoWidget, QWidget):
    def __init__(self, state):
        AbstractAutoWidget.__init__(self, state)
        QWidget.__init__(self)
        self.skill = None
        self._loading = False

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.note = QLabel(
            "What this skill does in battle (needs the Paragon Unlimited code.ips, exp04 or later). "
            "Every line applies when the unit has the skill equipped and both conditions hold. "
            "The game's own built-in effects (Sol, Astra, breakers...) still work and are not listed here."
        )
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.list = QListWidget()
        self.list.setMinimumHeight(90)
        self.list.currentRowChanged.connect(self._on_select)
        layout.addWidget(self.list)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add effect")
        self.add_button.clicked.connect(self._on_add)
        self.remove_button = QPushButton("Remove effect")
        self.remove_button.clicked.connect(self._on_remove)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        form = QFormLayout()
        self.effect = QComboBox()
        for k, v in fx.EFFECTS.items():
            self.effect.addItem(v, k)
        self.amount = QSpinBox()
        self.amount.setRange(-128, 127)
        self.when = QComboBox()
        self.and_when = QComboBox()
        for box in (self.when, self.and_when):
            for k, v in fx.CONDITIONS.items():
                box.addItem(v[0].upper() + v[1:], k)
        form.addRow("Effect", self.effect)
        form.addRow("Amount", self.amount)
        form.addRow("When", self.when)
        form.addRow("And when", self.and_when)
        self.hint = QLabel(
            "Damage received: a negative amount means less damage (e.g. -10)."
        )
        self.hint.setWordWrap(True)
        form.addRow(self.hint)
        layout.addLayout(form)
        self.effect.currentIndexChanged.connect(lambda _i: self._on_edit("effect", self.effect.currentData()))
        self.when.currentIndexChanged.connect(lambda _i: self._on_edit("condition_1", self.when.currentData()))
        self.and_when.currentIndexChanged.connect(lambda _i: self._on_edit("condition_2", self.and_when.currentData()))
        self.amount.valueChanged.connect(lambda v: self._on_edit("value", v))
        self.setLayout(layout)
        self._rules = []
        self._refresh()

    # ------------------------------------------------------------------ data
    def set_target(self, rid):
        self.skill = rid
        self._refresh()

    def _refresh(self, keep_row=None):
        self._loading = True
        try:
            self._rules = fx.rules_for(self.data, self.skill) if self.skill else []
        except Exception:
            logging.exception("Could not read skill effects.")
            self._rules = []
        self.list.clear()
        for r in self._rules:
            QListWidgetItem(fx.describe(self.data, r, with_skill=False), self.list)
        has_root = bool(self.skill) and fx.root(self.data) is not None
        self.add_button.setEnabled(has_root)
        self._loading = False
        if self._rules:
            row = keep_row if keep_row is not None else 0
            self.list.setCurrentRow(min(row, len(self._rules) - 1))
        else:
            self._on_select(-1)

    def _current(self):
        row = self.list.currentRow()
        if 0 <= row < len(self._rules):
            return self._rules[row]
        return None

    def _on_select(self, _row):
        rule = self._current()
        self._loading = True
        for w in (self.effect, self.amount, self.when, self.and_when, self.remove_button):
            w.setEnabled(rule is not None)
        if rule is not None:
            self._set_combo(self.effect, self.data.int(rule, "effect") or 0)
            self._set_combo(self.when, self.data.int(rule, "condition_1") or 0)
            self._set_combo(self.and_when, self.data.int(rule, "condition_2") or 0)
            self.amount.setValue(self.data.int(rule, "value") or 0)
        self._loading = False

    @staticmethod
    def _set_combo(box, value):
        i = box.findData(value)
        box.setCurrentIndex(i if i >= 0 else 0)

    def _on_edit(self, field, value):
        if self._loading:
            return
        rule = self._current()
        if rule is None or value is None:
            return
        self.data.set_int(rule, field, int(value))
        self.data.set_store_dirty("gamedata", True)
        item = self.list.currentItem()
        if item is not None:
            item.setText(fx.describe(self.data, rule, with_skill=False))

    def _on_add(self):
        if not self.skill:
            return
        rule = fx.add_rule(self.data, self.skill, effect=3, when=0, and_when=0, amount=10)
        if rule is None:
            return
        self._refresh(keep_row=len(self._rules))

    def _on_remove(self):
        rule = self._current()
        if rule is None:
            return
        row = self.list.currentRow()
        fx.remove_rule(self.data, rule)
        self._refresh(keep_row=max(0, row - 1))
