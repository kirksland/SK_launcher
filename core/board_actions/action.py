from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


def _clean_kind(value: object) -> str:
    return str(value or "").strip().lower()


def _freeze_payload(payload: Mapping[str, object] | None) -> Mapping[str, object]:
    if not payload:
        return MappingProxyType({})
    return MappingProxyType(dict(payload))


@dataclass(frozen=True, slots=True)
class BoardAction:
    """Describes an intentional board mutation."""

    kind: str
    payload: Mapping[str, object] = field(default_factory=dict)
    history_label: str | None = None
    affects_history: bool = True
    should_save: bool = False
    update_groups: bool = True

    def __post_init__(self) -> None:
        kind = _clean_kind(self.kind)
        if not kind:
            raise ValueError("BoardAction.kind must be non-empty.")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "payload", _freeze_payload(self.payload))
        if self.history_label is not None:
            label = str(self.history_label or "").strip()
            object.__setattr__(self, "history_label", label or None)


@dataclass(frozen=True, slots=True)
class BoardMutationResult:
    action: BoardAction
    state: Mapping[str, object]
    dirty: bool
    history_scheduled: bool
    saved: bool
