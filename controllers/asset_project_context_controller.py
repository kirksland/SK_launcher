from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets

from core.asset_detection import DetectedProjectLayout, detect_project_layout
from core.asset_layout import resolve_asset_layout
from core.fs import find_projects
from core.settings import normalize_asset_schema, save_settings
from ui.dialogs.asset_layout_mapper_dialog import AssetLayoutMapperDialog


class AssetProjectContextController:
    """Owns project context loading, layout detection, and onboarding flow."""

    def __init__(self, asset_manager_controller: object) -> None:
        self.host = asset_manager_controller
        self.w = asset_manager_controller.w

    def queue_project_context(self, project_path: Optional[Path]) -> None:
        self.host._pending_project_context = project_path
        if not self.asset_page_is_active():
            if project_path is None:
                self.clear_asset_browser_state("Select a project in Projects to browse its assets.")
            else:
                self.w._asset_current_project_root = project_path
                self.w.asset_details_title.setText(project_path.name)
                self.w.asset_path_label.setText(f"{project_path.name} / Inventory will load when opened")
                self.host.set_asset_status("Asset Manager will load when opened.")
            return
        self.host._context_refresh_timer.start()

    def ensure_project_context_loaded(self) -> None:
        if self.host._pending_project_context is not None:
            self.apply_queued_project_context()
            return
        current_item = self.w.project_grid.currentItem()
        if current_item is None:
            self.set_project_context(None)
            return
        path_text = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
        project_path = Path(str(path_text)) if path_text else None
        if self.project_context_is_current(project_path):
            return
        self.set_project_context(project_path)

    def apply_queued_project_context(self) -> None:
        project_path = self.host._pending_project_context
        self.host._pending_project_context = None
        self.set_project_context(project_path)

    def asset_page_is_active(self) -> bool:
        pages = getattr(self.w, "pages", None)
        if pages is None:
            return False
        try:
            return int(pages.currentIndex()) == 1
        except Exception:
            return False

    def project_context_is_current(self, project_path: Optional[Path]) -> bool:
        current_root = getattr(self.w, "_asset_current_project_root", None)
        if project_path is None:
            return current_root is None
        if current_root != project_path:
            return False
        return getattr(self.w, "_asset_resolved_layout", None) is not None or self.w.asset_onboarding_card.isVisible()

    def clear_asset_browser_state(self, message: str) -> None:
        self.host._clear_asset_detail_lists(self.w)
        self.w._asset_current_project_root = None
        self.w._asset_current_entity = None
        self.w._asset_current_entity_type = None
        self.w._asset_active_schema = dict(self.w._asset_schema)
        self.w._asset_resolved_layout = None
        self.w.asset_details_title.setText("No project selected")
        self.w.asset_path_label.setText(message)
        self.w.asset_meta.setText(message)
        self.host._set_asset_pipeline_panel_state(
            summary_text="No pipeline inspection available.",
            pipeline_item_text="No entity selected",
            process_item_text="No entity selected",
        )
        self.host._asset_pipeline_inspection = None
        self.host._set_asset_detail_placeholder_state(
            inventory_text="No entity selected",
            history_text="No entity selected",
        )
        self.host._set_asset_selection_summary("No entity selected")
        self.set_asset_onboarding_visible(False)
        if hasattr(self.w, "asset_layout_btn"):
            self.w.asset_layout_btn.setEnabled(False)

    def set_project_context(self, project_path: Optional[Path]) -> None:
        available_projects = find_projects(self.w.projects_dir)
        self.w.project_controller.prune_cache(available_projects, self.w._asset_cache)
        if project_path is None:
            self.clear_asset_browser_state("Select a project in Projects to browse its assets.")
            self.host.set_asset_status("No project selected.")
            return
        if not project_path.exists():
            self.clear_asset_browser_state(f"{project_path.name} does not exist anymore.")
            self.host.set_asset_status("Selected project is missing.")
            return
        if hasattr(self.w, "asset_layout_btn"):
            self.w.asset_layout_btn.setEnabled(True)
        self.w.asset_path_label.setText(f"{project_path.name} / Loading inventory...")
        self.host.set_asset_status("Scanning project layout...")
        active_schema = self.effective_project_schema(project_path)
        self.w._asset_detected_layout = detect_project_layout(project_path, base_schema=active_schema)
        has_override = str(project_path) in self.w._asset_project_schemas
        if not has_override:
            self.set_asset_onboarding(project_path, self.w._asset_detected_layout)
            self.host._clear_asset_detail_lists(self.w)
            self.w._asset_current_entity = None
            self.w._asset_current_entity_type = None
            self.w._asset_current_project_root = project_path
            self.w.asset_details_title.setText(project_path.name)
            self.w.asset_path_label.setText(f"{project_path.name} / Confirm asset layout")
            self.w.asset_meta.setText("Confirm the detected asset layout before browsing entities.")
            self.host._set_asset_pipeline_panel_state(
                summary_text="Pipeline inspection will be available after layout confirmation.",
                pipeline_item_text="Layout setup required",
                process_item_text="Layout setup required",
                process_summary_text="Confirm the layout before preparing process requests.",
            )
            self.host._asset_pipeline_inspection = None
            self.host._set_asset_detail_placeholder_state(
                inventory_text="Layout setup required",
                history_text="Layout setup required",
            )
            self.host.set_asset_status("Confirm the detected layout or use the default layout.")
            return
        self.set_asset_onboarding_visible(False)
        self.w._asset_active_schema = active_schema
        self.w._asset_resolved_layout = resolve_asset_layout(project_path, active_schema)
        self.w.asset_details_title.setText(project_path.name)
        self.w.asset_path_label.setText(f"{project_path.name} / Select a shot or asset")
        self.host._set_asset_selection_summary(f"{project_path.name} / No entity selected")
        self.w._asset_current_project_root = project_path
        self.host._clear_asset_detail_lists(self.w)
        self.w.asset_preview.clear()
        self.w.asset_meta.setText("Select a shot or asset to view details.")
        self.host._set_asset_pipeline_panel_state(
            summary_text="Select a shot or asset to inspect pipeline status.",
            pipeline_item_text="No entity selected",
            process_item_text="No entity selected",
        )
        self.host._asset_pipeline_inspection = None
        self.host._set_asset_detail_placeholder_state(
            inventory_text="No entity selected",
            history_text="No entity selected",
        )
        self.sync_asset_contexts(active_schema)
        self.host._rebuild_asset_entity_lists(target="both")
        self.update_layout_status_summary(self.w._asset_resolved_layout)
        self.host.set_asset_status(f"Asset Manager ready for {project_path.name}.")

    def accept_detected_layout(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        detected = getattr(self.w, "_asset_detected_layout", None)
        if project_root is None or not isinstance(detected, DetectedProjectLayout):
            return
        self.save_project_schema(project_root, detected.schema)
        self.set_project_context(Path(project_root))

    def accept_default_layout(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is None:
            return
        self.save_project_schema(Path(project_root), self.w._asset_schema)
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
            self.host.set_asset_status("Select a project first before creating a manual layout.")
            return

        project_path = Path(project_root)
        detected = getattr(self.w, "_asset_detected_layout", None)
        seed_schema = (
            deepcopy(detected.schema)
            if isinstance(detected, DetectedProjectLayout) and detected.project_root == project_path
            else deepcopy(self.effective_project_schema(project_path))
        )

        dialog = AssetLayoutMapperDialog(project_path, seed_schema, parent=self.w)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        schema = dialog.schema()
        if schema is None:
            return
        self.save_project_schema(project_path, schema)
        self.set_project_context(project_path)
        self.host.set_asset_status("Manual asset layout saved.")

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
        self.save_project_schema(Path(project_root), schema)
        self.set_project_context(Path(project_root))
        self.host.set_asset_status("Layout saved with library sources merged into Assets.")

    def redetect_layout(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is None:
            return
        self.set_project_context(Path(project_root))

    def reopen_layout_setup(self) -> None:
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is None:
            self.host.set_asset_status("Select a tracked project first to review its asset layout.")
            return
        project_path = Path(project_root)
        detected = detect_project_layout(project_path, base_schema=self.effective_project_schema(project_path))
        self.w._asset_detected_layout = detected
        self.w._asset_current_project_root = project_path
        self.w.asset_details_title.setText(project_path.name)
        self.w.asset_path_label.setText(f"{project_path.name} / Review asset layout")
        self.w.asset_meta.setText("Review the detected layout and confirm a replacement if needed.")
        self.host._clear_asset_detail_lists(self.w)
        self.w.asset_inventory_list.addItem("Layout review in progress")
        self.w.asset_history_list.addItem("Layout review in progress")
        self.set_asset_onboarding(project_path, detected)
        self.host.set_asset_status(
            "Asset layout review reopened. Your saved layout stays unchanged until you confirm a new one."
        )

    def save_project_schema(self, project_root: Path, schema: object) -> None:
        normalized = normalize_asset_schema(schema)
        self.w._asset_project_schemas[str(project_root)] = normalized
        self.w.settings["asset_project_schemas"] = dict(self.w._asset_project_schemas)
        save_settings(self.w.settings)

    def effective_project_schema(self, project_root: Path) -> dict:
        override = self.w._asset_project_schemas.get(str(project_root))
        if override:
            return normalize_asset_schema(override)
        return normalize_asset_schema(self.w._asset_schema)

    def set_asset_onboarding(self, project_root: Path, detected: DetectedProjectLayout) -> None:
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
        sources = self.format_detected_sources(detected)
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
        details = "\n".join(
            part
            for part in [
                "Detected roots: " + " / ".join(roots) if roots else "Detected roots: none yet",
                "Representations: " + " / ".join(reps) if reps else "Representations: no publish or preview folders confirmed",
                f"Contexts: {', '.join(detected.schema.get('contexts', []))}" if detected.schema.get("contexts") else "",
                "Why: " + " | ".join(sources[:5]) if sources else "Why: no strong source evidence found",
                f"Warnings: {'; '.join(detected.warnings)}" if detected.warnings else "",
                f"Needs review: {'; '.join(detected.unresolved)}" if detected.unresolved else "",
                "Correction: use Merge Library into Assets if source files should appear in the main Assets tab."
                if library_count
                else "",
            ]
            if part
        )
        self.w.asset_onboarding_summary.setText(summary)
        self.w.asset_onboarding_details.setText(details)
        if hasattr(self.w, "asset_onboarding_merge_library_btn"):
            self.w.asset_onboarding_merge_library_btn.setVisible(library_count > 0)
        self.set_asset_onboarding_visible(True)

    def set_asset_onboarding_visible(self, visible: bool) -> None:
        self.w.asset_onboarding_card.setVisible(visible)
        self.w.asset_main_split.setVisible(not visible)

    @staticmethod
    def format_detected_sources(detected: DetectedProjectLayout) -> list[str]:
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

    def update_layout_status_summary(self, layout: object) -> None:
        if layout is None:
            return
        shots = len(layout.entities_by_role("shot")) if hasattr(layout, "entities_by_role") else 0
        assets = len(layout.entities_by_role("pipeline_asset")) if hasattr(layout, "entities_by_role") else 0
        library = len(layout.entities_by_role("library_asset")) if hasattr(layout, "entities_by_role") else 0
        if hasattr(self.w.asset_page, "asset_selection_summary"):
            self.w.asset_page.asset_selection_summary.setText(
                f"Detected: {shots} shot(s), {assets} asset(s), {library} library item(s)"
            )

    def sync_asset_contexts(self, schema: dict) -> None:
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
