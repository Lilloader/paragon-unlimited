"""Paragon Unlimited - choose where a new chapter sits on the world map.

The picker shows the bottom-screen map's layout (the game's chapters and the roads between them)
and the chapter's spot. Click or drag to move the spot. The globe on the top screen follows the
same spot (world_map.from_gm), and the road is drawn from the chapter it appears after.

The game's parchment picture is not drawn behind the spots: it does not line up with the spot
positions in a simple way (the game scales or scrolls it), so the layout uses the spots alone.
"""
import math
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from paragon.unlimited.map_maker import world_map as wm

AREA = (20, 15, 460, 230)  # the part of the bottom-screen map shown (spots are kept in GM_BOUNDS)
TOO_CLOSE = 9  # bottom-map pixels: closer than this to another chapter is hard to tap in the game


def short_name(cid: str) -> str:
    """Short label on the map: 1-26 = chapters, Px = paralogues, U = your slots."""
    if cid.isdigit():
        return str(int(cid))
    if cid.startswith("X") and cid[1:].isdigit():
        return f"P{int(cid[1:])}"
    return cid


class WorldSpotCanvas(QWidget):
    moved = Signal(object)  # (x, y) on the bottom-screen map

    def __init__(self, layout: dict, cid: str, anchor: str, spot: Optional[Tuple[int, int]], parent=None):
        super().__init__(parent)
        self.nodes: Dict[str, Tuple[int, int]] = {k: tuple(v) for k, v in layout.get("nodes", {}).items()}
        self.routes: List[Tuple[str, str]] = list(layout.get("routes", []))
        self.names: Dict[str, str] = dict(layout.get("names", {}))
        self.cid = cid
        self.anchor = anchor
        self.current = self.nodes.pop(cid, None)  # where the chapter is now (if it has a spot)
        self.routes = [r for r in self.routes if cid not in r]
        self.spot = tuple(spot) if spot else None
        self.hover: Optional[str] = None
        self.setMouseTracking(True)
        self.setMinimumSize(660, 330)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # coordinates -------------------------------------------------------------
    def _scale(self) -> Tuple[float, float, float]:
        w = AREA[2] - AREA[0]
        h = AREA[3] - AREA[1]
        s = min(self.width() / w, self.height() / h)
        ox = (self.width() - w * s) / 2
        oy = (self.height() - h * s) / 2
        return s, ox, oy

    def to_screen(self, p) -> QPointF:
        s, ox, oy = self._scale()
        return QPointF(ox + (p[0] - AREA[0]) * s, oy + (p[1] - AREA[1]) * s)

    def to_map(self, pt) -> Tuple[float, float]:
        s, ox, oy = self._scale()
        return (AREA[0] + (pt.x() - ox) / s, AREA[1] + (pt.y() - oy) / s)

    def shown(self) -> Optional[Tuple[int, int]]:
        """The spot the chapter will have (chosen, else where it is now)."""
        return self.spot or self.current

    def nearest(self, p, limit: float = 8) -> Optional[str]:
        best = None
        for k, q in self.nodes.items():
            d = math.hypot(p[0] - q[0], p[1] - q[1])
            if d <= limit and (best is None or d < best[0]):
                best = (d, k)
        return best[1] if best else None

    def crowded(self) -> Optional[str]:
        """The chapter the spot is too close to, if any."""
        s = self.shown()
        if s is None:
            return None
        return self.nearest(s, TOO_CLOSE)

    # input --------------------------------------------------------------------
    def set_spot(self, spot):
        self.spot = wm.clamp_gm(*spot) if spot else None
        self.update()
        self.moved.emit(self.spot)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.set_spot(self.to_map(e.position()))

    def mouseMoveEvent(self, e):
        p = self.to_map(e.position())
        if e.buttons() & Qt.LeftButton:
            self.set_spot(p)
            return
        h = self.nearest(p)
        if h != self.hover:
            self.hover = h
            self.setToolTip(self.names.get(h, h) if h else "")
            self.update()

    # drawing ------------------------------------------------------------------
    def paintEvent(self, _e):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.fillRect(self.rect(), QColor(38, 52, 58))
        s, _ox, _oy = self._scale()
        a = self.to_screen((wm.GM_BOUNDS[0], wm.GM_BOUNDS[1]))
        b = self.to_screen((wm.GM_BOUNDS[2], wm.GM_BOUNDS[3]))
        qp.fillRect(QRectF(a, b), QColor(70, 84, 78))
        qp.setPen(QPen(QColor(150, 140, 110), 1, Qt.DashLine))
        qp.drawRect(QRectF(a, b))
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, s * 3.2))
        qp.setFont(font)
        # roads
        qp.setPen(QPen(QColor(170, 150, 110, 160), max(1.0, s * 0.6)))
        for f, t in self.routes:
            if f in self.nodes and t in self.nodes:
                qp.drawLine(self.to_screen(self.nodes[f]), self.to_screen(self.nodes[t]))
        # the road of this chapter
        spot = self.shown()
        if spot is not None and self.anchor in self.nodes:
            qp.setPen(QPen(QColor(235, 90, 80), max(1.5, s * 0.8), Qt.DashLine))
            qp.drawLine(self.to_screen(self.nodes[self.anchor]), self.to_screen(spot))
        # the game's chapters
        r = max(3.0, s * 2.2)
        for k, q in self.nodes.items():
            c = self.to_screen(q)
            if k == self.anchor:
                fill, edge = QColor(245, 200, 80), QColor(255, 240, 190)
            elif k == self.hover:
                fill, edge = QColor(230, 230, 230), QColor(255, 255, 255)
            elif k.startswith("U"):
                fill, edge = QColor(150, 190, 240), QColor(220, 235, 255)
            else:
                fill, edge = QColor(205, 190, 150), QColor(90, 75, 50)
            qp.setPen(QPen(edge, 1))
            qp.setBrush(fill)
            qp.drawEllipse(c, r, r)
            qp.setPen(QColor(235, 230, 215))
            qp.drawText(c + QPointF(r + 2, -r), short_name(k))
        # this chapter
        if spot is not None:
            c = self.to_screen(spot)
            rr = r * 1.8
            path = QPainterPath()
            path.moveTo(c + QPointF(0, -rr))
            path.lineTo(c + QPointF(rr, 0))
            path.lineTo(c + QPointF(0, rr))
            path.lineTo(c + QPointF(-rr, 0))
            path.closeSubpath()
            qp.setPen(QPen(QColor(255, 235, 230), 1.5))
            qp.setBrush(QColor(225, 60, 55) if self.spot else QColor(225, 60, 55, 110))
            qp.drawPath(path)
            qp.setPen(QColor(255, 225, 220))
            qp.drawText(c + QPointF(rr + 3, rr), short_name(self.cid))
        qp.end()


class WorldSpotDialog(QDialog):
    """Returns the chosen spot with spot() ((x, y), or None = automatic, next to the chapter it
    appears after)."""

    def __init__(self, layout: dict, cid: str, anchor: str, spot=None, anchor_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"World map spot of {cid}")
        v = QVBoxLayout(self)
        intro = QLabel(
            "Click (or drag) where the chapter should be on the world map. The globe on the top screen "
            f"follows the same spot, and the road starts at <b>{anchor_name or anchor}</b> (gold), the "
            "chapter it appears after. Point at a chapter to see its name.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        self.canvas = WorldSpotCanvas(layout, cid, anchor, spot, self)
        v.addWidget(self.canvas, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        legend = QLabel("<small>Numbers are the story chapters, P = paralogues, blue = your chapters. "
                        "Valm is on the left, Ylisse and the other lands of Archanea on the right.</small>")
        legend.setWordWrap(True)
        v.addWidget(legend)
        row = QHBoxLayout()
        self.auto_button = QPushButton("Automatic (next to the chapter)")
        self.auto_button.setToolTip("Let the Map Maker pick a free spot next to the chapter it appears after.")
        self.auto_button.clicked.connect(lambda: self.canvas.set_spot(None))
        row.addWidget(self.auto_button)
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        v.addLayout(row)
        self.canvas.moved.connect(self._status)
        self._status()
        self.resize(860, 560)

    def _status(self, *_):
        c = self.canvas
        if c.spot is None:
            text = ("<b>Automatic:</b> placed in a free spot next to the chapter it appears after"
                    + (" (shown faded: where it is now)." if c.current else "."))
        else:
            text = f"<b>Chosen spot:</b> {c.spot[0]}, {c.spot[1]} on the bottom-screen map."
        near = c.crowded()
        if near and c.spot is not None:
            text += (f" <span style='color:#d06030'>Very close to {c.names.get(near, near)}: "
                     "the two may be hard to tell apart in the game.</span>")
        self.status.setText(text)

    def spot(self) -> Optional[Tuple[int, int]]:
        return self.canvas.spot
