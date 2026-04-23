from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets


class BoardGroupsTree(QtWidgets.QTreeWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)

    def mimeData(self, items: list[QtWidgets.QTreeWidgetItem]) -> QtCore.QMimeData:  # type: ignore[override]
        mime = QtCore.QMimeData()
        urls: list[QtCore.QUrl] = []
        for item in items:
            path_text = item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)
            if not path_text:
                continue
            urls.append(QtCore.QUrl.fromLocalFile(str(path_text)))
        if urls:
            mime.setUrls(urls)
            mime.setText(urls[0].toLocalFile())
        return mime
