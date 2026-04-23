from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.asset_inventory import AssetInventoryFile
from ui.utils.styles import PALETTE
from ui.utils.thumbnails import load_media_pixmap, make_placeholder_pixmap


class AssetFileRow(QtWidgets.QWidget):
    def __init__(
        self,
        entry: AssetInventoryFile,
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        cache_root: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        self.entry = entry
        self._thumb_size = QtCore.QSize(48, 30)
        self._cache_root = cache_root

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)

        self.thumb_label = QtWidgets.QLabel()
        self.thumb_label.setFixedSize(self._thumb_size)
        self.thumb_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet(
            f"background: {PALETTE['thumb_bg']}; border: 1px solid {PALETTE['border']};"
        )
        layout.addWidget(self.thumb_label, 0)

        text_block = QtWidgets.QVBoxLayout()
        text_block.setContentsMargins(0, 0, 0, 0)
        text_block.setSpacing(1)
        layout.addLayout(text_block, 1)

        self.name_label = QtWidgets.QLabel(entry.label)
        self.name_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        text_block.addWidget(self.name_label, 0)

        self.path_label = QtWidgets.QLabel(entry.relative_label)
        self.path_label.setStyleSheet(f"color: {PALETTE['muted']};")
        text_block.addWidget(self.path_label, 0)

        self.type_label = QtWidgets.QLabel(self._type_label(entry.path))
        self.type_label.setStyleSheet(f"color: {PALETTE['muted']};")
        layout.addWidget(self.type_label, 0)

        self.show_placeholder_thumbnail()

    def selected_path(self) -> tuple[Path, str]:
        return self.entry.path, self.entry.kind

    def show_placeholder_thumbnail(self) -> None:
        self.thumb_label.setPixmap(make_placeholder_pixmap(self.entry.path.suffix.upper(), self._thumb_size))

    def refresh_thumbnail(self) -> None:
        thumbnail_path = self.entry.thumbnail_path
        if thumbnail_path and thumbnail_path.exists():
            pixmap = load_media_pixmap(
                thumbnail_path,
                self._thumb_size,
                cache_root=self._cache_root,
                allow_sync_exr=True,
            )
            if not pixmap.isNull():
                scaled = pixmap
                x = max(0, (scaled.width() - self._thumb_size.width()) // 2)
                y = max(0, (scaled.height() - self._thumb_size.height()) // 2)
                self.thumb_label.setPixmap(
                    scaled.copy(x, y, self._thumb_size.width(), self._thumb_size.height())
                )
                return
        self.show_placeholder_thumbnail()

    @staticmethod
    def _type_label(path: Path) -> str:
        suffix = path.suffix.upper().lstrip(".")
        return suffix or "FILE"
