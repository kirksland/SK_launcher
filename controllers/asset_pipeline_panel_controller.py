from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6 import QtCore, QtWidgets

from core.asset_details import normalize_list_context
from core.asset_layout import EntityRecord, ResolvedAssetLayout
from core.pipeline.entities.models import FreshnessState


class AssetPipelinePanelController:
    def __init__(
        self,
        window: object,
        *,
        default_process_summary: str,
        default_run_summary: str,
        default_artifact_placeholder: str,
        get_pipeline_inspection: Callable[[], object | None],
        set_pipeline_inspection: Callable[[object | None], None],
        format_pipeline_kind_label: Callable[[object], str],
        set_process_summary: Callable[[str], None],
        set_run_summary: Callable[[str], None],
        reset_run_feedback: Callable[[], None],
        update_run_feedback: Callable[[object], None],
        resolve_publish_parameters: Callable[[bool], dict[str, object] | None],
        log_pipeline_run_start: Callable[[str, dict[str, object]], None],
        log_pipeline_run_result: Callable[[object], None],
        set_status: Callable[[str], None],
        reload_current_entity: Callable[[], None],
    ) -> None:
        self.w = window
        self._default_process_summary = default_process_summary
        self._default_run_summary = default_run_summary
        self._default_artifact_placeholder = default_artifact_placeholder
        self._get_pipeline_inspection = get_pipeline_inspection
        self._set_pipeline_inspection = set_pipeline_inspection
        self._format_pipeline_kind_label = format_pipeline_kind_label
        self._set_process_summary = set_process_summary
        self._set_run_summary = set_run_summary
        self._reset_run_feedback = reset_run_feedback
        self._update_run_feedback = update_run_feedback
        self._resolve_publish_parameters = resolve_publish_parameters
        self._log_pipeline_run_start = log_pipeline_run_start
        self._log_pipeline_run_result = log_pipeline_run_result
        self._set_status = set_status
        self._reload_current_entity = reload_current_entity

    def update_inspection(
        self,
        layout: ResolvedAssetLayout | None,
        record: EntityRecord | None,
        *,
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
        list_widget.clear()
        process_list.clear()
        self._reset_run_feedback()
        if inspection is None:
            summary_label.setText("No pipeline inspection available.")
            list_widget.addItem("No pipeline data")
            process_list.addItem("No process definitions")
            self._set_process_summary(self._default_process_summary, run_enabled=False)
            self._set_pipeline_inspection(None)
            return
        self._set_pipeline_inspection(inspection)
        freshness_label = inspection.freshness.replace("_", " ").title()
        downstream_count = len(inspection.downstream)
        summary_label.setText(f"Freshness: {freshness_label}\nDownstream items: {downstream_count}")
        if not inspection.downstream:
            list_widget.addItem("No downstream outputs tracked yet")
        else:
            for downstream in inspection.downstream[:6]:
                list_widget.addItem(self._build_downstream_list_item(downstream))
        if not inspection.available_processes:
            process_list.addItem("No process definitions")
            self._set_process_summary(
                "No process definitions are registered for this entity yet.",
                run_enabled=False,
            )
            return
        for process in inspection.available_processes:
            item = QtWidgets.QListWidgetItem(f"{process.label} [{process.family}]")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, process.id)
            if process.description:
                item.setToolTip(process.description)
            process_list.addItem(item)
        process_list.setCurrentRow(0)
        self.on_process_selected()

    def on_process_selected(self) -> None:
        if not hasattr(self.w.asset_page, "asset_pipeline_process_summary"):
            return
        process_list = self.w.asset_page.asset_pipeline_process_list
        item = process_list.currentItem()
        if item is None:
            self._set_process_summary(self._default_process_summary, run_enabled=False)
            return
        process_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        process_controller = getattr(self.w, "process_controller", None)
        inspection = self._get_pipeline_inspection()
        prepared = (
            process_controller.prepare_request(inspection, process_id)
            if process_controller is not None
            else None
        )
        runtime_request = (
            process_controller.build_runtime_request(inspection, process_id)
            if process_controller is not None
            else None
        )
        if prepared is None:
            self._set_process_summary(
                "This process cannot be prepared for the current selection.",
                run_enabled=False,
            )
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
            preview_parameters = self._resolve_publish_parameters(ensure_dirs=False)
            if preview_parameters is not None:
                preview_text = (
                    f"\nResolved source: {preview_parameters['source']}\n"
                    f"Resolved output: {preview_parameters['output']}\n"
                    f"Resolved context: {preview_parameters['context']}"
                )
        self._set_process_summary(
            f"{prepared.process_label}\n"
            f"Target: {prepared.entity_label} [{prepared.entity_kind}]\n"
            f"Requires: {capability_text}\n"
            f"Outputs: {outputs_text}\n"
            f"Mode: {remote_text} / {review_text}\n"
            f"{runtime_text}"
            f"{preview_text}",
            run_enabled=runtime_request is not None and prepared.process_id == "publish.asset.usd",
        )

    def run_selected_process(self) -> None:
        process_list = getattr(self.w.asset_page, "asset_pipeline_process_list", None)
        if process_list is None:
            return
        item = process_list.currentItem()
        if item is None:
            self._set_status("Select a pipeline process first.")
            return
        process_id = str(item.data(QtCore.Qt.ItemDataRole.UserRole) or "").strip()
        if not process_id:
            self._set_status("Selected pipeline process has no identifier.")
            return
        process_controller = getattr(self.w, "process_controller", None)
        inspection = self._get_pipeline_inspection()
        if process_controller is None or inspection is None:
            self._set_status("No pipeline inspection is available for this selection.")
            return
        parameters = self._resolve_pipeline_process_parameters(process_id)
        if parameters is None:
            return
        self._log_pipeline_run_start(process_id, parameters)
        self._set_run_summary(f"Running {process_id}...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            runtime_result = process_controller.execute_houdini_request(
                inspection,
                process_id,
                parameters=parameters,
            )
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if runtime_result is None:
            self._set_run_summary("Process execution could not be prepared.")
            self._set_status("Pipeline execution could not be prepared.")
            return
        self._update_run_feedback(runtime_result)
        self._log_pipeline_run_result(runtime_result)
        if runtime_result.execution.status in (FreshnessState.UP_TO_DATE, "succeeded"):
            self._set_status(f"{runtime_result.request.process_id} completed.")
            self._reload_current_entity()
        else:
            self._set_status(runtime_result.execution.message or "Pipeline execution failed.")

    def _resolve_pipeline_process_parameters(self, process_id: str) -> dict[str, object] | None:
        if process_id == "publish.asset.usd":
            return self._resolve_publish_parameters(ensure_dirs=True)
        self._set_status(f"{process_id} is not executable from the Asset Manager yet.")
        self._set_run_summary(
            f"{process_id} is visible in the inspector, but its execution planner is not wired yet."
        )
        return None

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

    def build_artifact_list_item(self, artifact: object) -> QtWidgets.QListWidgetItem:
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
