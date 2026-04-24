from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from core.pipeline.entities.models import EntityRef


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


def _clean_label(value: object) -> str:
    return str(value or "").strip()


def _freeze_mapping(payload: Mapping[str, object] | None) -> Mapping[str, object]:
    if not payload:
        return MappingProxyType({})
    return MappingProxyType(dict(payload))


def _validate_enum(value: object, *, allowed: set[str], field_name: str) -> str:
    token = _clean_token(value)
    if token not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}.")
    return token


class JobState:
    QUEUED = "queued"
    PLANNING = "planning"
    BLOCKED = "blocked"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL = {
        QUEUED,
        PLANNING,
        BLOCKED,
        RUNNING,
        SUCCEEDED,
        FAILED,
        CANCELLED,
    }


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: str
    process_id: str
    target_entity: EntityRef
    execution_target_id: str
    state: str = JobState.QUEUED
    parameters: Mapping[str, object] = field(default_factory=dict)
    message: str = ""

    def __post_init__(self) -> None:
        job_id = _clean_token(self.id)
        process_id = _clean_token(self.process_id)
        execution_target_id = _clean_token(self.execution_target_id)
        if not job_id:
            raise ValueError("JobRecord.id must be non-empty.")
        if not process_id:
            raise ValueError("JobRecord.process_id must be non-empty.")
        if not execution_target_id:
            raise ValueError("JobRecord.execution_target_id must be non-empty.")
        object.__setattr__(self, "id", job_id)
        object.__setattr__(self, "process_id", process_id)
        object.__setattr__(self, "execution_target_id", execution_target_id)
        object.__setattr__(self, "state", _validate_enum(self.state, allowed=JobState.ALL, field_name="JobRecord.state"))
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters))
        object.__setattr__(self, "message", _clean_label(self.message))
