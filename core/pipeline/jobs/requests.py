from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from core.pipeline.entities.models import EntityRef, ExecutionTarget
from core.pipeline.processes.planning import PreparedProcessRequest


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


def _clean_label(value: object) -> str:
    return str(value or "").strip()


def _clean_tokens(values: tuple[object, ...]) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _clean_token(value)
        if not token or token in seen:
            continue
        seen.add(token)
        cleaned.append(token)
    return tuple(cleaned)


def _freeze_mapping(payload: Mapping[str, object] | None) -> Mapping[str, object]:
    if not payload:
        return MappingProxyType({})
    return MappingProxyType(dict(payload))


def default_local_execution_target() -> ExecutionTarget:
    return ExecutionTarget(
        id="local",
        kind="local_workstation",
        label="Local Workstation",
    )


@dataclass(frozen=True, slots=True)
class RuntimeProcessRequest:
    process_id: str
    process_label: str
    family: str
    target_entity: EntityRef
    execution_target: ExecutionTarget
    description: str = ""
    required_capabilities: tuple[object, ...] = field(default_factory=tuple)
    outputs: tuple[object, ...] = field(default_factory=tuple)
    parameters: Mapping[str, object] = field(default_factory=dict)
    review_required: bool = False
    supports_remote: bool = False
    capability_gaps: tuple[object, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        process_id = _clean_token(self.process_id)
        process_label = _clean_label(self.process_label)
        if not process_id:
            raise ValueError("RuntimeProcessRequest.process_id must be non-empty.")
        if not process_label:
            raise ValueError("RuntimeProcessRequest.process_label must be non-empty.")
        object.__setattr__(self, "process_id", process_id)
        object.__setattr__(self, "process_label", process_label)
        object.__setattr__(self, "family", _clean_token(self.family))
        object.__setattr__(self, "description", _clean_label(self.description))
        object.__setattr__(self, "required_capabilities", _clean_tokens(tuple(self.required_capabilities)))
        object.__setattr__(self, "outputs", _clean_tokens(tuple(self.outputs)))
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters))
        object.__setattr__(self, "capability_gaps", _clean_tokens(tuple(self.capability_gaps)))

    def is_runtime_ready(self) -> bool:
        return not self.capability_gaps


def build_runtime_process_request(
    prepared: PreparedProcessRequest | None,
    *,
    execution_target: ExecutionTarget | None = None,
    parameters: Mapping[str, object] | None = None,
) -> RuntimeProcessRequest | None:
    if prepared is None:
        return None
    target = execution_target or default_local_execution_target()
    required_capabilities = tuple(str(value) for value in prepared.required_capabilities)
    capability_gaps = tuple(
        capability for capability in required_capabilities if not target.supports(capability)
    )
    return RuntimeProcessRequest(
        process_id=prepared.process_id,
        process_label=prepared.process_label,
        family=prepared.family,
        target_entity=EntityRef(
            id=prepared.entity_id,
            kind=prepared.entity_kind,
            label=prepared.entity_label,
        ),
        execution_target=target,
        description=prepared.description,
        required_capabilities=required_capabilities,
        outputs=tuple(str(value) for value in prepared.outputs),
        parameters=parameters,
        review_required=bool(prepared.review_required),
        supports_remote=bool(prepared.supports_remote),
        capability_gaps=capability_gaps,
    )
