from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .definitions import ProcessDefinition
from .registry import list_process_definitions

if TYPE_CHECKING:
    from core.pipeline.asset_bridge import PipelineEntityInspection


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True, slots=True)
class PreparedProcessRequest:
    process_id: str
    process_label: str
    family: str
    entity_id: str
    entity_label: str
    entity_kind: str
    description: str
    required_capabilities: tuple[str, ...]
    outputs: tuple[str, ...]
    supports_remote: bool
    review_required: bool


def get_process_definition(process_id: object) -> ProcessDefinition | None:
    key = _clean_token(process_id)
    if not key:
        return None
    for process in list_process_definitions():
        if process.id == key:
            return process
    return None


def prepare_process_request(
    inspection: PipelineEntityInspection | None,
    process_id: object,
) -> PreparedProcessRequest | None:
    if inspection is None:
        return None
    process = get_process_definition(process_id)
    if process is None:
        return None
    if not process.supports_entity_kind(inspection.entity.kind):
        return None
    return PreparedProcessRequest(
        process_id=process.id,
        process_label=process.label,
        family=process.family,
        entity_id=inspection.entity.id,
        entity_label=inspection.entity.label or inspection.entity.id,
        entity_kind=inspection.entity.kind,
        description=process.description,
        required_capabilities=tuple(str(value) for value in process.required_capabilities),
        outputs=tuple(str(value) for value in process.outputs),
        supports_remote=bool(process.supports_remote),
        review_required=bool(process.review_required),
    )
