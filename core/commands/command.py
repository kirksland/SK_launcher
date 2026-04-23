from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .scopes import normalize_scope


def normalize_command_id(value: object) -> str:
    return str(value or "").strip().lower()


def normalize_domain(value: object) -> str:
    return str(value or "").strip().lower()


def clean_shortcut_sequence(value: object) -> str:
    return "+".join(part.strip() for part in str(value or "").strip().split("+") if part.strip())


def clean_shortcut_sequences(values: tuple[object, ...]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for value in values:
        sequence = clean_shortcut_sequence(value)
        if sequence:
            cleaned.append(sequence)
    return tuple(cleaned)


@dataclass(frozen=True, slots=True)
class AppCommand:
    id: str
    label: str
    domain: str
    scope: str
    default_shortcuts: tuple[object, ...] = field(default_factory=tuple)
    description: str = ""
    when: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", normalize_command_id(self.id))
        object.__setattr__(self, "domain", normalize_domain(self.domain))
        object.__setattr__(self, "scope", normalize_scope(self.scope))
        object.__setattr__(self, "label", str(self.label or "").strip())
        object.__setattr__(self, "description", str(self.description or "").strip())
        object.__setattr__(self, "when", str(self.when or "").strip())
        object.__setattr__(self, "default_shortcuts", clean_shortcut_sequences(tuple(self.default_shortcuts)))


@dataclass(frozen=True, slots=True)
class CommandContext:
    active_scope: str
    page_id: str = ""
    focus_kind: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_scope", normalize_scope(self.active_scope))
        object.__setattr__(self, "page_id", str(self.page_id or "").strip().lower())
        object.__setattr__(self, "focus_kind", str(self.focus_kind or "").strip().lower())
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class CommandResult:
    command_id: str
    handled: bool
    message: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", normalize_command_id(self.command_id))
        object.__setattr__(self, "message", str(self.message or "").strip())
