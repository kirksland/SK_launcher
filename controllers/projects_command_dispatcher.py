from __future__ import annotations

from pathlib import Path

from core.commands import CommandContext, CommandResult


class ProjectsCommandDispatcher:
    """Executes projects-domain app commands."""

    def __init__(self, projects_controller: object) -> None:
        self.projects = projects_controller

    def execute_command(self, command_id: str, context: CommandContext | None = None) -> CommandResult:
        command_id = str(command_id or "").strip().lower()
        if command_id == "projects.send_to_board":
            return self._send_to_board(command_id, context)
        return CommandResult(command_id, handled=False, message="Unknown projects command.")

    def _send_to_board(self, command_id: str, context: CommandContext | None) -> CommandResult:
        window = getattr(self.projects, "w", None)
        board_controller = getattr(window, "board_controller", None)
        add_paths = getattr(board_controller, "add_paths_from_selection", None)
        if not callable(add_paths):
            return CommandResult(command_id, handled=False, message="Board is unavailable.")
        raw_paths = context.metadata.get("paths") if context is not None else None
        if not isinstance(raw_paths, (list, tuple)):
            return CommandResult(command_id, handled=False, message="No project paths selected.")
        paths = [Path(str(path)) for path in raw_paths if str(path or "").strip()]
        if not paths:
            return CommandResult(command_id, handled=False, message="No project paths selected.")
        add_paths(paths)
        return CommandResult(command_id, handled=True)
