import struct
from typing import Any, List

from PySide6 import QtCore
from PySide6.QtCore import QAbstractListModel, QModelIndex, QMimeData, QByteArray

from paragon.core.display import display_rid
from paragon.unlimited.characters import job_rows


_REORDERING_MIMETYPE = "application/paragon-model-row"
_ASKED = {"class_move": False}


def ask_class_move() -> bool:
    """Asked once per session before the first class is moved in the class list."""
    if _ASKED["class_move"]:
        return True
    from PySide6.QtWidgets import QMessageBox

    answer = QMessageBox.question(
        None,
        "Move a class",
        "Moving a class changes its number (its place in the class list).\n\n"
        "Paragon moves every character's sprite list entry with it, so map sprites stay right. "
        "Anything else that counts classes by number (a code patch, notes you made, other tools) "
        "is not updated.\n\nMove it? (You will not be asked again until Paragon is restarted.)",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if answer == QMessageBox.Yes:
        _ASKED["class_move"] = True
        return True
    return False


class ListFieldModel(QAbstractListModel):
    def __init__(self, gd, icons, rid, field_id, display_function=None):
        super().__init__()
        self.gd = gd
        self.icons = icons
        self.rid = rid
        self.field_id = field_id
        self.display_function = display_function
        self._job_list = None
        self.confirm_job_move = ask_class_move  # tests replace it

    def _is_job_list(self) -> bool:
        """FE13's class list: moving / inserting / deleting classes also does it to every
        character's sprite list (one entry per class)."""
        if self._job_list is None:
            self._job_list = job_rows.is_job_list(self.gd, self.rid, self.field_id)
        return self._job_list

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return self.gd.list_size(self.rid, self.field_id)

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if not index.isValid():
            return None
        rid = self.gd.list_get(self.rid, self.field_id, index.row())
        if role == QtCore.Qt.DisplayRole:
            if self.display_function:
                display = display_rid(self.gd, rid, self.display_function, index.row())
            else:
                display = None
            display = display if display else self.gd.display(rid)
            display = display if display else self.gd.key(rid)
            display = display if display else "Item"
            return f"{display} #{index.row() + 1}"
        elif role == QtCore.Qt.DecorationRole:
            return self.icons.icon(rid)
        elif role == QtCore.Qt.UserRole:
            return rid
        return None

    def insertRows(self, row: int, count: int, parent: QModelIndex = ...) -> bool:
        if row > self.rowCount():
            return False
        else:
            at_end = row == self.rowCount()
            self.beginInsertRows(parent, row, row + count - 1)
            for i in range(0, count):
                self.gd.list_insert(self.rid, self.field_id, row)
            self.endInsertRows()
            if not at_end and self._is_job_list():
                job_rows.inserted(self.gd, row, count)
            return True

    def _move_row(self, source_row: int, dest_row: int) -> bool:
        """Move one row (dest_row counted after removing it). One model reset around the whole
        change: resetting inside an insert left Qt's views pointing at stale rows (a crash)."""
        if self._is_job_list() and not self.confirm_job_move():
            return False
        self.beginResetModel()
        try:
            rid = self.gd.list_get(self.rid, self.field_id, source_row)
            self.gd.list_remove(self.rid, self.field_id, source_row)
            self.gd.list_insert_existing(self.rid, self.field_id, rid, dest_row)
            if self._is_job_list():
                job_rows.moved(self.gd, source_row, dest_row)
        finally:
            self.endResetModel()
        return True

    def removeRows(self, row: int, count: int, parent: QModelIndex = ...) -> bool:
        if row >= self.rowCount() or row + count > self.rowCount():
            return False
        else:
            self.beginRemoveRows(parent, row, row + count - 1)
            for _ in range(0, count):
                self.gd.list_remove(self.rid, self.field_id, row)
            self.endRemoveRows()
            if self._is_job_list():
                job_rows.removed(self.gd, row, count)
            return True

    def moveRows(self, source_parent, source_row, count, dest_parent, dest_child) -> bool:
        """Qt's list views move rows with this (dest_child: the row to insert before)."""
        if count != 1 or not (0 <= source_row < self.rowCount()) or not (0 <= dest_child <= self.rowCount()):
            return False
        if dest_child in (source_row, source_row + 1):
            return False
        return self._move_row(source_row, dest_child - 1 if dest_child > source_row else dest_child)

    def add_item(self):
        self.insertRow(self.rowCount())

    def supportedDropActions(self) -> QtCore.Qt.DropActions:
        return QtCore.Qt.MoveAction

    def flags(self, index: QModelIndex) -> QtCore.Qt.ItemFlags:
        flags = super().flags(index)
        if index.isValid():
            return QtCore.Qt.ItemIsDragEnabled | flags
        else:
            return QtCore.Qt.ItemIsDropEnabled | flags

    def mimeTypes(self) -> List:
        return [_REORDERING_MIMETYPE]

    def mimeData(self, indexes: List) -> QMimeData:
        if not indexes:
            return QMimeData()
        raw_data = bytearray()
        for index in indexes:
            raw_data.extend(index.row().to_bytes(8, byteorder="little"))
        mime_data = QMimeData()
        mime_data.setData(_REORDERING_MIMETYPE, QByteArray(raw_data))
        return mime_data

    def dropMimeData(
        self,
        data: QMimeData,
        action: QtCore.Qt.DropAction,
        row: int,
        column: int,
        parent: QModelIndex,
    ) -> bool:
        raw_indices = bytearray(data.data(_REORDERING_MIMETYPE))
        source_row = struct.unpack_from("<L", raw_indices, 0)[0]
        if source_row not in range(0, self.rowCount()):
            return False
        if row < 0 or row > self.rowCount():
            row = self.rowCount()  # dropped below the last row
        dest_row = row - 1 if source_row < row else row
        if dest_row == source_row:
            return False
        return self._move_row(source_row, dest_row)
