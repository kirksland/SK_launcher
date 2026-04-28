from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
import json

from core.dcc import DccCreateContext, DccCreateResult, DccDescriptor, DccHandler, DccOpenContext, get_dcc


@dataclass(frozen=True)
class BlenderDccHandler(DccHandler):
    descriptor: DccDescriptor

    def supports_path(self, path: Path) -> bool:
        return path.suffix.lower() in self.descriptor.extensions

    def default_scene_filename(self, project_name: str) -> str:
        try:
            return self.descriptor.default_filename.format(projectName=project_name)
        except Exception:
            return f"{project_name}_001{self.descriptor.extensions[0]}"

    def create_scene(self, context: DccCreateContext) -> DccCreateResult:
        filename = Path(
            str(context.filename_pattern or self.default_scene_filename(context.project_path.name)).strip()
        ).name
        if not filename:
            return DccCreateResult(None, "Scene name cannot be empty.")
        target = context.project_path / filename
        if target.exists():
            return DccCreateResult(target, "")

        executable = _resolve_blender_executable(context.executable)
        if not executable:
            return DccCreateResult(
                None,
                "Could not resolve a valid Blender executable. Configure Blender in Settings before creating a Blender scene.",
            )

        expression = (
            "import bpy; "
            "bpy.ops.wm.read_homefile(use_empty=True); "
            f"bpy.ops.wm.save_as_mainfile(filepath={json.dumps(str(target))})"
        )
        command = [
            executable,
            "--background",
            "--factory-startup",
            "--python-expr",
            expression,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(context.launcher_root),
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            return DccCreateResult(None, f"Failed to launch Blender for scene creation:\n{exc}")
        if completed.returncode != 0:
            message = str(completed.stderr or completed.stdout or "").strip()
            if not message:
                message = f"Blender exited with code {completed.returncode}."
            return DccCreateResult(None, f"Failed to create Blender scene:\n{message}")
        if not target.exists():
            return DccCreateResult(None, "Blender scene creation completed, but no scene file was written.")
        return DccCreateResult(target, "")

    def open_scene(self, scene_path: Path, context: DccOpenContext) -> None:
        if not context.use_file_association and context.executable:
            subprocess.Popen([context.executable, str(scene_path)])
            return
        os.startfile(str(scene_path))  # type: ignore[attr-defined]


def _resolve_blender_executable(executable: str) -> str:
    raw = str(executable or "").strip()
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.exists():
        if candidate.name.lower() == "blender.exe":
            return str(candidate)
        return ""
    token = raw.lower()
    if token in {"blender", "blender.exe"}:
        return shutil.which("blender") or shutil.which("blender.exe") or ""
    which_value = shutil.which(raw)
    if which_value and Path(which_value).name.lower() in {"blender", "blender.exe"}:
        return which_value
    return ""


def build_blender_handler() -> BlenderDccHandler:
    descriptor = get_dcc("blender")
    if descriptor is None:
        raise RuntimeError("Blender DCC descriptor is not registered.")
    return BlenderDccHandler(descriptor)
