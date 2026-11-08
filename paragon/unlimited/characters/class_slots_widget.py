"""Paragon Unlimited: reclass slots 4-5 and the avatar class checklist in the FE13 character
editor (Stats tab). Both need the Paragon Unlimited game code patch to work in game."""
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from paragon.model.auto_generator_state import AutoGeneratorState
from paragon.model.auto_ui import SpriteFormSpec
from paragon.ui.controllers.auto.abstract_auto_widget import AbstractAutoWidget
from paragon.ui.controllers.auto.sprite_form import SpriteForm
from paragon.unlimited.characters import class_slots as cs

PATCH_NOTE = "Needs the Paragon Unlimited game code patch (Unlimited -> Install Game Code Patch)."


class _EntrySpriteForm(SpriteForm):
    """A class picker on a PU_ClassEx entry; the sprite preview uses the entry's character."""

    def _load_sprite(self, struct_rid):
        try:
            owner = self.data.rid(self.rid, "owner") if self.rid else None
            pid = (self.data.string(owner, "pid") or "")[4:] if owner else None
            bmap_icon_rid = self.data.rid(struct_rid, "bmap_icon")
            fallback = self.data.string(bmap_icon_rid, "name") if bmap_icon_rid else None
            jid = fallback[:-1] if fallback else None
            self.sprite_item.set_sprite(self.service.load(pid, jid, self.team, fallback_job=fallback))
        except Exception:
            self.sprite_item.set_sprite(None)


def _entry_state(state):
    gen = state.generator
    return AutoGeneratorState(
        main_state=state.main_state,
        game_state=state.game_state,
        generator=gen,
        type_metadata=gen.data.type_metadata("PUClassEx"),
        field_metadata=gen.data.field_metadata("PUClassEx"),
        typename="PUClassEx",
        labeled_widgets={},
    )


class FE13ClassSlotsWidget(AbstractAutoWidget, QWidget):
    """Reclass 4 and Reclass 5 for one gender (spec.gender), under the game's 3 slots."""

    def __init__(self, state, spec):
        AbstractAutoWidget.__init__(self, state)
        QWidget.__init__(self)
        self.gender = spec.gender
        self.forms = []
        layout = QFormLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        try:
            if not cs.has_class_ex(self.data):
                raise RuntimeError("no PU_ClassEx table")
            es = _entry_state(state)
            for k in cs.EXTRA_SLOTS:
                form = _EntrySpriteForm(es, SpriteFormSpec(type="sprite_form"), cs.slot_field(self.gender, k))
                form.setToolTip(f"Reclass slot {k} (Unlimited). " + PATCH_NOTE)
                layout.addRow(f"Reclass {k}", form)
                self.forms.append(form)
        except Exception:
            logging.exception("Could not build reclass slots 4-5.")
            layout.addRow(QLabel("Reclass 4-5 are not available for this data."))

    def set_target(self, rid):
        entry = None
        if rid and self.forms:
            try:
                entry = cs.ensure_entry(self.data, rid)
            except Exception:
                logging.exception("Could not open reclass slots 4-5.")
        for f in self.forms:
            f.set_target(entry)
        self.setEnabled(entry is not None)


class FE13AvatarClassesWidget(AbstractAutoWidget, QWidget):
    """Checklist of the classes avatars get (shown for characters with Tactician as a
    reclass class). One list for every avatar of a gender: Robin, Morgan and any character
    you give Tactician."""

    def __init__(self, state):
        AbstractAutoWidget.__init__(self, state)
        QWidget.__init__(self)
        self.rid = None
        self._loading = False
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer)
        box = QGroupBox("Avatar classes (Unlimited)")
        outer.addWidget(box)
        layout = QVBoxLayout()
        box.setLayout(layout)
        note = QLabel(
            "This character has Tactician as a reclass class, so the game treats it as an avatar "
            "(like Robin): a Second Seal offers every class ticked here, plus its own reclass "
            "classes. The list is shared by every avatar of that gender (and their children). "
            "Tick the base classes; the game adds their promotions from level 10. "
            + PATCH_NOTE
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        cols = QHBoxLayout()
        layout.addLayout(cols)
        self.lists = {}
        for g in cs.GENDERS:
            col = QVBoxLayout()
            col.addWidget(QLabel("Male avatars" if g == "male" else "Female avatars"))
            lw = QListWidget()
            lw.setMinimumHeight(260)
            lw.itemChanged.connect(lambda _item, g=g: self._on_changed(g))
            col.addWidget(lw)
            buttons = QHBoxLayout()
            all_b = QPushButton("Tick all")
            all_b.setToolTip("Every unpromoted class of this gender, except the game's enemy-only "
                             "classes (Revenant, Entombed, Mirage, Grima, ...) and classes without a name.")
            all_b.clicked.connect(lambda _=False, g=g: self._tick_all(g))
            none_b = QPushButton("Untick all")
            none_b.clicked.connect(lambda _=False, g=g: self._set_all(g, False))
            buttons.addWidget(all_b)
            buttons.addWidget(none_b)
            col.addLayout(buttons)
            cols.addLayout(col)
            self.lists[g] = lw
        bottom = QHBoxLayout()
        self.size_label = QLabel("")
        self.size_label.setWordWrap(True)
        bottom.addWidget(self.size_label, 1)
        reset = QPushButton("Game's own list")
        reset.setToolTip("Back to the game's 13 classes per gender.")
        reset.clicked.connect(self._reset)
        bottom.addWidget(reset)
        layout.addLayout(bottom)
        self.setVisible(False)

    # ------------------------------------------------------------------ helpers
    def _jobs(self, gender):
        try:
            table_rid, field = self.data.table("jobs")
            jobs = self.data.items(table_rid, field) or []
        except Exception:
            return []
        return [j for j in jobs if cs.job_gender(self.data, j) == gender]

    def _name(self, job):
        try:
            return self.data.display(job) or cs.jid(self.data, job)
        except Exception:
            return cs.jid(self.data, job) or "?"

    def _fill(self):
        self._loading = True
        try:
            for g, lw in self.lists.items():
                lw.clear()
                ticked = set(cs.avatar_classes(self.data, g))
                jobs = self._jobs(g)
                names = [self._name(j) for j in jobs]
                for j, n in zip(jobs, names):
                    text = n if names.count(n) == 1 else f"{n} ({cs.jid(self.data, j)})"
                    if not cs.promotions(self.data, j):
                        text += "  (no promotion)"
                    item = QListWidgetItem(text)
                    item.setData(Qt.UserRole, j)
                    item.setToolTip(cs.jid(self.data, j) or "")
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if j in ticked else Qt.Unchecked)
                    lw.addItem(item)
        finally:
            self._loading = False
        self._update_size()

    def _checked(self, gender):
        lw = self.lists[gender]
        out = []
        for i in range(lw.count()):
            it = lw.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole))
        return out

    def _update_size(self):
        if not self.rid:
            self.size_label.setText("")
            return
        parts = []
        worst = 0
        for g in cs.GENDERS:
            n = cs.seal_list_size(self.data, self.rid, g)
            worst = max(worst, n)
            parts.append(f"{'male' if g == 'male' else 'female'}: up to {n}")
        text = (f"Second Seal list for this character ({', '.join(parts)} classes with promotions; "
                f"the game holds {cs.SEAL_LIST_MAX}).")
        if worst > cs.SEAL_LIST_MAX:
            text += " Too many: classes after the 64th are left out."
            self.size_label.setStyleSheet("color: #c0392b;")
        else:
            self.size_label.setStyleSheet("")
        if cs.uses_game_list(self.data):
            text += " Now: the game's own list."
        self.size_label.setText(text)

    # ------------------------------------------------------------------ edits
    def _on_changed(self, gender):
        if self._loading:
            return
        try:
            cs.set_avatar_classes(self.data, gender, self._checked(gender))
        except Exception:
            logging.exception("Could not save the avatar classes.")
        self._update_size()

    def _set_all(self, gender, on, only=None):
        lw = self.lists[gender]
        self._loading = True
        try:
            for i in range(lw.count()):
                it = lw.item(i)
                if only is None or only(it.data(Qt.UserRole)):
                    it.setCheckState(Qt.Checked if on else Qt.Unchecked)
        finally:
            self._loading = False
        self._on_changed(gender)

    def _tick_all(self, gender):
        keep = set(cs.playable_base_classes(self.data, gender))
        self._set_all(gender, True, only=lambda j: j in keep)

    def _reset(self):
        try:
            cs.reset_avatar_classes(self.data)
        except Exception:
            logging.exception("Could not reset the avatar classes.")
        self._fill()

    def set_target(self, rid):
        self.rid = rid
        show = False
        try:
            show = bool(rid) and cs.has_avatar_table(self.data) and cs.is_avatar(self.data, rid)
        except Exception:
            logging.exception("Could not check for an avatar.")
        self.setVisible(show)
        if show:
            self._fill()
