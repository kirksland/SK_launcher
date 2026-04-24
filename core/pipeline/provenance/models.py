from __future__ import annotations

from dataclasses import dataclass, field


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


def _clean_label(value: object) -> str:
    return str(value or "").strip()


def _clean_optional_path(value: object) -> str:
    return str(value or "").strip()


@dataclass(frozen=True, slots=True)
class SourceArtifactRef:
    path: str
    kind: str = "file"
    label: str = ""
    entity_id: str = ""

    def __post_init__(self) -> None:
        path = _clean_optional_path(self.path)
        kind = _clean_token(self.kind)
        if not path:
            raise ValueError("SourceArtifactRef.path must be non-empty.")
        if not kind:
            raise ValueError("SourceArtifactRef.kind must be non-empty.")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "label", _clean_label(self.label))
        object.__setattr__(self, "entity_id", _clean_token(self.entity_id))


@dataclass(frozen=True, slots=True)
class ProducedArtifactRecord:
    id: str
    path: str
    kind: str
    process_id: str
    job_id: str
    target_entity_id: str
    execution_target_id: str
    label: str = ""
    source_artifacts: tuple[SourceArtifactRef, ...] = field(default_factory=tuple)
    execution_mode: str = ""

    def __post_init__(self) -> None:
        artifact_id = _clean_token(self.id)
        path = _clean_optional_path(self.path)
        kind = _clean_token(self.kind)
        process_id = _clean_token(self.process_id)
        job_id = _clean_token(self.job_id)
        target_entity_id = _clean_token(self.target_entity_id)
        execution_target_id = _clean_token(self.execution_target_id)
        if not artifact_id:
            raise ValueError("ProducedArtifactRecord.id must be non-empty.")
        if not path:
            raise ValueError("ProducedArtifactRecord.path must be non-empty.")
        if not kind:
            raise ValueError("ProducedArtifactRecord.kind must be non-empty.")
        if not process_id:
            raise ValueError("ProducedArtifactRecord.process_id must be non-empty.")
        if not job_id:
            raise ValueError("ProducedArtifactRecord.job_id must be non-empty.")
        if not target_entity_id:
            raise ValueError("ProducedArtifactRecord.target_entity_id must be non-empty.")
        if not execution_target_id:
            raise ValueError("ProducedArtifactRecord.execution_target_id must be non-empty.")
        object.__setattr__(self, "id", artifact_id)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "process_id", process_id)
        object.__setattr__(self, "job_id", job_id)
        object.__setattr__(self, "target_entity_id", target_entity_id)
        object.__setattr__(self, "execution_target_id", execution_target_id)
        object.__setattr__(self, "label", _clean_label(self.label))
        object.__setattr__(self, "source_artifacts", tuple(self.source_artifacts))
        object.__setattr__(self, "execution_mode", _clean_token(self.execution_mode))
