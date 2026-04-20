from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.asset_detection import DetectedProjectLayout, detect_project_layout
from core.asset_details import (
    build_asset_meta_text,
    empty_versions_message,
    normalize_list_context,
    pick_best_context,
    read_history_note,
)
from core.asset_browser import (
    entity_prefixes,
    filter_entity_dirs,
    resolved_filter_choice,
)
from core.asset_layout import EntityRecord, resolve_asset_layout
from core.asset_schema import entity_root_candidates
from core.fs import find_projects
from core.metadata import load_metadata
from core.settings import normalize_asset_schema, save_settings
from core.watchers import update_watcher_paths
from ui.utils.thumbnails import build_thumbnail_pixmap
from ui.widgets.asset_version_row import AssetVersionRow
from core.versions import group_asset_versions


LIBRARY_SOURCE_EXTS = {
    ".abc",
    ".blend",
    ".fbx",
    ".gltf",
    ".glb",
    ".json",
    ".mtl",
    ".obj",
    ".png",
    ".jpg",
    ".jpeg",
    ".exr",
    ".tif",
    ".tiff",
    ".txt",
}


class _ManualLayoutDropList(QtWidgets.QListWidget):
    def __init__(self, project_root: Path, title: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.project_root = project_root.resolve()
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setToolTip(f"Drop the parent folders that should appear as {title}.")

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # type: ignore[override]
        if self._mime_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # type: ignore[override]
        if self._mime_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[override]
        accepted = False
        for path in self._mime_paths(event.mimeData()):
            accepted = self.add_folder(path) or accepted
        if accepted:
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        if event.key() in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
            for item in self.selectedItems():
                self.takeItem(self.row(item))
            return
        super().keyPressEvent(event)

    def add_folder(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            relative = resolved.relative_to(self.project_root)
        except (OSError, ValueError):
            return False
        if not resolved.is_dir() or not relative.parts:
            return False
        rel_text = str(relative).replace("\\", "/")
        for index in range(self.count()):
            if self.item(index).data(QtCore.Qt.ItemDataRole.UserRole) == rel_text:
                return False
        item = QtWidgets.QListWidgetItem(rel_text)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, rel_text)
        self.addItem(item)
        return True

    def relative_paths(self) -> list[str]:
        return [
            str(self.item(index).data(QtCore.Qt.ItemDataRole.UserRole))
            for index in range(self.count())
            if self.item(index).data(QtCore.Qt.ItemDataRole.UserRole)
        ]

    @staticmethod
    def _mime_paths(mime: QtCore.QMimeData) -> list[Path]:
        paths: list[Path] = []
        for url in mime.urls():
            if url.isLocalFile():
                paths.append(Path(url.toLocalFile()))
        if not paths and mime.hasText():
            for line in mime.text().splitlines():
                text = line.strip()
                if text:
                    paths.append(Path(text))
        return paths


class AssetManagerController:
    def __init__(self, window: QtWidgets.QMainWindow) -> None:
        self.w = window
        self._thumb_cache: dict[tuple, tuple[float, QtGui.QPixmap]] = {}

    def refresh_asset_manager(self, *_: object) -> None:
        self.w.asset_grid.clear()
        current_item = self.w.project_grid.currentItem()
        project_path: Optional[Path] = None
        if current_item is not None:
            path_text = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if path_text:
                project_path = Path(str(path_text))
        self.set_project_context(project_path)
        self._refresh_asset_watch_paths()

    def _clear_asset_browser_state(self, message: str) -> None:
        self._clear_asset_detail_lists(self.w)
        self.w._asset_current_project_root = None
        self.w._asset_current_entity = None
        self.w._asset_current_entity_type = None
        self.w._asset_active_schema = dict(self.w._asset_schema)
        self.w._asset_resolved_layout = None
        self.w.asset_details_title.setText("No project selected")
        self.w.asset_path_label.setText(message)
        self.w.asset_meta.setText(message)
        self.w.asset_versions_list.clear()
        self.w.asset_versions_list.addItem("No entity selected")
        self.w.asset_history_list.clear()
        self.w.asset_history_list.addItem("No entity selected")
        if hasattr(self.w.asset_page, "asset_selection_summary"):
            self.w.asset_page.asset_selection_summary.setText("No entity selected")
        self._set_asset_onboarding_visible(False)
        if hasattr(self.w, "asset_layout_btn"):
            self.w.asset_layout_btn.setEnabled(False)

    def set_project_context(self, project_path: Optional[Path]) -> None:
        available_projects = find_projects(self.w.projects_dir)
        self.w.project_controller.prune_cache(available_projects, self.w._asset_cache)
        if project_path is None:
            self._clear_asset_browser_state("Select a project in Projects to browse its assets.")
            self.set_asset_status("No project selected.")
            return
        if not project_path.exists():
            self._clear_asset_browser_state(f"{project_path.name} does not exist anymore.")
            self.set_asset_status("Selected project is missing.")
            return
        if hasattr(self.w, "asset_layout_btn"):
            self.w.asset_layout_btn.setEnabled(True)
        active_schema = self._effective_project_schema(project_path)
        self.w._asset_detected_layout = detect_project_layout(project_path, base_schema=active_schema)
        has_override = str(project_path) in self.w._asset_project_schemas
        if not has_override:
            self._set_asset_onboarding(project_path, self.w._asset_detected_layout)
            self._clear_asset_detail_lists(self.w)
            self.w._asset_current_entity = None
            self.w._asset_current_entity_type = None
            self.w._asset_current_project_root = project_path
            self.w.asset_details_title.setText(project_path.name)
            self.w.asset_path_label.setText(f"{project_path.name} / Confirm asset layout")
            self.w.asset_meta.setText("Confirm the detected asset layout before browsing entities.")
            self.w.asset_versions_list.addItem("Layout setup required")
            self.w.asset_history_list.addItem("Layout setup required")
            self.set_asset_status("Confirm the detected layout or use the default layout.")
            return
        self._set_asset_onboarding_visible(False)
        self.w._asset_active_schema = active_schema
        self.w._asset_resolved_layout = resolve_asset_layout(project_path, active_schema)
        self.w.asset_details_title.setText(project_path.name)
        self.w.asset_path_label.setText(f"{project_path.name} / Select a shot or asset")
        if hasattr(self.w.asset_page, "asset_selection_summary"):
            self.w.asset_page.asset_selection_summary.setText(f"{project_path.name} / No entity selected")
        self.w._asset_current_project_root = project_path
        self._clear_asset_detail_lists(self.w)
        self.w.asset_preview.clear()
        self.w.asset_meta.setText("Select a shot or asset to view details.")
        self.w.asset_versions_list.addItem("No entity selected")
        self.w.asset_history_list.addItem("No entity selected")
        self._sync_asset_contexts(active_schema)
        self._refresh_asset_entity_lists(target="both")
        self._update_layout_status_summary(self.w._asset_resolved_layout)
        self.set_asset_status(f"Asset Manager ready for {project_path.name}.")

    @staticmethod
    def _clear_asset_detail_lists(window: QtWidgets.QMainWindow) -> None:
        window.asset_shots_list.clear()
        window.asset_assets_list.clear()
        window.asset_library_list.clear()
        window.asset_versions_list.clear()
        window.asset_history_list.clear()

    def open_asset_details(self, item: QtWidgets.QListWidgetItem) -> None:
        project_path = Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        self.set_project_context(project_path)

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
        sender = self.w.sender()
        list_widget = sender if isinstance(sender, QtWidgets.QListWidget) else self.w.asset_assets_list
        item = list_widget.itemAt(pos)
        if item is None:
            return
        menu = QtWidgets.QMenu(self.w)
        action = menu.addAction("Copy Asset Path")
        chosen = menu.exec(list_widget.mapToGlobal(pos))
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
        action = menu.addAction("Copy Project Path")
        chosen = menu.exec(self.w.asset_grid.mapToGlobal(pos))
        if chosen == action:
            path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if not path_text:
                return
            normalized = self.w._to_houdini_path(str(path_text))
            QtWidgets.QApplication.clipboard().setText(normalized)
            self.set_asset_status(f"Copied: {normalized}")

    def _refresh_asset_entity_lists(self, target: str) -> None:
        layout = getattr(self.w, "_asset_resolved_layout", None)
        if layout is None:
            shots: list[EntityRecord] = []
            assets: list[EntityRecord] = []
            library_assets: list[EntityRecord] = []
        else:
            shots = layout.entities_by_role("shot")
            assets = layout.entities_by_role("pipeline_asset")
            library_assets = layout.entities_by_role("library_asset")

        # Build filter options from prefixes
        shot_paths = [item.source_path for item in shots]
        asset_paths = [item.source_path for item in assets]
        library_paths = [item.source_path for item in library_assets]
        shot_prefixes = entity_prefixes(shot_paths)
        asset_prefixes = entity_prefixes(asset_paths)
        library_prefixes = entity_prefixes(library_paths)

        prev_shot_filter = self.w.asset_shots_filter.currentText() if self.w.asset_shots_filter.count() else "All"
        prev_asset_filter = self.w.asset_assets_filter.currentText() if self.w.asset_assets_filter.count() else "All"
        prev_library_filter = self.w.asset_library_filter.currentText() if self.w.asset_library_filter.count() else "All"

        self.w.asset_shots_filter.blockSignals(True)
        self.w.asset_shots_filter.clear()
        self.w.asset_shots_filter.addItem("All")
        for p in shot_prefixes:
            self.w.asset_shots_filter.addItem(p)
        self.w.asset_shots_filter.setCurrentText(
            resolved_filter_choice(prev_shot_filter, ["All", *shot_prefixes])
        )
        self.w.asset_shots_filter.blockSignals(False)

        self.w.asset_assets_filter.blockSignals(True)
        self.w.asset_assets_filter.clear()
        self.w.asset_assets_filter.addItem("All")
        for p in asset_prefixes:
            self.w.asset_assets_filter.addItem(p)
        self.w.asset_assets_filter.setCurrentText(
            resolved_filter_choice(prev_asset_filter, ["All", *asset_prefixes])
        )
        self.w.asset_assets_filter.blockSignals(False)

        self.w.asset_library_filter.blockSignals(True)
        self.w.asset_library_filter.clear()
        self.w.asset_library_filter.addItem("All")
        for p in library_prefixes:
            self.w.asset_library_filter.addItem(p)
        self.w.asset_library_filter.setCurrentText(
            resolved_filter_choice(prev_library_filter, ["All", *library_prefixes])
        )
        self.w.asset_library_filter.blockSignals(False)

        # Apply filters
        shot_filter = self.w.asset_shots_filter.currentText()
        asset_filter = self.w.asset_assets_filter.currentText()
        library_filter = self.w.asset_library_filter.currentText()
        search_text = self.w.asset_entity_search.text().strip().lower()
        active_tab = self.w.asset_work_tabs.currentIndex()

        shot_icon_size = self.w.asset_shots_list.iconSize()
        asset_icon_size = self.w.asset_assets_list.iconSize()

        if target in ("both", "shots"):
            self.w.asset_shots_list.clear()
            visible_shots = filter_entity_dirs(
                shot_paths,
                prefix_filter=shot_filter,
                search_text=search_text if active_tab == 0 else "",
            )
            for shot_dir in visible_shots:
                shot_item = QtWidgets.QListWidgetItem(shot_dir.name)
                shot_item.setData(QtCore.Qt.ItemDataRole.UserRole, str(shot_dir))
                shot_item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, "shot")
                preview = layout.preview_path(self._entity_record_for_path(shot_dir)) if layout else None
                if preview:
                    pix = self._get_scaled_preview_pixmap(preview, shot_dir, shot_icon_size)
                else:
                    pix = self._get_placeholder_pixmap(shot_dir, shot_icon_size)
                shot_item.setIcon(QtGui.QIcon(pix))
                self.w.asset_shots_list.addItem(shot_item)
            if not visible_shots:
                self._add_empty_entity_item(
                    self.w.asset_shots_list,
                    "No shots found",
                    self._empty_reason(
                        total=len(shot_paths),
                        search_text=search_text if active_tab == 0 else "",
                        prefix_filter=shot_filter,
                        role_label="shot",
                    ),
                )

        if target in ("both", "assets"):
            self.w.asset_assets_list.clear()
            visible_assets = filter_entity_dirs(
                asset_paths,
                prefix_filter=asset_filter,
                search_text=search_text if active_tab == 1 else "",
            )
            for asset_dir in visible_assets:
                asset_item = QtWidgets.QListWidgetItem(asset_dir.name)
                asset_item.setData(QtCore.Qt.ItemDataRole.UserRole, str(asset_dir))
                asset_item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, "asset")
                preview = layout.preview_path(self._entity_record_for_path(asset_dir)) if layout else None
                if preview:
                    pix = self._get_scaled_preview_pixmap(preview, asset_dir, asset_icon_size)
                else:
                    pix = self._get_placeholder_pixmap(asset_dir, asset_icon_size)
                asset_item.setIcon(QtGui.QIcon(pix))
                self.w.asset_assets_list.addItem(asset_item)
            if not visible_assets:
                self._add_empty_entity_item(
                    self.w.asset_assets_list,
                    "No pipeline assets found",
                    self._empty_reason(
                        total=len(asset_paths),
                        search_text=search_text if active_tab == 1 else "",
                        prefix_filter=asset_filter,
                        role_label="pipeline asset",
                    ),
                )

        if target in ("both", "library"):
            self.w.asset_library_list.clear()
            visible_library_assets = filter_entity_dirs(
                library_paths,
                prefix_filter=library_filter,
                search_text=search_text if active_tab == 2 else "",
            )
            for library_dir in visible_library_assets:
                library_item = QtWidgets.QListWidgetItem(library_dir.name)
                library_item.setData(QtCore.Qt.ItemDataRole.UserRole, str(library_dir))
                library_item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, "asset")
                preview = layout.preview_path(self._entity_record_for_path(library_dir)) if layout else None
                if preview:
                    pix = self._get_scaled_preview_pixmap(preview, library_dir, asset_icon_size)
                else:
                    pix = self._get_placeholder_pixmap(library_dir, asset_icon_size)
                library_item.setIcon(QtGui.QIcon(pix))
                self.w.asset_library_list.addItem(library_item)
            if not visible_library_assets:
                self._add_empty_entity_item(
                    self.w.asset_library_list,
                    "No library assets found",
                    self._empty_reason(
                        total=len(library_paths),
                        search_text=search_text if active_tab == 2 else "",
                        prefix_filter=library_filter,
                        role_label="library asset",
                    ),
                )

    @staticmethod
    def _add_empty_entity_item(list_widget: QtWidgets.QListWidget, title: str, detail: str) -> None:
        item = QtWidgets.QListWidgetItem(f"{title}\n{detail}")
        item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
        item.setToolTip(detail)
        list_widget.addItem(item)

    @staticmethod
    def _empty_reason(*, total: int, search_text: str, prefix_filter: str, role_label: str) -> str:
        if total > 0 and search_text:
            return "Try clearing the search field or changing the current group filter."
        if total > 0 and prefix_filter and prefix_filter != "All":
            return "Try switching Group back to All."
        return f"The current layout did not classify any folder as a {role_label}."

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

    def refresh_library_list(self, *_: object) -> None:
        self._refresh_asset_entity_lists(target="library")

    def refresh_active_list(self, *_: object) -> None:
        target_by_index = {0: "shots", 1: "assets", 2: "library"}
        target = target_by_index.get(self.w.asset_work_tabs.currentIndex(), "assets")
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
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            return
        entity_path = Path(str(path_text))
        entity_type = item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        self._load_entity_details(entity_path, entity_type if isinstance(entity_type, str) else None)

    def on_asset_tab_changed(self, index: int) -> None:
        if index == 0:
            self.w.asset_entity_search.setPlaceholderText("Search shots...")
        elif index == 1:
            self.w.asset_entity_search.setPlaceholderText("Search assets...")
        else:
            self.w.asset_entity_search.setPlaceholderText("Search library...")
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is not None:
            tab_label = {0: "Shots", 1: "Assets", 2: "Library"}.get(index, "Assets")
            self.w.asset_path_label.setText(f"{Path(project_root).name} / {tab_label}")
        self.refresh_active_list()

    def _load_entity_details(self, entity_dir: Path, entity_type: Optional[str] = None) -> None:
        self.w._asset_current_entity = entity_dir
        self.w._asset_current_entity_type = entity_type or self._entity_type_for_path(entity_dir)
        project_root = getattr(self.w, "_asset_current_project_root", entity_dir.parent.parent)
        tab_label = "Shots" if self.w._asset_current_entity_type == "shot" else "Assets"
        self.w.asset_path_label.setText(f"{Path(project_root).name} / {tab_label} / {entity_dir.name}")
        if hasattr(self.w.asset_page, "asset_selection_summary"):
            self.w.asset_page.asset_selection_summary.setText(
                f"{entity_dir.name} [{self.w._asset_current_entity_type.upper()}]"
            )
        record = self._entity_record_for_path(entity_dir)
        layout = getattr(self.w, "_asset_resolved_layout", None)
        is_library_entity = bool(record and record.role == "library_asset")
        self.w._preview_images = (
            layout.representation_paths(record, "preview_image") if layout and record is not None else []
        )
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
        list_context = normalize_list_context(context)
        self.w.asset_meta.setText(build_asset_meta_text(owner, status, context, entity_dir.name))

        self.w.asset_versions_list.clear()
        if is_library_entity:
            self._populate_library_source_files(entity_dir)
            self.w.asset_history_list.clear()
            self.w.asset_history_list.addItem(read_history_note(entity_dir))
            return

        usd_versions = layout.representation_paths(record, "usd", context=list_context) if layout and record else []
        video_versions = (
            layout.representation_paths(record, "review_video", context=list_context)
            if layout and record and self.w._asset_current_entity_type == "shot"
            else []
        )
        image_versions = layout.representation_paths(record, "preview_image") if layout and record else []
        grouped = group_asset_versions(usd_versions, video_versions, image_versions)
        if hasattr(self.w.asset_page, "asset_versions_hint"):
            self.w.asset_page.asset_versions_hint.setText(
                f"{len(grouped)} bundle(s) in {context}" if grouped else f"No bundles in {context}"
            )
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
            self.w.asset_versions_list.addItem(empty_versions_message(self.w._asset_current_entity_type))

        if not self.w._preview_images and video_versions:
            self.w.asset_video_controller.preview_first_frame(video_versions[0])

        self.w.asset_history_list.clear()
        self.w.asset_history_list.addItem(read_history_note(entity_dir))

    def _populate_library_source_files(self, entity_dir: Path) -> None:
        files = self._collect_library_source_files(entity_dir)
        if hasattr(self.w.asset_page, "asset_versions_hint"):
            self.w.asset_page.asset_versions_hint.setText(
                f"{len(files)} source file(s)" if files else "No source files found"
            )
        if not files:
            self.w.asset_versions_list.addItem(
                "No source files found in this library item.\nCheck the manual mapping if this folder is not the real asset root."
            )
            return
        for path in files:
            try:
                rel_path = path.relative_to(entity_dir)
            except ValueError:
                rel_path = path
            item = QtWidgets.QListWidgetItem(f"{rel_path.as_posix()}\n{path.suffix.upper().lstrip('.') or 'FILE'}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(path))
            kind = "image" if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff"} else "source"
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, kind)
            item.setToolTip(str(path))
            self.w.asset_versions_list.addItem(item)

    @staticmethod
    def _collect_library_source_files(entity_dir: Path) -> list[Path]:
        if not entity_dir.exists():
            return []
        found: list[Path] = []
        try:
            for path in entity_dir.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in LIBRARY_SOURCE_EXTS:
                    continue
                found.append(path)
        except OSError:
            return []

        def sort_key(path: Path) -> tuple[int, str]:
            suffix = path.suffix.lower()
            priority = 0 if suffix in {".fbx", ".obj", ".abc", ".blend", ".gltf", ".glb"} else 1
            return (priority, path.relative_to(entity_dir).as_posix().lower())

        return sorted(found, key=sort_key)[:200]

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
        def has_content(ctx: str) -> bool:
            record = self._entity_record_for_path(entity_dir)
            layout = getattr(self.w, "_asset_resolved_layout", None)
            if layout and record and layout.representation_paths(record, "usd", context=ctx):
                return True
            if layout and record and layout.representation_paths(record, "review_video", context=ctx):
                return True
            return False

        contexts = [self.w.asset_context_combo.itemText(i) for i in range(self.w.asset_context_combo.count())]
        chosen = pick_best_context(
            entity_type=self.w._asset_current_entity_type,
            current=current,
            contexts=contexts,
            has_content=has_content,
        )
        if chosen != current:
            self.w.asset_context_combo.blockSignals(True)
            self.w.asset_context_combo.setCurrentText(chosen)
            self.w.asset_context_combo.blockSignals(False)
        return chosen

    def on_asset_version_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        kind = item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            return
        path = Path(str(path_text))
        if kind == "video" and path.exists():
            self.w.asset_video_controller.play_path(path)
            return
        if kind == "source" and path.exists():
            self.set_asset_status(f"Selected source file: {self.w._to_houdini_path(str(path))}")
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
        self.set_asset_status("Git actions are intentionally disabled for now. We should redesign this flow before wiring commit, push and fetch.")

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
        project_paths = find_projects(self.w.projects_dir)
        current_project = getattr(self.w, "_asset_current_project_root", None)
        if current_project is not None:
            current_project_path = Path(current_project)
            if current_project_path.exists() and current_project_path not in project_paths:
                project_paths.append(current_project_path)
        for project_path in project_paths:
            if project_path.exists():
                paths.append(project_path)
                project_schema = self._effective_project_schema(project_path)
                for root_name in entity_root_candidates(project_schema, "shot"):
                    shots_root = project_path / root_name
                    if shots_root.exists():
                        paths.append(shots_root)
                for root_name in entity_root_candidates(project_schema, "asset"):
                    assets_root = project_path / root_name
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
            return
        if not Path(project_root).exists():
            return
        os.startfile(str(project_root))  # type: ignore[attr-defined]

    def accept_detected_layout(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        detected = getattr(self.w, "_asset_detected_layout", None)
        if project_root is None or not isinstance(detected, DetectedProjectLayout):
            return
        self._save_project_schema(project_root, detected.schema)
        self.set_project_context(Path(project_root))

    def accept_default_layout(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is None:
            return
        self._save_project_schema(Path(project_root), self.w._asset_schema)
        self.set_project_context(Path(project_root))

    def open_manual_layout_mapper(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is None:
            current_item = self.w.project_grid.currentItem()
            if current_item is not None:
                path_text = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
                if path_text:
                    project_root = Path(str(path_text))
        if project_root is None or not Path(project_root).exists():
            self.set_asset_status("Select a project first before creating a manual layout.")
            return

        project_path = Path(project_root)
        detected = getattr(self.w, "_asset_detected_layout", None)
        seed_schema = (
            deepcopy(detected.schema)
            if isinstance(detected, DetectedProjectLayout) and detected.project_root == project_path
            else deepcopy(self._effective_project_schema(project_path))
        )

        dialog = QtWidgets.QDialog(self.w)
        dialog.setWindowTitle(f"Manual Asset Layout: {project_path.name}")
        dialog.setModal(True)
        dialog.resize(920, 560)

        root_layout = QtWidgets.QVBoxLayout(dialog)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        intro = QtWidgets.QLabel(
            "Drag collection folders from the project tree into Shots, Assets or Library. "
            "Use parent folders that contain entities, for example a folder that contains many props or shots."
        )
        intro.setWordWrap(True)
        root_layout.addWidget(intro, 0)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(12)
        root_layout.addLayout(body, 1)

        model = QtWidgets.QFileSystemModel(dialog)
        model.setReadOnly(True)
        model.setFilter(QtCore.QDir.Filter.AllDirs | QtCore.QDir.Filter.NoDotAndDotDot)
        model.setRootPath(str(project_path))

        tree = QtWidgets.QTreeView()
        tree.setModel(model)
        tree.setRootIndex(model.index(str(project_path)))
        tree.setHeaderHidden(True)
        tree.setDragEnabled(True)
        tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        for column in (1, 2, 3):
            tree.setColumnHidden(column, True)
        body.addWidget(tree, 2)

        columns = QtWidgets.QWidget()
        columns_layout = QtWidgets.QVBoxLayout(columns)
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(8)
        body.addWidget(columns, 3)

        shots_list = self._manual_mapping_group(columns_layout, project_path, "Shots")
        assets_list = self._manual_mapping_group(columns_layout, project_path, "Assets")
        library_list = self._manual_mapping_group(columns_layout, project_path, "Library")
        self._seed_manual_mapping_lists(project_path, seed_schema, shots_list, assets_list, library_list)

        add_row = QtWidgets.QHBoxLayout()
        add_row.setSpacing(8)
        columns_layout.addLayout(add_row)

        def selected_folder() -> Optional[Path]:
            index = tree.currentIndex()
            if not index.isValid():
                return None
            path = Path(model.filePath(index))
            return path if path.is_dir() else None

        for label, target in (
            ("Add Selected to Shots", shots_list),
            ("Add Selected to Assets", assets_list),
            ("Add Selected to Library", library_list),
        ):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda _checked=False, target=target: target.add_folder(selected_folder() or Path()))
            add_row.addWidget(button)

        cleanup_row = QtWidgets.QHBoxLayout()
        cleanup_row.setSpacing(8)
        columns_layout.addLayout(cleanup_row)
        remove_btn = QtWidgets.QToolButton()
        remove_btn.setText("Remove Selected")
        clear_btn = QtWidgets.QToolButton()
        clear_btn.setText("Clear All")
        cleanup_row.addWidget(remove_btn, 0)
        cleanup_row.addWidget(clear_btn, 0)
        cleanup_row.addStretch(1)

        def remove_selected() -> None:
            for list_widget in (shots_list, assets_list, library_list):
                for item in list_widget.selectedItems():
                    list_widget.takeItem(list_widget.row(item))

        def clear_all() -> None:
            for list_widget in (shots_list, assets_list, library_list):
                list_widget.clear()

        remove_btn.clicked.connect(remove_selected)
        clear_btn.clicked.connect(clear_all)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        root_layout.addWidget(buttons, 0)
        buttons.rejected.connect(dialog.reject)

        def save_manual_layout() -> None:
            schema = self._schema_from_manual_mapping(
                seed_schema,
                shots=shots_list.relative_paths(),
                assets=assets_list.relative_paths(),
                library=library_list.relative_paths(),
            )
            if not schema.get("entity_sources"):
                QtWidgets.QMessageBox.warning(
                    dialog,
                    "Manual Asset Layout",
                    "Assign at least one folder before saving the manual layout.",
                )
                return
            self._save_project_schema(project_path, schema)
            dialog.accept()
            self.set_project_context(project_path)
            self.set_asset_status("Manual asset layout saved.")

        buttons.accepted.connect(save_manual_layout)
        dialog.exec()

    def accept_detected_layout_with_library_merged(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        detected = getattr(self.w, "_asset_detected_layout", None)
        if project_root is None or not isinstance(detected, DetectedProjectLayout):
            return
        schema = deepcopy(detected.schema)
        for source in schema.get("entity_sources", []):
            if isinstance(source, dict) and source.get("role") == "library_asset":
                source["role"] = "pipeline_asset"
                source["evidence"] = list(source.get("evidence", [])) + ["user merged library into assets"]
        self._save_project_schema(Path(project_root), schema)
        self.set_project_context(Path(project_root))
        self.set_asset_status("Layout saved with library sources merged into Assets.")

    def redetect_layout(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is None:
            return
        self.set_project_context(Path(project_root))

    def reopen_layout_setup(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is None:
            self.set_asset_status("Select a tracked project first to review its asset layout.")
            return
        project_path = Path(project_root)
        detected = detect_project_layout(project_path, base_schema=self._effective_project_schema(project_path))
        self.w._asset_detected_layout = detected
        self.w._asset_current_project_root = project_path
        self.w.asset_details_title.setText(project_path.name)
        self.w.asset_path_label.setText(f"{project_path.name} / Review asset layout")
        self.w.asset_meta.setText("Review the detected layout and confirm a replacement if needed.")
        self._clear_asset_detail_lists(self.w)
        self.w.asset_versions_list.addItem("Layout review in progress")
        self.w.asset_history_list.addItem("Layout review in progress")
        self._set_asset_onboarding(project_path, detected)
        self.set_asset_status("Asset layout review reopened. Your saved layout stays unchanged until you confirm a new one.")

    def _save_project_schema(self, project_root: Path, schema: object) -> None:
        normalized = normalize_asset_schema(schema)
        self.w._asset_project_schemas[str(project_root)] = normalized
        self.w.settings["asset_project_schemas"] = dict(self.w._asset_project_schemas)
        save_settings(self.w.settings)

    def _effective_project_schema(self, project_root: Path) -> dict:
        override = self.w._asset_project_schemas.get(str(project_root))
        if override:
            return normalize_asset_schema(override)
        return normalize_asset_schema(self.w._asset_schema)

    @staticmethod
    def _manual_mapping_group(
        parent_layout: QtWidgets.QVBoxLayout,
        project_root: Path,
        title: str,
    ) -> _ManualLayoutDropList:
        group = QtWidgets.QGroupBox(title)
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        list_widget = _ManualLayoutDropList(project_root, title)
        list_widget.setMinimumHeight(90)
        layout.addWidget(list_widget)
        parent_layout.addWidget(group, 1)
        return list_widget

    @staticmethod
    def _seed_manual_mapping_lists(
        project_root: Path,
        schema: dict,
        shots_list: _ManualLayoutDropList,
        assets_list: _ManualLayoutDropList,
        library_list: _ManualLayoutDropList,
    ) -> None:
        sources = schema.get("entity_sources", [])
        if isinstance(sources, list) and sources:
            for source in sources:
                if not isinstance(source, dict):
                    continue
                rel_path = str(source.get("path", "")).strip()
                if not rel_path:
                    continue
                role = str(source.get("role", "")).strip().lower()
                target = library_list if role == "library_asset" else assets_list
                if source.get("entity_type") == "shot" or role == "shot":
                    target = shots_list
                target.add_folder(project_root.joinpath(*[part for part in rel_path.split("/") if part]))
            return

        for rel_path in schema.get("entity_roots", {}).get("shot", []):
            shots_list.add_folder(project_root.joinpath(*[part for part in str(rel_path).split("/") if part]))
        for rel_path in schema.get("entity_roots", {}).get("asset", []):
            assets_list.add_folder(project_root.joinpath(*[part for part in str(rel_path).split("/") if part]))

    @staticmethod
    def _schema_from_manual_mapping(
        seed_schema: dict,
        *,
        shots: list[str],
        assets: list[str],
        library: list[str],
    ) -> dict:
        schema = deepcopy(seed_schema)
        sources: list[dict] = []
        for rel_path in shots:
            sources.append(
                {
                    "path": rel_path,
                    "entity_type": "shot",
                    "role": "shot",
                    "confidence": "high",
                    "evidence": ["user manual mapping"],
                }
            )
        for rel_path in assets:
            sources.append(
                {
                    "path": rel_path,
                    "entity_type": "asset",
                    "role": "pipeline_asset",
                    "confidence": "high",
                    "evidence": ["user manual mapping"],
                }
            )
        for rel_path in library:
            sources.append(
                {
                    "path": rel_path,
                    "entity_type": "asset",
                    "role": "library_asset",
                    "confidence": "high",
                    "evidence": ["user manual mapping"],
                }
            )
        schema["entity_sources"] = sources
        schema.setdefault("entity_roots", {})
        schema["entity_roots"]["shot"] = list(shots)
        schema["entity_roots"]["asset"] = list(dict.fromkeys([*assets, *library]))
        return schema

    def _set_asset_onboarding(self, project_root: Path, detected: DetectedProjectLayout) -> None:
        roots = []
        shot_roots = detected.schema.get("entity_roots", {}).get("shot", [])
        asset_roots = detected.schema.get("entity_roots", {}).get("asset", [])
        if shot_roots:
            roots.append(f"Shots: {', '.join(shot_roots)}")
        if asset_roots:
            roots.append(f"Assets: {', '.join(asset_roots)}")
        reps = []
        usd_folders = detected.schema.get("representations", {}).get("usd", {}).get("folders", [])
        video_folders = detected.schema.get("representations", {}).get("review_video", {}).get("folders", [])
        image_folders = detected.schema.get("representations", {}).get("preview_image", {}).get("folders", [])
        if usd_folders:
            reps.append(f"USD: {', '.join(usd_folders)}")
        if video_folders:
            reps.append(f"Review: {', '.join(video_folders)}")
        if image_folders:
            reps.append(f"Preview: {', '.join(image_folders)}")
        sources = self._format_detected_sources(detected)
        library_count = sum(
            1
            for source in detected.schema.get("entity_sources", [])
            if isinstance(source, dict) and source.get("role") == "library_asset"
        )
        summary = (
            f"{project_root.name} layout review. "
            f"Confidence: {detected.confidence.upper()}. "
            "Choose the detected layout if this map matches how you work."
        )
        details = "\n".join(part for part in [
            "Detected roots: " + " / ".join(roots) if roots else "Detected roots: none yet",
            "Representations: " + " / ".join(reps) if reps else "Representations: no publish or preview folders confirmed",
            f"Contexts: {', '.join(detected.schema.get('contexts', []))}" if detected.schema.get("contexts") else "",
            "Why: " + " | ".join(sources[:5]) if sources else "Why: no strong source evidence found",
            f"Warnings: {'; '.join(detected.warnings)}" if detected.warnings else "",
            f"Needs review: {'; '.join(detected.unresolved)}" if detected.unresolved else "",
            "Correction: use Merge Library into Assets if source files should appear in the main Assets tab."
            if library_count
            else "",
        ] if part)
        self.w.asset_onboarding_summary.setText(summary)
        self.w.asset_onboarding_details.setText(details)
        if hasattr(self.w, "asset_onboarding_merge_library_btn"):
            self.w.asset_onboarding_merge_library_btn.setVisible(library_count > 0)
        self._set_asset_onboarding_visible(True)

    def _set_asset_onboarding_visible(self, visible: bool) -> None:
        self.w.asset_onboarding_card.setVisible(visible)
        self.w.asset_main_split.setVisible(not visible)

    @staticmethod
    def _format_detected_sources(detected: DetectedProjectLayout) -> list[str]:
        labels = {
            "shot": "Shots",
            "pipeline_asset": "Assets",
            "library_asset": "Library",
            "unknown_asset": "Unknown",
            "representation_source": "Publish source",
        }
        formatted: list[str] = []
        for source in detected.schema.get("entity_sources", []):
            if not isinstance(source, dict):
                continue
            path = str(source.get("path", "")).strip()
            if not path:
                continue
            role = labels.get(str(source.get("role", "")), str(source.get("role", "Source")))
            confidence = str(source.get("confidence", "unknown")).upper()
            evidence = ", ".join(str(item) for item in source.get("evidence", [])[:2])
            formatted.append(f"{path} -> {role} ({confidence}{'; ' + evidence if evidence else ''})")
        return formatted

    def _update_layout_status_summary(self, layout: object) -> None:
        if layout is None:
            return
        shots = len(layout.entities_by_role("shot")) if hasattr(layout, "entities_by_role") else 0
        assets = len(layout.entities_by_role("pipeline_asset")) if hasattr(layout, "entities_by_role") else 0
        library = len(layout.entities_by_role("library_asset")) if hasattr(layout, "entities_by_role") else 0
        if hasattr(self.w.asset_page, "asset_selection_summary"):
            self.w.asset_page.asset_selection_summary.setText(
                f"Detected: {shots} shot(s), {assets} asset(s), {library} library item(s)"
            )

    def _sync_asset_contexts(self, schema: dict) -> None:
        contexts = schema.get("contexts", [])
        if not isinstance(contexts, list) or not contexts:
            contexts = ["modeling", "lookdev", "layout", "animation", "vfx", "lighting"]
        current = self.w.asset_context_combo.currentText() or "All"
        self.w.asset_context_combo.blockSignals(True)
        self.w.asset_context_combo.clear()
        self.w.asset_context_combo.addItem("All")
        for context in contexts:
            self.w.asset_context_combo.addItem(str(context))
        if current not in ["All", *[str(c) for c in contexts]]:
            current = "All"
        self.w.asset_context_combo.setCurrentText(current)
        self.w.asset_context_combo.blockSignals(False)

    def _entity_type_for_path(self, entity_dir: Path) -> str:
        layout = getattr(self.w, "_asset_resolved_layout", None)
        if layout is not None:
            return layout.entity_type_for_path(entity_dir)
        schema = getattr(self.w, "_asset_active_schema", self.w._asset_schema)
        for root_name in entity_root_candidates(schema, "shot"):
            if all(part in entity_dir.parts for part in root_name.split("/")):
                return "shot"
        for root_name in entity_root_candidates(schema, "asset"):
            if all(part in entity_dir.parts for part in root_name.split("/")):
                return "asset"
        return "shot" if self.w.asset_work_tabs.currentIndex() == 0 else "asset"

    def _entity_record_for_path(self, entity_dir: Path) -> Optional[EntityRecord]:
        layout = getattr(self.w, "_asset_resolved_layout", None)
        if layout is None:
            return None
        entity_type = layout.entity_type_for_path(entity_dir)
        for record in layout.entities(entity_type):
            if record.source_path == entity_dir:
                return record
        return None
