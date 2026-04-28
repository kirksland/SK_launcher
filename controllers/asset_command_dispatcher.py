from __future__ import annotations

from PySide6 import QtWidgets

from core.commands import CommandContext, CommandResult


class AssetCommandDispatcher:
    """Executes asset-manager domain app commands."""

    def __init__(self, asset_controller: object) -> None:
        self.asset = asset_controller

    def execute_command(self, command_id: str, context: CommandContext | None = None) -> CommandResult:
        command_id = str(command_id or "").strip().lower()
        if command_id == "asset.copy_path":
            return self._copy_path(command_id, context)
        return CommandResult(command_id, handled=False, message="Unknown asset command.")

    def _copy_path(self, command_id: str, context: CommandContext | None) -> CommandResult:
        path_text = context.metadata.get("path") if context is not None else None
        if not path_text:
            return CommandResult(command_id, handled=False, message="No asset path selected.")
        window = getattr(self.asset, "w", None)
        normalizer = getattr(window, "_to_houdini_path", None)
        normalized = normalizer(str(path_text)) if callable(normalizer) else str(path_text)
        QtWidgets.QApplication.clipboard().setText(normalized)
        set_status = getattr(self.asset, "set_asset_status", None)
        if callable(set_status):
            set_status(f"Copied: {normalized}")
        return CommandResult(command_id, handled=True)
