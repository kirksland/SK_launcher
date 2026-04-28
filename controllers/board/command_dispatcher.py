from __future__ import annotations

from PySide6 import QtWidgets

from core.commands import CommandContext, CommandResult


class BoardCommandDispatcher:
    """Executes board-domain app commands."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller

    def execute_command(self, command_id: str, context: CommandContext | None = None) -> CommandResult:
        command_id = str(command_id or "").strip().lower()
        if command_id == "board.add.image":
            return self._execute(command_id, "add_image")
        if command_id == "board.add.video":
            return self._execute(command_id, "add_video")
        if command_id == "board.add.sequence":
            return self._execute(command_id, "add_sequence")
        if command_id == "board.add.note":
            return self._add_note(command_id, context)
        if command_id == "board.media.convert_picnc":
            return self._convert_picnc(command_id, context)
        if command_id == "board.media.convert_video_to_sequence":
            return self._convert_video_to_sequence(command_id, context)
        if command_id == "board.layout.auto":
            return self._execute(command_id, "layout_selection_grid")
        if command_id == "board.view.fit":
            return self._execute(command_id, "fit_view")
        if command_id == "board.view.toggle_grid":
            return self._toggle_grid(command_id)
        if command_id == "board.group.toggle":
            return self._execute(command_id, "toggle_group_selection")
        if command_id == "board.group.create":
            return self._execute(command_id, "add_group")
        if command_id == "board.group.add_selected_to_group":
            return self._add_selected_to_group(command_id, context)
        if command_id == "board.group.ungroup":
            self._select_tree_info_target(context)
            return self._execute(command_id, "ungroup_selected")
        if command_id == "board.group.remove_selected":
            self._select_tree_info_target(context)
            return self._execute(command_id, "remove_selected_from_groups")
        if command_id == "board.item.open":
            return self._open_item(command_id, context)
        if command_id == "board.item.rename":
            return self._rename_item(command_id, context)
        if command_id == "board.path.copy":
            return self._copy_path(command_id, context)
        if command_id == "board.focus.exit":
            return self._execute(command_id, "exit_focus_mode")
        return CommandResult(command_id, handled=False, message="Unknown board command.")

    def _execute(self, command_id: str, method_name: str) -> CommandResult:
        method = getattr(self.board, method_name, None)
        if not callable(method):
            return CommandResult(command_id, handled=False, message=f"Missing board method: {method_name}")
        method()
        return CommandResult(command_id, handled=True)

    def _add_note(self, command_id: str, context: CommandContext | None) -> CommandResult:
        method = getattr(self.board, "add_note_at", None)
        if not callable(method):
            return CommandResult(command_id, handled=False, message="Missing board method: add_note_at")
        scene_pos = None
        if context is not None:
            scene_pos = context.metadata.get("scene_pos")
        method(scene_pos)
        return CommandResult(command_id, handled=True)

    def _convert_picnc(self, command_id: str, context: CommandContext | None) -> CommandResult:
        method = getattr(self.board, "convert_picnc_interactive", None)
        if not callable(method):
            return CommandResult(command_id, handled=False, message="Missing board method: convert_picnc_interactive")
        src_path = context.metadata.get("path") if context is not None else None
        if src_path:
            method(src_path)
        else:
            method()
        return CommandResult(command_id, handled=True)

    def _convert_video_to_sequence(self, command_id: str, context: CommandContext | None) -> CommandResult:
        method = getattr(self.board, "convert_video_to_sequence", None)
        if not callable(method):
            return CommandResult(command_id, handled=False, message="Missing board method: convert_video_to_sequence")
        item = context.metadata.get("item") if context is not None else None
        if item is None:
            return CommandResult(command_id, handled=False, message="No video item selected.")
        method(item)
        return CommandResult(command_id, handled=True)

    def _add_selected_to_group(self, command_id: str, context: CommandContext | None) -> CommandResult:
        method = getattr(self.board, "add_selected_to_group", None)
        if not callable(method):
            return CommandResult(command_id, handled=False, message="Missing board method: add_selected_to_group")
        group_key = context.metadata.get("group_key") if context is not None else None
        if group_key is None:
            return CommandResult(command_id, handled=False, message="No group selected.")
        method(int(group_key))
        return CommandResult(command_id, handled=True)

    def _open_item(self, command_id: str, context: CommandContext | None) -> CommandResult:
        if context is None:
            return CommandResult(command_id, handled=False, message="No item selected.")
        item = context.metadata.get("item")
        kind = str(context.metadata.get("kind", ""))
        if item is None:
            return CommandResult(command_id, handled=False, message="Item not found.")
        if kind == "image":
            return self._execute_with_arg(command_id, "open_image_item", item)
        if kind in ("video", "sequence"):
            return self._execute_with_arg(command_id, "open_media_item", item)
        if kind == "note":
            return self._execute_with_arg(command_id, "edit_note", item)
        return CommandResult(command_id, handled=False, message="Unsupported board item.")

    def _rename_item(self, command_id: str, context: CommandContext | None) -> CommandResult:
        method = getattr(self.board, "begin_group_tree_rename", None)
        if not callable(method):
            return CommandResult(command_id, handled=False, message="Missing board method: begin_group_tree_rename")
        if context is None:
            return CommandResult(command_id, handled=False, message="No tree item selected.")
        tree_item = context.metadata.get("tree_item")
        info = context.metadata.get("info")
        if tree_item is None or info is None:
            return CommandResult(command_id, handled=False, message="No tree item selected.")
        method(tree_item, info)
        return CommandResult(command_id, handled=True)

    def _copy_path(self, command_id: str, context: CommandContext | None) -> CommandResult:
        path = context.metadata.get("path") if context is not None else None
        if path is None:
            return CommandResult(command_id, handled=False, message="No path selected.")
        QtWidgets.QApplication.clipboard().setText(str(path))
        notify = getattr(self.board, "_notify", None)
        if callable(notify):
            notify(f"Copied: {path}")
        return CommandResult(command_id, handled=True)

    def _select_tree_info_target(self, context: CommandContext | None) -> None:
        if context is None:
            return
        info = context.metadata.get("info")
        method = getattr(self.board, "_select_tree_info_target", None)
        if info is not None and callable(method):
            method(info)

    def _execute_with_arg(self, command_id: str, method_name: str, arg: object) -> CommandResult:
        method = getattr(self.board, method_name, None)
        if not callable(method):
            return CommandResult(command_id, handled=False, message=f"Missing board method: {method_name}")
        method(arg)
        return CommandResult(command_id, handled=True)

    def _toggle_grid(self, command_id: str) -> CommandResult:
        page = getattr(getattr(self.board, "w", None), "board_page", None)
        toggle = getattr(page, "grid_toggle", None)
        if toggle is None or not callable(getattr(toggle, "setChecked", None)):
            return CommandResult(command_id, handled=False, message="Board grid toggle is unavailable.")
        toggle.setChecked(not bool(toggle.isChecked()))
        return CommandResult(command_id, handled=True)
