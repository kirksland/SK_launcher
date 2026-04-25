from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets

from core.asset_details import build_asset_meta_text, normalize_list_context, read_history_note
from core.asset_inventory import build_entity_inventory
from core.project_storage import asset_exr_thumb_dir
from core.asset_selection import build_active_asset_selection, choose_best_context_for_selection
from core.metadata import load_metadata
from ui.utils.thumbnails import build_thumbnail_pixmap, load_media_pixmap
from ui.widgets.asset_inventory_renderer import AssetInventoryRenderer


class AssetDetailsPanelController:
    """Owns entity detail loading, inventory rendering, and preview media."""

    def __init__(self, asset_manager_controller: object) -> None:
        self.host = asset_manager_controller
        self.w = asset_manager_controller.w

    def load_entity_details(self, entity_dir: Path, entity_type: Optional[str] = None) -> None:
        self.host._asset_detail_request_id += 1
        request_id = self.host._asset_detail_request_id
        layout = getattr(self.w, "_asset_resolved_layout", None)
        selection = build_active_asset_selection(
            entity_dir,
            layout=layout,
            schema=getattr(self.w, "_asset_active_schema", self.w._asset_schema),
            active_tab_index=self.w.asset_work_tabs.currentIndex(),
            explicit_entity_type=entity_type,
        )
        self.w._asset_current_entity = entity_dir
        self.w._asset_current_entity_type = selection.entity_type
        project_root = getattr(self.w, "_asset_current_project_root", entity_dir.parent.parent)
        self.w.asset_path_label.setText(
            f"{Path(project_root).name} / {selection.tab_label} / {entity_dir.name}"
        )
        self.host._set_asset_selection_summary(selection.selection_summary)
        record = selection.record
        self.w._preview_images = (
            layout.representation_paths(record, "preview_image") if layout and record is not None else []
        )
        self.w._preview_index = 0
        self.w._asset_inventory_preview_path = None
        preview_size = self.asset_preview_target_size()
        self.w.asset_preview.setPixmap(build_thumbnail_pixmap(entity_dir, preview_size))
        self.update_preview_label()

        self.host._set_asset_detail_placeholder_state(
            inventory_text="Loading inventory...",
            history_text="Loading history...",
        )
        self.host._set_asset_pipeline_panel_state(
            summary_text="Loading pipeline inspection...",
            pipeline_item_text="Loading pipeline inspection...",
            process_item_text="Loading processes...",
            process_summary_text="Preparing process request preview...",
            artifact_item_text=self.host._DEFAULT_ARTIFACT_PLACEHOLDER,
        )

        QtCore.QTimer.singleShot(
            0,
            lambda rid=request_id, path=Path(entity_dir), kind=self.w._asset_current_entity_type: self.hydrate_entity_details(rid, path, kind),
        )

    def hydrate_entity_details(self, request_id: int, entity_dir: Path, entity_type: Optional[str]) -> None:
        if request_id != self.host._asset_detail_request_id:
            return
        if getattr(self.w, "_asset_current_entity", None) != entity_dir:
            return
        layout = getattr(self.w, "_asset_resolved_layout", None)
        selection = build_active_asset_selection(
            entity_dir,
            layout=layout,
            schema=getattr(self.w, "_asset_active_schema", self.w._asset_schema),
            active_tab_index=self.w.asset_work_tabs.currentIndex(),
            explicit_entity_type=entity_type,
        )
        self.w._asset_current_entity_type = selection.entity_type
        record = selection.record
        if self.w._preview_images:
            preview = self.w._preview_images[self.w._preview_index]
            preview_size = self.asset_preview_target_size()
            pixmap = load_media_pixmap(
                preview,
                preview_size,
                cache_root=self.asset_preview_cache_root(),
                allow_sync_exr=True,
            )
            if not pixmap.isNull():
                self.w.asset_preview.setPixmap(pixmap)
                self.w.asset_video_controller.show_image(pixmap)
            else:
                self.w.asset_preview.setPixmap(build_thumbnail_pixmap(entity_dir, preview_size))
            self.update_preview_label()
        else:
            self.w.asset_preview.setPixmap(build_thumbnail_pixmap(entity_dir, QtCore.QSize(420, 200)))
            self.update_preview_label()

        meta = load_metadata(entity_dir)
        owner = meta.get("owner", "Unknown")
        status = meta.get("status", "WIP")
        context = self.w.asset_context_combo.currentText()
        if selection.entity_type == "shot":
            context = self.pick_best_context(entity_dir, context)
        list_context = normalize_list_context(context)
        self.w.asset_meta.setText(build_asset_meta_text(owner, status, context, entity_dir.name))
        self.host._update_asset_pipeline_inspection(layout, record, context)

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
            cache_root=self.asset_preview_cache_root(),
        )
        first_video = inventory_renderer.render(
            inventory,
            on_selected_path=self.sync_asset_inventory_preview,
        )

        if not self.w._preview_images and first_video is not None:
            self.w.asset_video_controller.preview_first_frame(first_video)

        self.w.asset_history_list.clear()
        self.w.asset_history_list.addItem(read_history_note(entity_dir))

    def update_preview_label(self) -> None:
        total = len(getattr(self.w, "_preview_images", []))
        index = getattr(self.w, "_preview_index", 0) + 1 if total else 0
        self.w.asset_preview_label.setText(f"{index}/{total}")
        self.w.asset_prev_btn.setEnabled(total > 1)
        self.w.asset_next_btn.setEnabled(total > 1)

    def show_preview_at(self, index: int) -> None:
        if not getattr(self.w, "_preview_images", []):
            return
        total = len(self.w._preview_images)
        self.w._preview_index = index % total
        preview = self.w._preview_images[self.w._preview_index]
        self.w._asset_inventory_preview_path = None
        preview_size = self.asset_preview_target_size()
        entity = getattr(self.w, "_asset_current_entity", None)
        if entity:
            self.w.asset_preview.setPixmap(build_thumbnail_pixmap(Path(entity), preview_size))
        self.host._asset_preview_request_id += 1
        request_id = self.host._asset_preview_request_id
        QtCore.QTimer.singleShot(
            0,
            lambda rid=request_id, path=Path(preview): self.render_asset_preview_request(rid, path),
        )
        self.update_preview_label()

    def render_asset_preview_request(self, request_id: int, path: Path) -> None:
        if request_id != self.host._asset_preview_request_id:
            return
        if not path.exists():
            return
        preview_size = self.asset_preview_target_size()
        pixmap = load_media_pixmap(
            path,
            preview_size,
            cache_root=self.asset_preview_cache_root(),
            allow_sync_exr=True,
        )
        if not pixmap.isNull():
            self.w.asset_preview.setPixmap(pixmap)
            self.w.asset_video_controller.show_image(pixmap)

    def prev_preview_image(self) -> None:
        self.show_preview_at(getattr(self.w, "_preview_index", 0) - 1)

    def next_preview_image(self) -> None:
        self.show_preview_at(getattr(self.w, "_preview_index", 0) + 1)

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
        dialog.finished.connect(self.restore_asset_video_from_fullscreen)
        self.w._asset_video_fullscreen_dialog = dialog
        dialog.showFullScreen()

    def restore_asset_video_from_fullscreen(self) -> None:
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
            self.load_entity_details(Path(entity))

    def pick_best_context(self, entity_dir: Path, current: str) -> str:
        layout = getattr(self.w, "_asset_resolved_layout", None)
        selection = build_active_asset_selection(
            entity_dir,
            layout=layout,
            schema=getattr(self.w, "_asset_active_schema", self.w._asset_schema),
            active_tab_index=self.w.asset_work_tabs.currentIndex(),
            explicit_entity_type=getattr(self.w, "_asset_current_entity_type", None),
        )
        contexts = [self.w.asset_context_combo.itemText(i) for i in range(self.w.asset_context_combo.count())]
        chosen = choose_best_context_for_selection(
            selection,
            layout=layout,
            current=current,
            contexts=contexts,
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
            self.host.set_asset_status(f"Selected source file: {self.w._to_houdini_path(str(path))}")
            return
        if path.exists():
            self.sync_asset_inventory_preview(path, kind)

    def sync_asset_inventory_preview(self, path: Path, kind: Optional[str]) -> None:
        if not path.exists():
            return
        if kind == "video":
            self.w.asset_video_controller.preview_first_frame(path)
            return
        if kind == "image":
            images = getattr(self.w, "_preview_images", [])
            if images and path in images:
                self.show_preview_at(images.index(path))
                return
            self.w._asset_inventory_preview_path = path
            preview_size = self.asset_preview_target_size()
            entity = getattr(self.w, "_asset_current_entity", None)
            if entity:
                self.w.asset_preview.setPixmap(build_thumbnail_pixmap(Path(entity), preview_size))
            self.host._asset_preview_request_id += 1
            request_id = self.host._asset_preview_request_id
            QtCore.QTimer.singleShot(
                0,
                lambda rid=request_id, preview_path=Path(path): self.render_asset_preview_request(rid, preview_path),
            )

    def asset_preview_cache_root(self) -> Optional[Path]:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        project_path = Path(project_root) if project_root else None
        return asset_exr_thumb_dir(project_path, getattr(self.w, "settings", None))

    def asset_preview_target_size(self) -> QtCore.QSize:
        size = self.w.asset_preview.size()
        if size.width() <= 0 or size.height() <= 0:
            return QtCore.QSize(420, 200)
        return size

    def asset_placeholder_action(self) -> None:
        self.host.set_asset_status(
            "Git actions are intentionally disabled for now. We should redesign this flow before wiring commit, push and fetch."
        )
