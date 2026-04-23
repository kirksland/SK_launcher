from __future__ import annotations

from core.commands import CommandContext, CommandResult


class BoardCommandDispatcher:
    """Executes board-domain app commands."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller

    def execute_command(self, command_id: str, context: CommandContext | None = None) -> CommandResult:
        command_id = str(command_id or "").strip().lower()
        if command_id == "board.layout.auto":
            return self._execute(command_id, "layout_selection_grid")
        if command_id == "board.view.fit":
            return self._execute(command_id, "fit_view")
        if command_id == "board.view.toggle_grid":
            return self._toggle_grid(command_id)
        if command_id == "board.group.create":
            return self._execute(command_id, "add_group")
        if command_id == "board.group.ungroup":
            return self._execute(command_id, "ungroup_selected")
        if command_id == "board.focus.exit":
            return self._execute(command_id, "exit_focus_mode")
        return CommandResult(command_id, handled=False, message="Unknown board command.")

    def _execute(self, command_id: str, method_name: str) -> CommandResult:
        method = getattr(self.board, method_name, None)
        if not callable(method):
            return CommandResult(command_id, handled=False, message=f"Missing board method: {method_name}")
        method()
        return CommandResult(command_id, handled=True)

    def _toggle_grid(self, command_id: str) -> CommandResult:
        page = getattr(getattr(self.board, "w", None), "board_page", None)
        toggle = getattr(page, "grid_toggle", None)
        if toggle is None or not callable(getattr(toggle, "setChecked", None)):
            return CommandResult(command_id, handled=False, message="Board grid toggle is unavailable.")
        toggle.setChecked(not bool(toggle.isChecked()))
        return CommandResult(command_id, handled=True)
