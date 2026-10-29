"""Paragon Unlimited - icons for the FE13 main window buttons.

Game-themed icons are taken from YOUR game files at run time (item / skill / army icons and
FC portraits, the same images Paragon already shows in its editors); nothing from the game is
bundled. Everything else is a small drawn icon. Any lookup that fails falls back to a drawn one.
"""
import logging
import math

from PIL import Image
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QPolygonF, QFont

S = 64  # drawing canvas; Qt scales the icon down


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
    return QIcon(pm)


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


def _face_icon(gs, fsid):
    """FC portrait cropped to the face (the game's own menu crop), as an icon."""
    textures = gs.portraits.from_fsid(fsid)
    if not textures or "通常" not in textures:
        return None
    img = textures["通常"].to_pillow_image()
    rid = gs.data.key_to_rid("portraits", fsid)
    cx = cy = 0
    cw, ch = img.width, img.height
    if rid is not None:
        cx = gs.data.int(rid, "portrait_menu_position_x") or 0
        cy = gs.data.int(rid, "portrait_menu_position_y") or 0
        cw = gs.data.int(rid, "portrait_menu_size_x") or cw
        ch = gs.data.int(rid, "portrait_menu_size_y") or ch
    side = min(cw, ch)
    img = img.crop((cx, cy, cx + side, cy + side)).transpose(Image.FLIP_LEFT_RIGHT)
    return QIcon(img.resize((S, S), Image.LANCZOS).toqpixmap())


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

    avatar_fsid = None
    try:
        fid = config.fe13_avatar.portraits if config else None
        if fid:
            avatar_fsid = f"FSID_FC_{fid[4:]}_通常"
    except Exception:
        pass

    return {
        "characters_button": safe(lambda: _face_icon(gs, "FSID_FC_クロム_通常"), "person"),
        "items_button": safe(lambda: _icon_from_table(gs, "items", "IID_封剣ファルシオン", "item"), "sword"),
        "classes_button": safe(lambda: _icon_from_table(gs, "items", "IID_マスタープルフ", "item"), "class"),
        "skills_button": safe(lambda: _icon_from_table(gs, "skills", "RSID_天空", "skill"), "skill"),
        "armies_button": safe(lambda: _pixel_icon(gs.icons.model("belong").icons[0]) if gs.icons.model("belong") else None, "army"),
        "chapters_button": drawn("flag"),
        "tiles_button": drawn("grid"),
        "sprite_data_button": drawn("sprite"),
        "gmap_button": drawn("pin"),
        "endings_button": drawn("book"),
        "scripts_button": drawn("code"),
        "renown_button": drawn("star"),
        "asset_definitions_button": drawn("cube"),
        "presets_button": drawn("sliders"),
        "portraits_button": safe(lambda: _face_icon(gs, "FSID_FC_リズ_通常"), "person"),
        "edit_dialogue_button": drawn("bubble"),
        "quick_dialogue_button": drawn("bolt"),
        "configure_avatar_button": safe(lambda: _face_icon(gs, avatar_fsid) if avatar_fsid else None, "person"),
        "store_manager_button": drawn("db"),
        "ui_colors_button": drawn("palette"),
    }
