from __future__ import annotations

from pathlib import Path

from core.pipeline.execution.result import ExecutionResult
from core.pipeline.jobs.models import JobRecord
from core.pipeline.jobs.requests import RuntimeProcessRequest

from .models import ProducedArtifactRecord, SourceArtifactRef


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


def _clean_path(value: object) -> str:
    return str(value or "").strip()


def _source_refs_from_request(request: RuntimeProcessRequest) -> tuple[SourceArtifactRef, ...]:
    params = request.parameters
    candidates: list[tuple[str, str]] = []
    for key in ("source", "source_path", "input", "input_path"):
        value = _clean_path(params.get(key))
        if value:
            candidates.append((key, value))
    refs: list[SourceArtifactRef] = []
    seen: set[str] = set()
    for key, value in candidates:
        if value in seen:
            continue
        seen.add(value)
        refs.append(
            SourceArtifactRef(
                path=value,
                kind="file",
                label=Path(value).name or key,
                entity_id=request.target_entity.id,
            )
        )
    return tuple(refs)


def build_artifact_records(
    *,
    request: RuntimeProcessRequest,
    job: JobRecord,
    execution: ExecutionResult,
) -> tuple[ProducedArtifactRecord, ...]:
    source_artifacts = _source_refs_from_request(request)
    execution_mode = _clean_token(execution.payload.get("execution_mode"))
    records: list[ProducedArtifactRecord] = []
    for index, output in enumerate(execution.outputs, start=1):
        record = ProducedArtifactRecord(
            id=f"{job.id}:artifact:{index}",
            path=output.path,
            kind=output.kind,
            label=output.label,
            process_id=job.process_id,
            job_id=job.id,
            target_entity_id=job.target_entity.id,
            execution_target_id=job.execution_target_id,
            source_artifacts=source_artifacts,
            execution_mode=execution_mode,
        )
        records.append(record)
    return tuple(records)
