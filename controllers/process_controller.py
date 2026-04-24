from __future__ import annotations

from core.asset_layout import EntityRecord, ResolvedAssetLayout
from core.pipeline.asset_bridge import PipelineEntityInspection, inspect_entity_pipeline
from core.pipeline.entities.models import ExecutionTarget
from core.pipeline.jobs import (
    LocalJobRuntime,
    RuntimeProcessRequest,
    RuntimeSubmissionResult,
    build_runtime_process_request,
)
from core.pipeline.processes.planning import PreparedProcessRequest, prepare_process_request


class ProcessController:
    """Thin bridge between UI selection context and pipeline core services."""

    def __init__(self, window: object) -> None:
        self.w = window
        self._runtime = LocalJobRuntime()

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

    def build_runtime_request(
        self,
        inspection: PipelineEntityInspection | None,
        process_id: object,
        *,
        execution_target: ExecutionTarget | None = None,
        parameters: dict[str, object] | None = None,
    ) -> RuntimeProcessRequest | None:
        prepared = self.prepare_request(inspection, process_id)
        return build_runtime_process_request(
            prepared,
            execution_target=execution_target,
            parameters=parameters,
        )

    def submit_runtime_request(
        self,
        inspection: PipelineEntityInspection | None,
        process_id: object,
        *,
        execution_target: ExecutionTarget | None = None,
        parameters: dict[str, object] | None = None,
    ) -> RuntimeSubmissionResult | None:
        request = self.build_runtime_request(
            inspection,
            process_id,
            execution_target=execution_target,
            parameters=parameters,
        )
        return self._runtime.submit(request)

    def runtime_jobs(self) -> tuple[object, ...]:
        return self._runtime.jobs()
