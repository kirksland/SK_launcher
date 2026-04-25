from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.asset_detection import DetectedProjectLayout
from core.asset_selection import resolve_entity_record_for_path, resolve_entity_type_for_path
from core.asset_layout import EntityRecord, ResolvedAssetLayout
from core.pipeline.processes import plan_asset_manager_process_execution
from controllers.asset_browser_panel_controller import AssetBrowserPanelController
from controllers.asset_details_panel_controller import AssetDetailsPanelController
from controllers.asset_project_context_controller import AssetProjectContextController
from controllers.asset_refresh_controller import AssetRefreshController
from ui.utils.thumbnails import build_thumbnail_pixmap, load_media_pixmap
from ui.widgets.asset_version_row import AssetVersionRow


class AssetManagerController:
    _EMPTY_ENTITY_ROLE = QtCore.Qt.ItemDataRole.UserRole + 98
    _DEFAULT_PROCESS_SUMMARY = "Select a process to inspect what it would prepare."
    _DEFAULT_RUN_SUMMARY = "No process execution yet."
    _DEFAULT_ARTIFACT_PLACEHOLDER = "No produced artifacts yet"

    def __init__(self, window: QtWidgets.QMainWindow) -> None:
        self.w = window
        self._thumb_cache: dict[tuple, tuple[float, QtGui.QPixmap]] = {}
        self._asset_detail_request_id = 0
        self._asset_preview_request_id = 0
        self._entity_icon_request_id = 0
        self._asset_pipeline_inspection = None
        self._pending_project_context: Optional[Path] = None
        self._browser_panel = AssetBrowserPanelController(self)
        self._details_panel = AssetDetailsPanelController(self)
        self._project_context_controller = AssetProjectContextController(self)
        self._refresh_controller = AssetRefreshController(self)
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
        self._project_context_controller.queue_project_context(project_path)

    def ensure_project_context_loaded(self) -> None:
        self._project_context_controller.ensure_project_context_loaded()

    def _apply_queued_project_context(self) -> None:
        self._project_context_controller.apply_queued_project_context()

    def _asset_page_is_active(self) -> bool:
        return self._project_context_controller.asset_page_is_active()

    def _project_context_is_current(self, project_path: Optional[Path]) -> bool:
        return self._project_context_controller.project_context_is_current(project_path)

    def _clear_asset_browser_state(self, message: str) -> None:
        self._project_context_controller.clear_asset_browser_state(message)

    def set_project_context(self, project_path: Optional[Path]) -> None:
        self._project_context_controller.set_project_context(project_path)

    @staticmethod
    def _clear_asset_detail_lists(window: QtWidgets.QMainWindow) -> None:
        window.asset_shots_list.clear()
        window.asset_assets_list.clear()
        window.asset_library_list.clear()
        window.asset_inventory_list.clear()
        window.asset_history_list.clear()

    def _set_asset_selection_summary(self, text: str) -> None:
        if hasattr(self.w.asset_page, "asset_selection_summary"):
            self.w.asset_page.asset_selection_summary.setText(text)

    def _set_asset_detail_placeholder_state(self, *, inventory_text: str, history_text: str) -> None:
        self.w.asset_inventory_list.clear()
        self.w.asset_inventory_list.addItem(inventory_text)
        self.w.asset_history_list.clear()
        self.w.asset_history_list.addItem(history_text)

    def _set_asset_pipeline_panel_state(
        self,
        *,
        summary_text: str,
        pipeline_item_text: str,
        process_item_text: str,
        process_summary_text: str | None = None,
        run_summary_text: str | None = None,
        artifact_item_text: str | None = None,
        run_enabled: bool = False,
    ) -> None:
        if not hasattr(self.w.asset_page, "asset_pipeline_summary"):
            return
        self.w.asset_page.asset_pipeline_summary.setText(summary_text)
        self.w.asset_page.asset_pipeline_list.clear()
        self.w.asset_page.asset_pipeline_list.addItem(pipeline_item_text)
        self.w.asset_page.asset_pipeline_process_list.clear()
        self.w.asset_page.asset_pipeline_process_list.addItem(process_item_text)
        self.w.asset_page.asset_pipeline_process_summary.setText(
            process_summary_text or self._DEFAULT_PROCESS_SUMMARY
        )
        self.w.asset_page.asset_pipeline_run_summary.setText(
            run_summary_text or self._DEFAULT_RUN_SUMMARY
        )
        self.w.asset_page.asset_pipeline_run_btn.setEnabled(run_enabled)
        self.w.asset_page.asset_pipeline_artifact_list.clear()
        self.w.asset_page.asset_pipeline_artifact_list.addItem(
            artifact_item_text or self._DEFAULT_ARTIFACT_PLACEHOLDER
        )

    def _set_asset_pipeline_process_summary(
        self,
        text: str,
        *,
        run_enabled: bool = False,
    ) -> None:
        if not hasattr(self.w.asset_page, "asset_pipeline_process_summary"):
            return
        self.w.asset_page.asset_pipeline_process_summary.setText(text)
        run_btn = getattr(self.w.asset_page, "asset_pipeline_run_btn", None)
        if run_btn is not None:
            run_btn.setEnabled(run_enabled)

    def _set_asset_pipeline_run_summary(self, text: str) -> None:
        if hasattr(self.w.asset_page, "asset_pipeline_run_summary"):
            self.w.asset_page.asset_pipeline_run_summary.setText(text)

    @staticmethod
    def _format_pipeline_kind_label(kind: object) -> str:
        text = str(kind or "").strip().replace("_", " ")
        return text.title() if text else "Unknown"

    def _build_downstream_list_item(self, record: object) -> QtWidgets.QListWidgetItem:
        entity = getattr(record, "entity", None)
        freshness = str(getattr(record, "freshness", "") or "").strip().replace("_", " ").title()
        kind_label = self._format_pipeline_kind_label(getattr(entity, "kind", ""))
        label = str(getattr(entity, "label", "") or getattr(entity, "id", "") or "").strip() or "Unnamed artifact"
        text = f"{freshness} | {kind_label} | {label}"
        item = QtWidgets.QListWidgetItem(text)
        path_text = str(getattr(entity, "path", "") or "").strip()
        via = tuple(getattr(record, "via", ()) or ())
        tooltip_lines = [f"Freshness: {freshness}", f"Kind: {kind_label}"]
        if path_text:
            tooltip_lines.append(f"Path: {path_text}")
        if via:
            edge = via[-1]
            tooltip_lines.append(f"Relation: {str(getattr(edge, 'kind', '')).replace('_', ' ')}")
        item.setToolTip("\n".join(tooltip_lines))
        return item

    def _build_artifact_list_item(self, artifact: object) -> QtWidgets.QListWidgetItem:
        kind_label = self._format_pipeline_kind_label(getattr(artifact, "kind", ""))
        label = str(getattr(artifact, "label", "") or Path(str(getattr(artifact, "path", "") or "")).name or "").strip()
        process_id = str(getattr(artifact, "process_id", "") or "").strip()
        execution_mode = str(getattr(artifact, "execution_mode", "") or "").strip().replace("_", " ")
        source_refs = tuple(getattr(artifact, "source_artifacts", ()) or ())
        source_label = ""
        if source_refs:
            first = source_refs[0]
            source_label = str(getattr(first, "label", "") or Path(str(getattr(first, "path", "") or "")).name or "").strip()
        text_parts = [kind_label, label]
        if source_label:
            text_parts.append(f"from {source_label}")
        item = QtWidgets.QListWidgetItem(" | ".join(part for part in text_parts if part))
        tooltip_lines = []
        path_text = str(getattr(artifact, "path", "") or "").strip()
        if path_text:
            tooltip_lines.append(f"Path: {path_text}")
        if process_id:
            tooltip_lines.append(f"Process: {process_id}")
        if execution_mode:
            tooltip_lines.append(f"Execution: {execution_mode}")
        if source_refs:
            tooltip_lines.append("Sources:")
            for source_ref in source_refs[:4]:
                ref_path = str(getattr(source_ref, "path", "") or "").strip()
                ref_label = str(getattr(source_ref, "label", "") or Path(ref_path).name or "").strip()
                tooltip_lines.append(f"- {ref_label}: {ref_path}")
        item.setToolTip("\n".join(line for line in tooltip_lines if line))
        return item

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
        self._browser_panel.rebuild_entity_lists(target)

    def _entity_paths_by_target(self, layout: ResolvedAssetLayout | None) -> dict[str, list[Path]]:
        return self._browser_panel.entity_paths_by_target(layout)

    def _sync_entity_filter_combos(self, paths_by_target: dict[str, list[Path]]) -> None:
        self._browser_panel.sync_entity_filter_combos(paths_by_target)

    @staticmethod
    def _populate_entity_filter_combo(
        combo: QtWidgets.QComboBox,
        prefixes: list[str],
        previous_value: str,
    ) -> None:
        AssetBrowserPanelController.populate_entity_filter_combo(combo, prefixes, previous_value)

    def _rebuild_entity_list_target(
        self,
        target: str,
        *,
        layout: ResolvedAssetLayout | None,
        entity_paths: list[Path],
        search_text: str,
        active_tab: int,
    ) -> None:
        self._browser_panel.rebuild_entity_list_target(
            target,
            layout=layout,
            entity_paths=entity_paths,
            search_text=search_text,
            active_tab=active_tab,
        )

    def _build_entity_list_item(
        self,
        entity_dir: Path,
        *,
        entity_type: str,
        icon_size: QtCore.QSize,
        layout: ResolvedAssetLayout | None,
    ) -> QtWidgets.QListWidgetItem:
        return self._browser_panel.build_entity_list_item(
            entity_dir,
            entity_type=entity_type,
            icon_size=icon_size,
            layout=layout,
        )

    def _entity_target_spec(self, target: str) -> dict[str, object]:
        return self._browser_panel.entity_target_spec(target)

    def _restore_entity_selection(self, list_widget: QtWidgets.QListWidget) -> None:
        self._browser_panel.restore_entity_selection(list_widget)

    def _add_empty_entity_item(self, list_widget: QtWidgets.QListWidget, title: str, detail: str) -> None:
        self._browser_panel.add_empty_entity_item(list_widget, title, detail)

    def _remove_empty_entity_items(self, list_widget: QtWidgets.QListWidget) -> None:
        self._browser_panel.remove_empty_entity_items(list_widget)

    @staticmethod
    def _empty_reason(*, total: int, search_text: str, prefix_filter: str, role_label: str) -> str:
        return AssetBrowserPanelController.empty_reason(
            total=total,
            search_text=search_text,
            prefix_filter=prefix_filter,
            role_label=role_label,
        )

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
        self._browser_panel.rebuild_entity_lists(target="both")

    def refresh_shots_list(self, *_: object) -> None:
        self._browser_panel.refresh_shots_list()

    def refresh_assets_list(self, *_: object) -> None:
        self._browser_panel.refresh_assets_list()

    def refresh_library_list(self, *_: object) -> None:
        self._browser_panel.refresh_library_list()

    def refresh_active_list(self, *_: object) -> None:
        self._browser_panel.refresh_active_list()

    def _apply_entity_filters(self, target: str) -> None:
        self._browser_panel.apply_entity_filters(target)

    def apply_asset_shots_size(self, label: str, refresh: bool = True) -> None:
        self._browser_panel.apply_asset_shots_size(label, refresh=refresh)

    def on_asset_shots_size_changed(self, label: str) -> None:
        self._browser_panel.on_asset_shots_size_changed(label)

    def on_asset_entity_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        self._browser_panel.on_asset_entity_clicked(item)

    def on_asset_tab_changed(self, index: int) -> None:
        self._browser_panel.on_asset_tab_changed(index)

    def _load_entity_details(self, entity_dir: Path, entity_type: Optional[str] = None) -> None:
        self._details_panel.load_entity_details(entity_dir, entity_type)

    def _hydrate_entity_details(self, request_id: int, entity_dir: Path, entity_type: Optional[str]) -> None:
        self._details_panel.hydrate_entity_details(request_id, entity_dir, entity_type)

    def _update_asset_pipeline_inspection(
        self,
        layout: ResolvedAssetLayout | None,
        record: EntityRecord | None,
        context: str,
    ) -> None:
        panel_controller = getattr(self.w, "asset_pipeline_panel_controller", None)
        if panel_controller is not None:
            panel_controller.update_inspection(layout, record, context=context)
            return

    def on_asset_pipeline_process_selected(self) -> None:
        panel_controller = getattr(self.w, "asset_pipeline_panel_controller", None)
        if panel_controller is not None:
            panel_controller.on_process_selected()
            return

    def run_selected_asset_pipeline_process(self) -> None:
        panel_controller = getattr(self.w, "asset_pipeline_panel_controller", None)
        if panel_controller is not None:
            panel_controller.run_selected_process()
            return

    def _resolve_pipeline_process_parameters(self, process_id: str) -> dict[str, object] | None:
        plan = self._plan_pipeline_process_execution(process_id, ensure_dirs=True)
        if not plan.is_ready:
            if plan.run_summary:
                self._set_asset_pipeline_run_summary(plan.run_summary)
            if plan.status_message:
                self.set_asset_status(plan.status_message)
            return None
        return dict(plan.parameters)

    def _resolve_publish_asset_usd_parameters(self, *, ensure_dirs: bool) -> dict[str, object] | None:
        plan = self._plan_pipeline_process_execution("publish.asset.usd", ensure_dirs=ensure_dirs)
        if not plan.is_ready:
            if plan.run_summary:
                self._set_asset_pipeline_run_summary(plan.run_summary)
            if plan.status_message:
                self.set_asset_status(plan.status_message)
            return None
        return dict(plan.parameters)

    def _current_asset_inventory_path(self) -> Optional[Path]:
        current_item = self.w.asset_inventory_list.currentItem()
        if current_item is not None:
            current_path = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if current_path:
                return Path(str(current_path))
        return None

    def _plan_pipeline_process_execution(self, process_id: object, *, ensure_dirs: bool) -> object:
        entity = getattr(self.w, "_asset_current_entity", None)
        entity_dir = Path(entity) if entity else None
        record = self._entity_record_for_path(entity_dir) if entity_dir is not None else None
        layout = getattr(self.w, "_asset_resolved_layout", None)
        return plan_asset_manager_process_execution(
            process_id,
            entity_dir=entity_dir,
            current_inventory_path=self._current_asset_inventory_path(),
            record=record,
            layout=layout,
            current_context=self.w.asset_context_combo.currentText(),
            schema_contexts=tuple(getattr(self.w, "_asset_active_schema", {}).get("contexts", ())),
            ensure_dirs=ensure_dirs,
        )

    def _reset_asset_pipeline_run_feedback(self) -> None:
        self._set_asset_pipeline_run_summary(self._DEFAULT_RUN_SUMMARY)
        if hasattr(self.w.asset_page, "asset_pipeline_artifact_list"):
            self.w.asset_page.asset_pipeline_artifact_list.clear()
            self.w.asset_page.asset_pipeline_artifact_list.addItem(self._DEFAULT_ARTIFACT_PLACEHOLDER)

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
        self._set_asset_pipeline_run_summary(summary)

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
            artifact_list.addItem(self._build_artifact_list_item(artifact))

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
        self._details_panel.update_preview_label()

    def _show_preview_at(self, index: int) -> None:
        self._details_panel.show_preview_at(index)

    def _render_asset_preview_request(self, request_id: int, path: Path) -> None:
        self._details_panel.render_asset_preview_request(request_id, path)

    def prev_preview_image(self) -> None:
        self._details_panel.prev_preview_image()

    def next_preview_image(self) -> None:
        self._details_panel.next_preview_image()

    def toggle_asset_video_fullscreen(self) -> None:
        self._details_panel.toggle_asset_video_fullscreen()

    def _restore_asset_video_from_fullscreen(self) -> None:
        self._details_panel.restore_asset_video_from_fullscreen()

    def update_asset_context(self, context: str) -> None:
        self._details_panel.update_asset_context(context)

    def _pick_best_context(self, entity_dir: Path, current: str) -> str:
        return self._details_panel.pick_best_context(entity_dir, current)

    def on_asset_inventory_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        self._details_panel.on_asset_inventory_clicked(item)

    def _sync_asset_inventory_preview(self, path: Path, kind: Optional[str]) -> None:
        self._details_panel.sync_asset_inventory_preview(path, kind)

    def _asset_preview_cache_root(self) -> Optional[Path]:
        return self._details_panel.asset_preview_cache_root()

    def _asset_preview_target_size(self) -> QtCore.QSize:
        return self._details_panel.asset_preview_target_size()

    def asset_placeholder_action(self) -> None:
        self._details_panel.asset_placeholder_action()

    def setup_asset_auto_refresh(self) -> None:
        self._refresh_controller.setup_asset_auto_refresh()

    def toggle_asset_auto_refresh(self, checked: bool) -> None:
        self._refresh_controller.toggle_asset_auto_refresh(checked)

    def setup_asset_watcher(self) -> None:
        self._refresh_controller.setup_asset_watcher()

    def _queue_asset_refresh(self, changed_path: str) -> None:
        self._refresh_controller.queue_asset_refresh(changed_path)

    def _run_asset_refresh(self) -> None:
        self._refresh_controller.run_asset_refresh()

    def _refresh_asset_watch_paths(self) -> None:
        self._refresh_controller.refresh_asset_watch_paths()

    @staticmethod
    def _is_ignored_asset_watch_path(path_text: str) -> bool:
        return AssetRefreshController.is_ignored_asset_watch_path(path_text)

    def refresh_asset_watch_paths(self) -> None:
        self._refresh_controller.refresh_asset_watch_paths()

    def open_asset_project_folder(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is None:
            return
        if not Path(project_root).exists():
            return
        os.startfile(str(project_root))  # type: ignore[attr-defined]

    def accept_detected_layout(self) -> None:
        self._project_context_controller.accept_detected_layout()

    def accept_default_layout(self) -> None:
        self._project_context_controller.accept_default_layout()

    def open_manual_layout_mapper(self) -> None:
        self._project_context_controller.open_manual_layout_mapper()

    def accept_detected_layout_with_library_merged(self) -> None:
        self._project_context_controller.accept_detected_layout_with_library_merged()

    def redetect_layout(self) -> None:
        self._project_context_controller.redetect_layout()

    def reopen_layout_setup(self) -> None:
        self._project_context_controller.reopen_layout_setup()

    def _save_project_schema(self, project_root: Path, schema: object) -> None:
        self._project_context_controller.save_project_schema(project_root, schema)

    def _effective_project_schema(self, project_root: Path) -> dict:
        return self._project_context_controller.effective_project_schema(project_root)

    def _set_asset_onboarding(self, project_root: Path, detected: DetectedProjectLayout) -> None:
        self._project_context_controller.set_asset_onboarding(project_root, detected)

    def _set_asset_onboarding_visible(self, visible: bool) -> None:
        self._project_context_controller.set_asset_onboarding_visible(visible)

    @staticmethod
    def _format_detected_sources(detected: DetectedProjectLayout) -> list[str]:
        return AssetProjectContextController.format_detected_sources(detected)

    def _update_layout_status_summary(self, layout: object) -> None:
        self._project_context_controller.update_layout_status_summary(layout)

    def _sync_asset_contexts(self, schema: dict) -> None:
        self._project_context_controller.sync_asset_contexts(schema)

    def _entity_type_for_path(self, entity_dir: Path) -> str:
        return resolve_entity_type_for_path(
            entity_dir,
            layout=getattr(self.w, "_asset_resolved_layout", None),
            schema=getattr(self.w, "_asset_active_schema", self.w._asset_schema),
            active_tab_index=self.w.asset_work_tabs.currentIndex(),
        )

    def _entity_record_for_path(self, entity_dir: Path) -> Optional[EntityRecord]:
        return resolve_entity_record_for_path(
            entity_dir,
            layout=getattr(self.w, "_asset_resolved_layout", None),
        )
