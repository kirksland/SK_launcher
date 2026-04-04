from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.fs import (
    latest_preview_image,
    list_preview_images,
    list_review_videos,
    list_usd_versions,
    name_prefix,
)
from core.metadata import load_metadata
from core.settings import save_settings
from core.watchers import update_watcher_paths
from ui.utils.thumbnails import build_thumbnail_pixmap
from ui.widgets.asset_version_row import AssetVersionRow
from ui.widgets.project_card import ProjectCard
from core.versions import group_asset_versions


class AssetManagerController:
    def __init__(self, window: QtWidgets.QMainWindow) -> None:
        self.w = window
        self._thumb_cache: dict[tuple, tuple[float, QtGui.QPixmap]] = {}

    def refresh_asset_manager(self, *_: object) -> None:
        self.w.asset_grid.clear()
        entries = list(self.w._asset_manager_projects)
        query = self.w.asset_search_input.text().strip().lower()
        if query:
            entries = [e for e in entries if query in str(e.get("local_path", "")).lower()]

        projects: List[Path] = []
        for entry in entries:
            path = Path(str(entry.get("local_path", "")))
            if path.exists() and path.is_dir():
                projects.append(path)

        self.w.project_controller.prune_cache(projects, self.w._asset_cache)

        for project in projects:
            entry = next((e for e in entries if Path(e.get("local_path", "")) == project), None)
            show_cloud = bool(entry and entry.get("client_id"))
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(project))
            item.setSizeHint(QtCore.QSize(230, 240))
            self.w.asset_grid.addItem(item)
            hips = self.w.project_controller.get_project_hips(project, self.w._asset_cache)
            card = ProjectCard(project, self.w.asset_grid.iconSize(), hips, show_cloud_badge=show_cloud, parent=self.w.asset_grid)
            self.w.asset_grid.setItemWidget(item, card)

        self.w.asset_status.setText(f"{self.w.asset_grid.count()} project(s) found.")
        self._refresh_asset_watch_paths()

    def open_asset_details(self, item: QtWidgets.QListWidgetItem) -> None:
        project_path = Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        self.w.asset_details_title.setText(project_path.name)
        self.w.asset_shots_list.clear()
        self.w.asset_assets_list.clear()
        self.w.asset_versions_list.clear()
        self.w.asset_history_list.clear()

        # Clear detail fields until an entity is selected
        self.w.asset_preview.clear()
        self.w.asset_meta.setText("Select a shot or asset to view details.")
        self.w.asset_versions_list.addItem("No entity selected")
        self.w.asset_history_list.addItem("No entity selected")

        # Populate shots/assets from selected server project (fallback to test pipeline)
        if project_path.exists():
            self.w._asset_current_project_root = project_path
        else:
            self.w._asset_current_project_root = self.w.test_pipeline_root
        self._refresh_asset_entity_lists(target="both")

        self.w.asset_pages.setCurrentIndex(1)

    def set_asset_status(self, text: str) -> None:
        if not text:
            self.w.asset_status.setText("")
            self.w.asset_status.setToolTip("")
            return
        metrics = QtGui.QFontMetrics(self.w.asset_status.font())
        width = max(self.w.asset_status.width(), 320)
        elided = metrics.elidedText(
            text,
            QtCore.Qt.TextElideMode.ElideMiddle,
            width,
        )
        self.w.asset_status.setText(elided)
        self.w.asset_status.setToolTip(text)

    def show_asset_version_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.w.asset_versions_list.itemAt(pos)
        if item is None:
            return
        widget = self.w.asset_versions_list.itemWidget(item)
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        kind = item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        if isinstance(widget, AssetVersionRow):
            path, kind = widget.selected_path()
            path_text = str(path) if path else ""
        if not path_text or not isinstance(path_text, str):
            return
        menu = QtWidgets.QMenu(self.w)
        label = "Copy Path" if kind not in ("usd", "video", "image") else f"Copy {str(kind).upper()} Path"
        action = menu.addAction(label)
        chosen = menu.exec(self.w.asset_versions_list.mapToGlobal(pos))
        if chosen == action:
            normalized = self.w._to_houdini_path(path_text)
            QtWidgets.QApplication.clipboard().setText(normalized)
            self.set_asset_status(f"Copied: {normalized}")

    def show_asset_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.w.asset_assets_list.itemAt(pos)
        if item is None:
            return
        menu = QtWidgets.QMenu(self.w)
        action = menu.addAction("Copy Asset Path")
        chosen = menu.exec(self.w.asset_assets_list.mapToGlobal(pos))
        if chosen == action:
            path = str(item.data(QtCore.Qt.ItemDataRole.UserRole))
            normalized = self.w._to_houdini_path(path)
            QtWidgets.QApplication.clipboard().setText(normalized)
            self.set_asset_status(f"Copied: {normalized}")

    def show_asset_manager_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.w.asset_grid.itemAt(pos)
        if item is None:
            return
        menu = QtWidgets.QMenu(self.w)
        action = menu.addAction("Remove from Asset Manager")
        chosen = menu.exec(self.w.asset_grid.mapToGlobal(pos))
        if chosen == action:
            path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if not path_text:
                return
            project_path = str(path_text)
            self.w._asset_manager_projects = [
                e for e in self.w._asset_manager_projects if e.get("local_path") != project_path
            ]
            self.w.settings["asset_manager_projects"] = list(self.w._asset_manager_projects)
            save_settings(self.w.settings)
            self.refresh_asset_manager()

    def _refresh_asset_entity_lists(self, target: str) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", self.w.test_pipeline_root)
        shots_root = project_root / "shots"
        assets_root = project_root / "assets"

        shots = sorted([p for p in shots_root.iterdir() if p.is_dir()]) if shots_root.exists() else []
        assets = sorted([p for p in assets_root.iterdir() if p.is_dir()]) if assets_root.exists() else []

        # Build filter options from prefixes
        shot_prefixes = sorted({name_prefix(p.name) for p in shots})
        asset_prefixes = sorted({name_prefix(p.name) for p in assets})

        prev_shot_filter = self.w.asset_shots_filter.currentText() if self.w.asset_shots_filter.count() else "All"
        prev_asset_filter = self.w.asset_assets_filter.currentText() if self.w.asset_assets_filter.count() else "All"

        self.w.asset_shots_filter.blockSignals(True)
        self.w.asset_shots_filter.clear()
        self.w.asset_shots_filter.addItem("All")
        for p in shot_prefixes:
            self.w.asset_shots_filter.addItem(p)
        if prev_shot_filter in [self.w.asset_shots_filter.itemText(i) for i in range(self.w.asset_shots_filter.count())]:
            self.w.asset_shots_filter.setCurrentText(prev_shot_filter)
        else:
            self.w.asset_shots_filter.setCurrentText("All")
        self.w.asset_shots_filter.blockSignals(False)

        self.w.asset_assets_filter.blockSignals(True)
        self.w.asset_assets_filter.clear()
        self.w.asset_assets_filter.addItem("All")
        for p in asset_prefixes:
            self.w.asset_assets_filter.addItem(p)
        if prev_asset_filter in [self.w.asset_assets_filter.itemText(i) for i in range(self.w.asset_assets_filter.count())]:
            self.w.asset_assets_filter.setCurrentText(prev_asset_filter)
        else:
            self.w.asset_assets_filter.setCurrentText("All")
        self.w.asset_assets_filter.blockSignals(False)

        # Apply filters
        shot_filter = self.w.asset_shots_filter.currentText()
        asset_filter = self.w.asset_assets_filter.currentText()
        search_text = self.w.asset_entity_search.text().strip().lower()
        active_tab = self.w.asset_work_tabs.currentIndex()

        shot_icon_size = self.w.asset_shots_list.iconSize()
        asset_icon_size = self.w.asset_assets_list.iconSize()

        if target in ("both", "shots"):
            self.w.asset_shots_list.clear()
            for shot_dir in shots:
                if shot_filter != "All" and name_prefix(shot_dir.name) != shot_filter:
                    continue
                if active_tab == 0 and search_text and search_text not in shot_dir.name.lower():
                    continue
                shot_item = QtWidgets.QListWidgetItem(shot_dir.name)
                shot_item.setData(QtCore.Qt.ItemDataRole.UserRole, str(shot_dir))
                preview = latest_preview_image(shot_dir)
                if preview:
                    pix = self._get_scaled_preview_pixmap(preview, shot_dir, shot_icon_size)
                else:
                    pix = self._get_placeholder_pixmap(shot_dir, shot_icon_size)
                shot_item.setIcon(QtGui.QIcon(pix))
                self.w.asset_shots_list.addItem(shot_item)

        if target in ("both", "assets"):
            self.w.asset_assets_list.clear()
            for asset_dir in assets:
                if asset_filter != "All" and name_prefix(asset_dir.name) != asset_filter:
                    continue
                if active_tab == 1 and search_text and search_text not in asset_dir.name.lower():
                    continue
                asset_item = QtWidgets.QListWidgetItem(asset_dir.name)
                asset_item.setData(QtCore.Qt.ItemDataRole.UserRole, str(asset_dir))
                preview = latest_preview_image(asset_dir)
                if preview:
                    pix = self._get_scaled_preview_pixmap(preview, asset_dir, asset_icon_size)
                else:
                    pix = self._get_placeholder_pixmap(asset_dir, asset_icon_size)
                asset_item.setIcon(QtGui.QIcon(pix))
                self.w.asset_assets_list.addItem(asset_item)

    def _get_scaled_preview_pixmap(
        self, preview_path: Path, entity_dir: Path, size: QtCore.QSize
    ) -> QtGui.QPixmap:
        try:
            mtime = preview_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        key = ("preview", str(preview_path), size.width(), size.height())
        cached = self._thumb_cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        pix = QtGui.QPixmap(str(preview_path))
        if pix.isNull():
            pix = build_thumbnail_pixmap(entity_dir, size)
            self._thumb_cache[key] = (mtime, pix)
            return pix
        scaled = pix.scaled(
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self._thumb_cache[key] = (mtime, scaled)
        return scaled

    def _get_placeholder_pixmap(self, entity_dir: Path, size: QtCore.QSize) -> QtGui.QPixmap:
        key = ("placeholder", str(entity_dir), size.width(), size.height())
        cached = self._thumb_cache.get(key)
        if cached:
            return cached[1]
        pix = build_thumbnail_pixmap(entity_dir, size)
        self._thumb_cache[key] = (0.0, pix)
        return pix

    def refresh_asset_entity_lists(self, *_: object) -> None:
        self._refresh_asset_entity_lists(target="both")

    def refresh_shots_list(self, *_: object) -> None:
        self._refresh_asset_entity_lists(target="shots")

    def refresh_assets_list(self, *_: object) -> None:
        self._refresh_asset_entity_lists(target="assets")

    def refresh_active_list(self, *_: object) -> None:
        target = "shots" if self.w.asset_work_tabs.currentIndex() == 0 else "assets"
        self._refresh_asset_entity_lists(target=target)

    def apply_asset_shots_size(self, label: str, refresh: bool = True) -> None:
        size = self.w._asset_shot_size_map.get(label, self.w._asset_shot_size_map["Medium"])
        self.w.asset_shots_list.setIconSize(size)
        grid = QtCore.QSize(size.width() + 20, size.height() + 40)
        self.w.asset_shots_list.setGridSize(grid)
        if refresh:
            self._refresh_asset_entity_lists(target="shots")

    def on_asset_shots_size_changed(self, label: str) -> None:
        self.apply_asset_shots_size(label, refresh=True)

    def on_asset_entity_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        entity_path = Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        self._load_entity_details(entity_path)

    def on_asset_tab_changed(self, index: int) -> None:
        if index == 0:
            self.w.asset_entity_search.setPlaceholderText("Search shots...")
        else:
            self.w.asset_entity_search.setPlaceholderText("Search assets...")
        self.refresh_active_list()

    def _load_entity_details(self, entity_dir: Path) -> None:
        self.w._asset_current_entity = entity_dir
        self.w._asset_current_entity_type = "shot" if entity_dir.parent.name == "shots" else "asset"
        self.w._preview_images = list_preview_images(entity_dir)
        self.w._preview_index = 0
        if self.w._preview_images:
            preview = self.w._preview_images[self.w._preview_index]
            pixmap = QtGui.QPixmap(str(preview))
            if not pixmap.isNull():
                self.w.asset_preview.setPixmap(
                    pixmap.scaled(
                        self.w.asset_preview.size(),
                        QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.w.asset_video_controller.show_image(pixmap)
            self._update_preview_label()
        else:
            self.w.asset_preview.setPixmap(build_thumbnail_pixmap(entity_dir, QtCore.QSize(420, 200)))
            self._update_preview_label()

        meta = load_metadata(entity_dir)
        owner = meta.get("owner", "Unknown")
        status = meta.get("status", "WIP")
        context = self.w.asset_context_combo.currentText()
        if self.w._asset_current_entity_type == "shot":
            context = self._pick_best_context(entity_dir, context)
        normalized = context.strip().lower()
        list_context = None if normalized in ("all", "tous", "toutes") else context
        self.w.asset_meta.setText(
            f"Owner: {owner}\n"
            f"Status: {status}\n"
            f"Context: {context}\n"
            f"Entity: {entity_dir.name}"
        )

        self.w.asset_versions_list.clear()
        usd_versions = list_usd_versions(
            entity_dir,
            context=list_context,
            search_locations=self.w._asset_schema.get("usd_search"),
        )
        video_versions = list_review_videos(entity_dir, context=list_context) if self.w._asset_current_entity_type == "shot" else []
        image_versions = list_preview_images(entity_dir)
        grouped = group_asset_versions(usd_versions, video_versions, image_versions)
        if grouped:
            for base_name, entries in grouped.items():
                row = AssetVersionRow(base_name, entries, parent=self.w.asset_versions_list)
                item = QtWidgets.QListWidgetItem()
                item.setSizeHint(QtCore.QSize(280, 40))
                self.w.asset_versions_list.addItem(item)
                self.w.asset_versions_list.setItemWidget(item, row)

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
                    if path is not None:
                        self._sync_asset_version_preview(path, kind)

                row.selection_changed.connect(sync_item_data_and_preview)
                sync_item_data()
        else:
            if self.w._asset_current_entity_type == "shot":
                self.w.asset_versions_list.addItem("No published USD/Video for this context")
            else:
                self.w.asset_versions_list.addItem("No published USD for this context")

        if not self.w._preview_images and video_versions:
            self.w.asset_video_controller.preview_first_frame(video_versions[0])

        self.w.asset_history_list.clear()
        notes_path = entity_dir / "notes.txt"
        if notes_path.exists():
            try:
                note = notes_path.read_text(encoding="utf-8").strip()
            except Exception:
                note = ""
            if note:
                self.w.asset_history_list.addItem(note)
            else:
                self.w.asset_history_list.addItem("No history yet")
        else:
            self.w.asset_history_list.addItem("No history yet")

    def _update_preview_label(self) -> None:
        total = len(getattr(self.w, "_preview_images", []))
        index = getattr(self.w, "_preview_index", 0) + 1 if total else 0
        self.w.asset_preview_label.setText(f"{index}/{total}")
        self.w.asset_prev_btn.setEnabled(total > 1)
        self.w.asset_next_btn.setEnabled(total > 1)

    def _show_preview_at(self, index: int) -> None:
        if not getattr(self.w, "_preview_images", []):
            return
        total = len(self.w._preview_images)
        self.w._preview_index = index % total
        preview = self.w._preview_images[self.w._preview_index]
        pixmap = QtGui.QPixmap(str(preview))
        if not pixmap.isNull():
            self.w.asset_preview.setPixmap(
                pixmap.scaled(
                    self.w.asset_preview.size(),
                    QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.w.asset_video_controller.show_image(pixmap)
        self._update_preview_label()

    def prev_preview_image(self) -> None:
        self._show_preview_at(getattr(self.w, "_preview_index", 0) - 1)

    def next_preview_image(self) -> None:
        self._show_preview_at(getattr(self.w, "_preview_index", 0) + 1)

    def toggle_asset_video_fullscreen(self) -> None:
        if self.w._asset_video_fullscreen_dialog and self.w._asset_video_fullscreen_dialog.isVisible():
            self.w._asset_video_fullscreen_dialog.close()
            return

        dialog = QtWidgets.QDialog(self.w)
        dialog.setWindowTitle("Video Preview")
        dialog.setWindowFlag(QtCore.Qt.WindowType.Window, True)
        dialog.setModal(False)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.w._asset_video_original_layout = self.w.asset_video_layout
        if self.w._asset_video_original_layout is not None:
            self.w._asset_video_original_layout.removeWidget(self.w.asset_video)
        layout.addWidget(self.w.asset_video)
        dialog.finished.connect(self._restore_asset_video_from_fullscreen)
        self.w._asset_video_fullscreen_dialog = dialog
        dialog.showFullScreen()

    def _restore_asset_video_from_fullscreen(self) -> None:
        if self.w._asset_video_original_layout is not None:
            self.w._asset_video_original_layout.insertWidget(0, self.w.asset_video, 1)
        if self.w._asset_video_fullscreen_dialog is not None:
            self.w._asset_video_fullscreen_dialog.deleteLater()
        self.w._asset_video_fullscreen_dialog = None

    def update_asset_context(self, context: str) -> None:
        current = self.w.asset_meta.text().splitlines()
        rebuilt = []
        replaced = False
        for line in current:
            if line.startswith("Context:"):
                rebuilt.append(f"Context: {context}")
                replaced = True
            else:
                rebuilt.append(line)
        if not replaced:
            rebuilt.insert(2, f"Context: {context}")
        self.w.asset_meta.setText("\n".join(rebuilt))
        entity = getattr(self.w, "_asset_current_entity", None)
        if entity:
            self._load_entity_details(Path(entity))

    def _pick_best_context(self, entity_dir: Path, current: str) -> str:
        if self.w._asset_current_entity_type != "shot":
            return current
        if current.strip().lower() in ("all", "tous", "toutes"):
            return current

        def has_content(ctx: str) -> bool:
            if list_usd_versions(
                entity_dir,
                context=ctx,
                search_locations=self.w._asset_schema.get("usd_search"),
            ):
                return True
            if list_review_videos(entity_dir, context=ctx):
                return True
            return False

        if current and has_content(current):
            return current

        contexts = [self.w.asset_context_combo.itemText(i) for i in range(self.w.asset_context_combo.count())]
        for ctx in contexts:
            if has_content(ctx):
                if ctx != current:
                    self.w.asset_context_combo.blockSignals(True)
                    self.w.asset_context_combo.setCurrentText(ctx)
                    self.w.asset_context_combo.blockSignals(False)
                return ctx
        return current

    def on_asset_version_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        kind = item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            return
        path = Path(str(path_text))
        if kind == "video" and path.exists():
            self.w.asset_video_controller.play_path(path)
            return
        if path.exists():
            self._sync_asset_version_preview(path, kind)

    def _sync_asset_version_preview(self, path: Path, kind: Optional[str]) -> None:
        if not path.exists():
            return
        if kind == "video":
            self.w.asset_video_controller.preview_first_frame(path)
            return
        if kind == "image":
            images = getattr(self.w, "_preview_images", [])
            if images and path in images:
                self._show_preview_at(images.index(path))
                return
            pixmap = QtGui.QPixmap(str(path))
            if not pixmap.isNull():
                self.w.asset_video_controller.show_image(pixmap)

    def asset_placeholder_action(self) -> None:
        self.w.asset_status.setText("Git actions coming soon (commit/push/fetch).")

    def setup_asset_auto_refresh(self) -> None:
        self._asset_refresh_timer = QtCore.QTimer(self.w)
        self._asset_refresh_timer.setInterval(60000)
        self._asset_refresh_timer.timeout.connect(self.refresh_asset_manager)
        if self.w.asset_auto_refresh.isChecked():
            self._asset_refresh_timer.start()

    def toggle_asset_auto_refresh(self, checked: bool) -> None:
        if not hasattr(self, "_asset_refresh_timer"):
            return
        if checked:
            self._asset_refresh_timer.start()
            self.w._asset_watch_enabled = True
            self._refresh_asset_watch_paths()
        else:
            self._asset_refresh_timer.stop()
            self.w._asset_watch_enabled = False
            self._refresh_asset_watch_paths()

    def setup_asset_watcher(self) -> None:
        self._asset_watcher = QtCore.QFileSystemWatcher(self.w)
        self._asset_watcher.directoryChanged.connect(self._queue_asset_refresh)
        self._asset_refresh_watch_timer = QtCore.QTimer(self.w)
        self._asset_refresh_watch_timer.setSingleShot(True)
        self._asset_refresh_watch_timer.setInterval(500)
        self._asset_refresh_watch_timer.timeout.connect(self._run_asset_refresh)
        self._refresh_asset_watch_paths()

    def _queue_asset_refresh(self, _path: str) -> None:
        if not getattr(self.w, "_asset_watch_enabled", True):
            return
        if not self._asset_refresh_watch_timer.isActive():
            self._asset_refresh_watch_timer.start()

    def _run_asset_refresh(self) -> None:
        self._refresh_asset_watch_paths()
        self.refresh_asset_manager()
        if getattr(self.w.asset_pages, "currentIndex", lambda: 0)() == 1:
            self._refresh_asset_entity_lists(target="both")
            entity = getattr(self.w, "_asset_current_entity", None)
            if entity:
                self._load_entity_details(Path(entity))

    def _refresh_asset_watch_paths(self) -> None:
        if not getattr(self.w, "_asset_watch_enabled", True):
            if hasattr(self, "_asset_watcher"):
                self._asset_watcher.removePaths(self._asset_watcher.directories())
            return
        if not hasattr(self, "_asset_watcher"):
            return
        paths: List[Path] = []
        for entry in self.w._asset_manager_projects:
            project_path = Path(str(entry.get("local_path", "")))
            if project_path.exists():
                paths.append(project_path)
                shots_root = project_path / "shots"
                assets_root = project_path / "assets"
                if shots_root.exists():
                    paths.append(shots_root)
                if assets_root.exists():
                    paths.append(assets_root)
        entity = getattr(self.w, "_asset_current_entity", None)
        if entity and Path(entity).exists():
            paths.append(Path(entity))
        update_watcher_paths(self._asset_watcher, paths)

    def refresh_asset_watch_paths(self) -> None:
        self._refresh_asset_watch_paths()

    def open_asset_project_folder(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is None:
            item = self.w.asset_grid.currentItem()
            if item is None:
                return
            path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if not path_text:
                return
            project_root = Path(str(path_text))
        if not Path(project_root).exists():
            return
        os.startfile(str(project_root))  # type: ignore[attr-defined]
