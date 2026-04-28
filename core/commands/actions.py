from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping

from .command import CommandContext, clean_shortcut_sequence, normalize_command_id
from .registry import CommandRegistry
from .scopes import normalize_scope, scopes_overlap
from .shortcuts import ShortcutBinding


@dataclass(frozen=True, slots=True)
class ActionContext:
    scope: str
    target: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", normalize_scope(self.scope))
        object.__setattr__(self, "target", str(self.target or "").strip().lower())
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_command_context(self) -> CommandContext:
        return CommandContext(
            active_scope=self.scope,
            page_id=self.scope.split(".", 1)[0],
            metadata={"target": self.target, **dict(self.metadata)},
        )


@dataclass(frozen=True, slots=True)
class ResolvedAction:
    command_id: str
    label: str
    shortcut: str = ""
    enabled: bool = True
    visible: bool = True
    separator_before: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", normalize_command_id(self.command_id))
        object.__setattr__(self, "label", str(self.label or "").strip())
        object.__setattr__(self, "shortcut", clean_shortcut_sequence(self.shortcut))
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "visible", bool(self.visible))
        object.__setattr__(self, "separator_before", bool(self.separator_before))


@dataclass(frozen=True, slots=True)
class ActionRule:
    command_id: str
    targets: tuple[str, ...] = ()
    when: str = ""
    label: str = ""
    separator_before: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", normalize_command_id(self.command_id))
        object.__setattr__(self, "targets", tuple(str(target or "").strip().lower() for target in self.targets))
        object.__setattr__(self, "when", str(self.when or "").strip())
        object.__setattr__(self, "label", str(self.label or "").strip())
        object.__setattr__(self, "separator_before", bool(self.separator_before))


class ActionResolver:
    def __init__(
        self,
        registry: CommandRegistry,
        shortcut_bindings: Iterable[ShortcutBinding] = (),
        rules: Iterable[ActionRule] = (),
    ) -> None:
        self.registry = registry
        self.shortcut_bindings = tuple(shortcut_bindings)
        self.rules = tuple(rules)

    def resolve(self, context: ActionContext) -> list[ResolvedAction]:
        actions: list[ResolvedAction] = []
        shortcuts = self._shortcut_map()
        for rule in self.rules:
            command = self.registry.get(rule.command_id)
            if command is None:
                continue
            if rule.targets and context.target not in rule.targets:
                continue
            if not scopes_overlap(context.scope, command.scope):
                continue
            if rule.when and not _condition_matches(rule.when, context.metadata):
                continue
            actions.append(
                ResolvedAction(
                    command_id=command.id,
                    label=rule.label or command.label,
                    shortcut=shortcuts.get(command.id, ""),
                    separator_before=rule.separator_before,
                )
            )
        return actions

    def _shortcut_map(self) -> dict[str, str]:
        shortcuts: dict[str, str] = {}
        for binding in self.shortcut_bindings:
            shortcuts.setdefault(binding.command_id, binding.sequence)
        return shortcuts


def _condition_matches(condition: str, metadata: Mapping[str, object]) -> bool:
    if not condition:
        return True
    if condition.startswith("not "):
        return not _condition_matches(condition[4:].strip(), metadata)
    if "=" in condition:
        key, expected = (part.strip() for part in condition.split("=", 1))
        return str(metadata.get(key, "")).strip().lower() == expected.lower()
    value = metadata.get(condition)
    return bool(value)
