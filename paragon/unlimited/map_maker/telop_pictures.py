"""Paragon Unlimited - full-screen scene pictures (telops) for Map Maker events.

A telop (telop/<name>.r.lz) is a small CGFX scene: picture layers (textures) plus their animation.
The game plays them in its story scenes (bev::テロップ再生). The DLC does the same for its event
pictures (Hot Spring Scramble plays Tlp_Ev_003_OP1 and Tlp_Ev_002_ED1_02 with its own textures).

* Game pictures: every Tlp_Ev_* telop of the game can be used as it is.
* Your pictures: a copy of a game telop with its picture layers replaced by your images. The
  confession pictures (Tlp_Ev_c001-c050) have a background ("BG") and the character ("chara",
  "chara1", or "chara_01"); Tlp_Ev_c040 is the simplest (one background, one character, a light
  streak), so it is the base of new pictures. Your images are scaled to the layer's size
  (character 512 x 512 with transparency, background 256 x 256) and keep the base's animation.
New pictures are saved as telop/Tlp_PU_<chapter>_<n>.r.lz in the project.
"""
import logging
from typing import List, Optional, Tuple

from paragon.unlimited.models import model_textures as mt

PREFIX = "Tlp_PU_"
BASE = "Tlp_Ev_c040"
CHARA_LAYERS = ("chara_01", "chara", "chara1")
BG_LAYERS = ("BG",)

STORY = [  # (telop, what it shows) - story scene pictures of the game
    ("Tlp_Ev_001_ED2_02", "Emmeryn and the knights"),
    ("Tlp_Ev_002_ED1_02", "Sumia's pegasus"),
    ("Tlp_Ev_003_OP1", "Snowy gate in the storm"),
    ("Tlp_Ev_011_ED3", "Celebration with confetti"),
    ("Tlp_Ev_012_OP0_01", "Chrom's family"),
    ("Tlp_Ev_012_OP0_02", "Baby"),
    ("Tlp_Ev_013_ED3_01", "Character close-up"),
    ("Tlp_Ev_014_ED2", "Ships at sea"),
    ("Tlp_Ev_016_ED1_02", "Tree branches"),
    ("Tlp_Ev_017_OP2", "Castle in the mountains"),
    ("Tlp_Ev_019_ED2", "Castle in the fog"),
    ("Tlp_Ev_019_OP3", "Army on the field"),
    ("Tlp_Ev_021_OP2", "Bones of the dragon"),
    ("Tlp_Ev_022_OP1", "Land seen from above"),
    ("Tlp_Ev_023_ED4", "Grima"),
    ("Tlp_Ev_024_ED1_03", "Naga"),
    ("Tlp_Ev_025_ED2", "Grima in the smoke"),
    ("Tlp_Ev_025_OP1", "Mountains on fire"),
    ("Tlp_Ev_026_ED1_A_2", "Ruins"),
    ("Tlp_Ev_026_ED1_A_3", "Character in the light"),
    ("Tlp_Ev_026_ED1_B_1", "Chrom and Grima"),
    ("Tlp_Ev_t001", "Smoke"),
]
CONFESSIONS = [(f"Tlp_Ev_c{n:03d}", f"Confession picture {n}") for n in range(1, 51)]


def path_of(name: str) -> str:
    return f"telop/{name}.r.lz"


def read(gd, name: str, pending=None) -> Optional[bytes]:
    """The telop's CGFX (decompressed), from the pending edits or the game / project files."""
    if pending and path_of(name) in pending:
        return pending[path_of(name)]
    try:
        if gd.file_exists(path_of(name), False):
            from paragon import paragon as pgn

            blob = bytes(gd.read_file(path_of(name)))  # the game data reader unpacks .lz files itself
            return blob if blob[:4] == b"CGFX" else bytes(pgn.decompress_lz13(blob))
    except BaseException:  # noqa: B902 - a broken file must not break the editor
        logging.exception("Could not read %s", name)
    return None


def own_pictures(gd, output_path: Optional[str], pending=None) -> List[str]:
    """Names of the pictures made for this project."""
    import os

    names = set()
    for p in (pending or {}):
        if p.startswith("telop/" + PREFIX) and p.endswith(".r.lz"):
            names.add(p[len("telop/"):-len(".r.lz")])
    folder = os.path.join(output_path, "telop") if output_path else None
    if folder and os.path.isdir(folder):
        for f in os.listdir(folder):
            if f.startswith(PREFIX) and f.endswith(".r.lz"):
                names.add(f[: -len(".r.lz")])
    return sorted(names)


def choices(gd, output_path=None, pending=None) -> List[Tuple[str, str]]:
    """(label, telop name) of every picture an event can show."""
    out = [(f"Your picture: {n[len(PREFIX):]}", n) for n in own_pictures(gd, output_path, pending)]
    out += [(f"{label} ({name})", name) for name, label in STORY + CONFESSIONS]
    return out


def preview(gd, name: str, pending=None) -> Optional[Tuple[int, int, bytes]]:
    """(width, height, RGBA) of the picture's main layers (background, then the character)."""
    raw = read(gd, name, pending)
    if raw is None:
        return None
    try:
        from paragon import paragon as pgn
        from PIL import Image

        layers = {t.filename: t for t in pgn.read_cgfx(raw)}
    except BaseException:  # noqa: B902 - the decoder can fail on rare formats
        return None
    try:
        from PIL import Image

        def img(t):
            return Image.frombytes("RGBA", (t.width, t.height), bytes(t.pixel_data))

        bg = next((layers[k] for k in BG_LAYERS if k in layers), None)
        ch = next((layers[k] for k in CHARA_LAYERS if k in layers), None)
        if bg is None and ch is None:
            big = max(layers.values(), key=lambda t: t.width * t.height)
            out = img(big)
        else:
            out = Image.new("RGBA", (512, 512), (0, 0, 0, 255))
            if bg is not None:
                out.alpha_composite(img(bg).resize((512, 512)))
            if ch is not None:
                out.alpha_composite(img(ch).resize((512, 512)))
        return out.width, out.height, out.tobytes()
    except Exception:
        logging.exception("Preview of %s", name)
        return None


def next_name(gd, cid: str, output_path=None, pending=None) -> str:
    have = set(own_pictures(gd, output_path, pending))
    n = 1
    while f"{PREFIX}{cid}_{n}" in have:
        n += 1
    return f"{PREFIX}{cid}_{n}"


def make_picture(gd, character_img, background_img=None, base: str = BASE, pending=None) -> bytes:
    """A new telop (CGFX, decompressed) from the base with the character and background layers
    replaced. Images are PIL images; the character should have a transparent background."""
    raw = read(gd, base, pending)
    if raw is None:
        raise FileNotFoundError(f"The game picture {base} was not found.")
    names = {t.name for t in mt.textures(raw)}
    chara = [n for n in CHARA_LAYERS if n in names]
    if not chara:
        raise ValueError(f"{base} has no character layer.")
    for n in chara:  # every character layer shows the new picture
        raw = mt.replace_texture(raw, n, character_img)
    if background_img is not None:
        for n in BG_LAYERS:
            if n in names:
                raw = mt.replace_texture(raw, n, background_img)
    return raw
