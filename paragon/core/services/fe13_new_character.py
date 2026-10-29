"""Paragon Unlimited: set up a new FE13 character in one go.

Creates, from a template character:
  * the character (copy of the template; new PID / FID / name / description; empty supports)
  * FaceData entries FSID_BU_<id>_通常 and FSID_FC_<id>_通常
  * portrait files face/<id>_bu_通常.arc and face/<id>_fc_通常.arc with the basic
    expressions (blank or copies of the template's), built when the project is saved
  * Asset Definitions entries named PID_<id> (copies of the template's battle model)
Everything goes through the normal project data, so nothing is written until you save.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional

GAME_DATA_TEXT = "m/GameData.bin.lz"
NO_SUPPORT = 0x63636363
ID_RE = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass
class NewCharacterRequest:
    ident: str  # e.g. "Gisselle" -> PID_Gisselle, FID_Gisselle
    name: str  # display name, e.g. "Gisselle"
    description: str
    template_pid: str  # e.g. "PID_リズ"
    portraits: str = "blank"  # "blank" | "copy" | "none"
    battle_model: bool = True


@dataclass
class NewCharacterResult:
    person: Optional[int] = None
    face_data: List[int] = field(default_factory=list)
    portrait_files: List[str] = field(default_factory=list)
    assets: List[int] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def validate(gd, req: NewCharacterRequest) -> Optional[str]:
    if not req.ident or not ID_RE.match(req.ident):
        return "The ID may only use letters, numbers and _ (it becomes PID_<ID>, FID_<ID> and file names)."
    if not req.name.strip():
        return "Please enter a name."
    if gd.key_to_rid("characters", "PID_" + req.ident) is not None:
        return f"PID_{req.ident} already exists."
    if gd.key_to_rid("characters", req.template_pid) is None:
        return f"Template {req.template_pid} was not found."
    for mode in ("BU", "FC"):
        if gd.key_to_rid("portraits", f"FSID_{mode}_{req.ident}_通常") is not None:
            return f"FaceData FSID_{mode}_{req.ident}_通常 already exists."
    return None


def _append_copy(gd, models, table_rid, field_id, source_rid) -> int:
    """Add a row at the end of a list (through the UI model when there is one) and copy source into it."""
    model = None
    if models is not None:
        try:
            model = models.get(table_rid, field_id)
        except Exception:
            model = None
    if model is not None:
        model.add_item()
    else:
        gd.list_add(table_rid, field_id)
    new = gd.list_get(table_rid, field_id, gd.list_size(table_rid, field_id) - 1)
    gd.copy(source_rid, new, [])
    return new


def _list_of(gd, node_id, field_id):
    node = gd.node(node_id)
    if node is None:
        return None, []
    n = gd.list_size(node.rid, field_id)
    return node.rid, [gd.list_get(node.rid, field_id, i) for i in range(n)]


def create(gd, req: NewCharacterRequest, portrait_edits=None, models=None) -> NewCharacterResult:
    err = validate(gd, req)
    if err:
        raise ValueError(err)
    res = NewCharacterResult()
    template = gd.key_to_rid("characters", req.template_pid)
    tfid = gd.string(template, "fid") or ("FID_" + req.template_pid[4:])
    pid, fid = "PID_" + req.ident, "FID_" + req.ident

    # ---- character
    table_rid, field_id = gd.table("characters")
    people = gd.items(table_rid, field_id)
    next_id = max([gd.int(r, "id") or 0 for r in people] + [0]) + 1
    person = _append_copy(gd, models, table_rid, field_id, template)
    gd.set_string(person, "pid", pid)
    gd.set_string(person, "fid", fid)
    gd.set_int(person, "id", next_id)
    name_key, desc_key = "MPID_" + req.ident, "MPID_H_" + req.ident
    gd.set_message(GAME_DATA_TEXT, True, name_key, req.name.strip())
    gd.set_message(GAME_DATA_TEXT, True, desc_key, req.description.strip() or req.name.strip())
    gd.set_string(person, "name", name_key)
    gd.set_string(person, "description", desc_key)
    for k in range(52):
        gd.set_rid(person, f"support_character_{k:03}", None)
        gd.set_int(person, f"support_type_{k:03}", NO_SUPPORT)
    try:
        gd.set_rid(person, "parent", None)
    except Exception:
        pass
    res.person = person
    res.notes.append(f"Character {pid} (copy of {req.template_pid}, internal id {next_id}, no supports).")

    # ---- FaceData + portrait files
    ptable = gd.table("portraits")
    for mode in ("BU", "FC"):
        tfsid = f"FSID_{mode}_{tfid[4:]}_通常"
        src = gd.key_to_rid("portraits", tfsid)
        if src is None or not ptable:
            res.notes.append(f"No {tfsid} in FaceData to copy; {mode} portrait not set up.")
            continue
        fd = _append_copy(gd, models, ptable[0], ptable[1], src)
        gd.set_string(fd, "fsid", f"FSID_{mode}_{req.ident}_通常")
        res.face_data.append(fd)
        if req.portraits == "none":
            continue
        file_name = f"{req.ident}_{mode.lower()}_通常.arc"
        gd.set_string(fd, "portrait_file", file_name)
        if portrait_edits is not None:
            template_file = gd.string(src, "portrait_file")
            try:
                template_arc = gd.read_arc(f"face/{template_file}") if template_file else {}
            except Exception:
                template_arc = {}
            parts = basic_portrait_parts(template_arc, mode, req.portraits == "copy")
            portrait_edits.create_arc(f"face/{file_name}", parts)
            res.portrait_files.append(f"face/{file_name}")
    if res.portrait_files:
        res.notes.append("Portrait files (built on save): " + ", ".join(res.portrait_files))

    # ---- battle model
    if req.battle_model:
        node_rid, specs = _list_of(gd, "asset_definitions", "specs")
        sources = [r for r in specs if gd.string(r, "name") == req.template_pid]
        for src in sources:
            new = _append_copy(gd, models, node_rid, "specs", src)
            gd.set_string(new, "name", pid)
            res.assets.append(new)
        if sources:
            res.notes.append(f"{len(sources)} Asset Definitions entr{'y' if len(sources) == 1 else 'ies'} named {pid}.")
        else:
            res.notes.append(f"{req.template_pid} has no Asset Definitions entry; the class default model is used.")
    return res


def basic_portrait_parts(template_arc, mode: str, copy: bool):
    """Decompressed CTPKs for a new portrait file: basic expressions + blush/sweat/hair."""
    from paragon import paragon as pgn
    from paragon.core.services.fe13_portrait_shift import (
        BASIC_EXPRESSIONS,
        EXTRA_PARTS,
        ENTRY_SUFFIX,
        blank_ctpk,
        new_ctpk,
    )

    def raw(key):
        blob = (template_arc or {}).get(key + ENTRY_SUFFIX)
        return bytes(pgn.decompress_lz13(bytes(blob))) if blob else None

    template = raw("通常")
    if template is None:
        size = 256 if mode == "BU" else 128
        parts = {k: new_ctpk(size, size) for k in BASIC_EXPRESSIONS}
        parts.update({"頬": new_ctpk(64, 32), "汗": new_ctpk(16, 16), "髪": new_ctpk(32, 32), "髪0": new_ctpk(32, 32)})
        return parts
    parts = {}
    for k in BASIC_EXPRESSIONS:
        src = raw(k) if copy else None
        parts[k] = src if src is not None else blank_ctpk(template)
    for k in EXTRA_PARTS:
        src = raw(k)
        if src is not None:
            parts[k] = src
    return parts
