from __future__ import annotations

from dataclasses import dataclass

from core.pipeline.entities.models import EntityRef, FreshnessState


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


def _validate_enum(value: object, *, allowed: set[str], field_name: str) -> str:
    token = _clean_token(value)
    if token not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}.")
    return token


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    upstream: EntityRef
    downstream: EntityRef
    kind: str
    freshness: str = FreshnessState.UP_TO_DATE

    _ALLOWED_KINDS = {
        "consumes",
        "builds_from",
        "publishes_from",
        "refreshes_from",
        "references",
    }

    def __post_init__(self) -> None:
        if self.upstream.id == self.downstream.id:
            raise ValueError("DependencyEdge cannot link an entity to itself.")
        object.__setattr__(
            self,
            "kind",
            _validate_enum(self.kind, allowed=self._ALLOWED_KINDS, field_name="DependencyEdge.kind"),
        )
        object.__setattr__(
            self,
            "freshness",
            _validate_enum(self.freshness, allowed=FreshnessState.ALL, field_name="DependencyEdge.freshness"),
        )
