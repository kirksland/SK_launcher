from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6 import QtCore, QtWidgets

from core.asset_inventory import AssetInventory
from ui.widgets.asset_file_row import AssetFileRow
from ui.widgets.asset_version_row import AssetVersionRow


class AssetInventoryRenderer:
    def __init__(
        self,
        list_widget: QtWidgets.QListWidget,
        hint_label: Optional[QtWidgets.QLabel] = None,
        *,
        cache_root: Optional[Path] = None,
    ) -> None:
        self.list_widget = list_widget
        self.hint_label = hint_label
        self.cache_root = cache_root
        self._pending_rows: list[object] = []
        self._hydrate_index = 0

    def render(
        self,
        inventory: AssetInventory,
        *,
        on_selected_path: Callable[[Path, str], None],
    ) -> Optional[Path]:
        self.list_widget.clear()
        self._pending_rows = []
        self._hydrate_index = 0
        if self.hint_label is not None:
            self.hint_label.setText(inventory.hint)

        first_video: Optional[Path] = None
        if inventory.bundles:
            first_video = self._render_bundles(inventory, on_selected_path)
        elif inventory.files:
            self._render_files(inventory)
        else:
            self.list_widget.addItem(inventory.empty_message)
        self._schedule_thumbnail_hydration()
        return first_video

    def _render_bundles(
        self,
        inventory: AssetInventory,
        on_selected_path: Callable[[Path, str], None],
    ) -> Optional[Path]:
        first_video: Optional[Path] = None
        for bundle in inventory.bundles:
            row = AssetVersionRow(
                bundle.name,
                bundle.entries,
                parent=self.list_widget,
                cache_root=self.cache_root,
            )
            item = QtWidgets.QListWidgetItem()
            item.setSizeHint(QtCore.QSize(280, 40))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)
            self._pending_rows.append(row)

            def sync_item_data(
                _row: AssetVersionRow = row,
                _item: QtWidgets.QListWidgetItem = item,
            ) -> None:
                path, kind = _row.selected_path()
                if path is None:
                    _item.setData(QtCore.Qt.ItemDataRole.UserRole, "")
                    _item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, None)
                    return
                _item.setData(QtCore.Qt.ItemDataRole.UserRole, str(path))
                _item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, kind)

            def sync_item_data_and_preview(
                _row: AssetVersionRow = row,
                _item: QtWidgets.QListWidgetItem = item,
            ) -> None:
                sync_item_data(_row, _item)
                path, kind = _row.selected_path()
                if path is not None and kind is not None:
                    on_selected_path(path, kind)

            row.selection_changed.connect(sync_item_data_and_preview)
            sync_item_data()
            if first_video is None:
                first_video = _first_video_path(bundle.entries)
        return first_video

    def _render_files(self, inventory: AssetInventory) -> None:
        for file_entry in inventory.files:
            row = AssetFileRow(
                file_entry,
                parent=self.list_widget,
                cache_root=self.cache_root,
            )
            item = QtWidgets.QListWidgetItem()
            item.setSizeHint(QtCore.QSize(280, 44))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(file_entry.path))
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, file_entry.kind)
            item.setToolTip(str(file_entry.path))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)
            self._pending_rows.append(row)

    def _schedule_thumbnail_hydration(self) -> None:
        if not self._pending_rows:
            return
        QtCore.QTimer.singleShot(0, self._hydrate_thumbnail_batch)

    def _hydrate_thumbnail_batch(self) -> None:
        if not self._pending_rows:
            return
        batch_size = 8
        end = min(self._hydrate_index + batch_size, len(self._pending_rows))
        for row in self._pending_rows[self._hydrate_index:end]:
            refresh = getattr(row, "refresh_thumbnail", None)
            if callable(refresh):
                refresh()
        self._hydrate_index = end
        if self._hydrate_index < len(self._pending_rows):
            QtCore.QTimer.singleShot(0, self._hydrate_thumbnail_batch)


def _first_video_path(entries: list[dict[str, object]]) -> Optional[Path]:
    for entry in entries:
        video = entry.get("video")
        if isinstance(video, Path):
            return video
    return None
