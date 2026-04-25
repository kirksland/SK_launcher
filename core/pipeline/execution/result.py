from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


def _clean_label(value: object) -> str:
    return str(value or "").strip()


def _freeze_mapping(payload: Mapping[str, object] | None) -> Mapping[str, object]:
    if not payload:
        return MappingProxyType({})
    return MappingProxyType(dict(payload))


class ExecutionStatus:
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"

    ALL = {
        SUCCEEDED,
        FAILED,
        BLOCKED,
        SKIPPED,
    }


@dataclass(frozen=True, slots=True)
class ProducedOutput:
    kind: str
    path: str
    label: str = ""

    def __post_init__(self) -> None:
        kind = _clean_token(self.kind)
        path = str(self.path or "").strip()
        if not kind:
            raise ValueError("ProducedOutput.kind must be non-empty.")
        if not path:
            raise ValueError("ProducedOutput.path must be non-empty.")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "label", _clean_label(self.label))


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: str
    message: str = ""
    outputs: tuple[ProducedOutput, ...] = field(default_factory=tuple)
    log_path: str = ""
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        status = _clean_token(self.status)
        if status not in ExecutionStatus.ALL:
            raise ValueError(f"ExecutionResult.status must be one of {sorted(ExecutionStatus.ALL)}.")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "message", _clean_label(self.message))
        object.__setattr__(self, "log_path", str(self.log_path or "").strip())
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))
