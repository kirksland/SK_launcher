from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from ui.utils.thumbnails import AsyncExrThumbnailLoader, is_exr_path, load_media_pixmap, make_placeholder_pixmap
from ui.utils.styles import PALETTE, combo_dark_style


class AssetVersionRow(QtWidgets.QWidget):
    selection_changed = QtCore.Signal()

    def __init__(
        self,
        base_name: str,
        entries: List[Dict[str, object]],
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        preview_loader: Optional[AsyncExrThumbnailLoader] = None,
        cache_root: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        self._entries = entries
        self._entry_by_label = {str(e.get("label")): e for e in entries}
        self._thumb_size = QtCore.QSize(48, 30)
        self._preview_loader = preview_loader
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

        self.name_label = QtWidgets.QLabel(base_name)
        self.name_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.name_label, 1)

        self.types_label = QtWidgets.QLabel("")
        self.types_label.setStyleSheet(f"color: {PALETTE['muted']};")
        layout.addWidget(self.types_label, 0)

        self.version_combo = QtWidgets.QComboBox()
        self.version_combo.setFixedWidth(80)
        self.version_combo.setStyleSheet(combo_dark_style())
        for entry in entries:
            self.version_combo.addItem(str(entry.get("label")))
        layout.addWidget(self.version_combo, 0)

        self.version_combo.currentTextChanged.connect(self._on_combo_changed)
        if self._preview_loader is not None:
            self._preview_loader.previewReady.connect(self._on_preview_ready)
        self._update_types_label()
        self._update_thumbnail()

    def _current_entry(self) -> Optional[Dict[str, object]]:
        label = self.version_combo.currentText()
        return self._entry_by_label.get(label)

    def _update_types_label(self) -> None:
        entry = self._current_entry()
        if not entry:
            self.types_label.setText("")
            return
        parts = []
        if entry.get("usd") is not None:
            parts.append("USD")
        if entry.get("video") is not None:
            parts.append("VIDEO")
        if entry.get("image") is not None:
            parts.append("IMG")
        self.types_label.setText(" / ".join(parts))

    def _update_thumbnail(self) -> None:
        entry = self._current_entry()
        if not entry:
            self.thumb_label.clear()
            return
        image = entry.get("image")
        if isinstance(image, Path) and image.exists():
            pixmap = load_media_pixmap(
                image,
                self._thumb_size,
                cache_root=self._cache_root,
                allow_sync_exr=False,
            )
            if not pixmap.isNull():
                scaled = pixmap
                # Center-crop to exact size
                x = max(0, (scaled.width() - self._thumb_size.width()) // 2)
                y = max(0, (scaled.height() - self._thumb_size.height()) // 2)
                self.thumb_label.setPixmap(
                    scaled.copy(x, y, self._thumb_size.width(), self._thumb_size.height())
                )
                return
            if is_exr_path(image) and self._preview_loader is not None:
                self._preview_loader.request(image, self._thumb_size, self._cache_root)
        self.thumb_label.setPixmap(make_placeholder_pixmap("", self._thumb_size))

    def _on_combo_changed(self) -> None:
        self._update_types_label()
        self._update_thumbnail()
        self.selection_changed.emit()

    @QtCore.Slot(str, int, int, bool)
    def _on_preview_ready(self, path_str: str, width: int, height: int, success: bool) -> None:
        entry = self._current_entry()
        image = entry.get("image") if entry else None
        if not success or not isinstance(image, Path):
            return
        if str(image) != path_str:
            return
        if width != self._thumb_size.width() or height != self._thumb_size.height():
            return
        self._update_thumbnail()

    def selected_path(self) -> Tuple[Optional[Path], Optional[str]]:
        entry = self._current_entry()
        if not entry:
            return None, None
        video = entry.get("video")
        usd = entry.get("usd")
        image = entry.get("image")
        if isinstance(video, Path):
            return video, "video"
        if isinstance(usd, Path):
            return usd, "usd"
        if isinstance(image, Path):
            return image, "image"
        return None, None
