from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from .models import JobRecord, JobState
from .requests import RuntimeProcessRequest


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True, slots=True)
class RuntimeSubmissionResult:
    request: RuntimeProcessRequest
    job: JobRecord
    accepted: bool


class LocalJobRuntime:
    """Minimal shared runtime that records jobs without executing them yet."""

    def __init__(self) -> None:
        self._jobs: list[JobRecord] = []

    def submit(self, request: RuntimeProcessRequest | None) -> RuntimeSubmissionResult | None:
        if request is None:
            return None
        state = JobState.QUEUED if request.is_runtime_ready() else JobState.BLOCKED
        message = (
            "Queued for local runtime."
            if state == JobState.QUEUED
            else "Blocked: execution target capabilities are not fully resolved."
        )
        job = JobRecord(
            id=f"job_{uuid4().hex}",
            process_id=request.process_id,
            target_entity=request.target_entity,
            execution_target_id=request.execution_target.id,
            state=state,
            parameters=request.parameters,
            message=message,
        )
        self._jobs.append(job)
        return RuntimeSubmissionResult(
            request=request,
            job=job,
            accepted=state == JobState.QUEUED,
        )

    def jobs(self) -> tuple[JobRecord, ...]:
        return tuple(self._jobs)

    def latest_job(self) -> JobRecord | None:
        if not self._jobs:
            return None
        return self._jobs[-1]

    def jobs_for_process(self, process_id: object) -> tuple[JobRecord, ...]:
        key = _clean_token(process_id)
        if not key:
            return ()
        return tuple(job for job in self._jobs if job.process_id == key)

    def jobs_for_entity(self, entity_id: object) -> tuple[JobRecord, ...]:
        key = _clean_token(entity_id)
        if not key:
            return ()
        return tuple(job for job in self._jobs if job.target_entity.id == key)
