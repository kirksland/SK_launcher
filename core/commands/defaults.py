from __future__ import annotations

from .command import AppCommand
from .registry import CommandRegistry


DEFAULT_APP_COMMANDS: tuple[AppCommand, ...] = (
    AppCommand(
        id="app.command_palette.open",
        label="Open Command Palette",
        domain="app",
        scope="global",
        default_shortcuts=("Ctrl+K",),
    ),
    AppCommand(
        id="board.layout.auto",
        label="Auto Layout",
        domain="board",
        scope="board",
        default_shortcuts=("L",),
    ),
    AppCommand(
        id="board.view.fit",
        label="Fit Board View",
        domain="board",
        scope="board",
        default_shortcuts=("F",),
    ),
    AppCommand(
        id="board.view.toggle_grid",
        label="Toggle Board Grid",
        domain="board",
        scope="board",
        default_shortcuts=("G",),
    ),
    AppCommand(
        id="board.group.create",
        label="Group Selection",
        domain="board",
        scope="board",
        default_shortcuts=("Ctrl+G",),
    ),
    AppCommand(
        id="board.group.ungroup",
        label="Ungroup Selection",
        domain="board",
        scope="board",
        default_shortcuts=("Ctrl+Shift+G",),
    ),
    AppCommand(
        id="board.focus.exit",
        label="Exit Board Focus",
        domain="board",
        scope="board.focus",
        default_shortcuts=("Escape",),
    ),
)


def create_default_command_registry() -> CommandRegistry:
    return CommandRegistry(DEFAULT_APP_COMMANDS)
