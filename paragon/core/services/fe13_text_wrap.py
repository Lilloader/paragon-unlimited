"""Paragon Unlimited - FE13 automatic line breaks for conversations.

How wide a line can be
----------------------
Awakening draws conversation text with fonts/System.bfnt, a proportional font: an "i" is 4
pixels wide, a "W" 13. So the limit is a width in pixels, not a number of letters (about 40-48
letters, depending on the letters). The limits below were measured over every line of the
game's own English text (m/E, about 120,000 lines), using the font's own letter widths:

    conversation type ($SetConversationType)   widest line in the game
    1  supports, base and most cutscenes        320 px
    0  small boxes on the map / in battle       285 px
    2  narration                                293 px
    none (barracks / status talk)               312 px

A text box holds 2 lines (the game's text has 2 lines or fewer in every box but 3).
Lines that print the avatar's name ($Nu) leave about 100 px for it in the game's text.

What wrap does
--------------
When a line is wider than the limit, the line break (\\n) goes before the first word that
does not fit. When a box would get a third line, a new box is started instead ($k$p:
"$Pause" + "$Clear"), the way the game continues one speaker's text. Line breaks you typed are
kept. Text that already fits is not changed.
"""
import logging
import re
import struct
from typing import Dict, List, Optional, Tuple

from paragon.core.dialogue.commands import (
    ClearCommand,
    Command,
    NewlineCommand,
    PauseCommand,
    PrintAvatar2Command,
    PrintAvatarCommand,
    PrintCommand,
    PrintGenderDependentCommand,
    SetConversationTypeCommand,
    SetSpeakerCommand,
)

FONT_PATH = "fonts/System.bfnt.lz"
LIMITS = {0: 285, 1: 320, 2: 293}
DEFAULT_LIMIT = 312
LINES_PER_BOX = 2
AVATAR_WIDTH = 100

# Letter widths from System.bfnt, used when the font file cannot be read.
_BUILT_IN_CHARS = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
    "abcdefghijklmnopqrstuvwxyz{|}~¡¿éèàçñüöä―‘’“”…‥♪　"
)
_BUILT_IN_WIDTHS = bytes.fromhex(
    "05060609090e0b050606070905060506090909090909090909090505090909090c0a0a0b0c09080c0b05060a"
    "090d0b0d090d0a0a090b090d0908090606060907060809080908060908040407040c0809090906080608070a"
    "07070806050607060a08080808080809080e0e0e0e0e0e0e0e0e"
)
# Characters that may not start a line (Japanese punctuation).
_NO_LINE_START = set("、。，．・：；？！ー」』）】〉》…‥ぁぃぅぇぉっゃゅょァィゥェォッャュョ")


def _is_cjk(ch: str) -> bool:
    return ord(ch) >= 0x2E80


class Metrics:
    """Letter widths (advance in pixels) of the game's conversation font."""

    def __init__(self, advances: Dict[int, int], source: str):
        self.advances = advances
        self.source = source
        self._unknown = advances.get(ord("?"), 9)
        self._wide = advances.get(0x3000, 14)

    @staticmethod
    def parse_font(data: bytes) -> Dict[int, int]:
        """{code point: advance} from an IS .bfnt (decompressed)."""
        table, count = struct.unpack_from("<HH", data, 0x20)
        if table < 0x30 or table + 16 * count > len(data):
            raise ValueError("Not a .bfnt font.")
        out = {}
        for i in range(count):
            code = struct.unpack_from("<H", data, table + 16 * i)[0]
            out[code] = data[table + 16 * i + 12]
        return out

    @classmethod
    def from_font(cls, data: bytes, source: str = FONT_PATH) -> "Metrics":
        return cls(cls.parse_font(data), source)

    @classmethod
    def built_in(cls) -> "Metrics":
        return cls({ord(c): w for c, w in zip(_BUILT_IN_CHARS, _BUILT_IN_WIDTHS)}, "built-in table")

    def char(self, ch: str) -> int:
        w = self.advances.get(ord(ch))
        if w is not None:
            return w
        return self._wide if _is_cjk(ch) else self._unknown

    def text(self, s: str) -> int:
        return sum(self.char(c) for c in s)


_cache: Dict[int, Metrics] = {}


def metrics_for(gd) -> Metrics:
    """The game's font metrics (read once per project), or the built-in table."""
    key = id(gd)
    if key in _cache:
        return _cache[key]
    m = None
    try:
        data = bytes(gd.read_file(FONT_PATH))
        if data[:4] != b"\x00\x00\x20\x00":
            from paragon import paragon as pgn

            data = bytes(pgn.decompress_lz13(data))
        m = Metrics.from_font(data)
    except Exception:
        logging.info("Line breaks: could not read the game font, using the built-in letter widths.")
        m = Metrics.built_in()
    _cache[key] = m
    return m


def limit_for(conversation_type: Optional[int]) -> int:
    if conversation_type is None:
        return DEFAULT_LIMIT
    return LIMITS.get(conversation_type, DEFAULT_LIMIT)


# ----------------------------------------------------------------------------- wrapping

# An atom is one piece of a line: ("text", str), ("cmd", Command) for $Nu / $G, or ("space", str).


def _atoms(cmd: Command) -> List[Tuple[str, object]]:
    if isinstance(cmd, PrintCommand):
        out = []
        for part in re.split(r"( +)", cmd.text):
            if not part:
                continue
            if part[0] == " ":
                out.append(("space", part))
            else:
                # Japanese text has no spaces: every CJK letter is a possible break.
                buf = ""
                for ch in part:
                    if _is_cjk(ch) and ch not in _NO_LINE_START and buf:
                        out.append(("text", buf))
                        out.append(("space", ""))
                        buf = ""
                    buf += ch
                if buf:
                    out.append(("text", buf))
        return out
    return [("cmd", cmd)]


def _atom_width(atom, m: Metrics, avatar_width: int) -> int:
    kind, v = atom
    if kind in ("text", "space"):
        return m.text(v)
    if isinstance(v, PrintGenderDependentCommand):
        return max(m.text(v.m), m.text(v.f))
    if isinstance(v, (PrintAvatarCommand, PrintAvatar2Command)):
        return avatar_width
    return 0


def _is_print(cmd: Command) -> bool:
    return isinstance(
        cmd, (PrintCommand, PrintAvatarCommand, PrintAvatar2Command, PrintGenderDependentCommand)
    )


class _Wrapper:
    def __init__(self, m: Metrics, avatar_width: int):
        self.m = m
        self.avatar_width = avatar_width
        self.limit = DEFAULT_LIMIT
        self.x = 0
        self.lines = 1
        self.after_pause = False
        self.out: List[Command] = []
        self.changes = 0
        self.third_line_break = None
        self._text = ""

    def _flush_text(self):
        if self._text:
            self.out.append(PrintCommand(self._text))
            self._text = ""

    def _emit(self, atom):
        kind, v = atom
        if kind in ("text", "space"):
            self._text += v
        else:
            self._flush_text()
            self.out.append(v)

    def _break(self):
        self._flush_text()
        self.changes += 1
        self.x = 0
        if self.lines >= LINES_PER_BOX:
            self.out.extend([PauseCommand(), ClearCommand()])
            self.lines = 1
        else:
            self.out.append(NewlineCommand())
            self.lines += 1

    def _place_word(self, word, ww):
        if ww <= self.limit or len(word) != 1 or word[0][0] != "text":
            for a in word:
                self._emit(a)
            self.x += ww
            return
        # A single word wider than a whole line: split it by letters.
        text = word[0][1]
        for ch in text:
            cw = self.m.char(ch)
            if self.x and self.x + cw > self.limit:
                self._break()
            self._text += ch
            self.x += cw

    def run(self, prints: List[Command]):
        """Lay out consecutive print commands."""
        self.after_pause = False
        if self.third_line_break is not None:
            k = self.third_line_break
            self.out[k : k + 1] = [PauseCommand(), ClearCommand()]
            self.third_line_break = None
            self.changes += 1
            self.x, self.lines = 0, 1
        atoms = [a for c in prints for a in _atoms(c)]
        i = 0
        while i < len(atoms):
            spaces = []
            while i < len(atoms) and atoms[i][0] == "space":
                spaces.append(atoms[i])
                i += 1
            word = []
            while i < len(atoms) and atoms[i][0] != "space":
                word.append(atoms[i])
                i += 1
            sw = sum(_atom_width(a, self.m, self.avatar_width) for a in spaces)
            ww = sum(_atom_width(a, self.m, self.avatar_width) for a in word)
            if not word:
                for a in spaces:  # trailing spaces: keep them
                    self._emit(a)
                self.x += sw
                continue
            if self.x > 0 and self.x + sw + ww > self.limit:
                self._break()  # the spaces before the word are replaced by the break
            else:
                for a in spaces:
                    self._emit(a)
                self.x += sw
            self._place_word(word, ww)
        self._flush_text()

    def other(self, c: Command):
        if isinstance(c, (PauseCommand, ClearCommand, SetSpeakerCommand)):
            self.third_line_break = None
        if isinstance(c, SetConversationTypeCommand):
            self.limit = limit_for(_type_of(c))
        elif isinstance(c, PauseCommand):
            self.x, self.lines, self.after_pause = 0, 1, True
        elif isinstance(c, ClearCommand):
            self.x, self.lines = 0, 1
        elif isinstance(c, SetSpeakerCommand):
            self.x, self.lines = 0, 1
        elif isinstance(c, NewlineCommand):
            if not self.after_pause:
                if self.lines >= LINES_PER_BOX:
                    # A line break you typed would start a third line. If text follows in this
                    # box, run() turns the break into a new box.
                    self.third_line_break = len(self.out)
                    self.out.append(c)
                    return
                self.x = 0
                self.lines += 1
        self.out.append(c)


def _type_of(c: SetConversationTypeCommand) -> Optional[int]:
    try:
        return int(c.t)
    except (TypeError, ValueError, AttributeError):
        return None


def wrap_commands(commands: List[Command], m: Metrics, avatar_width: int = AVATAR_WIDTH) -> Tuple[List[Command], int]:
    """(commands with line breaks added, number of breaks added)."""
    w = _Wrapper(m, avatar_width)
    i = 0
    while i < len(commands):
        if _is_print(commands[i]):
            j = i
            while j < len(commands) and _is_print(commands[j]):
                j += 1
            w.run(commands[i:j])
            i = j
        else:
            w.other(commands[i])
            i += 1
    if not w.changes:
        return commands, 0
    return w.out, w.changes


def wrap_game_text(text: str, m: Metrics, avatar_width: int = AVATAR_WIDTH) -> Tuple[str, int]:
    from paragon.core.dialogue.game_script_parser import GameScriptParser

    commands = GameScriptParser().scan(text)
    out, n = wrap_commands(commands, m, avatar_width)
    if not n:
        return text, 0
    return "".join(c.to_game() for c in out), n


def wrap_pretty_text(pretty: str, m: Metrics, avatar_width: int = AVATAR_WIDTH) -> Tuple[str, int]:
    """Same, on the text shown in the conversation editor."""
    from paragon.core.dialogue import convert
    from paragon.core.dialogue.pretty_script_parser import PrettyScriptParser

    commands = PrettyScriptParser().scan(pretty)
    out, n = wrap_commands(commands, m, avatar_width)
    if not n:
        return pretty, 0
    return convert._commands_to_pretty(out), n


# ----------------------------------------------------------------------------- live help while typing

_INLINE = re.compile(r"\$Nu|\$Np|\$G\(([^,()]*),([^()]*)\)")


def _segments(line: str):
    """Split an editor line at typed line breaks (\\n): [(start, end), ...]."""
    out, start = [], 0
    for mt in re.finditer(r"\\n", line):
        out.append((start, mt.start()))
        start = mt.end()
    out.append((start, len(line)))
    return out


def _width_upto(line: str, start: int, end: int, m: Metrics, avatar_width: int) -> List[Tuple[int, int]]:
    """[(index, width of line[start:index])] for every index in [start, end]."""
    out = [(start, 0)]
    x, i = 0, start
    while i < end:
        mt = _INLINE.match(line, i)
        if mt and mt.end() <= end:
            if mt.group(0).startswith("$G"):
                x += max(m.text(mt.group(1)), m.text(mt.group(2)))
            else:
                x += avatar_width
            i = mt.end()
        else:
            x += m.char(line[i])
            i += 1
        out.append((i, x))
    return out


def is_text_line(line: str) -> bool:
    s = line.strip()
    if not s or s == "\\n":
        return False
    if s.startswith("$"):
        return bool(_INLINE.match(s))
    return True


def line_width(line: str, column: int, m: Metrics, avatar_width: int = AVATAR_WIDTH) -> int:
    """Width in pixels of the game line (between \\n breaks) that contains column."""
    for start, end in _segments(line):
        if start <= column <= end:
            return _width_upto(line, start, end, m, avatar_width)[-1][1]
    return 0


def live_break(line: str, column: int, m: Metrics, limit: int, avatar_width: int = AVATAR_WIDTH) -> Optional[Tuple[int, int]]:
    """While typing: if the game line holding column is too wide, (start, end) of the spaces
    to replace with a line break (before the first word that does not fit). None: fits, or
    nowhere to break."""
    for start, end in _segments(line):
        if not start <= column <= end:
            continue
        widths = _width_upto(line, start, end, m, avatar_width)
        index = dict(widths)
        keys = [k for k, _ in widths]

        def width_at(i):
            # $Nu / $G(...) count as one piece: the width up to the end of the piece holding i
            import bisect

            return index[keys[min(bisect.bisect_left(keys, i), len(keys) - 1)]]

        if widths[-1][1] <= limit:
            return None
        # Break before the first word that does not fit.
        for s_start, s_end in _spaces(line, start, end):
            if s_start == start:
                continue
            if s_start not in index:
                continue  # a space inside $G(...)
            if width_at(_next_space(line, s_end, end)) > limit:
                return (s_start, s_end)
        return None
    return None


def _spaces(line, start, end):
    k = start
    while k < end:
        if line[k] == " ":
            j = k
            while j < end and line[j] == " ":
                j += 1
            yield k, j
            k = j
        else:
            k += 1


def _next_space(line, k, end):
    while k < end and line[k] != " ":
        k += 1
    return k


def conversation_type_before(text: str) -> Optional[int]:
    """The last $SetConversationType(n) in the editor text (None: not set)."""
    found = None
    for mt in re.finditer(r"\$SetConversationType\((\d+)\)", text):
        found = int(mt.group(1))
    return found
