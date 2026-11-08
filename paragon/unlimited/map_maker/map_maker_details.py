"""Paragon Unlimited - Map Maker: everything about one unit, chests and villages, and events.

* UnitDetails: the right-hand panel, one page laid out like Paragon's spawn editor (Core Data,
  Spawn Flags, Items with their bitflags, AI, Misc. & Unknown) plus the unit's class, level,
  portrait, stats, skills and battle quotes. Every spawn field is kept; fields changed by hand
  win when the chapter is saved.
* SceneEditor, MakePictureDialog: scenes with full-screen pictures (telop_pictures.py).
* TreasureDialog: what a chest or a village / house gives.
* TalkDialog, TurnDialog, TileEventDialog: the chapter's events (chapter_events.py).
* EventsPanel: the lists of events in the left column.
"""
import copy
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from paragon.unlimited.map_maker import chapter_builder as cm
from paragon.unlimited.map_maker import chapter_events as ce

STAT_NAMES = ("HP", "Str", "Mag", "Skl", "Spd", "Lck", "Def", "Res")
ANYONE = "Anyone"


def search_combo(choices: List[Tuple[str, str]], current: str = "", empty: Optional[str] = None,
                 width: int = 200) -> QComboBox:
    """Combo box you can type in to search (matches anywhere in the name)."""
    box = QComboBox()
    box.setEditable(True)
    box.setInsertPolicy(QComboBox.NoInsert)
    box.setMinimumWidth(width)
    if empty is not None:
        box.addItem(empty, "")
    for name, key in choices:
        box.addItem(name, key)
    comp = QCompleter([box.itemText(i) for i in range(box.count())], box)
    comp.setCaseSensitivity(Qt.CaseInsensitive)
    comp.setFilterMode(Qt.MatchContains)
    box.setCompleter(comp)
    set_combo(box, current)
    return box


def set_combo(box: QComboBox, key: str):
    i = box.findData(key or "")
    if i < 0 and key:
        box.addItem(key, key)
        i = box.count() - 1
    box.blockSignals(True)
    box.setCurrentIndex(max(0, i))
    box.blockSignals(False)


def combo_value(box: QComboBox) -> str:
    """The key of what is picked, also when the name was typed and not picked from the list."""
    i = box.findText(box.currentText(), Qt.MatchFixedString)
    if i >= 0:
        return box.itemData(i) or ""
    return box.currentData() or ""


def _conversation_editor(speakers):
    from paragon.unlimited.map_maker.map_maker_window import ConversationEditor

    return ConversationEditor(speakers)


# ============================================================================= unit panel
def _hex(v) -> str:
    return " ".join(f"{int(b) & 0xFF:02X}" for b in (v or []))


def _unhex(text: str, length: int) -> Optional[list]:
    try:
        out = [int(x, 16) for x in text.replace(",", " ").split()]
    except ValueError:
        return None
    if len(out) != length or any(not 0 <= b <= 255 for b in out):
        return None
    return out


RAW_LEN = {"unknown_1": 4, "unknown_2": 4, "unknown_3": 1, "padding_?": 2, "end_section_1": 4,
           "end_section_2": 4, "end_section_3": 4, "end_section_4": 4, **{f"item_bitflags_{i}": 4 for i in range(1, 6)}}
AI_KEYS = ("action", "action_param", "mission", "mission_param", "attack", "attack_param", "move", "move_param")


def effective_raw(u: cm.Unit) -> dict:
    """The spawn fields as they will be saved: the unit's own values, the Map Maker's settings
    (always deployed, boss, behavior, drops) and then what was changed by hand."""
    r = {k: (copy.copy(v)) for k, v in (u.raw or {}).items()}
    for k, kind in cm.RAW_FIELDS.items():
        r.setdefault(k, "" if kind == "string" else 0 if kind == "int" else [0] * RAW_LEN.get(k, 4))
    if not u.raw:  # a new unit: what the Map Maker writes
        r["spawn_flags_1"] |= (0x40 if u.modes[0] else 0) | (0x80 if u.modes[1] else 0)
        r["spawn_flags_2"] |= 0x01 if u.modes[2] else 0
        if u.team == "join":
            r["spawn_flags_1"], r["spawn_flags_2"] = cm.JOIN_FLAGS
    if u.team == "player":
        r["spawn_flags_1"] = (r["spawn_flags_1"] | 0x02) if u.forced else (r["spawn_flags_1"] & ~0x02)
    if u.team in ("enemy", "ally"):
        r["spawn_flags_2"] = (r["spawn_flags_2"] | cm.BOSS_FLAG) if u.boss else (r["spawn_flags_2"] & ~cm.BOSS_FLAG)
    b = cm.BEHAVIORS.get(u.behavior)
    if b and u.team in ("enemy", "ally") and cm.behavior_of_ai(r["action"], r["mission"], r["attack"], r["move"], 0) != u.behavior:
        r["action"], r["mission"], r["attack"], r["move"] = b[:4]
        for k in ("action_param", "mission_param", "attack_param", "move_param"):
            r[k] = ""
        r["end_section_1"] = [b[4]] + list(r["end_section_1"] or [0, 0, 0, 0])[1:4]
    for i in range(1, 6):
        k = f"item_bitflags_{i}"
        have = i <= len(u.items)
        if not have:
            r[k] = [0, 0, 0, 0]
        elif i <= len(u.drops):
            if (list(r[k])[:1] == [1]) != bool(u.drops[i - 1]) or not any(r[k]):
                r[k] = list(cm.DROP_FLAGS if u.drops[i - 1] else cm.ITEM_FLAGS)
        elif not any(r[k]):
            r[k] = list(cm.ITEM_FLAGS)
    r.update(copy.deepcopy(u.raw_edits))
    return r


class BitFlags(QWidget):
    """Eight check boxes for one byte of flags (as in Paragon)."""

    changed = Signal(int)

    def __init__(self, names):
        super().__init__()
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setVerticalSpacing(0)
        self.boxes = []
        for i, n in enumerate(names):
            b = QCheckBox(n)
            b.toggled.connect(lambda _on: self.changed.emit(self.value()))
            g.addWidget(b, i // 2, i % 2)
            self.boxes.append(b)

    def value(self) -> int:
        return sum(1 << i for i, b in enumerate(self.boxes) if b.isChecked())

    def set_value(self, v: int):
        for i, b in enumerate(self.boxes):
            b.blockSignals(True)
            b.setChecked(bool(v & (1 << i)))
            b.blockSignals(False)


class UnitDetails(QScrollArea):
    """Everything about the selected unit on one page, laid out like Paragon's spawn editor
    (Core Data, Spawn Flags, Items, AI, Misc), plus the unit's class, stats, skills and battle
    quotes. Changes go straight into the unit (with undo)."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.maker: cm.ChapterMaker = win.maker
        self.unit: Optional[cm.Unit] = None
        self._loading = False
        self.items = self.maker.item_choices()
        self.skills = self.maker.skill_choices()
        self.characters = self.maker.character_choices()
        self.char_jobs = {pid: jid for _n, pid, jid in self.characters}
        self.faces = [(n, "FID_" + c) for n, c in self.maker.speakers() if c != cm.AVATAR_SPEAKER]
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.page = QWidget()
        self.lay = QVBoxLayout(self.page)
        self.lay.setContentsMargins(2, 2, 2, 2)
        self.setWidget(self.page)
        self.sections = {}
        self._quote_timer = QTimer(self)
        self._quote_timer.setSingleShot(True)
        self._quote_timer.setInterval(700)  # one undo step per pause in typing
        self._quote_timer.timeout.connect(self._quotes_changed)
        self._build_core()
        self._build_unit()
        self._build_stats()
        self._build_skills()
        self._build_items()
        self._build_flags()
        self._build_ai()
        self._build_quotes()
        self._build_misc()
        self.lay.addStretch(1)
        self.remove = QPushButton("Remove this unit")
        self.remove.clicked.connect(lambda: self.unit and self.win.remove_unit(self.unit))
        self.lay.addWidget(self.remove)
        self.show_unit(None)

    def _section(self, key, title) -> QFormLayout:
        box = QGroupBox(title)
        f = QFormLayout(box)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.lay.addWidget(box)
        self.sections[key] = box
        return f

    # ------------------------------------------------------------------ building
    def _build_core(self):
        f = self._section("core", "Core Data")
        self.info = QLabel("Click a unit on the map.")
        self.info.setWordWrap(True)
        f.addRow(self.info)
        self.character = search_combo([(n, p) for n, p, _j in self.characters], "", "A generic soldier")
        self.character.setToolTip("Make this unit one of the game's characters (they keep their own\n"
                                  "class, level, stats, skills and portrait), for example an enemy you can recruit.")
        self.start = search_combo([(n, p) for n, p, _j in self.characters], "", "You choose (a deploy slot)")
        self.start.setToolTip("Who starts on this tile. 'You choose' is a normal deploy slot.")
        self.team = QLabel()
        pos = QHBoxLayout()
        self.pos_x, self.pos_y = QSpinBox(), QSpinBox()
        for sb in (self.pos_x, self.pos_y):
            sb.setRange(0, 31)
            pos.addWidget(sb)
        self.forced = QCheckBox("Always deployed (can't be taken off the map)")
        self.forced.setToolTip("Spawn flag 'Forced Unit': the game always puts this character here, like Chrom.")
        f.addRow("Pid:", self.character)
        f.addRow("Starts here:", self.start)
        f.addRow("Team:", self.team)
        f.addRow("Coord:", pos)
        f.addRow(self.forced)
        self.note = QLabel()
        self.note.setWordWrap(True)
        f.addRow(self.note)
        self.core_form = f
        self.character.activated.connect(self._character_changed)
        self.character.lineEdit().editingFinished.connect(self._character_changed)
        self.start.activated.connect(self._start_changed)
        self.start.lineEdit().editingFinished.connect(self._start_changed)
        self.pos_x.valueChanged.connect(self._pos_changed)
        self.pos_y.valueChanged.connect(self._pos_changed)
        self.forced.toggled.connect(self._forced_changed)

    def _build_unit(self):
        f = self._section("unit", "Unit")
        self.cls = QComboBox()
        for name, jid in self.maker.enemy_classes():
            self.cls.addItem(name, jid)
        self.level = QSpinBox()
        self.level.setRange(1, 20)
        self.boss = QCheckBox("This is the boss")
        self.name = QLineEdit()
        self.name.setPlaceholderText("Shown when you look at the unit")
        self.face = search_combo(self.faces, "", "No portrait", 180)
        self.face.setToolTip("A portrait lets the unit speak (battle quotes, last words).")
        f.addRow("Class:", self.cls)
        f.addRow("Level:", self.level)
        f.addRow(self.boss)
        f.addRow("Name:", self.name)
        f.addRow("Portrait:", self.face)
        self.cls.activated.connect(self._class_changed)
        self.level.valueChanged.connect(self._level_changed)
        self.boss.toggled.connect(self._boss_changed)
        self.name.editingFinished.connect(self._name_changed)
        self.face.activated.connect(self._face_changed)

    def _build_stats(self):
        f = self._section("stats", "Stats")
        self.stats_own = QCheckBox("Set the stat bonus myself")
        self.stats_own.setToolTip("Off: the Map Maker's own bonus (bosses get a little more).")
        self.stats_own.toggled.connect(self._stats_toggled)
        f.addRow(self.stats_own)
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(0, 0, 0, 0)
        g.setVerticalSpacing(1)
        for c, t in enumerate(("", "Base", "Bonus", "Total", "Max")):
            g.addWidget(QLabel(f"<b>{t}</b>"), 0, c)
        self.stat_base, self.stat_spin, self.stat_total, self.stat_max = [], [], [], []
        for r, name in enumerate(STAT_NAMES, 1):
            g.addWidget(QLabel(name), r, 0)
            b, t, m = QLabel(), QLabel(), QLabel()
            s = QSpinBox()
            s.setRange(-30, 99)
            s.valueChanged.connect(self._stats_changed)
            for c, wid in enumerate((b, s, t, m), 1):
                g.addWidget(wid, r, c)
            self.stat_base.append(b)
            self.stat_spin.append(s)
            self.stat_total.append(t)
            self.stat_max.append(m)
        f.addRow(w)
        note = QLabel("<small>Base = the class's base stats. In the game the unit also gets level-ups for "
                      "its level and the Hard / Lunatic bonus.</small>")
        note.setWordWrap(True)
        f.addRow(note)

    def _build_skills(self):
        f = self._section("skills", "Skills")
        self.skill_boxes = []
        for i in range(5):
            box = search_combo(self.skills, "", "(none)", 180)
            box.activated.connect(self._skills_changed)
            box.lineEdit().editingFinished.connect(self._skills_changed)
            f.addRow(f"Skill {i + 1}:", box)
            self.skill_boxes.append(box)

    def _build_items(self):
        f = self._section("items", "Items")
        self.item_boxes, self.drop_boxes, self.bit_edits = [], [], []
        for i in range(5):
            box = search_combo(self.items, "", "(empty)", 160)
            drop = QCheckBox("Drops")
            drop.setToolTip("You get this item when you defeat the unit (bitflags 01 01 01 01).")
            bits = QLineEdit()
            bits.setMaximumWidth(92)
            bits.setToolTip(f"Item Bitflags {i + 1}")
            box.activated.connect(self._items_changed)
            box.lineEdit().editingFinished.connect(self._items_changed)
            drop.toggled.connect(lambda _on, k=i: self._drop_changed(k))
            bits.editingFinished.connect(lambda k=i: self._raw_hex_changed(f"item_bitflags_{k + 1}", self.bit_edits[k]))
            row = QHBoxLayout()
            row.addWidget(box, 1)
            row.addWidget(drop)
            row.addWidget(bits)
            f.addRow(f"Item {i + 1}:", row)
            self.item_boxes.append(box)
            self.drop_boxes.append(drop)
            self.bit_edits.append(bits)
        self.items_note = QLabel()
        self.items_note.setWordWrap(True)
        f.addRow(self.items_note)

    def _build_flags(self):
        f = self._section("flags", "Spawn Flags")
        self.condition = QLineEdit()
        self.condition.setToolTip("A script function that decides if the unit appears (e.g. ev::IsTiamoJoin).")
        self.flags1 = BitFlags(cm.SPAWN_FLAGS_1)
        self.flags2 = BitFlags(cm.SPAWN_FLAGS_2)
        self.flags3, self.flags4 = QSpinBox(), QSpinBox()
        for sb in (self.flags3, self.flags4):
            sb.setRange(0, 255)
        f.addRow("Spawn Condition:", self.condition)
        f.addRow("Spawn Flags 1:", self.flags1)
        f.addRow("Spawn Flags 2:", self.flags2)
        f.addRow("Spawn Flags 3:", self.flags3)
        f.addRow("Spawn Flags 4:", self.flags4)
        self.condition.editingFinished.connect(lambda: self._raw_set("spawn_condition", self.condition.text().strip()))
        self.flags1.changed.connect(lambda v: self._raw_set("spawn_flags_1", v))
        self.flags2.changed.connect(lambda v: self._raw_set("spawn_flags_2", v))
        self.flags3.valueChanged.connect(lambda v: self._raw_set("spawn_flags_3", v))
        self.flags4.valueChanged.connect(lambda v: self._raw_set("spawn_flags_4", v))

    def _build_ai(self):
        f = self._section("ai", "AI")
        self.behavior = QComboBox()
        for k, n in cm.BEHAVIOR_NAMES.items():
            self.behavior.addItem(n, k)
        self.behavior.setToolTip("A quick choice; the fields below show (and change) exactly what the unit does.")
        f.addRow("Behavior:", self.behavior)
        self.behavior.activated.connect(self._behavior_changed)
        self.ai = {}
        for k in AI_KEYS:
            box = QComboBox()
            box.setEditable(True)
            box.setInsertPolicy(QComboBox.NoInsert)
            if not k.endswith("_param"):
                box.addItems(cm.AI_VALUES.get(k, []))
            box.lineEdit().editingFinished.connect(lambda k=k: self._ai_changed(k))
            box.activated.connect(lambda _i, k=k: self._ai_changed(k))
            f.addRow(k.replace("_", " ").title() + ":", box)
            self.ai[k] = box
        self.ends = []
        for i in range(1, 5):
            e = QLineEdit()
            e.editingFinished.connect(lambda i=i: self._raw_hex_changed(f"end_section_{i}", self.ends[i - 1]))
            f.addRow(f"End Section {i}:", e)
            self.ends.append(e)

    def _build_quotes(self):
        f = self._section("quotes", "Battle quotes")
        self.quotes_note = QLabel()
        self.quotes_note.setWordWrap(True)
        f.addRow(self.quotes_note)
        self.quote_rows_box = QVBoxLayout()
        f.addRow(self.quote_rows_box)
        self.quote_rows = []
        add = QPushButton("+ Add a battle quote")
        add.clicked.connect(lambda: self._add_quote_row({"vs": "", "text": ""}, True))
        f.addRow(add)
        self.quote_add = add

    def _build_misc(self):
        f = self._section("misc", "Misc. && Unknown")
        self.misc = {}
        for k, label in (("unknown_1", "Unknown 1"), ("unknown_2", "Unknown 2"), ("unknown_3", "Unknown 3"),
                         ("padding_?", "Padding ?")):
            e = QLineEdit()
            e.editingFinished.connect(lambda k=k, e=e: self._raw_hex_changed(k, e))
            f.addRow(label + ":", e)
            self.misc[k] = e

    # ------------------------------------------------------------------ showing
    def _row_visible(self, form: QFormLayout, wid, on: bool):
        wid.setVisible(on)
        lab = form.labelForField(wid)
        if lab is not None:
            lab.setVisible(on)

    def show_unit(self, u: Optional[cm.Unit]):
        if self._quote_timer.isActive():  # keep what was just typed
            self._quote_timer.stop()
            self._quotes_changed()
        self.unit = u
        self._loading = True
        try:
            self._show(u)
        finally:
            self._loading = False

    def _show(self, u):
        enemy = u is not None and u.team in ("enemy", "ally")
        player = u is not None and u.team == "player"
        join = u is not None and u.team == "join"
        is_char = enemy and bool(u.character)
        self._row_visible(self.core_form, self.character, enemy)
        self._row_visible(self.core_form, self.start, player)
        self.forced.setVisible(player)
        for key, on in (("unit", enemy), ("stats", enemy and not is_char), ("skills", enemy and not is_char),
                        ("items", u is not None), ("flags", u is not None), ("ai", enemy or join),
                        ("quotes", enemy), ("misc", u is not None)):
            self.sections[key].setVisible(on)
        self.remove.setEnabled(u is not None and not u.forced)
        if u is None:
            self.info.setText("Click a unit on the map to see and change it.")
            self.note.setText("")
            self.team.setText("")
            return
        self.info.setText(f"<b>{self.win.describe(u)}</b><br>Tile: {self.win.canvas.tile_name(u.x, u.y)}")
        self.team.setText({"player": "Player", "enemy": "Enemy", "ally": "Ally", "join": "Joins your army (Player)"}
                          .get(u.team, u.team))
        g = self.win.canvas.grid
        self.pos_x.setMaximum((g[0] if g else 32) - 1)
        self.pos_y.setMaximum((g[1] if g else 32) - 1)
        self.pos_x.setValue(u.x)
        self.pos_y.setValue(u.y)
        note = ""
        if enemy:
            set_combo(self.character, u.character)
            i = self.cls.findData(u.job)
            if i < 0:
                self.cls.addItem(self.maker.class_name(u.job), u.job)
                i = self.cls.count() - 1
            self.cls.setCurrentIndex(i)
            self.level.setValue(max(1, min(20, u.level)))
            self.boss.setChecked(u.boss)
            self.name.setText(u.name)
            set_combo(self.face, u.face)
            for wid in (self.cls, self.level, self.name, self.face):
                wid.setEnabled(not is_char)
            if is_char:
                note = ("One of the game's characters: they keep their own class, level, stats, skills and "
                        "portrait. Add a Talk event (left, Events) to recruit them.")
        elif player:
            set_combo(self.start, u.pid)
            self.forced.setChecked(u.forced)
            note = "Pick who starts here, or leave 'You choose' for a normal deploy slot."
        elif join:
            note = "Joins your army at the start of turn 1."
        self.note.setText(note)
        self.note.setVisible(bool(note))
        self._show_stats(u)
        self._show_items(u)
        for i in range(5):
            set_combo(self.skill_boxes[i], u.skills[i] if i < len(u.skills) else "")
        self._show_raw(u)
        self._show_quotes(u)

    def _show_raw(self, u):
        r = effective_raw(u)
        self.condition.setText(r["spawn_condition"])
        self.flags1.set_value(r["spawn_flags_1"])
        self.flags2.set_value(r["spawn_flags_2"])
        self.flags3.setValue(r["spawn_flags_3"])
        self.flags4.setValue(r["spawn_flags_4"])
        i = self.behavior.findData(u.behavior if u.behavior in cm.BEHAVIOR_NAMES else "custom")
        self.behavior.setCurrentIndex(max(0, i))
        for k, box in self.ai.items():
            box.setEditText(r[k])
        for i, e in enumerate(self.ends, 1):
            e.setText(_hex(r[f"end_section_{i}"]))
        for k, e in self.misc.items():
            e.setText(_hex(r[k]))
        for i, e in enumerate(self.bit_edits, 1):
            e.setText(_hex(r[f"item_bitflags_{i}"]))

    def _show_stats(self, u):
        base, top = self.maker.class_stats(u.job) if u.job else ([0] * 8, [0] * 8)
        own = u.stats is not None
        self.stats_own.setChecked(own)
        vals = list(u.stats) if own else [0] * 8
        for i in range(8):
            self.stat_base[i].setText(str(base[i]))
            self.stat_spin[i].setValue(vals[i])
            self.stat_spin[i].setEnabled(own)
            self.stat_total[i].setText(f"<b>{base[i] + vals[i]}</b>")
            self.stat_max[i].setText(str(top[i]))

    def _show_items(self, u):
        for i in range(5):
            set_combo(self.item_boxes[i], u.items[i] if i < len(u.items) else "")
            self.drop_boxes[i].setChecked(bool(u.drops[i]) if i < len(u.drops) else False)
            self.drop_boxes[i].setEnabled(u.team in ("enemy", "ally") and i < len(u.items))
        self.items_note.setText("<small>A unit that joins your army brings these items.</small>" if u.team == "join"
                                else "<small>The game shows an item that drops in green.</small>")

    def _show_quotes(self, u):
        for row in self.quote_rows:
            row[2].deleteLater()
        self.quote_rows = []
        made = self.win.made_here
        for q in u.quotes:
            self._add_quote_row(q, False)
        has_face = bool(u.face or u.character)
        txt = "What the unit says before a fight: with anyone, or with one character. Each quote is said once."
        if not made:
            txt = "<b>Battle quotes can be added to chapters made with the Map Maker.</b>"
        elif not has_face:
            txt += "<br><span style='color:#d33'>Give the unit a portrait (Unit) so it can speak.</span>"
        self.quotes_note.setText(txt)
        self.quote_add.setEnabled(made)

    def _add_quote_row(self, q: dict, edited: bool):
        row = QWidget()
        h = QVBoxLayout(row)
        h.setContentsMargins(0, 4, 0, 4)
        top = QHBoxLayout()
        vs = search_combo([(n, p) for n, p, _j in self.characters], q.get("vs", ""), "Anyone", 150)
        rm = QToolButton()
        rm.setText("✕")
        rm.setToolTip("Remove this quote")
        top.addWidget(QLabel("Against:"))
        top.addWidget(vs, 1)
        top.addWidget(rm)
        text = QPlainTextEdit(q.get("text", ""))
        text.setPlaceholderText("What they say... (Enter = new row, empty row = new text box)")
        text.setTabChangesFocus(True)
        text.setFixedHeight(text.fontMetrics().lineSpacing() * 3 + 12)
        h.addLayout(top)
        h.addWidget(text)
        entry = (vs, text, row)
        self.quote_rows.append(entry)
        self.quote_rows_box.addWidget(row)
        vs.activated.connect(self._quotes_changed)
        text.textChanged.connect(self._quote_timer.start)
        rm.clicked.connect(lambda: self._remove_quote(entry))
        row.setEnabled(self.win.made_here)
        if edited:
            text.setFocus()

    def _remove_quote(self, entry):
        if entry in self.quote_rows:
            self.quote_rows.remove(entry)
            entry[2].deleteLater()
            self._quotes_changed()

    # ------------------------------------------------------------------ editing
    def _changed(self, u, refresh):
        self.win.unit_changed(u, refresh)
        if not refresh:
            self._loading = True
            try:
                self._show_raw(u)
            finally:
                self._loading = False

    def _set(self, attr, value, refresh=False):
        u = self.unit
        if self._loading or u is None or getattr(u, attr) == value:
            return
        self.win.before_change("Change unit")
        setattr(u, attr, value)
        self._changed(u, refresh)

    def _raw_set(self, key, value):
        """A Spawn Flags / AI / Misc field changed by hand."""
        u = self.unit
        if self._loading or u is None or effective_raw(u).get(key) == value:
            return
        self.win.before_change("Change spawn")
        if key in AI_KEYS or key.startswith("end_section"):
            r = effective_raw(u)  # the AI as it is now becomes the unit's own, then this field changes
            for k in AI_KEYS + ("end_section_1",):
                u.raw_edits.setdefault(k, copy.deepcopy(r[k]))
        u.raw_edits[key] = value
        # keep the Map Maker's own settings in step with the flags
        if key == "spawn_flags_1" and u.team == "player":
            u.forced = bool(value & 0x02)
        if key == "spawn_flags_2" and u.team in ("enemy", "ally"):
            u.boss = bool(value & cm.BOSS_FLAG)
        if key in ("action", "mission", "attack", "move"):
            r = effective_raw(u)
            u.behavior = cm.behavior_of_ai(r["action"], r["mission"], r["attack"], r["move"], 0)
        if key.startswith("item_bitflags_"):
            i = int(key[-1]) - 1
            if i < len(u.items):
                drops = list(u.drops) + [False] * (len(u.items) - len(u.drops))
                drops[i] = list(value)[:1] == [1]
                u.drops = drops[: len(u.items)]
        self._loading = True
        try:
            self._show(u)
        finally:
            self._loading = False
        self.win.unit_changed(u, False)

    def _raw_hex_changed(self, key, edit: QLineEdit):
        u = self.unit
        if self._loading or u is None:
            return
        v = _unhex(edit.text(), RAW_LEN.get(key, 4))
        if v is None:
            self.win.statusBar().showMessage(f"{key}: type {RAW_LEN.get(key, 4)} hex numbers, e.g. 00 01 01 01.", 5000)
            edit.setText(_hex(effective_raw(u)[key]))
            return
        self._raw_set(key, v)

    def _ai_changed(self, key):
        if self._loading or self.unit is None:
            return
        self._raw_set(key, self.ai[key].currentText().strip())

    def _behavior_changed(self, *_):
        u = self.unit
        k = self.behavior.currentData()
        if self._loading or u is None or k == u.behavior:
            return
        self.win.before_change("Change unit")
        u.behavior = k
        if k != "custom":
            for key in AI_KEYS + ("end_section_1",):
                u.raw_edits.pop(key, None)
        self._changed(u, False)

    def _pos_changed(self, *_):
        u = self.unit
        if self._loading or u is None:
            return
        x, y = self.pos_x.value(), self.pos_y.value()
        if (x, y) == (u.x, u.y):
            return
        if not self.win.canvas.can_place(x, y, u):
            self.win.statusBar().showMessage("The unit can't stand there (or another unit is there).", 4000)
            self._loading = True
            self.pos_x.setValue(u.x)
            self.pos_y.setValue(u.y)
            self._loading = False
            return
        self.win.before_change("Move unit")
        u.x, u.y = x, y
        self._changed(u, False)

    def _forced_changed(self, on):
        u = self.unit
        if self._loading or u is None or bool(on) == u.forced:
            return
        self.win.before_change("Change unit")
        u.forced = bool(on)
        if "spawn_flags_1" in u.raw_edits:
            f = u.raw_edits["spawn_flags_1"]
            u.raw_edits["spawn_flags_1"] = (f | 0x02) if on else (f & ~0x02)
        self._changed(u, False)

    def _character_changed(self, *_):
        u = self.unit
        if self._loading or u is None or u.team not in ("enemy", "ally"):
            return
        pid = combo_value(self.character)
        if pid == u.character:
            return
        jid = self.char_jobs.get(pid, "") if pid else u.job
        if pid and jid and not cm.ChapterMaker.can_stand(self.win.canvas.grid, u.x, u.y, jid):
            self.win.statusBar().showMessage("That character can't stand on this tile. Move the unit first.", 5000)
            self.show_unit(u)
            return
        self.win.before_change("Change unit")
        u.character = pid
        if pid:
            u.pid = pid
            u.job = jid or u.job
            u.name, u.face = "", ""
            u.skills, u.stats = [], None
        else:
            u.pid = ""
        self.win.unit_changed(u, True)

    def _class_changed(self, *_):
        u = self.unit
        if self._loading or u is None:
            return
        new = self.cls.currentData()
        if new == u.job:
            return
        if not cm.ChapterMaker.can_stand(self.win.canvas.grid, u.x, u.y, new):
            self.win.statusBar().showMessage("That class can't stand on this tile. Move the unit first.", 5000)
            self.show_unit(u)
            return
        self.win.before_change("Change unit")
        u.job = new
        u.items = cm.items_for(new, self.win.current_tier(), u.boss)
        u.drops = []
        for i in range(1, 6):
            u.raw_edits.pop(f"item_bitflags_{i}", None)
        self.win.unit_changed(u, True)

    def _level_changed(self, v):
        self._set("level", int(v))

    def _boss_changed(self, on):
        u = self.unit
        if self._loading or u is None or bool(on) == u.boss:
            return
        self.win.before_change("Change unit")
        u.boss = bool(on)
        u.items = cm.items_for(u.job, self.win.current_tier(), u.boss)
        u.drops = []
        if "spawn_flags_2" in u.raw_edits:
            f = u.raw_edits["spawn_flags_2"]
            u.raw_edits["spawn_flags_2"] = (f | cm.BOSS_FLAG) if on else (f & ~cm.BOSS_FLAG)
        if u.boss and self.win.made_here:
            u.name = u.name or self.win.boss_name.text()
            u.face = u.face or (self.win.boss_face.currentData() or "")
        self.win.unit_changed(u, True)

    def _name_changed(self):
        u = self.unit
        if self._loading or u is None or self.name.text().strip() == u.name:
            return
        self.win.before_change("Change unit")
        u.name = self.name.text().strip()
        u.own = u.own or bool(u.name)
        self._changed(u, False)

    def _face_changed(self, *_):
        u = self.unit
        fid = combo_value(self.face)
        if self._loading or u is None or fid == u.face:
            return
        self.win.before_change("Change unit")
        u.face = fid
        u.own = u.own or bool(fid)
        self.win.unit_changed(u, True)

    def _start_changed(self, *_):
        u = self.unit
        if self._loading or u is None or u.team != "player":
            return
        pid = combo_value(self.start)
        if pid == u.pid:
            return
        if pid and any(o is not u and o.pid == pid and o.team in ("player", "join") for o in self.win.plan.units):
            self.win.statusBar().showMessage("That character already starts somewhere on this map.", 5000)
            self.show_unit(u)
            return
        self.win.before_change("Change unit")
        u.pid = pid
        u.job = self.char_jobs.get(pid, "") if pid else ""
        if not pid:
            u.forced = False
        self.win.unit_changed(u, True)

    def _stats_toggled(self, on):
        u = self.unit
        if self._loading or u is None:
            return
        self.win.before_change("Change unit")
        u.stats = [s.value() for s in self.stat_spin] if on else None
        self.win.unit_changed(u, True)

    def _stats_changed(self, *_):
        u = self.unit
        if self._loading or u is None or u.stats is None:
            return
        vals = [s.value() for s in self.stat_spin]
        if vals == list(u.stats):
            return
        self.win.before_change("Change unit")
        u.stats = vals
        base, _top = self.maker.class_stats(u.job)
        for i in range(8):
            self.stat_total[i].setText(f"<b>{base[i] + vals[i]}</b>")
        self.win.unit_changed(u, False)

    def _items_changed(self, *_):
        u = self.unit
        if self._loading or u is None:
            return
        items, drops = [], []
        for box, drop in zip(self.item_boxes, self.drop_boxes):
            iid = combo_value(box)
            if iid:
                items.append(iid)
                drops.append(drop.isChecked())
        if items == list(u.items) and drops == list(u.drops)[: len(items)]:
            return
        self.win.before_change("Change items")
        u.items = items
        u.drops = drops
        for i in range(1, 6):
            u.raw_edits.pop(f"item_bitflags_{i}", None)
        self._loading = True
        try:
            self._show_items(u)
        finally:
            self._loading = False
        self._changed(u, False)

    def _drop_changed(self, i):
        u = self.unit
        if self._loading or u is None or i >= len(u.items):
            return
        u.raw_edits.pop(f"item_bitflags_{i + 1}", None)
        self._items_changed()

    def _skills_changed(self, *_):
        u = self.unit
        if self._loading or u is None:
            return
        skills = []
        for box in self.skill_boxes:
            k = combo_value(box)
            if k and k not in skills:
                skills.append(k)
        if skills == list(u.skills):
            return
        self.win.before_change("Change skills")
        u.skills = skills
        u.own = u.own or bool(skills)
        self.win.unit_changed(u, False)

    def _quotes_changed(self, *_):
        u = self.unit
        if self._loading or u is None:
            return
        quotes = [{"vs": combo_value(vs), "text": t.toPlainText().strip()} for vs, t, _r in self.quote_rows]
        if quotes == list(u.quotes):
            return
        self.win.before_change("Battle quotes")
        u.quotes = quotes
        u.own = u.own or bool(quotes)
        self.win.unit_changed(u, False)


# ============================================================================= dialogs
class _Dialog(QDialog):
    def __init__(self, title: str, parent):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(620)
        self.form = QFormLayout()
        self.lay = QVBoxLayout(self)
        self.lay.addLayout(self.form)

    def talk_tabs(self, maker, e, cid: str, label: str):
        """Tabs: the conversation, the scene (pictures) and the conversation after the scene."""
        self.resize(780, 760)
        tabs = QTabWidget()
        self.talk = _conversation_editor(maker.speakers())
        self.talk.set_lines(e.lines)
        self.scene = SceneEditor(maker, cid)
        self.scene.set_steps(getattr(e, "scene", []) or [])
        self.after = _conversation_editor(maker.speakers())
        self.after.set_lines(getattr(e, "after", []) or [])
        for w, title in ((self.talk, label), (self.scene, "Scene (pictures)"), (self.after, "After the scene")):
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setWidget(w)
            tabs.addTab(sc, title)
        self.tabs = tabs
        self.lay.addWidget(tabs, 1)

    def talk_result(self, e):
        e.lines = self.talk.lines()
        e.scene = self.scene.result_steps()
        e.after = self.after.lines()
        return e

    def finish(self, removable: bool = False):
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.removed = False
        if removable:
            rm = bb.addButton("Remove", QDialogButtonBox.DestructiveRole)
            rm.clicked.connect(self._remove)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.lay.addWidget(bb)

    def _remove(self):
        self.removed = True
        self.accept()


# ============================================================================= scenes (pictures)
SOUNDS = [("No sound", ""), ("Changing clothes (*fwip*, as in the DLC)", "SE_BTL_EFF_CHANGE_FOOT2"),
          ("Hit", "SE_EVT_DAMAGE1"), ("Jewel shine", "SE_EVT_JEWEL1"), ("Headache", "SE_EVT_HEADACHE1"),
          ("Explosion", "SE_EVT_EXPLOSION1"), ("Pegasus", "SE_EVT_PEGASUS1")]


def _pixmap(rgba_info, size=150):
    from PySide6.QtGui import QImage, QPixmap

    if not rgba_info:
        return None
    w, h, rgba = rgba_info
    img = QImage(rgba, w, h, w * 4, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class MakePictureDialog(_Dialog):
    """Your own scene picture: your character art over your background, with the animation of
    the game's confession pictures (telop_pictures.py)."""

    def __init__(self, maker, cid: str, parent=None):
        super().__init__("Make a scene picture", parent)
        self.maker = maker
        self.cid = cid
        self.chara_path = self.bg_path = ""
        intro = QLabel(
            "Pick your <b>character picture</b> (a PNG with a transparent background, like a portrait or an "
            "illustration; it is scaled to 512 x 512) and, if you like, a <b>background</b> (scaled to "
            "256 x 256; without one the game's room stays). It plays like the game's support S-rank "
            "pictures.")
        intro.setWordWrap(True)
        self.form.addRow(intro)
        self.chara_btn = QPushButton("Choose character picture...")
        self.bg_btn = QPushButton("Choose background (optional)...")
        self.chara_btn.clicked.connect(lambda: self._pick("chara"))
        self.bg_btn.clicked.connect(lambda: self._pick("bg"))
        self.form.addRow("Character:", self.chara_btn)
        self.form.addRow("Background:", self.bg_btn)
        self.preview = QLabel()
        self.preview.setMinimumSize(256, 256)
        self.preview.setAlignment(Qt.AlignCenter)
        self.form.addRow(self.preview)
        self.name = ""
        self.finish(False)

    def _pick(self, which):
        from PySide6.QtWidgets import QFileDialog

        path, _f = QFileDialog.getOpenFileName(self, "Choose a picture", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        if which == "chara":
            self.chara_path = path
            self.chara_btn.setText(path.replace("\\", "/").split("/")[-1])
        else:
            self.bg_path = path
            self.bg_btn.setText(path.replace("\\", "/").split("/")[-1])
        self._show_preview()

    def _show_preview(self):
        try:
            from PIL import Image

            out = Image.new("RGBA", (256, 256), (20, 20, 30, 255))
            if self.bg_path:
                out.alpha_composite(Image.open(self.bg_path).convert("RGBA").resize((256, 256)))
            if self.chara_path:
                out.alpha_composite(Image.open(self.chara_path).convert("RGBA").resize((256, 256)))
            pix = _pixmap((256, 256, out.tobytes()), 256)
            if pix is not None:
                self.preview.setPixmap(pix)
        except Exception:
            self.preview.setText("Could not open that picture.")

    def accept(self):
        if not self.chara_path:
            self.preview.setText("Choose the character picture first.")
            return
        try:
            from PIL import Image

            from paragon.unlimited.map_maker import telop_pictures as tp

            chara = Image.open(self.chara_path).convert("RGBA")
            bg = Image.open(self.bg_path).convert("RGBA") if self.bg_path else None
            files = self.maker.edits.files
            raw = tp.make_picture(self.maker.gd, chara, bg, pending=files)
            self.name = tp.next_name(self.maker.gd, self.cid, self.maker.output_path, files)
            files[tp.path_of(self.name)] = raw
        except Exception as e:
            import logging

            logging.exception("Make picture")
            self.preview.setText(f"Could not make the picture: {e}")
            return
        super().accept()


class SceneEditor(QWidget):
    """The steps of a scene: a picture, an optional sound, and what is said while it shows."""

    def __init__(self, maker, cid: str):
        super().__init__()
        self.maker = maker
        self.cid = cid
        self.steps = []  # (picture combo, sound combo, conversation, frame, preview)
        lay = QVBoxLayout(self)
        intro = QLabel(
            "<small>A scene fades the map out and shows full-screen pictures one after another, each with its "
            "own conversation (like Cordelia's swimsuit scene in the Hot Spring Scramble DLC). Leave this empty "
            "for no scene.</small>")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.box = QVBoxLayout()
        lay.addLayout(self.box)
        add = QPushButton("+ Add a picture step")
        add.clicked.connect(lambda: self.add_step(ce.SceneStep()))
        lay.addWidget(add, 0, Qt.AlignLeft)
        lay.addStretch(1)

    def _choices(self):
        from paragon.unlimited.map_maker import telop_pictures as tp

        return tp.choices(self.maker.gd, self.maker.output_path, self.maker.edits.files)

    def set_steps(self, steps):
        for st in self.steps:
            st[3].deleteLater()
        self.steps = []
        for st in steps:
            self.add_step(st)

    def add_step(self, st):
        frame = QGroupBox(f"Step {len(self.steps) + 1}")
        v = QVBoxLayout(frame)
        top = QHBoxLayout()
        pic = search_combo(self._choices(), st.picture, "Keep the picture of the step before", 260)
        own = QPushButton("Make my own picture...")
        rm = QToolButton()
        rm.setText("✕")
        rm.setToolTip("Remove this step")
        top.addWidget(QLabel("Picture:"))
        top.addWidget(pic, 1)
        top.addWidget(own)
        top.addWidget(rm)
        v.addLayout(top)
        mid = QHBoxLayout()
        preview = QLabel()
        preview.setFixedSize(150, 150)
        preview.setAlignment(Qt.AlignCenter)
        preview.setStyleSheet("background: #111; color: #aaa;")
        sound = QComboBox()
        sound.setEditable(True)
        for n, k in SOUNDS:
            sound.addItem(n, k)
        set_combo(sound, st.sound)
        right = QVBoxLayout()
        right.addWidget(QLabel("Sound before the talk:"))
        right.addWidget(sound)
        right.addStretch(1)
        mid.addWidget(preview)
        mid.addLayout(right, 1)
        v.addLayout(mid)
        talk = _conversation_editor(self.maker.speakers())
        talk.set_lines(st.lines)
        v.addWidget(talk)
        entry = (pic, sound, talk, frame, preview)
        self.steps.append(entry)
        self.box.addWidget(frame)
        pic.activated.connect(lambda _i: self._preview(entry))
        pic.lineEdit().editingFinished.connect(lambda: self._preview(entry))
        own.clicked.connect(lambda: self._make_own(entry))
        rm.clicked.connect(lambda: self._remove(entry))
        self._preview(entry)

    def _preview(self, entry):
        from paragon.unlimited.map_maker import telop_pictures as tp

        name = combo_value(entry[0])
        pix = _pixmap(tp.preview(self.maker.gd, name, self.maker.edits.files)) if name else None
        if pix is not None:
            entry[4].setPixmap(pix)
        else:
            entry[4].clear()
            entry[4].setText("(the picture\nbefore)" if not name else "(no preview)")

    def _make_own(self, entry):
        d = MakePictureDialog(self.maker, self.cid, self)
        if d.exec() != QDialog.Accepted or not d.name:
            return
        from paragon.unlimited.map_maker import telop_pictures as tp

        for pic, *_rest in self.steps:  # every step can use the new picture
            pic.addItem(f"Your picture: {d.name[len(tp.PREFIX):]}", d.name)
        set_combo(entry[0], d.name)
        self._preview(entry)

    def _remove(self, entry):
        if entry in self.steps:
            self.steps.remove(entry)
            entry[3].deleteLater()
            for i, st in enumerate(self.steps, 1):
                st[3].setTitle(f"Step {i}")

    def result_steps(self):
        out = []
        for pic, sound, talk, _f, _p in self.steps:
            out.append(ce.SceneStep(combo_value(pic), talk.lines(), combo_value(sound)))
        return [s for s in out if s.picture or s.lines or s.sound]


class TreasureDialog(_Dialog):
    def __init__(self, maker: cm.ChapterMaker, t: ce.Treasure, removable: bool, parent=None):
        super().__init__(f"{'Chest' if t.is_chest else 'Village / house'} at ({t.x}, {t.y})", parent)
        self.t = copy.deepcopy(t)
        self.kind = QComboBox()
        self.kind.addItem("Chest (needs a key, a Thief or Locktouch)", ce.CHEST_KIND)
        self.kind.addItem("Village / house (visit it: talk, then a gift)", ce.VILLAGE_KIND)
        self.kind.setCurrentIndex(0 if t.is_chest else 1)
        self.item = search_combo(maker.item_choices(), t.item, "(no item)")
        self.gold = QSpinBox()
        self.gold.setRange(0, 99999)
        self.gold.setSingleStep(100)
        self.gold.setValue(int(t.gold))
        self.form.addRow("What it is:", self.kind)
        self.form.addRow("Item:", self.item)
        self.form.addRow("Gold:", self.gold)
        self.talk_label = QLabel("<b>What the villager says</b> (leave empty for no talk):")
        self.talk = _conversation_editor(maker.speakers())
        self.talk.set_lines(t.lines)
        self.lay.addWidget(self.talk_label)
        self.lay.addWidget(self.talk)
        self.kind.currentIndexChanged.connect(self._kind)
        self._kind()
        self.finish(removable)

    def _kind(self, *_):
        village = self.kind.currentData() == ce.VILLAGE_KIND
        self.talk_label.setVisible(village)
        self.talk.setVisible(village)

    def result_treasure(self) -> ce.Treasure:
        t = self.t
        kind = self.kind.currentData()
        if kind != t.kind:
            t.kind = kind
            t.model = ce.CHEST_MODEL if kind == ce.CHEST_KIND else ce.VILLAGE_MODEL
        t.item = combo_value(self.item)
        t.gold = self.gold.value()
        t.lines = self.talk.lines() if kind == ce.VILLAGE_KIND else []
        return t


class TalkDialog(_Dialog):
    def __init__(self, maker, e: ce.TalkEvent, chars, removable: bool, parent=None, cid: str = ""):
        super().__init__("Talk event", parent)
        self.e = copy.deepcopy(e)
        self.a = search_combo(chars, e.a, None)
        self.b = search_combo(chars, e.b, None)
        self.recruit = QCheckBox("They join your army after the talk (recruit)")
        self.recruit.setChecked(e.recruit)
        self.form.addRow("Who talks (has the Talk command):", self.a)
        self.form.addRow("Talks to:", self.b)
        self.form.addRow(self.recruit)
        note = QLabel("<small>Both must be on the map: put the one to recruit on the map as an enemy and pick "
                      "them in Unit → Character. The talk happens once.</small>")
        note.setWordWrap(True)
        self.form.addRow(note)
        self.talk_tabs(maker, e, cid, "Conversation")
        self.finish(removable)

    def result_event(self) -> ce.TalkEvent:
        self.e.a, self.e.b = combo_value(self.a), combo_value(self.b)
        self.e.recruit = self.recruit.isChecked()
        return self.talk_result(self.e)


class TurnDialog(_Dialog):
    def __init__(self, maker, e: ce.TurnEvent, removable: bool, parent=None, cid: str = ""):
        super().__init__("Turn conversation", parent)
        self.e = copy.deepcopy(e)
        self.turn = QSpinBox()
        self.turn.setRange(2, 99)
        self.turn.setValue(max(2, int(e.turn)))
        self.form.addRow("At the start of player turn:", self.turn)
        self.form.addRow(QLabel("<small>Turn 1 is the 'Before the battle' story.</small>"))
        self.talk_tabs(maker, e, cid, "Conversation")
        self.finish(removable)

    def result_event(self) -> ce.TurnEvent:
        self.e.turn = self.turn.value()
        return self.talk_result(self.e)


class TileEventDialog(_Dialog):
    def __init__(self, maker, e: ce.TileEvent, chars, grid, removable: bool, parent=None, cid: str = ""):
        super().__init__("Tile event", parent)
        self.e = copy.deepcopy(e)
        w, h = (grid[0], grid[1]) if grid else (32, 32)
        self.x = QSpinBox()
        self.x.setRange(0, w - 1)
        self.x.setValue(e.x)
        self.y = QSpinBox()
        self.y.setRange(0, h - 1)
        self.y.setValue(e.y)
        pos = QHBoxLayout()
        pos.addWidget(QLabel("x"))
        pos.addWidget(self.x)
        pos.addWidget(QLabel("y"))
        pos.addWidget(self.y)
        pos.addStretch(1)
        self.who = search_combo(chars, e.who, "Any of your units")
        self.item = search_combo(maker.item_choices(), e.item, "(no item)")
        self.gold = QSpinBox()
        self.gold.setRange(0, 99999)
        self.gold.setSingleStep(100)
        self.gold.setValue(int(e.gold))
        self.form.addRow("Tile:", pos)
        self.form.addRow("Who must wait on it:", self.who)
        self.form.addRow("Then they get item:", self.item)
        self.form.addRow("And gold:", self.gold)
        self.flash = QSpinBox()
        self.flash.setRange(0, 20)
        self.flash.setSpecialValueText("Never")
        self.flash.setSuffix(" turns")
        self.flash.setPrefix("every ")
        self.flash.setValue(int(getattr(e, "flash_every", 5)) if getattr(e, "sparkle", True) else 0)
        self.flash.setToolTip("At the start of your turn the camera goes to the tile and a red sparkle flashes\n"
                              "there for a moment, until the event happens. 1 = every turn, 5 = turns 1, 6, 11...\n"
                              "(The game only keeps its own item-tile sparkles on the map all the time.)")
        self.form.addRow("Show the tile (red flash):", self.flash)
        note = QLabel("<small>When that unit ends its move on the tile (Wait), the conversation plays and the "
                      "gift is given, once. Like the DLC maps where a character finds something.</small>")
        note.setWordWrap(True)
        self.form.addRow(note)
        self.talk_tabs(maker, e, cid, "Conversation on the map")
        self.finish(removable)

    def result_event(self) -> ce.TileEvent:
        e = self.e
        e.x, e.y = self.x.value(), self.y.value()
        e.who = combo_value(self.who)
        e.item = combo_value(self.item)
        e.gold = self.gold.value()
        e.flash_every = self.flash.value()
        e.sparkle = e.flash_every > 0
        return self.talk_result(e)


# ============================================================================= events (left column)
class EventsPanel(QGroupBox):
    """Talk / recruit events, turn conversations, tile events, chests and villages."""

    changed = Signal()

    def __init__(self, win):
        super().__init__("6. Events")
        self.win = win
        self.maker = win.maker
        chars = self.maker.character_choices()
        self.chars = [(n, p) for n, p, _j in chars]
        self.names = {p: n for n, p in self.chars}
        self.item_names = {k: n for n, k in self.maker.item_choices()}
        v = QVBoxLayout(self)
        intro = QLabel("<small>Every event happens once. Double-click one to change it.</small>")
        intro.setWordWrap(True)
        v.addWidget(intro)
        self.lists = {}
        for kind, title, tip in (
            ("talks", "Talk / recruit", "Two characters talk (the Talk command). Can recruit."),
            ("turn_events", "Turn conversations", "A conversation at the start of a turn."),
            ("tile_events", "Tile events", "Take a unit (or one character) to a tile: a conversation and a gift.\n"
                                           "You can also use the ! Event tile tool on the map."),
            ("treasures", "Chests and villages", "What chests and villages give. Use the Chest / village tool on the map\n"
                                                 "to add one."),
        ):
            box = QGroupBox(title)
            box.setToolTip(tip)
            bl = QVBoxLayout(box)
            lst = QListWidget()
            lst.setMaximumHeight(110)
            lst.itemDoubleClicked.connect(lambda _i, k=kind: self.edit(k))
            bl.addWidget(lst)
            row = QHBoxLayout()
            if kind != "treasures":
                add = QPushButton("+ Add")
                add.clicked.connect(lambda _c=False, k=kind: self.add(k))
                row.addWidget(add)
            ed = QPushButton("Change")
            ed.clicked.connect(lambda _c=False, k=kind: self.edit(k))
            rm = QPushButton("Remove")
            rm.clicked.connect(lambda _c=False, k=kind: self.remove(k))
            row.addWidget(ed)
            row.addWidget(rm)
            row.addStretch(1)
            bl.addLayout(row)
            v.addWidget(box)
            self.lists[kind] = (lst, box)

    def set_made(self, made: bool):
        for kind, (_lst, box) in self.lists.items():
            box.setVisible(made or kind == "treasures")
        self.setTitle("6. Events" if made else "Chests and villages")

    # ------------------------------------------------------------------ listing
    def _who(self, pid):
        return self.names.get(pid, pid) if pid else ANYONE

    def _label(self, kind, e) -> str:
        if kind == "talks":
            s = f"{self._who(e.a)} → {self._who(e.b)}"
            return s + ("  (recruit)" if e.recruit else "") + f"  - {len(e.lines)} line(s)" + (
                f", scene of {len(e.scene)} step(s)" if e.scene else "")
        scene = f", scene of {len(e.scene)} picture step(s)" if getattr(e, "scene", None) else ""
        if kind == "turn_events":
            return f"Turn {max(2, e.turn)}  - {len(e.lines)} line(s){scene}"
        gift = ", ".join(x for x in (self.item_names.get(e.item, e.item) if e.item else "",
                                     f"{e.gold} gold" if e.gold else "") if x) or "nothing"
        if kind == "tile_events":
            return f"({e.x}, {e.y}) {e.who and self._who(e.who) or 'any unit'}: {gift}{scene}"
        return f"{'Chest' if e.is_chest else 'Village'} ({e.x}, {e.y}): {gift}"

    def refresh(self):
        plan = self.win.plan
        for kind, (lst, _box) in self.lists.items():
            lst.clear()
            for e in getattr(plan, kind, []) if plan else []:
                lst.addItem(QListWidgetItem(self._label(kind, e)))

    # ------------------------------------------------------------------ editing
    def _dialog(self, kind, e, removable):
        cid = self.win.plan.cid if self.win.plan else ""
        if kind == "talks":
            return TalkDialog(self.maker, e, self.chars, removable, self, cid)
        if kind == "turn_events":
            return TurnDialog(self.maker, e, removable, self, cid)
        if kind == "tile_events":
            return TileEventDialog(self.maker, e, self.chars, self.win.canvas.grid, removable, self, cid)
        return TreasureDialog(self.maker, e, removable, self)

    @staticmethod
    def _result(d):
        return d.result_treasure() if isinstance(d, TreasureDialog) else d.result_event()

    def add(self, kind, x=None, y=None):
        plan = self.win.plan
        if plan is None:
            return
        e = {"talks": ce.TalkEvent, "turn_events": lambda: ce.TurnEvent(turn=2),
             "tile_events": ce.TileEvent, "treasures": ce.Treasure}[kind]()
        if x is not None:
            e.x, e.y = x, y
        d = self._dialog(kind, e, False)
        if d.exec() != QDialog.Accepted:
            return
        e = self._result(d)
        if kind == "talks" and (not e.a or not e.b or e.a == e.b):
            self.win.statusBar().showMessage("A talk needs two different characters.", 5000)
            return
        self.win.before_change("Add event")
        getattr(plan, kind).append(e)
        self.win.events_changed()

    def edit(self, kind, index=None):
        plan = self.win.plan
        lst, _box = self.lists[kind]
        i = lst.currentRow() if index is None else index
        items = getattr(plan, kind, []) if plan else []
        if not (0 <= i < len(items)):
            return
        d = self._dialog(kind, items[i], True)
        if d.exec() != QDialog.Accepted:
            return
        self.win.before_change("Change event")
        if d.removed:
            items.pop(i)
        else:
            items[i] = self._result(d)
        self.win.events_changed()

    def remove(self, kind):
        plan = self.win.plan
        lst, _box = self.lists[kind]
        i = lst.currentRow()
        items = getattr(plan, kind, []) if plan else []
        if 0 <= i < len(items):
            self.win.before_change("Remove event")
            items.pop(i)
            self.win.events_changed()

    def treasure_at(self, x, y) -> int:
        plan = self.win.plan
        for i, t in enumerate(plan.treasures if plan else []):
            if (t.x, t.y) == (x, y):
                return i
        return -1

    def tile_event_at(self, x, y) -> int:
        plan = self.win.plan
        for i, e in enumerate(plan.tile_events if plan else []):
            if (e.x, e.y) == (x, y):
                return i
        return -1
