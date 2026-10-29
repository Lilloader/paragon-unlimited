"""Paragon Unlimited: Clear button next to each FE13 support slot (#000-#059), and the default
support type when a partner is picked for an empty slot (two women or two men: Non-romantic,
a woman and a man: Slow, as in the game)."""
import logging
import re

from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QWidget

from paragon.core.services import fe13_support_tools as st
from paragon.ui.controllers.auto.abstract_auto_widget import AbstractAutoWidget


class FE13SupportSlotTools(AbstractAutoWidget, QWidget):
    def __init__(self, state, spec):
        AbstractAutoWidget.__init__(self, state)
        QWidget.__init__(self)
        self.field_id = spec.field_id
        self.slot = int(re.search(r"(\d+)$", spec.field_id).group(1))
        self.rid = None
        self._hooked = False
        self._partner_box = None
        self._type_box = None

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setToolTip(
            "Empty this support slot (partner and support type).\n"
            "You can also remove this character from the partner's list."
        )
        self.clear_button.clicked.connect(self._on_clear)
        layout.addWidget(self.clear_button)
        self.setLayout(layout)

    # ------------------------------------------------------------------ helpers
    def _siblings(self):
        """The partner and type boxes of this slot (in the same group box)."""
        if self._hooked:
            return
        self._hooked = True
        type_id = f"support_type_{self.slot:03}"
        p = self.parentWidget()
        for _ in range(4):
            if p is None:
                break
            for w in p.findChildren(QWidget):
                fid = getattr(w, "field_id", None)
                if fid == self.field_id and w is not self and hasattr(w, "currentIndexChanged") and self._partner_box is None:
                    self._partner_box = w
                elif fid == type_id and hasattr(w, "currentIndexChanged") and self._type_box is None:
                    self._type_box = w
            if self._partner_box is not None and self._type_box is not None:
                break
            p = p.parentWidget()
        if self._partner_box is not None:
            # Connected after the box's own handler, so the partner is already stored.
            self._partner_box.currentIndexChanged.connect(self._on_partner_changed)

    def _owner(self):
        return st.owner_of(self.data, self.rid) if self.rid else None

    def _partner(self):
        return self.data.rid(self.rid, self.field_id) if self.rid else None

    def _refresh_boxes(self):
        for box in (self._partner_box, self._type_box):
            if box is not None:
                try:
                    box.set_target(self.rid)
                except Exception:
                    logging.exception("Could not refresh the support slot.")

    # ------------------------------------------------------------------ events
    def set_target(self, rid):
        self.rid = rid
        self._siblings()
        self.clear_button.setEnabled(rid is not None)

    def _on_partner_changed(self, _index=None):
        """Partner picked for a slot with no support type: use the game's type for the pair."""
        if not self.rid:
            return
        owner, partner = self._owner(), self._partner()
        if owner is None or partner is None:
            return
        type_field = f"support_type_{self.slot:03}"
        if not st.is_none(self.data.int(self.rid, type_field)):
            return
        self.data.set_int(self.rid, type_field, st.default_type(self.data, owner, partner))
        if self._type_box is not None:
            self._type_box.set_target(self.rid)

    def _on_clear(self):
        if not self.rid:
            return
        owner, partner = self._owner(), self._partner()
        if partner is None and st.is_none(self.data.int(self.rid, f"support_type_{self.slot:03}")):
            return  # already empty
        both = False
        if partner is not None and owner is not None and st.slots_listing(self.data, partner, owner):
            box = QMessageBox(self)
            box.setWindowTitle("Clear support")
            box.setText(
                f"Clear support slot #{self.slot:03} ({self.data.display(partner)})?\n\n"
                f"{self.data.display(partner)} also lists {self.data.display(owner)} as a partner."
            )
            both_button = box.addButton("Clear both", QMessageBox.AcceptRole)
            both_button.setToolTip("Also remove this character from the partner's support list.")
            one_button = box.addButton("Only this slot", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(both_button)
            box.exec()
            clicked = box.clickedButton()
            if clicked is both_button:
                both = True
            elif clicked is not one_button:
                return
        try:
            st.clear(self.data, self.rid, self.slot, both)
        except Exception:
            logging.exception("Could not clear the support slot.")
            QMessageBox.warning(self, "Clear support", "Could not clear the slot (see paragon.log).")
            return
        self._refresh_boxes()
