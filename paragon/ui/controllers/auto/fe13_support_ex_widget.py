"""Paragon Unlimited: support slots #052-#059 inside the FE13 character editor."""
import logging

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from paragon.core.services import fe13_support_ex
from paragon.ui.controllers.auto.abstract_auto_widget import AbstractAutoWidget
from paragon.ui.controllers.auto.awakening_support_dialogue_button import (
    AwakeningSupportDialogueButton,
)


class FE13SupportExWidget(AbstractAutoWidget, QWidget):
    def __init__(self, state):
        AbstractAutoWidget.__init__(self, state)
        QWidget.__init__(self)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        note = QLabel(
            "Paragon Unlimited extra slots #052-#059.\n"
            "The game only uses them with the Paragon Unlimited code.ips."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.inner = None
        try:
            self.inner = state.generator.generate_for_type("PUSupportEx")
            layout.addWidget(self.inner)
        except Exception:
            logging.exception("Could not build the extra support slot editor.")
            note.setText(
                "Extra slots #052-#059 are not available: this data has no PUSupportEx type."
            )
        self.setLayout(layout)

    def set_target(self, rid):
        if not self.inner:
            return
        entry = None
        if rid:
            try:
                entry = fe13_support_ex.ensure_entry(self.data, rid)
            except Exception:
                logging.exception("Could not open extra support slots.")
        self.inner.set_target(entry)
        self.setEnabled(entry is not None)


class FE13SupportExDialogueButton(AwakeningSupportDialogueButton):
    """Same as the normal button, but the character is the entry's owner."""

    def _self_rid(self):
        return self.data.rid(self.rid, "owner") if self.rid else None
