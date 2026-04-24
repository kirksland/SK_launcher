from __future__ import annotations

from core.asset_layout import EntityRecord, ResolvedAssetLayout
from core.pipeline.asset_bridge import PipelineEntityInspection, inspect_entity_pipeline
from core.pipeline.processes.planning import PreparedProcessRequest, prepare_process_request


class ProcessController:
    """Thin bridge between UI selection context and pipeline core services."""

    def __init__(self, window: object) -> None:
        self.w = window

    def inspect_entity(
        self,
        layout: ResolvedAssetLayout | None,
        record: EntityRecord | None,
        *,
        context: str | None = None,
    ) -> PipelineEntityInspection | None:
        return inspect_entity_pipeline(layout, record, context=context)

    def prepare_request(
        self,
        inspection: PipelineEntityInspection | None,
        process_id: object,
    ) -> PreparedProcessRequest | None:
        return prepare_process_request(inspection, process_id)
