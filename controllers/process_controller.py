from __future__ import annotations

from pathlib import Path
import shutil

from core.asset_layout import EntityRecord, ResolvedAssetLayout
from core.pipeline.asset_bridge import PipelineEntityInspection, inspect_entity_pipeline
from core.pipeline.entities.models import ExecutionTarget, TargetCapability
from core.pipeline.execution import ExecutionResult, execute_houdini_request
from core.pipeline.jobs import (
    LocalJobRuntime,
    RuntimeProcessRequest,
    RuntimeExecutionResult,
    RuntimeSubmissionResult,
    build_runtime_process_request,
)
from core.pipeline.provenance import ProducedArtifactRecord
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
        return inspect_entity_pipeline(
            layout,
            record,
            context=context,
            produced_artifacts=self._runtime.artifact_records(),
        )

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
            execution_target=execution_target or self._local_execution_target(),
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
            execution_target=execution_target or self._local_execution_target(),
            parameters=parameters,
        )
        return self._runtime.submit(request)

    def execute_houdini_request(
        self,
        inspection: PipelineEntityInspection | None,
        process_id: object,
        *,
        execution_target: ExecutionTarget | None = None,
        parameters: dict[str, object] | None = None,
    ) -> RuntimeExecutionResult | None:
        request = self.build_runtime_request(
            inspection,
            process_id,
            execution_target=execution_target or self._local_execution_target(),
            parameters=parameters,
        )
        return self._runtime.execute(
            request,
            executor=lambda runtime_request: execute_houdini_request(
                runtime_request,
                executable=self._houdini_runner_executable(),
                launcher_root=self._launcher_root(),
                project_path=self._current_project_root(),
                run_subprocess=True,
            ),
        )

    def runtime_jobs(self) -> tuple[object, ...]:
        return self._runtime.jobs()

    def latest_execution_result(self) -> ExecutionResult | None:
        return self._runtime.latest_result()

    def latest_artifacts(self) -> tuple[ProducedArtifactRecord, ...]:
        return self._runtime.latest_artifacts()

    def produced_artifacts(self) -> tuple[ProducedArtifactRecord, ...]:
        return self._runtime.artifact_records()

    def _houdini_runner_executable(self) -> str:
        configured = str(getattr(self.w, "_houdini_exe", "") or "").strip()
        return configured or "hython"

    def _local_execution_target(self) -> ExecutionTarget:
        capabilities: list[str] = []
        executable = self._houdini_runner_executable()
        if self._can_resolve_houdini(executable):
            capabilities.extend(
                (
                    TargetCapability.HOUDINI,
                    TargetCapability.USD,
                    TargetCapability.SOLARIS,
                )
            )
        if shutil.which("ffmpeg"):
            capabilities.append(TargetCapability.FFMPEG)
        return ExecutionTarget(
            id="local",
            kind="local_workstation",
            label="Local Workstation",
            capabilities=tuple(capabilities),
        )

    @staticmethod
    def _can_resolve_houdini(executable: str) -> bool:
        raw = str(executable or "").strip()
        if not raw:
            return False
        candidate = Path(raw)
        if candidate.exists():
            return True
        return shutil.which(raw) is not None

    @staticmethod
    def _launcher_root() -> Path:
        return Path(__file__).resolve().parent.parent

    def _current_project_root(self) -> Path | None:
        current = getattr(self.w, "_asset_current_project_root", None)
        if not current:
            return None
        return Path(current)
