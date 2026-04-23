from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .command import AppCommand, clean_shortcut_sequence, normalize_command_id
from .scopes import scopes_overlap


def normalize_shortcut_sequence(value: object) -> str:
    sequence = clean_shortcut_sequence(value)
    return "+".join(part.casefold() for part in sequence.split("+") if part)


@dataclass(frozen=True, slots=True)
class ShortcutBinding:
    command_id: str
    sequence: str
    scope: str
    source: str = "default"

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", normalize_command_id(self.command_id))
        object.__setattr__(self, "sequence", clean_shortcut_sequence(self.sequence))
        object.__setattr__(self, "scope", str(self.scope or "").strip().lower())
        object.__setattr__(self, "source", str(self.source or "").strip().lower() or "default")

    @property
    def normalized_sequence(self) -> str:
        return normalize_shortcut_sequence(self.sequence)


@dataclass(frozen=True, slots=True)
class ShortcutConflict:
    sequence: str
    scope: str
    command_ids: tuple[str, ...]


def build_shortcut_bindings(
    commands: list[AppCommand],
    overrides: Mapping[str, object] | None = None,
) -> list[ShortcutBinding]:
    overrides = overrides or {}
    bindings: list[ShortcutBinding] = []
    for command in commands:
        override_key = _matching_override_key(command.id, overrides)
        if override_key is None:
            sequences = command.default_shortcuts
            source = "default"
        else:
            raw_sequences = overrides.get(override_key)
            sequences = _coerce_sequences(raw_sequences)
            source = "user"
        for sequence in sequences:
            cleaned = clean_shortcut_sequence(sequence)
            if cleaned:
                bindings.append(
                    ShortcutBinding(
                        command_id=command.id,
                        sequence=cleaned,
                        scope=command.scope,
                        source=source,
                    )
                )
    return bindings


def find_shortcut_conflicts(bindings: list[ShortcutBinding]) -> list[ShortcutConflict]:
    conflicts: list[ShortcutConflict] = []
    for index, binding in enumerate(bindings):
        command_ids = {binding.command_id}
        scopes = {binding.scope}
        for other in bindings[index + 1:]:
            if binding.normalized_sequence != other.normalized_sequence:
                continue
            if binding.command_id == other.command_id:
                continue
            if not scopes_overlap(binding.scope, other.scope):
                continue
            command_ids.add(other.command_id)
            scopes.add(other.scope)
        if len(command_ids) > 1:
            conflict_key = (
                binding.normalized_sequence,
                tuple(sorted(command_ids)),
            )
            if not any(
                existing.sequence == conflict_key[0]
                and existing.command_ids == conflict_key[1]
                for existing in conflicts
            ):
                conflicts.append(
                    ShortcutConflict(
                        sequence=binding.normalized_sequence,
                        scope="/".join(sorted(scopes)),
                        command_ids=tuple(sorted(command_ids)),
                    )
                )
    return conflicts


def _matching_override_key(command_id: str, overrides: Mapping[str, object]) -> str | None:
    normalized = normalize_command_id(command_id)
    for key in overrides.keys():
        if normalize_command_id(key) == normalized:
            return str(key)
    return None


def _coerce_sequences(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        sequence = clean_shortcut_sequence(value)
        return (sequence,) if sequence else ()
    if isinstance(value, (list, tuple)):
        sequences: list[str] = []
        for item in value:
            sequence = clean_shortcut_sequence(item)
            if sequence:
                sequences.append(sequence)
        return tuple(sequences)
    return ()
