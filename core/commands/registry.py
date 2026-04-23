from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .command import AppCommand, normalize_command_id
from .scopes import is_known_scope


@dataclass(frozen=True, slots=True)
class CommandRegistryIssue:
    command_id: str
    code: str
    message: str


class CommandRegistry:
    def __init__(self, commands: Iterable[AppCommand] = ()) -> None:
        self._commands: dict[str, AppCommand] = {}
        for command in commands:
            self.register(command)

    def register(self, command: AppCommand) -> None:
        issues = validate_command(command)
        if issues:
            details = "; ".join(issue.message for issue in issues)
            raise ValueError(details)
        if command.id in self._commands:
            raise ValueError(f"Command id already registered: {command.id}")
        self._commands[command.id] = command

    def get(self, command_id: str) -> AppCommand | None:
        return self._commands.get(normalize_command_id(command_id))

    def require(self, command_id: str) -> AppCommand:
        command = self.get(command_id)
        if command is None:
            raise KeyError(normalize_command_id(command_id))
        return command

    def list(self) -> list[AppCommand]:
        return sorted(self._commands.values(), key=lambda command: command.id)

    def list_by_domain(self, domain: str) -> list[AppCommand]:
        key = str(domain or "").strip().lower()
        return [command for command in self.list() if command.domain == key]

    def list_by_scope(self, scope: str) -> list[AppCommand]:
        key = str(scope or "").strip().lower()
        return [command for command in self.list() if command.scope == key]


def validate_command(command: AppCommand) -> list[CommandRegistryIssue]:
    command_id = command.id or "<missing>"
    issues: list[CommandRegistryIssue] = []
    if not command.id:
        issues.append(CommandRegistryIssue(command_id, "missing_id", "Command id must be non-empty."))
    if not command.label:
        issues.append(CommandRegistryIssue(command_id, "missing_label", "Command label must be non-empty."))
    if not command.domain:
        issues.append(CommandRegistryIssue(command_id, "missing_domain", "Command domain must be non-empty."))
    if not command.scope:
        issues.append(CommandRegistryIssue(command_id, "missing_scope", "Command scope must be non-empty."))
    elif not is_known_scope(command.scope):
        issues.append(
            CommandRegistryIssue(command_id, "unknown_scope", f"Command scope is unknown: {command.scope}")
        )
    if len(set(command.default_shortcuts)) != len(command.default_shortcuts):
        issues.append(
            CommandRegistryIssue(command_id, "duplicate_shortcut", "Command declares duplicate default shortcuts.")
        )
    return issues
