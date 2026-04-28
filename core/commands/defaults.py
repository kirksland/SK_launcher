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
        id="board.add.image",
        label="Add Image...",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.add.video",
        label="Add Video...",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.add.sequence",
        label="Add Image Sequence...",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.add.note",
        label="Add Note",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.media.convert_picnc",
        label="Convert PICNC...",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.media.convert_video_to_sequence",
        label="Convert Video To Sequence",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.layout.auto",
        label="Auto Layout",
        domain="board",
        scope="board",
        default_shortcuts=("I",),
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
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.group.toggle",
        label="Group Or Ungroup Selection",
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
        id="board.group.add_selected_to_group",
        label="Add Selected To Group",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.group.ungroup",
        label="Ungroup Selection",
        domain="board",
        scope="board",
        default_shortcuts=("Ctrl+Shift+G",),
    ),
    AppCommand(
        id="board.group.remove_selected",
        label="Remove From Group",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.item.open",
        label="Open Item",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.item.rename",
        label="Rename...",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.path.copy",
        label="Copy Path",
        domain="board",
        scope="board",
        default_shortcuts=(),
    ),
    AppCommand(
        id="board.focus.exit",
        label="Exit Board Focus",
        domain="board",
        scope="board.focus",
        default_shortcuts=("Escape",),
    ),
    AppCommand(
        id="projects.send_to_board",
        label="Send To Board",
        domain="projects",
        scope="projects",
        default_shortcuts=(),
    ),
    AppCommand(
        id="asset.copy_path",
        label="Copy Path",
        domain="asset",
        scope="asset_manager",
        default_shortcuts=(),
    ),
)


def create_default_command_registry() -> CommandRegistry:
    return CommandRegistry(DEFAULT_APP_COMMANDS)
