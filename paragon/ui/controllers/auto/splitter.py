from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter

from paragon.ui.controllers.auto.abstract_auto_widget import AbstractAutoWidget


class Splitter(AbstractAutoWidget, QSplitter):
    """Paragon Unlimited: resizable panes. Positions are remembered when `remember` is set."""

    def __init__(self, state, spec):
        AbstractAutoWidget.__init__(self, state)
        QSplitter.__init__(self, Qt.Vertical if spec.orientation == "vertical" else Qt.Horizontal)
        self.setChildrenCollapsible(False)
        self.widgets = []
        for inner_spec in spec.inner:
            w = state.generator.generate_top_level(state, inner_spec)
            self.addWidget(w)
            self.widgets.append(w)
        for i in range(len(self.widgets)):
            self.setStretchFactor(i, 1)
        if spec.sizes and len(spec.sizes) == len(self.widgets):
            self.setSizes(spec.sizes)
        if spec.remember:
            from paragon.ui import pu_window_memory

            pu_window_memory.remember_splitter(self, spec.remember)

    def set_target(self, rid):
        for widget in self.widgets:
            widget.set_target(rid)
