from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.dcc import DccCreateContext, DccCreateResult, DccDescriptor, DccHandler, DccOpenContext, get_dcc
from core.houdini_env import build_houdini_env, resolve_hython_executable


@dataclass(frozen=True)
class HoudiniDccHandler(DccHandler):
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

        hython_executable = resolve_hython_executable(context.executable)
        if not hython_executable:
            return DccCreateResult(
                None,
                "Could not resolve a valid hython executable. Configure Houdini in Settings before creating a Houdini scene.",
            )

        env = build_houdini_env(
            base_env=os.environ,
            project_path=context.project_path,
            launcher_root=context.launcher_root,
        )
        command = [
            hython_executable,
            "-c",
            (
                "import hou, sys; "
                "target = sys.argv[1]; "
                "hou.hipFile.clear(suppress_save_prompt=True); "
                "hou.hipFile.save(file_name=target)"
            ),
            str(target),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(context.launcher_root),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            return DccCreateResult(None, f"Failed to launch hython for scene creation:\n{exc}")
        if completed.returncode != 0:
            message = str(completed.stderr or completed.stdout or "").strip()
            if not message:
                message = f"hython exited with code {completed.returncode}."
            return DccCreateResult(None, f"Failed to create Houdini scene:\n{message}")
        if not target.exists():
            return DccCreateResult(None, "Houdini scene creation completed, but no scene file was written.")
        return DccCreateResult(target, "")

    def open_scene(self, scene_path: Path, context: DccOpenContext) -> None:
        if context.use_file_association or not context.executable:
            os.startfile(str(scene_path))  # type: ignore[attr-defined]
            return
        env = build_houdini_env(
            base_env=os.environ,
            project_path=context.project_path,
            launcher_root=context.launcher_root,
        )
        subprocess.Popen([context.executable, str(scene_path)], env=env)


def build_houdini_handler() -> HoudiniDccHandler:
    descriptor = get_dcc("houdini")
    if descriptor is None:
        raise RuntimeError("Houdini DCC descriptor is not registered.")
    return HoudiniDccHandler(descriptor)
