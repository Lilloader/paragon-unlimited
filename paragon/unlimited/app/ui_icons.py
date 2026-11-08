"""Paragon Unlimited - icons for the FE13 main window buttons.

Game-themed icons are taken from YOUR game files at run time (item / skill / army icons and
map sprites, the same images Paragon already shows in its editors); nothing from the game is
bundled. Everything else is a small drawn icon. Any lookup that fails falls back to a drawn one.
"""
import logging
import math

from PIL import Image
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QPolygonF, QFont

S = 64  # drawing canvas; Qt scales the icon down
DRAWN_KEYS = set()  # cacheKey() of every drawn icon (not pixel art)


def _canvas():
    pm = QPixmap(S, S)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    return pm, p


def _pen(color, w=5):
    pen = QPen(QColor(color), w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def drawn(kind: str, color: str = "#d4a64a") -> QIcon:
    pm, p = _canvas()
    c = QColor(color)
    p.setPen(_pen(c))
    p.setBrush(Qt.NoBrush)
    if kind == "flag":  # chapters
        p.drawLine(16, 8, 16, 58)
        path = QPainterPath(QPointF(18, 10))
        path.cubicTo(28, 4, 38, 18, 52, 10)
        path.lineTo(52, 34)
        path.cubicTo(38, 42, 28, 28, 18, 34)
        path.closeSubpath()
        p.setBrush(QBrush(c))
        p.drawPath(path)
    elif kind == "grid":  # tiles
        for i in range(3):
            for j in range(3):
                p.setBrush(QBrush(c) if (i + j) % 2 == 0 else Qt.NoBrush)
                p.drawRect(QRectF(8 + i * 16, 8 + j * 16, 15, 15))
    elif kind == "sprite":  # bmap / sprite data: little pixel figure
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(c))
        px = [(3, 0), (4, 0), (2, 1), (3, 1), (4, 1), (5, 1), (3, 2), (4, 2), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (6, 3),
              (2, 4), (3, 4), (4, 4), (5, 4), (2, 5), (5, 5), (2, 6), (5, 6)]
        for x, y in px:
            p.drawRect(QRectF(4 + x * 7, 6 + y * 7, 7, 7))
    elif kind == "pin":  # gmap
        path = QPainterPath(QPointF(32, 58))
        path.cubicTo(14, 36, 12, 26, 12, 24)
        path.arcTo(QRectF(12, 4, 40, 40), 180, -180)
        path.cubicTo(52, 26, 50, 36, 32, 58)
        p.setBrush(QBrush(c))
        p.drawPath(path)
        p.setBrush(QBrush(QColor("#00000080")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(32, 24), 8, 8)
    elif kind == "book":  # endings
        p.drawRoundedRect(QRectF(10, 10, 44, 44), 4, 4)
        p.drawLine(32, 10, 32, 54)
        p.drawLine(16, 20, 26, 20)
        p.drawLine(38, 20, 48, 20)
        p.drawLine(16, 30, 26, 30)
        p.drawLine(38, 30, 48, 30)
    elif kind == "code":  # scripts
        p.drawPolyline(QPolygonF([QPointF(22, 16), QPointF(8, 32), QPointF(22, 48)]))
        p.drawPolyline(QPolygonF([QPointF(42, 16), QPointF(56, 32), QPointF(42, 48)]))
        p.drawLine(36, 12, 28, 52)
    elif kind == "star":  # renown
        pts = []
        for i in range(10):
            r = 26 if i % 2 == 0 else 11
            a = -math.pi / 2 + i * math.pi / 5
            pts.append(QPointF(32 + r * math.cos(a), 34 + r * math.sin(a)))
        p.setBrush(QBrush(c))
        p.drawPolygon(QPolygonF(pts))
    elif kind == "cube":  # asset definitions
        top = QPolygonF([QPointF(32, 6), QPointF(56, 18), QPointF(32, 30), QPointF(8, 18)])
        p.setBrush(QBrush(c))
        p.drawPolygon(top)
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(QPolygonF([QPointF(8, 18), QPointF(32, 30), QPointF(32, 58), QPointF(8, 46)]))
        p.drawPolygon(QPolygonF([QPointF(56, 18), QPointF(32, 30), QPointF(32, 58), QPointF(56, 46)]))
    elif kind == "sliders":  # presets
        for y, x in ((16, 22), (32, 42), (48, 28)):
            p.drawLine(8, y, 56, y)
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(x, y), 6, 6)
            p.setBrush(Qt.NoBrush)
    elif kind == "bubble":  # edit dialogue
        path = QPainterPath()
        path.addRoundedRect(QRectF(6, 8, 52, 34), 10, 10)
        p.drawPath(path)
        p.drawPolyline(QPolygonF([QPointF(18, 42), QPointF(14, 56), QPointF(30, 42)]))
        for x in (20, 32, 44):
            p.drawPoint(QPointF(x, 25))
    elif kind == "bolt":  # quick dialogue
        path = QPainterPath()
        path.addRoundedRect(QRectF(4, 8, 44, 30), 9, 9)
        p.drawPath(path)
        p.setBrush(QBrush(c))
        p.setPen(_pen(c, 2))
        p.drawPolygon(QPolygonF([QPointF(46, 26), QPointF(36, 44), QPointF(44, 44), QPointF(38, 60),
                                 QPointF(58, 36), QPointF(49, 36), QPointF(56, 26)]))
    elif kind == "person":  # avatar fallback
        p.drawEllipse(QPointF(32, 20), 11, 11)
        p.drawArc(QRectF(12, 34, 40, 40), 0, 180 * 16)
    elif kind == "db":  # store manager
        for y in (14, 30, 46):
            p.drawEllipse(QRectF(12, y - 6, 40, 12))
        p.drawLine(12, 14, 12, 46)
        p.drawLine(52, 14, 52, 46)
    elif kind == "frame":  # portraits: an empty picture frame
        p.setPen(_pen(c, 4))
        p.drawRect(QRectF(8, 8, 48, 48))
        p.setPen(_pen(c, 2))
        p.drawRect(QRectF(15, 15, 34, 34))
        for x, y in ((8, 8), (56, 8), (8, 56), (56, 56)):
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(x, y), 4, 4)
        p.drawLine(15, 15, 8, 8)
        p.drawLine(49, 15, 56, 8)
        p.drawLine(15, 49, 8, 56)
        p.drawLine(49, 49, 56, 56)
    elif kind == "scroll":  # paralogue maker: a map with a route
        path = QPainterPath(QPointF(8, 14))
        path.lineTo(24, 8)
        path.lineTo(40, 14)
        path.lineTo(56, 8)
        path.lineTo(56, 50)
        path.lineTo(40, 56)
        path.lineTo(24, 50)
        path.lineTo(8, 56)
        path.closeSubpath()
        p.drawPath(path)
        p.setPen(_pen(c, 2))
        p.drawLine(24, 8, 24, 50)
        p.drawLine(40, 14, 40, 56)
        dash = QPen(c, 3, Qt.DashLine)
        p.setPen(dash)
        p.drawPolyline(QPolygonF([QPointF(14, 44), QPointF(28, 30), QPointF(38, 38), QPointF(48, 22)]))
        p.setPen(_pen(c, 4))
        p.drawLine(44, 18, 52, 26)
        p.drawLine(52, 18, 44, 26)
    elif kind == "coins":  # store manager: two stacks of gold coins
        for x0, n in ((8, 4), (32, 3)):
            for i in range(n):
                y = 50 - i * 8
                p.setPen(_pen(QColor("#5a4318"), 2))
                p.setBrush(QBrush(c))
                p.drawEllipse(QRectF(x0, y - 6, 24, 12))
        p.setPen(_pen(QColor("#5a4318"), 2))
        p.drawLine(44, 24, 44, 30)
    elif kind == "sword":  # items fallback
        p.setBrush(QBrush(c))
        p.drawPolygon(QPolygonF([QPointF(50, 8), QPointF(56, 14), QPointF(26, 44), QPointF(20, 38)]))
        p.drawLine(14, 34, 30, 50)
        p.drawLine(22, 42, 10, 54)
    elif kind == "seal":  # classes fallback: a seal medal
        p.drawEllipse(QPointF(32, 24), 16, 16)
        p.setBrush(QBrush(c))
        p.drawEllipse(QPointF(32, 24), 8, 8)
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(22, 36), QPointF(18, 58), QPointF(26, 52), QPointF(30, 40)]))
        p.drawPolyline(QPolygonF([QPointF(42, 36), QPointF(46, 58), QPointF(38, 52), QPointF(34, 40)]))
    elif kind == "skill":  # skills fallback: a burst
        pts = []
        for i in range(16):
            rr = 26 if i % 2 == 0 else 12
            a = i * math.pi / 8
            pts.append(QPointF(32 + rr * math.cos(a), 32 + rr * math.sin(a)))
        p.setBrush(QBrush(c))
        p.drawPolygon(QPolygonF(pts))
    elif kind == "army":  # armies fallback: three soldiers
        p.setBrush(QBrush(c))
        for x, y, r in ((18, 26, 6), (46, 26, 6), (32, 20, 7)):
            p.drawEllipse(QPointF(x, y), r, r)
        for x, w in ((18, 14), (46, 14)):
            p.drawRoundedRect(QRectF(x - w / 2, 36, w, 18), 5, 5)
        p.drawRoundedRect(QRectF(23, 30, 18, 26), 6, 6)
    elif kind == "palette":  # UI colors
        p.setBrush(QBrush(QColor("#00000000")))
        path = QPainterPath()
        path.addEllipse(QRectF(6, 8, 52, 46))
        hole = QPainterPath()
        hole.addEllipse(QRectF(36, 34, 12, 12))
        p.drawPath(path.subtracted(hole))
        for (x, y), col in zip(((20, 22), (32, 16), (44, 22), (18, 38)), ("#e05d5d", "#f2c94c", "#6fcf97", "#56ccf2")):
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(col)))
            p.drawEllipse(QPointF(x, y), 5, 5)
    else:
        p.setFont(QFont("Arial", 28, QFont.Bold))
        p.drawText(QRectF(0, 0, S, S), Qt.AlignCenter, kind[:1].upper())
    p.end()
    icon = QIcon(pm)
    DRAWN_KEYS.add(icon.cacheKey())
    return icon


def _pixel_icon(pm: QPixmap) -> QIcon:
    if pm is None or pm.isNull():
        return None
    return QIcon(pm.scaled(S, S, Qt.KeepAspectRatio, Qt.FastTransformation))


def _icon_from_table(gs, table, key, model):
    rid = gs.data.key_to_rid(table, key)
    if rid is None:
        return None
    idx = gs.data.int(rid, "icon")
    m = gs.icons.model(model)
    if m is None or idx is None or idx >= m.rowCount():
        return None
    return _pixel_icon(m.icons[idx])


def map_sprite_image(read, names, color="青"):
    """First frame (idle, facing the camera) of the first map sprite in `names` that exists, as a
    square Pillow image. read(path) returns the file's bytes or None."""
    from paragon.unlimited.sprites.sprite_sheets import _decompress, sheet_from_ctpk

    for name in names:
        try:
            data = read(f"map/unit/{name}{color}.ctpk.lz")
            if not data:
                continue
            sheet = sheet_from_ctpk(_decompress(bytes(data)))
        except Exception:
            continue
        img = Image.frombytes("RGBA", (sheet.width, sheet.height), bytes(sheet.rgba)).crop((0, 0, 32, 32))
        box = img.getbbox()
        if box is None:
            continue
        img = img.crop(box)
        side = max(img.width, img.height)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.alpha_composite(img, ((side - img.width) // 2, (side - img.height) // 2))
        return square
    return None


def map_sprite_icon(gs, names, color="青"):
    def read(path):
        return gs.data.read_file(path) if gs.data.file_exists(path, False) else None

    img = map_sprite_image(read, names, color)
    if img is None:
        return None
    alpha = img.getchannel("A").point(lambda a: 255 if a else 0)  # the game draws sprites see-through
    img.putalpha(alpha)
    scale = max(1, S // img.width)
    return QIcon(img.resize((img.width * scale, img.height * scale), Image.NEAREST).toqpixmap())


def _army_shield(gs):
    """The blue (player army) shield from the game's army icons (systems/icon*.ctpk.lz, belong.tga)."""
    for path in ("systems/icon_E.ctpk.lz", "systems/icon.ctpk.lz", "systems/icon_U.ctpk.lz"):
        try:
            if not gs.data.file_exists(path, False):
                continue
            t = gs.data.read_ctpk_textures(path)["belong.tga"]
        except Exception:
            continue
        img = Image.frombytes("RGBA", (t.width, t.height), bytes(t.pixel_data), "raw", "RGBA").crop((0, 0, 40, 40))
        if img.getbbox() is None:
            continue
        return QIcon(img.crop(img.getbbox()).toqpixmap())
    return None


# Buttons whose icon is pixel art from the game (scaled without smoothing on the home page),
# unless the game image was not found and a drawn icon is used instead.
PIXEL_ART = {"characters_button", "items_button", "classes_button", "skills_button", "armies_button",
             "configure_avatar_button", "sprite_data_button", "sprite_workshop_button"}


def fe13_button_icons(gs, config=None):
    """{button attribute name: QIcon}."""
    def safe(fn, fallback):
        try:
            ic = fn()
            if ic is not None and not ic.isNull():
                return ic
        except Exception:
            logging.exception("Icon lookup failed; using a drawn icon.")
        return drawn(fallback)

    return {
        "characters_button": safe(lambda: map_sprite_icon(gs, ["ロード男"]), "person"),  # Chrom (Lord)
        "items_button": safe(lambda: _icon_from_table(gs, "items", "IID_封剣ファルシオン", "item"), "sword"),
        "classes_button": safe(lambda: _icon_from_table(gs, "items", "IID_マスタープルフ", "item"), "seal"),
        "skills_button": safe(lambda: _icon_from_table(gs, "skills", "RSID_天空", "skill"), "skill"),
        "armies_button": safe(lambda: _army_shield(gs), "army"),
        "chapters_button": drawn("flag"),
        "tiles_button": drawn("grid"),
        "sprite_data_button": safe(lambda: map_sprite_icon(gs, ["ソルジャー男"]), "sprite"),
        "gmap_button": drawn("pin"),
        "endings_button": drawn("book"),
        "scripts_button": drawn("code"),
        "renown_button": drawn("star"),
        "asset_definitions_button": drawn("cube"),
        "presets_button": drawn("sliders"),
        "portraits_button": drawn("frame"),
        "edit_dialogue_button": drawn("bubble"),
        "quick_dialogue_button": drawn("bolt"),
        # default male Robin: Tactician, build 2, first hair style
        "configure_avatar_button": safe(lambda: map_sprite_icon(gs, ["戦術師20男", "戦術師男"]), "person"),
        "store_manager_button": drawn("coins"),
        "map_maker_button": drawn("scroll"),
        "sprite_workshop_button": safe(lambda: map_sprite_icon(gs, ["剣士男"]), "sprite"),
        "ui_colors_button": drawn("palette"),
    }
