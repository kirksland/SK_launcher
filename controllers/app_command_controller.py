from __future__ import annotations

from typing import Protocol

from core.commands import CommandContext, CommandRegistry, CommandResult, create_default_command_registry


class CommandDomainDispatcher(Protocol):
    def execute_command(self, command_id: str, context: CommandContext | None = None) -> CommandResult: ...


class AppCommandController:
    """Routes app commands to domain-specific dispatchers."""

    def __init__(self, registry: CommandRegistry | None = None) -> None:
        self.registry = registry or create_default_command_registry()
        self._dispatchers: dict[str, CommandDomainDispatcher] = {}

    def register_dispatcher(self, domain: str, dispatcher: CommandDomainDispatcher) -> None:
        key = str(domain or "").strip().lower()
        if not key:
            raise ValueError("Command dispatcher domain must be non-empty.")
        self._dispatchers[key] = dispatcher

    def has_dispatcher(self, domain: str) -> bool:
        return str(domain or "").strip().lower() in self._dispatchers

    def execute(self, command_id: str, context: CommandContext | None = None) -> CommandResult:
        command = self.registry.get(command_id)
        if command is None:
            return CommandResult(command_id, handled=False, message="Unknown command.")
        dispatcher = self._dispatchers.get(command.domain)
        if dispatcher is None:
            return CommandResult(command.id, handled=False, message=f"No dispatcher for domain: {command.domain}")
        return dispatcher.execute_command(command.id, context=context)
