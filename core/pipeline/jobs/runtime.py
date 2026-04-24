from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from core.pipeline.execution.result import ExecutionResult, ExecutionStatus
from core.pipeline.provenance import ProducedArtifactRecord, build_artifact_records

from .models import JobRecord, JobState
from .requests import RuntimeProcessRequest


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True, slots=True)
class RuntimeSubmissionResult:
    request: RuntimeProcessRequest
    job: JobRecord
    accepted: bool


@dataclass(frozen=True, slots=True)
class RuntimeExecutionResult:
    request: RuntimeProcessRequest
    job: JobRecord
    execution: ExecutionResult


def _job_state_for_execution_status(status: str) -> str:
    mapping = {
        ExecutionStatus.SUCCEEDED: JobState.SUCCEEDED,
        ExecutionStatus.FAILED: JobState.FAILED,
        ExecutionStatus.BLOCKED: JobState.BLOCKED,
        ExecutionStatus.SKIPPED: JobState.PLANNING,
    }
    return mapping.get(_clean_token(status), JobState.FAILED)


class LocalJobRuntime:
    """Minimal shared runtime that records jobs without executing them yet."""

    def __init__(self) -> None:
        self._jobs: list[JobRecord] = []
        self._results: dict[str, ExecutionResult] = {}
        self._artifacts: dict[str, tuple[ProducedArtifactRecord, ...]] = {}

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

    def execute(
        self,
        request: RuntimeProcessRequest | None,
        *,
        executor: object,
    ) -> RuntimeExecutionResult | None:
        submission = self.submit(request)
        if submission is None:
            return None
        if not callable(executor):
            raise ValueError("LocalJobRuntime.execute requires a callable executor.")
        execution = executor(submission.request)
        if not isinstance(execution, ExecutionResult):
            raise TypeError("LocalJobRuntime executor must return an ExecutionResult.")
        updated_job = JobRecord(
            id=submission.job.id,
            process_id=submission.job.process_id,
            target_entity=submission.job.target_entity,
            execution_target_id=submission.job.execution_target_id,
            state=_job_state_for_execution_status(execution.status),
            parameters=submission.job.parameters,
            message=execution.message or submission.job.message,
        )
        self._jobs[-1] = updated_job
        self._results[updated_job.id] = execution
        self._artifacts[updated_job.id] = build_artifact_records(
            request=submission.request,
            job=updated_job,
            execution=execution,
        )
        return RuntimeExecutionResult(
            request=submission.request,
            job=updated_job,
            execution=execution,
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

    def execution_result_for_job(self, job_id: object) -> ExecutionResult | None:
        key = _clean_token(job_id)
        if not key:
            return None
        return self._results.get(key)

    def latest_result(self) -> ExecutionResult | None:
        if not self._jobs:
            return None
        latest = self._jobs[-1]
        return self._results.get(latest.id)

    def artifact_records_for_job(self, job_id: object) -> tuple[ProducedArtifactRecord, ...]:
        key = _clean_token(job_id)
        if not key:
            return ()
        return self._artifacts.get(key, ())

    def latest_artifacts(self) -> tuple[ProducedArtifactRecord, ...]:
        if not self._jobs:
            return ()
        latest = self._jobs[-1]
        return self._artifacts.get(latest.id, ())
