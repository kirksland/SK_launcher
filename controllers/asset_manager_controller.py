from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.asset_detection import DetectedProjectLayout, detect_project_layout
from core.asset_details import (
    build_asset_meta_text,
    normalize_list_context,
    pick_best_context,
    read_history_note,
)
from core.asset_inventory import GEOMETRY_SOURCE_EXTS, build_entity_inventory, collect_library_source_files
from core.asset_browser import (
    entity_prefixes,
    filter_entity_dirs,
    resolved_filter_choice,
)
from core.asset_layout import EntityRecord, ResolvedAssetLayout, resolve_asset_layout
from core.asset_schema import entity_root_candidates, entity_sources_for_role
from core.fs import find_projects
from core.metadata import load_metadata
from core.settings import normalize_asset_schema, save_settings
from core.watchers import update_watcher_paths
from ui.utils.thumbnails import build_thumbnail_pixmap, load_media_pixmap
from ui.dialogs.asset_layout_mapper_dialog import AssetLayoutMapperDialog
from ui.widgets.asset_inventory_renderer import AssetInventoryRenderer
from ui.widgets.asset_version_row import AssetVersionRow


class AssetManagerController:
    _EMPTY_ENTITY_ROLE = QtCore.Qt.ItemDataRole.UserRole + 98

    def __init__(self, window: QtWidgets.QMainWindow) -> None:
        self.w = window
        self._thumb_cache: dict[tuple, tuple[float, QtGui.QPixmap]] = {}
        self._asset_detail_request_id = 0
        self._asset_preview_request_id = 0
        self._entity_icon_request_id = 0
        self._asset_pipeline_inspection = None
        self._pending_project_context: Optional[Path] = None
        self._context_refresh_timer = QtCore.QTimer(self.w)
        self._context_refresh_timer.setSingleShot(True)
        self._context_refresh_timer.setInterval(80)
        self._context_refresh_timer.timeout.connect(self._apply_queued_project_context)

    def refresh_asset_manager(self, *_: object) -> None:
        current_item = self.w.project_grid.currentItem()
        project_path: Optional[Path] = None
        if current_item is not None:
            path_text = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if path_text:
                project_path = Path(str(path_text))
        current_project = getattr(self.w, "_asset_current_project_root", None)
        if project_path is None and current_project is not None:
            project_path = Path(current_project)
        current_entity = getattr(self.w, "_asset_current_entity", None)
        if (
            project_path is not None
            and current_project == project_path
            and self._project_context_is_current(project_path)
        ):
            self._rebuild_asset_entity_lists(target="both")
            if current_entity and Path(current_entity).exists():
                self._load_entity_details(
                    Path(current_entity),
                    getattr(self.w, "_asset_current_entity_type", None),
                )
            self._refresh_asset_watch_paths()
            return
        self.w.asset_grid.clear()
        self.set_project_context(project_path)
        self._refresh_asset_watch_paths()

    def queue_project_context(self, project_path: Optional[Path]) -> None:
        self._pending_project_context = project_path
        if not self._asset_page_is_active():
            if project_path is None:
                self._clear_asset_browser_state("Select a project in Projects to browse its assets.")
            else:
                self.w._asset_current_project_root = project_path
                self.w.asset_details_title.setText(project_path.name)
                self.w.asset_path_label.setText(f"{project_path.name} / Inventory will load when opened")
                self.set_asset_status("Asset Manager will load when opened.")
            return
        self._context_refresh_timer.start()

    def ensure_project_context_loaded(self) -> None:
        if self._pending_project_context is not None:
            self._apply_queued_project_context()
            return
        current_item = self.w.project_grid.currentItem()
        if current_item is None:
            self.set_project_context(None)
            return
        path_text = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
        project_path = Path(str(path_text)) if path_text else None
        if self._project_context_is_current(project_path):
            return
        self.set_project_context(project_path)

    def _apply_queued_project_context(self) -> None:
        project_path = self._pending_project_context
        self._pending_project_context = None
        self.set_project_context(project_path)

    def _asset_page_is_active(self) -> bool:
        pages = getattr(self.w, "pages", None)
        if pages is None:
            return False
        try:
            return int(pages.currentIndex()) == 1
        except Exception:
            return False

    def _project_context_is_current(self, project_path: Optional[Path]) -> bool:
        current_root = getattr(self.w, "_asset_current_project_root", None)
        if project_path is None:
            return current_root is None
        if current_root != project_path:
            return False
        return getattr(self.w, "_asset_resolved_layout", None) is not None or self.w.asset_onboarding_card.isVisible()

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
        if hasattr(self.w.asset_page, "asset_pipeline_summary"):
            self.w.asset_page.asset_pipeline_summary.setText("No pipeline inspection available.")
            self.w.asset_page.asset_pipeline_list.clear()
            self.w.asset_page.asset_pipeline_list.addItem("No entity selected")
            self.w.asset_page.asset_pipeline_process_list.clear()
            self.w.asset_page.asset_pipeline_process_list.addItem("No entity selected")
            self.w.asset_page.asset_pipeline_process_summary.setText(
                "Select a process to inspect what it would prepare."
            )
            self.w.asset_page.asset_pipeline_run_summary.setText("No process execution yet.")
            self.w.asset_page.asset_pipeline_run_btn.setEnabled(False)
            self.w.asset_page.asset_pipeline_artifact_list.clear()
            self.w.asset_page.asset_pipeline_artifact_list.addItem("No produced artifacts yet")
        self._asset_pipeline_inspection = None
        self.w.asset_inventory_list.clear()
        self.w.asset_inventory_list.addItem("No entity selected")
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
        self.w.asset_path_label.setText(f"{project_path.name} / Loading inventory...")
        self.set_asset_status("Scanning project layout...")
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
            if hasattr(self.w.asset_page, "asset_pipeline_summary"):
                self.w.asset_page.asset_pipeline_summary.setText("Pipeline inspection will be available after layout confirmation.")
                self.w.asset_page.asset_pipeline_list.clear()
                self.w.asset_page.asset_pipeline_list.addItem("Layout setup required")
                self.w.asset_page.asset_pipeline_process_list.clear()
                self.w.asset_page.asset_pipeline_process_list.addItem("Layout setup required")
                self.w.asset_page.asset_pipeline_process_summary.setText(
                    "Confirm the layout before preparing process requests."
                )
                self.w.asset_page.asset_pipeline_run_summary.setText("No process execution yet.")
                self.w.asset_page.asset_pipeline_run_btn.setEnabled(False)
                self.w.asset_page.asset_pipeline_artifact_list.clear()
                self.w.asset_page.asset_pipeline_artifact_list.addItem("No produced artifacts yet")
            self._asset_pipeline_inspection = None
            self.w.asset_inventory_list.addItem("Layout setup required")
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
        if hasattr(self.w.asset_page, "asset_pipeline_summary"):
            self.w.asset_page.asset_pipeline_summary.setText("Select a shot or asset to inspect pipeline status.")
            self.w.asset_page.asset_pipeline_list.clear()
            self.w.asset_page.asset_pipeline_list.addItem("No entity selected")
            self.w.asset_page.asset_pipeline_process_list.clear()
            self.w.asset_page.asset_pipeline_process_list.addItem("No entity selected")
            self.w.asset_page.asset_pipeline_process_summary.setText(
                "Select a process to inspect what it would prepare."
            )
            self.w.asset_page.asset_pipeline_run_summary.setText("No process execution yet.")
            self.w.asset_page.asset_pipeline_run_btn.setEnabled(False)
            self.w.asset_page.asset_pipeline_artifact_list.clear()
            self.w.asset_page.asset_pipeline_artifact_list.addItem("No produced artifacts yet")
        self._asset_pipeline_inspection = None
        self.w.asset_inventory_list.addItem("No entity selected")
        self.w.asset_history_list.addItem("No entity selected")
        self._sync_asset_contexts(active_schema)
        self._rebuild_asset_entity_lists(target="both")
        self._update_layout_status_summary(self.w._asset_resolved_layout)
        self.set_asset_status(f"Asset Manager ready for {project_path.name}.")

    @staticmethod
    def _clear_asset_detail_lists(window: QtWidgets.QMainWindow) -> None:
        window.asset_shots_list.clear()
        window.asset_assets_list.clear()
        window.asset_library_list.clear()
        window.asset_inventory_list.clear()
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

    def show_asset_inventory_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.w.asset_inventory_list.itemAt(pos)
        if item is None:
            return
        widget = self.w.asset_inventory_list.itemWidget(item)
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
        chosen = menu.exec(self.w.asset_inventory_list.mapToGlobal(pos))
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

    def _rebuild_asset_entity_lists(self, target: str) -> None:
        self._entity_icon_request_id += 1
        entity_icon_request_id = self._entity_icon_request_id
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
            self.w.asset_shots_list.setUpdatesEnabled(False)
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
                shot_item.setData(QtCore.Qt.ItemDataRole.UserRole + 2, str(preview) if preview else "")
                initial_pix = (
                    self._get_scaled_preview_pixmap(Path(str(preview)), shot_dir, shot_icon_size)
                    if preview
                    else self._get_placeholder_pixmap(shot_dir, shot_icon_size)
                )
                shot_item.setIcon(QtGui.QIcon(initial_pix))
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
            self.w.asset_shots_list.setUpdatesEnabled(True)
            self._restore_entity_selection(self.w.asset_shots_list)

        if target in ("both", "assets"):
            self.w.asset_assets_list.setUpdatesEnabled(False)
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
                asset_item.setData(QtCore.Qt.ItemDataRole.UserRole + 2, str(preview) if preview else "")
                initial_pix = (
                    self._get_scaled_preview_pixmap(Path(str(preview)), asset_dir, asset_icon_size)
                    if preview
                    else self._get_placeholder_pixmap(asset_dir, asset_icon_size)
                )
                asset_item.setIcon(QtGui.QIcon(initial_pix))
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
            self.w.asset_assets_list.setUpdatesEnabled(True)
            self._restore_entity_selection(self.w.asset_assets_list)

        if target in ("both", "library"):
            self.w.asset_library_list.setUpdatesEnabled(False)
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
                library_item.setData(QtCore.Qt.ItemDataRole.UserRole + 2, str(preview) if preview else "")
                initial_pix = (
                    self._get_scaled_preview_pixmap(Path(str(preview)), library_dir, asset_icon_size)
                    if preview
                    else self._get_placeholder_pixmap(library_dir, asset_icon_size)
                )
                library_item.setIcon(QtGui.QIcon(initial_pix))
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
            self.w.asset_library_list.setUpdatesEnabled(True)
            self._restore_entity_selection(self.w.asset_library_list)
        # These entity cards should stay visually stable while the user scrolls,
        # hovers, or resizes the window. We now resolve the best preview
        # synchronously during list construction, so we intentionally avoid a
        # second async hydration pass here.

    def _schedule_entity_icon_hydration(self, target: str, request_id: int) -> None:
        QtCore.QTimer.singleShot(
            0,
            lambda rid=request_id, refresh_target=str(target): self._hydrate_entity_icon_batch(refresh_target, rid, 0),
        )

    def _hydrate_entity_icon_batch(self, target: str, request_id: int, start_index: int) -> None:
        if request_id != self._entity_icon_request_id:
            return
        target_widgets = self._entity_list_widgets_for_target(target)
        batch_size = 8
        next_index = start_index
        touched_widgets: list[QtWidgets.QListWidget] = []
        for list_widget in target_widgets:
            count = list_widget.count()
            if start_index >= count:
                continue
            icon_size = list_widget.iconSize()
            end = min(start_index + batch_size, count)
            for row in range(start_index, end):
                item = list_widget.item(row)
                if item is None:
                    continue
                path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
                preview_text = item.data(QtCore.Qt.ItemDataRole.UserRole + 2)
                if not path_text:
                    continue
                entity_dir = Path(str(path_text))
                if preview_text:
                    pix = self._get_scaled_preview_pixmap(Path(str(preview_text)), entity_dir, icon_size)
                else:
                    pix = self._get_placeholder_pixmap(entity_dir, icon_size)
                item.setIcon(QtGui.QIcon(pix))
            touched_widgets.append(list_widget)
            next_index = max(next_index, end)
        for list_widget in touched_widgets:
            list_widget.viewport().update()
        if any(next_index < widget.count() for widget in target_widgets):
            QtCore.QTimer.singleShot(
                0,
                lambda rid=request_id, refresh_target=target, offset=next_index: self._hydrate_entity_icon_batch(refresh_target, rid, offset),
            )

    def _entity_list_widgets_for_target(self, target: str) -> tuple[QtWidgets.QListWidget, ...]:
        if target == "shots":
            return (self.w.asset_shots_list,)
        if target == "assets":
            return (self.w.asset_assets_list,)
        if target == "library":
            return (self.w.asset_library_list,)
        return (
            self.w.asset_shots_list,
            self.w.asset_assets_list,
            self.w.asset_library_list,
        )

    def _restore_entity_selection(self, list_widget: QtWidgets.QListWidget) -> None:
        current_entity = getattr(self.w, "_asset_current_entity", None)
        if not current_entity:
            return
        current_text = str(current_entity)
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item is None or item.data(self._EMPTY_ENTITY_ROLE):
                continue
            if item.data(QtCore.Qt.ItemDataRole.UserRole) != current_text:
                continue
            if item.isHidden():
                return
            list_widget.blockSignals(True)
            list_widget.setCurrentItem(item)
            list_widget.blockSignals(False)
            return

    @staticmethod
    def _add_empty_entity_item(list_widget: QtWidgets.QListWidget, title: str, detail: str) -> None:
        item = QtWidgets.QListWidgetItem(f"{title}\n{detail}")
        item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
        item.setToolTip(detail)
        item.setData(AssetManagerController._EMPTY_ENTITY_ROLE, True)
        list_widget.addItem(item)

    @staticmethod
    def _remove_empty_entity_items(list_widget: QtWidgets.QListWidget) -> None:
        for row in range(list_widget.count() - 1, -1, -1):
            item = list_widget.item(row)
            if item is not None and item.data(AssetManagerController._EMPTY_ENTITY_ROLE):
                list_widget.takeItem(row)

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
        pix = load_media_pixmap(
            preview_path,
            size,
            cache_root=self._asset_preview_cache_root(),
            allow_sync_exr=True,
        )
        if pix.isNull():
            pix = build_thumbnail_pixmap(entity_dir, size)
            self._thumb_cache[key] = (mtime, pix)
            return pix
        scaled = pix
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
        self._rebuild_asset_entity_lists(target="both")

    def refresh_shots_list(self, *_: object) -> None:
        self._apply_entity_filters(target="shots")

    def refresh_assets_list(self, *_: object) -> None:
        self._apply_entity_filters(target="assets")

    def refresh_library_list(self, *_: object) -> None:
        self._apply_entity_filters(target="library")

    def refresh_active_list(self, *_: object) -> None:
        target_by_index = {0: "shots", 1: "assets", 2: "library"}
        target = target_by_index.get(self.w.asset_work_tabs.currentIndex(), "assets")
        self._apply_entity_filters(target=target)

    def _apply_entity_filters(self, target: str) -> None:
        active_tab = self.w.asset_work_tabs.currentIndex()
        search_text = self.w.asset_entity_search.text().strip().lower()
        filter_by_target = {
            "shots": self.w.asset_shots_filter.currentText(),
            "assets": self.w.asset_assets_filter.currentText(),
            "library": self.w.asset_library_filter.currentText(),
        }
        list_by_target = {
            "shots": self.w.asset_shots_list,
            "assets": self.w.asset_assets_list,
            "library": self.w.asset_library_list,
        }
        tab_index_by_target = {"shots": 0, "assets": 1, "library": 2}
        targets = list(filter_by_target.keys()) if target == "both" else [target]
        for current_target in targets:
            list_widget = list_by_target[current_target]
            prefix_filter = filter_by_target[current_target]
            scoped_search = search_text if active_tab == tab_index_by_target[current_target] else ""
            visible_count = 0
            self._remove_empty_entity_items(list_widget)
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                if item is None:
                    continue
                path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if not path_text:
                    continue
                path = Path(str(path_text))
                visible = bool(
                    filter_entity_dirs(
                        [path],
                        prefix_filter=prefix_filter,
                        search_text=scoped_search,
                    )
                )
                item.setHidden(not visible)
                if visible:
                    visible_count += 1
            if visible_count == 0:
                total = sum(
                    1
                    for row in range(list_widget.count())
                    if (item := list_widget.item(row)) is not None
                    and not item.data(self._EMPTY_ENTITY_ROLE)
                )
                self._add_empty_entity_item(
                    list_widget,
                    self._empty_title_for_target(current_target),
                    self._empty_reason(
                        total=total,
                        search_text=scoped_search,
                        prefix_filter=prefix_filter,
                        role_label=self._role_label_for_target(current_target),
                    ),
                )

    @staticmethod
    def _empty_title_for_target(target: str) -> str:
        if target == "shots":
            return "No shots found"
        if target == "assets":
            return "No pipeline assets found"
        return "No library assets found"

    @staticmethod
    def _role_label_for_target(target: str) -> str:
        if target == "shots":
            return "shot"
        if target == "assets":
            return "pipeline asset"
        return "library asset"

    def apply_asset_shots_size(self, label: str, refresh: bool = True) -> None:
        size = self.w._asset_shot_size_map.get(label, self.w._asset_shot_size_map["Medium"])
        self.w.asset_shots_list.setIconSize(size)
        grid = QtCore.QSize(size.width() + 20, size.height() + 40)
        self.w.asset_shots_list.setGridSize(grid)
        if refresh:
            self._rebuild_asset_entity_lists(target="shots")

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
        self._asset_detail_request_id += 1
        request_id = self._asset_detail_request_id
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
        self.w._preview_images = (
            layout.representation_paths(record, "preview_image") if layout and record is not None else []
        )
        self.w._preview_index = 0
        self.w._asset_inventory_preview_path = None
        preview_size = self._asset_preview_target_size()
        self.w.asset_preview.setPixmap(build_thumbnail_pixmap(entity_dir, preview_size))
        self._update_preview_label()

        self.w.asset_inventory_list.clear()
        self.w.asset_inventory_list.addItem("Loading inventory...")
        if hasattr(self.w.asset_page, "asset_pipeline_summary"):
            self.w.asset_page.asset_pipeline_summary.setText("Loading pipeline inspection...")
            self.w.asset_page.asset_pipeline_list.clear()
            self.w.asset_page.asset_pipeline_list.addItem("Loading pipeline inspection...")
            self.w.asset_page.asset_pipeline_process_list.clear()
            self.w.asset_page.asset_pipeline_process_list.addItem("Loading processes...")
            self.w.asset_page.asset_pipeline_process_summary.setText("Preparing process request preview...")

        self.w.asset_history_list.clear()
        self.w.asset_history_list.addItem("Loading history...")

        QtCore.QTimer.singleShot(
            0,
            lambda rid=request_id, path=Path(entity_dir), kind=self.w._asset_current_entity_type: self._hydrate_entity_details(rid, path, kind),
        )

    def _hydrate_entity_details(self, request_id: int, entity_dir: Path, entity_type: Optional[str]) -> None:
        if request_id != self._asset_detail_request_id:
            return
        if getattr(self.w, "_asset_current_entity", None) != entity_dir:
            return
        self.w._asset_current_entity_type = entity_type or self._entity_type_for_path(entity_dir)
        layout = getattr(self.w, "_asset_resolved_layout", None)
        record = self._entity_record_for_path(entity_dir)
        if self.w._preview_images:
            preview = self.w._preview_images[self.w._preview_index]
            preview_size = self._asset_preview_target_size()
            pixmap = load_media_pixmap(
                preview,
                preview_size,
                cache_root=self._asset_preview_cache_root(),
                allow_sync_exr=True,
            )
            if not pixmap.isNull():
                self.w.asset_preview.setPixmap(
                    pixmap
                )
                self.w.asset_video_controller.show_image(pixmap)
            else:
                self.w.asset_preview.setPixmap(build_thumbnail_pixmap(entity_dir, preview_size))
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
        self._update_asset_pipeline_inspection(layout, record, context)

        self.w.asset_inventory_list.clear()
        inventory = build_entity_inventory(
            entity_dir=entity_dir,
            entity_type=self.w._asset_current_entity_type,
            record=record,
            layout=layout,
            context=list_context,
            context_label=context,
        )
        inventory_renderer = AssetInventoryRenderer(
            self.w.asset_inventory_list,
            self.w.asset_page.asset_inventory_hint if hasattr(self.w.asset_page, "asset_inventory_hint") else None,
            cache_root=self._asset_preview_cache_root(),
        )
        first_video = inventory_renderer.render(
            inventory,
            on_selected_path=self._sync_asset_inventory_preview,
        )

        if not self.w._preview_images and first_video is not None:
            self.w.asset_video_controller.preview_first_frame(first_video)

        self.w.asset_history_list.clear()
        self.w.asset_history_list.addItem(read_history_note(entity_dir))

    def _update_asset_pipeline_inspection(
        self,
        layout: ResolvedAssetLayout | None,
        record: EntityRecord | None,
        context: str,
    ) -> None:
        if not hasattr(self.w.asset_page, "asset_pipeline_summary"):
            return
        process_controller = getattr(self.w, "process_controller", None)
        inspection = (
            process_controller.inspect_entity(
                layout,
                record,
                context=normalize_list_context(context),
            )
            if process_controller is not None
            else None
        )
        summary_label = self.w.asset_page.asset_pipeline_summary
        list_widget = self.w.asset_page.asset_pipeline_list
        process_list = self.w.asset_page.asset_pipeline_process_list
        run_btn = getattr(self.w.asset_page, "asset_pipeline_run_btn", None)
        list_widget.clear()
        process_list.clear()
        self._reset_asset_pipeline_run_feedback()
        if inspection is None:
            summary_label.setText("No pipeline inspection available.")
            list_widget.addItem("No pipeline data")
            process_list.addItem("No process definitions")
            self.w.asset_page.asset_pipeline_process_summary.setText(
                "Select a process to inspect what it would prepare."
            )
            if run_btn is not None:
                run_btn.setEnabled(False)
            self._asset_pipeline_inspection = None
            return
        self._asset_pipeline_inspection = inspection
        freshness_label = inspection.freshness.replace("_", " ").title()
        downstream_count = len(inspection.downstream)
        summary_label.setText(
            f"Freshness: {freshness_label}\nDownstream items: {downstream_count}"
        )
        if not inspection.downstream:
            list_widget.addItem("No downstream outputs tracked yet")
        else:
            for record in inspection.downstream[:6]:
                item = QtWidgets.QListWidgetItem(
                    f"{record.freshness.replace('_', ' ').title()} - {record.entity.label or record.entity.id}"
                )
                if record.entity.path:
                    item.setToolTip(record.entity.path)
                list_widget.addItem(item)
        if not inspection.available_processes:
            process_list.addItem("No process definitions")
            self.w.asset_page.asset_pipeline_process_summary.setText(
                "No process definitions are registered for this entity yet."
            )
            if run_btn is not None:
                run_btn.setEnabled(False)
            return
        for process in inspection.available_processes:
            item = QtWidgets.QListWidgetItem(f"{process.label} [{process.family}]")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, process.id)
            if process.description:
                item.setToolTip(process.description)
            process_list.addItem(item)
        process_list.setCurrentRow(0)
        self.on_asset_pipeline_process_selected()

    def on_asset_pipeline_process_selected(self) -> None:
        if not hasattr(self.w.asset_page, "asset_pipeline_process_summary"):
            return
        process_list = self.w.asset_page.asset_pipeline_process_list
        run_btn = getattr(self.w.asset_page, "asset_pipeline_run_btn", None)
        item = process_list.currentItem()
        if item is None:
            self.w.asset_page.asset_pipeline_process_summary.setText(
                "Select a process to inspect what it would prepare."
            )
            if run_btn is not None:
                run_btn.setEnabled(False)
            return
        process_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        process_controller = getattr(self.w, "process_controller", None)
        prepared = (
            process_controller.prepare_request(self._asset_pipeline_inspection, process_id)
            if process_controller is not None
            else None
        )
        runtime_request = (
            process_controller.build_runtime_request(self._asset_pipeline_inspection, process_id)
            if process_controller is not None
            else None
        )
        if prepared is None:
            self.w.asset_page.asset_pipeline_process_summary.setText(
                "This process cannot be prepared for the current selection."
            )
            if run_btn is not None:
                run_btn.setEnabled(False)
            return
        capability_text = ", ".join(prepared.required_capabilities) if prepared.required_capabilities else "No special capabilities"
        outputs_text = ", ".join(prepared.outputs) if prepared.outputs else "No declared outputs"
        remote_text = "Remote-capable" if prepared.supports_remote else "Local-only"
        review_text = "Review required" if prepared.review_required else "No review gate declared"
        runtime_text = "Runtime handoff unavailable"
        if runtime_request is not None:
            target_text = f"{runtime_request.execution_target.label} [{runtime_request.execution_target.kind}]"
            if runtime_request.capability_gaps:
                if runtime_request.execution_target.id == "local":
                    runtime_text = (
                        f"Runtime target: {target_text}\n"
                        "Runtime handoff: ready, target capabilities still need formal resolution"
                    )
                else:
                    gaps = ", ".join(runtime_request.capability_gaps)
                    runtime_text = f"Runtime target: {target_text}\nMissing target capabilities: {gaps}"
            else:
                runtime_text = f"Runtime target: {target_text}\nRuntime handoff: ready"
        preview_text = ""
        if prepared.process_id == "publish.asset.usd":
            preview_parameters = self._resolve_publish_asset_usd_parameters(ensure_dirs=False)
            if preview_parameters is not None:
                preview_text = (
                    f"\nResolved source: {preview_parameters['source']}\n"
                    f"Resolved output: {preview_parameters['output']}\n"
                    f"Resolved context: {preview_parameters['context']}"
                )
        self.w.asset_page.asset_pipeline_process_summary.setText(
            f"{prepared.process_label}\n"
            f"Target: {prepared.entity_label} [{prepared.entity_kind}]\n"
            f"Requires: {capability_text}\n"
            f"Outputs: {outputs_text}\n"
            f"Mode: {remote_text} / {review_text}\n"
            f"{runtime_text}"
            f"{preview_text}"
        )
        if run_btn is not None:
            run_btn.setEnabled(runtime_request is not None and prepared.process_id == "publish.asset.usd")

    def run_selected_asset_pipeline_process(self) -> None:
        process_list = getattr(self.w.asset_page, "asset_pipeline_process_list", None)
        if process_list is None:
            return
        item = process_list.currentItem()
        if item is None:
            self.set_asset_status("Select a pipeline process first.")
            return
        process_id = str(item.data(QtCore.Qt.ItemDataRole.UserRole) or "").strip()
        if not process_id:
            self.set_asset_status("Selected pipeline process has no identifier.")
            return
        process_controller = getattr(self.w, "process_controller", None)
        if process_controller is None or self._asset_pipeline_inspection is None:
            self.set_asset_status("No pipeline inspection is available for this selection.")
            return
        parameters = self._resolve_pipeline_process_parameters(process_id)
        if parameters is None:
            return
        self._log_pipeline_run_start(process_id, parameters)
        self.w.asset_page.asset_pipeline_run_summary.setText(
            f"Running {process_id}..."
        )
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            runtime_result = process_controller.execute_houdini_request(
                self._asset_pipeline_inspection,
                process_id,
                parameters=parameters,
            )
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if runtime_result is None:
            self.w.asset_page.asset_pipeline_run_summary.setText(
                "Process execution could not be prepared."
            )
            self.set_asset_status("Pipeline execution could not be prepared.")
            return
        self._update_asset_pipeline_run_feedback(runtime_result)
        self._log_pipeline_run_result(runtime_result)
        if runtime_result.execution.status == "succeeded":
            self.set_asset_status(f"{runtime_result.request.process_id} completed.")
            entity = getattr(self.w, "_asset_current_entity", None)
            entity_type = getattr(self.w, "_asset_current_entity_type", None)
            if entity:
                self._load_entity_details(Path(entity), entity_type)
        else:
            self.set_asset_status(runtime_result.execution.message or "Pipeline execution failed.")

    def _resolve_pipeline_process_parameters(self, process_id: str) -> dict[str, object] | None:
        if process_id == "publish.asset.usd":
            return self._resolve_publish_asset_usd_parameters(ensure_dirs=True)
        self.set_asset_status(f"{process_id} is not executable from the Asset Manager yet.")
        self.w.asset_page.asset_pipeline_run_summary.setText(
            f"{process_id} is visible in the inspector, but its execution planner is not wired yet."
        )
        return None

    def _resolve_publish_asset_usd_parameters(self, *, ensure_dirs: bool) -> dict[str, object] | None:
        entity = getattr(self.w, "_asset_current_entity", None)
        if not entity:
            self.set_asset_status("No entity selected.")
            return None
        entity_dir = Path(entity)
        source_path = self._resolve_publish_source_path(entity_dir)
        if source_path is None:
            self.w.asset_page.asset_pipeline_run_summary.setText(
                "No supported geometry source was found for this selection."
            )
            self.set_asset_status("No geometry source found for publish.asset.usd.")
            return None
        context = self._effective_pipeline_context()
        output_path = self._resolve_publish_output_path(entity_dir, context)
        if ensure_dirs:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        return {
            "source": source_path.as_posix(),
            "output": output_path.as_posix(),
            "context": context,
        }

    def _resolve_publish_source_path(self, entity_dir: Path) -> Optional[Path]:
        current_item = self.w.asset_inventory_list.currentItem()
        if current_item is not None:
            current_path = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if current_path:
                candidate = Path(str(current_path))
                if candidate.exists() and candidate.suffix.lower() in GEOMETRY_SOURCE_EXTS:
                    return candidate
        record = self._entity_record_for_path(entity_dir)
        if record is not None and record.role == "library_asset":
            for file in collect_library_source_files(entity_dir):
                if file.path.suffix.lower() in GEOMETRY_SOURCE_EXTS:
                    return file.path
        try:
            candidates = sorted(
                (
                    path
                    for path in entity_dir.rglob("*")
                    if path.is_file() and path.suffix.lower() in GEOMETRY_SOURCE_EXTS
                ),
                key=lambda path: (len(path.parts), path.as_posix().lower()),
            )
        except OSError:
            candidates = []
        return candidates[0] if candidates else None

    def _resolve_publish_output_path(self, entity_dir: Path, context: str) -> Path:
        record = self._entity_record_for_path(entity_dir)
        layout = getattr(self.w, "_asset_resolved_layout", None)
        if layout is not None and record is not None:
            if record.role == "library_asset":
                managed_dir = self._resolve_managed_asset_dir(record, layout)
                return managed_dir / "publish" / context / f"{record.name}.usdnc"
            existing = layout.representation_paths(record, "usd", context=context)
            if existing:
                return existing[0]
        return entity_dir / "publish" / context / f"{entity_dir.name}.usdnc"

    def _resolve_managed_asset_dir(self, record: EntityRecord, layout: ResolvedAssetLayout) -> Path:
        for candidate in layout.entities_by_role("pipeline_asset"):
            if candidate.name.strip().lower() == record.name.strip().lower():
                return candidate.source_path

        pipeline_sources = entity_sources_for_role(layout.schema, "pipeline_asset")
        for source in pipeline_sources:
            if str(source.get("entity_type", "")).strip().lower() != "asset":
                continue
            root_name = str(source.get("path", "")).strip()
            if root_name:
                return layout.project_root.joinpath(*[part for part in root_name.split("/") if part]) / record.name

        for root_name in entity_root_candidates(layout.schema, "asset"):
            if root_name:
                return layout.project_root.joinpath(*[part for part in root_name.split("/") if part]) / record.name

        return layout.project_root / "assets" / record.name

    def _effective_pipeline_context(self) -> str:
        current = str(self.w.asset_context_combo.currentText() or "").strip().lower()
        if current and current != "all":
            return current
        for value in getattr(self.w, "_asset_active_schema", {}).get("contexts", []):
            text = str(value or "").strip().lower()
            if text:
                return text
        return "modeling"

    def _reset_asset_pipeline_run_feedback(self) -> None:
        if hasattr(self.w.asset_page, "asset_pipeline_run_summary"):
            self.w.asset_page.asset_pipeline_run_summary.setText("No process execution yet.")
        if hasattr(self.w.asset_page, "asset_pipeline_artifact_list"):
            self.w.asset_page.asset_pipeline_artifact_list.clear()
            self.w.asset_page.asset_pipeline_artifact_list.addItem("No produced artifacts yet")

    def _update_asset_pipeline_run_feedback(self, runtime_result: object) -> None:
        execution = getattr(runtime_result, "execution", None)
        request = getattr(runtime_result, "request", None)
        if execution is None or request is None:
            return
        status_text = str(getattr(execution, "status", "") or "").replace("_", " ").title()
        message = str(getattr(execution, "message", "") or "").strip() or "No execution message."
        outputs = tuple(getattr(execution, "outputs", ()) or ())
        output_lines = []
        for output in outputs[:3]:
            label = str(getattr(output, "label", "") or getattr(output, "path", "") or "").strip()
            if label:
                output_lines.append(label)
        summary = (
            f"Last run: {request.process_id}\n"
            f"Status: {status_text}\n"
            f"{message}"
        )
        if output_lines:
            summary += "\nOutputs: " + ", ".join(output_lines)
        self.w.asset_page.asset_pipeline_run_summary.setText(summary)

        artifact_list = getattr(self.w.asset_page, "asset_pipeline_artifact_list", None)
        if artifact_list is None:
            return
        artifact_list.clear()
        process_controller = getattr(self.w, "process_controller", None)
        artifacts = process_controller.latest_artifacts() if process_controller is not None else ()
        if not artifacts:
            artifact_list.addItem("No produced artifacts were registered")
            return
        for artifact in artifacts[:8]:
            source_labels = [src.label or Path(src.path).name for src in artifact.source_artifacts[:2]]
            text = f"{artifact.kind.upper()} - {artifact.label or Path(artifact.path).name}"
            if source_labels:
                text += f" <- {', '.join(source_labels)}"
            item = QtWidgets.QListWidgetItem(text)
            item.setToolTip(artifact.path)
            artifact_list.addItem(item)

    @staticmethod
    def _log_pipeline_run_start(process_id: str, parameters: dict[str, object]) -> None:
        print(f"[PIPELINE] Starting {process_id}")
        for key in ("source", "output", "context"):
            value = str(parameters.get(key, "") or "").strip()
            if value:
                print(f"[PIPELINE]   {key}: {value}")

    @staticmethod
    def _log_pipeline_run_result(runtime_result: object) -> None:
        execution = getattr(runtime_result, "execution", None)
        request = getattr(runtime_result, "request", None)
        if execution is None or request is None:
            return
        print(
            f"[PIPELINE] Finished {request.process_id} with status={execution.status} "
            f"message={execution.message}"
        )
        for output in tuple(getattr(execution, "outputs", ()) or ()):
            path = str(getattr(output, "path", "") or "").strip()
            if path:
                print(f"[PIPELINE]   output: {path}")

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
        self.w._asset_inventory_preview_path = None
        preview_size = self._asset_preview_target_size()
        entity = getattr(self.w, "_asset_current_entity", None)
        if entity:
            self.w.asset_preview.setPixmap(build_thumbnail_pixmap(Path(entity), preview_size))
        self._asset_preview_request_id += 1
        request_id = self._asset_preview_request_id
        QtCore.QTimer.singleShot(
            0,
            lambda rid=request_id, path=Path(preview): self._render_asset_preview_request(rid, path),
        )
        self._update_preview_label()

    def _render_asset_preview_request(self, request_id: int, path: Path) -> None:
        if request_id != self._asset_preview_request_id:
            return
        if not path.exists():
            return
        preview_size = self._asset_preview_target_size()
        pixmap = load_media_pixmap(
            path,
            preview_size,
            cache_root=self._asset_preview_cache_root(),
            allow_sync_exr=True,
        )
        if not pixmap.isNull():
            self.w.asset_preview.setPixmap(
                pixmap
            )
            self.w.asset_video_controller.show_image(pixmap)

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

    def on_asset_inventory_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
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
            self._sync_asset_inventory_preview(path, kind)

    def _sync_asset_inventory_preview(self, path: Path, kind: Optional[str]) -> None:
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
            self.w._asset_inventory_preview_path = path
            preview_size = self._asset_preview_target_size()
            entity = getattr(self.w, "_asset_current_entity", None)
            if entity:
                self.w.asset_preview.setPixmap(build_thumbnail_pixmap(Path(entity), preview_size))
            self._asset_preview_request_id += 1
            request_id = self._asset_preview_request_id
            QtCore.QTimer.singleShot(
                0,
                lambda rid=request_id, preview_path=Path(path): self._render_asset_preview_request(rid, preview_path),
            )

    def _asset_preview_cache_root(self) -> Optional[Path]:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        return Path(project_root) if project_root else None

    def _asset_preview_target_size(self) -> QtCore.QSize:
        size = self.w.asset_preview.size()
        if size.width() <= 0 or size.height() <= 0:
            return QtCore.QSize(420, 200)
        return size

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

    def _queue_asset_refresh(self, changed_path: str) -> None:
        if not getattr(self.w, "_asset_watch_enabled", True):
            return
        if self._is_ignored_asset_watch_path(changed_path):
            return
        print(f"[ASSET_WATCH] queued refresh from: {changed_path}")
        if not self._asset_refresh_watch_timer.isActive():
            self._asset_refresh_watch_timer.start()

    def _run_asset_refresh(self) -> None:
        print("[ASSET_WATCH] running asset manager refresh")
        self._refresh_asset_watch_paths()
        self.refresh_asset_manager()

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
                project_schema = self._effective_project_schema(project_path)
                for root_name in entity_root_candidates(project_schema, "shot"):
                    shots_root = project_path / root_name
                    if shots_root.exists():
                        paths.append(shots_root)
                for root_name in entity_root_candidates(project_schema, "asset"):
                    assets_root = project_path / root_name
                    if assets_root.exists():
                        paths.append(assets_root)
        update_watcher_paths(self._asset_watcher, paths)

    @staticmethod
    def _is_ignored_asset_watch_path(path_text: str) -> bool:
        normalized = path_text.replace("\\", "/").lower()
        return "/.skyforge_cache" in normalized or normalized.endswith("/.skyforge_cache")

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

        dialog = AssetLayoutMapperDialog(project_path, seed_schema, parent=self.w)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        schema = dialog.schema()
        if schema is None:
            return
        self._save_project_schema(project_path, schema)
        self.set_project_context(project_path)
        self.set_asset_status("Manual asset layout saved.")

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
        self.w.asset_inventory_list.addItem("Layout review in progress")
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
