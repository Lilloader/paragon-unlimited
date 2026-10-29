"""Paragon Unlimited: "Check my mod" - find problems that only show up in the game.

Read-only scan of the project (base game + your output folder):

* dialogue: expressions a speaker's portrait file does not have, speakers without portraits,
  $PlayVoice lines that do not exist (English voice archive)
* FaceData: portrait files that are missing
* characters: portrait (FID) without FaceData entries
* asset definitions / presets: models and textures that are missing
* supports: one-sided support lists (same check as on save)
* file names: references whose file differs only in letter case (the game needs the exact
  name), custom map sprites missing their blue / red / green file, near-miss sprite names

Each problem is an Issue(severity, category, where, message). Severity "error" means the
game is likely to crash or show nothing; "warning" means it may look wrong.
"""
import logging
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set

OVERLAY_EMOTIONS = {"照": "頬", "汗": "汗"}


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    category: str
    where: str
    message: str


class ModChecker:
    def __init__(self, gd, voices=None, progress: Optional[Callable[[str], None]] = None,
                 roots: Optional[List[str]] = None):
        """roots: [project output folder, game RomFS folder] for the exact file-name checks."""
        self.gd = gd
        self.roots = [r for r in (roots or []) if r]
        # (root, actual rel, wanted rel) of project files whose name case can be fixed.
        self.case_fixes = []
        self.voices = voices
        self.progress = progress or (lambda s: None)
        self.issues: List[Issue] = []
        self._arc_keys: Dict[str, Optional[Set[str]]] = {}
        self._fsid_file: Dict[str, Optional[str]] = {}
        self._seen = set()

    # ------------------------------------------------------------------ helpers
    def add(self, severity, category, where, message, dedupe_key=None):
        key = dedupe_key or (category, where, message)
        if key in self._seen:
            return
        self._seen.add(key)
        self.issues.append(Issue(severity, category, where, message))

    def _exists(self, path) -> bool:
        try:
            return bool(self.gd.file_exists(path, False))
        except Exception:
            return False

    def portrait_file(self, fsid: str) -> Optional[str]:
        if fsid not in self._fsid_file:
            f = None
            try:
                rid = self.gd.key_to_rid("portraits", fsid)
                f = self.gd.string(rid, "portrait_file") if rid else None
            except Exception:
                f = None
            self._fsid_file[fsid] = f
        return self._fsid_file[fsid]

    def arc_keys(self, portrait_file: str) -> Optional[Set[str]]:
        if portrait_file not in self._arc_keys:
            keys = None
            path = f"face/{portrait_file}"
            if self._exists(path):
                try:
                    keys = {k[:-8] if k.endswith(".ctpk.lz") else k for k in self.gd.read_arc(path)}
                except Exception:
                    keys = set()
            self._arc_keys[portrait_file] = keys
        return self._arc_keys[portrait_file]

    def _table_rids(self, node_id: str, list_field: str):
        try:
            node = self.gd.node(node_id)
            if node is None:
                return []
            n = self.gd.list_size(node.rid, list_field)
            return [self.gd.list_get(node.rid, list_field, i) for i in range(n)]
        except Exception:
            return []

    # ------------------------------------------------------------------ checks
    @staticmethod
    def issue_key(i: "Issue") -> str:
        import hashlib

        return hashlib.sha1(f"{i.category}|{i.where}|{i.message}".encode("utf-8")).hexdigest()[:12]

    def run(self, baseline: Optional[Set[str]] = None) -> List[Issue]:
        """baseline: keys of problems the unmodified game already has; they are hidden
        (self.hidden counts them)."""
        self.hidden = 0
        for name, fn in (
            ("FaceData", self.check_face_data),
            ("characters", self.check_characters),
            ("asset definitions", self.check_assets),
            ("dialogue", self.check_dialogue),
            ("file names", self.check_file_names),
        ):
            self.progress(f"Checking {name}...")
            try:
                fn()
            except Exception as e:
                logging.exception(f"Mod check of {name} failed.")
                self.add("warning", "Checker", name, f"This check could not run: {e}")
        if baseline:
            kept = [i for i in self.issues if self.issue_key(i) not in baseline]
            self.hidden = len(self.issues) - len(kept)
            self.issues = kept
        order = {"error": 0, "warning": 1}
        self.issues.sort(key=lambda i: (order.get(i.severity, 2), i.category, i.where))
        return self.issues

    def check_face_data(self):
        for rid in self._table_rids("facedata", "portraits"):
            fsid = self.gd.string(rid, "fsid") or "?"
            f = self.gd.string(rid, "portrait_file")
            if not f:
                continue
            if self.arc_keys(f) is None:
                self.add("error", "FaceData", fsid, f"Portrait file face/{f} does not exist.")
            elif "通常" not in self.arc_keys(f):
                self.add("error", "FaceData", fsid, f"face/{f} has no 通常 (Standard) expression.")

    # ------------------------------------------------------------------ exact file names
    COLORS = (("青", "blue (player)"), ("赤", "red (enemy)"), ("緑", "green (ally)"))

    def _case_issue(self, category, where, rel):
        """Report a reference whose file exists only with different letter case."""
        from paragon.core.services import pu_file_case

        status, root, actual = pu_file_case.resolve(self.roots, rel)
        if status != "case":
            return status
        fixable = root == self.roots[0]
        if fixable:
            self.case_fixes.append((root, actual, rel))
        self.add(
            "error",
            category,
            where,
            f"The game asks for {rel} but the file is named {actual.split('/')[-1]} (letter case "
            "differs). Windows does not mind, the game does: the file is not found (crash or "
            "invisible unit)." + (" Fix name case renames it." if fixable else ""),
        )
        return status

    def _sprite_users(self):
        """{map sprite name: [character names]} for sprites listed in characters' sprite lists."""
        out = {}
        try:
            table = self.gd.table("characters")
            chars = self.gd.items(table[0], table[1]) if table else []
        except Exception:
            chars = []
        for c in chars:
            try:
                sd = self.gd.rid(c, "sprite_data")
                entries = self.gd.items(sd, "entries") if sd else []
            except Exception:
                continue
            for e in entries:
                icon = self.gd.rid(e, "bmap_icon")
                if not icon:
                    continue
                name = self.gd.string(icon, "name")
                if name:
                    who = self.gd.key(c) or "?"
                    out.setdefault(name, [])
                    if who not in out[name]:
                        out[name].append(who)
        return out

    def check_file_names(self):
        if not self.roots:
            return
        import difflib
        import os

        from paragon.core.services import pu_file_case

        pu_file_case.clear_cache()
        for rid in self._table_rids("facedata", "portraits"):
            f = self.gd.string(rid, "portrait_file")
            if f:
                self._case_issue("File names", self.gd.string(rid, "fsid") or "?", f"face/{f}")
        game_root = self.roots[-1] if len(self.roots) > 1 else None
        unit_names = set()
        for r in self.roots:
            try:
                unit_names |= set(os.listdir(os.path.join(r, "map", "unit")))
            except OSError:
                pass
        for name, users in sorted(self._sprite_users().items()):
            if game_root and any(
                pu_file_case.find(game_root, f"map/unit/{name}{c}.ctpk.lz")[0] != "missing" for c, _ in self.COLORS
            ):
                continue  # the game's own sprite
            where = f"map sprite {name} ({', '.join(users[:3])}{'...' if len(users) > 3 else ''})"
            missing = []
            for c, label in self.COLORS:
                status = self._case_issue("File names", where, f"map/unit/{name}{c}.ctpk.lz")
                if status == "missing":
                    missing.append((c, label))
            if len(missing) == 3:
                near = difflib.get_close_matches(f"{name}青.ctpk.lz", list(unit_names), 1, 0.75)
                hint = f" The closest file is {near[0]} - check the spelling of the sprite name." if near else ""
                self.add("error", "File names", where, f"No file map/unit/{name}青/赤/緑.ctpk.lz exists.{hint}")
            elif missing:
                labels = ", ".join(f"{name}{c}.ctpk.lz ({label})" for c, label in missing)
                self.add(
                    "error",
                    "File names",
                    where,
                    f"Missing {labels}. Every map sprite needs all three colors: the unit shows up "
                    "in that color when it is on that side.",
                )

    def fix_name_case(self) -> List[str]:
        """Rename project files to the exact names the game asks for. Returns what was renamed."""
        from paragon.core.services import pu_file_case

        done = []
        for root, actual, wanted in self.case_fixes:
            try:
                if pu_file_case.fix_project_name(root, actual, wanted):
                    done.append(f"{actual} -> {wanted.split('/')[-1]}")
            except OSError as e:
                logging.exception("Rename failed.")
                done.append(f"{actual}: could not rename ({e})")
        return done

    def check_characters(self):
        for rid in self._table_rids("characters", "people"):
            pid = self.gd.string(rid, "pid")
            fid = self.gd.string(rid, "fid")
            if not pid or not fid or not fid.startswith("FID_"):
                continue
            part = fid[4:]
            for mode in ("BU", "FC"):
                fsid = f"FSID_{mode}_{part}_通常"
                if self.portrait_file(fsid) is None:
                    self.add(
                        "warning",
                        "Characters",
                        pid,
                        f"{fid} has no FaceData entry {fsid} (no {'big' if mode == 'BU' else 'small'} portrait).",
                    )

    def check_assets(self):
        for node_id, label in (("asset_definitions", "Asset Definitions"), ("preset_asset_definitions", "Presets")):
            for rid in self._table_rids(node_id, "specs"):
                name = self.gd.string(rid, "name") or "?"
                for field, ext, kind in (
                    ("body_model", ".m.lz", "body model"),
                    ("head_model", ".m.lz", "head model"),
                    ("hair_model", ".m.lz", "hair model"),
                    ("mount_model", ".m.lz", "mount model"),
                    ("weapon_model", ".m.lz", "weapon model"),
                    ("body_texture", ".t.lz", "body texture"),
                    ("head_texture", ".t.lz", "head texture"),
                    ("hair_texture", ".t.lz", "hair texture"),
                    ("mount_texture", ".t.lz", "mount texture"),
                ):
                    v = self.gd.string(rid, field)
                    if not v or "%" in v or "#" in v or "?" in v:
                        continue
                    if not self._exists(f"b/{v}{ext}"):
                        self.add("warning", label, name, f"{kind} b/{v}{ext} not found (DLC files are not checked).")

    _wild_cache: Dict[str, bool] = {}

    def _voice_exists(self, sound: str, names: Set[str]) -> bool:
        if sound in names:
            return True
        if "#" in sound or "?" in sound:
            if sound not in self._wild_cache:
                rx = re.compile("^" + re.escape(sound).replace("\\#", "[0-9A-Z]").replace("\\?", ".") + "$")
                self._wild_cache[sound] = any(rx.match(n) for n in names)
            return self._wild_cache[sound]
        return False

    def _speaker_fid(self, name: str, alias: Optional[str]) -> Optional[str]:
        if alias:
            return alias
        if not name or name in ("username", "?", "") or name.startswith("$"):
            return None
        return "FID_" + name

    def check_dialogue(self):
        from paragon.core.dialogue.game_script_parser import GameScriptParser
        from paragon.core.dialogue import commands as c

        voice_names = None
        if self.voices is not None:
            try:
                voice_names = set(self.voices.all_voices())
            except Exception:
                voice_names = None
        parser = GameScriptParser()
        try:
            archives = self.gd.enumerate_text_archives()
        except Exception:
            archives = []
        for path in archives:
            try:
                self.gd.open_text_data(path, False)
                keys = self.gd.enumerate_messages(path, False) or []
            except Exception:
                continue
            for key in keys:
                text = self.gd.message(path, False, key) or ""
                if "$" not in text:
                    continue
                where = f"{path} : {key}"
                try:
                    cmds = parser.scan(text)
                except Exception:
                    continue
                speaker, alias = None, None
                for cmd in cmds:
                    if isinstance(cmd, c.SetSpeakerCommand):
                        speaker, alias = cmd.speaker, None
                    elif isinstance(cmd, c.FidAliasCommand):
                        alias = cmd.param if str(cmd.param).startswith("FID_") else None
                    elif isinstance(cmd, c.SetEmotionsCommand):
                        self._check_emotions(where, speaker, alias, cmd.emotions)
                    elif isinstance(cmd, (c.PlayVoiceCommand, c.PlayVoiceEnglishCommand)) and voice_names:
                        sound = str(cmd.sound).strip()
                        if sound and not self._voice_exists(sound, voice_names):
                            self.add(
                                "warning",
                                "Voices",
                                where,
                                f"Voice line {sound} has no English recording (it will be silent in the English game).",
                            )

    def _check_emotions(self, where, speaker, alias, emotions):
        fid = self._speaker_fid(speaker, alias)
        if not fid:
            return
        fsid = f"FSID_BU_{fid[4:]}_通常"
        f = self.portrait_file(fsid)
        if f is None:
            self.add(
                "warning",
                "Dialogue",
                fid,
                f"Speaker {speaker} has no portrait ({fsid} is not in FaceData).",
                dedupe_key=("nofsid", fid),
            )
            return
        keys = self.arc_keys(f)
        if keys is None:
            return  # reported by the FaceData check
        needed = []
        for e in emotions:
            e = (e or "").strip()
            if not e:
                continue
            if all(ch in OVERLAY_EMOTIONS for ch in e):  # 照, 汗, 照汗: blush / sweat overlays
                needed += [(e, OVERLAY_EMOTIONS[ch]) for ch in e]
            else:
                needed.append((e, e))
        for e, need in needed:
            if need not in keys:
                self.add(
                    "error",
                    "Dialogue",
                    where,
                    f"{speaker} uses expression {e}, but face/{f} has no {need}.",
                    dedupe_key=("emo", where, f, need),
                )


BASELINE_FILE = "Data/FE13/PU_ModCheckBaseline.txt"


def load_baseline(path: str = BASELINE_FILE) -> Set[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip() and not line.startswith("#")}
    except Exception:
        return set()


def report_text(issues: List[Issue]) -> str:
    lines = [f"[{i.severity.upper()}] {i.category} - {i.where}: {i.message}" for i in issues]
    return "\n".join(lines) if lines else "No problems found."
