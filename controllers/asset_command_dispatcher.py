from __future__ import annotations

from pathlib import Path

from PySide6 import QtWidgets

from core.commands import CommandContext, CommandResult
from core.dcc_handlers.blender import convert_obj_to_fbx


class AssetCommandDispatcher:
    """Executes asset-manager domain app commands."""

    def __init__(self, asset_controller: object) -> None:
        self.asset = asset_controller

    def execute_command(self, command_id: str, context: CommandContext | None = None) -> CommandResult:
        command_id = str(command_id or "").strip().lower()
        if command_id == "asset.copy_path":
            return self._copy_path(command_id, context)
        if command_id == "asset.convert_obj_to_fbx":
            return self._convert_obj_to_fbx(command_id, context)
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

    def _convert_obj_to_fbx(self, command_id: str, context: CommandContext | None) -> CommandResult:
        path_text = context.metadata.get("path") if context is not None else None
        if not path_text:
            return CommandResult(command_id, handled=False, message="No OBJ file selected.")
        source = Path(str(path_text))
        if source.suffix.lower() != ".obj":
            return CommandResult(command_id, handled=False, message="Selected file is not an OBJ.")

        window = getattr(self.asset, "w", None)
        blender_exe = str(getattr(window, "_blender_exe", "") or "").strip()
        set_status = getattr(self.asset, "set_asset_status", None)
        if callable(set_status):
            set_status(f"Converting OBJ to FBX with Blender: {source.name}")

        result = convert_obj_to_fbx(
            source,
            executable=blender_exe,
            launcher_root=Path(__file__).resolve().parents[1],
        )
        if result.error:
            if callable(set_status):
                set_status(result.error)
            return CommandResult(command_id, handled=False, message=result.error)

        output = result.output_path
        output_text = str(output) if output is not None else ""
        normalizer = getattr(window, "_to_houdini_path", None)
        normalized = normalizer(output_text) if callable(normalizer) else output_text
        if callable(set_status):
            set_status(f"Converted FBX: {normalized}")
        refresh = getattr(self.asset, "_load_entity_details", None)
        current_entity = getattr(window, "_asset_current_entity", None)
        if callable(refresh) and current_entity:
            refresh(Path(current_entity), getattr(window, "_asset_current_entity_type", None))
        return CommandResult(command_id, handled=True, message=output_text)
