from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.dcc import DccCreateContext, DccCreateResult, DccDescriptor, DccHandler, DccOpenContext, get_dcc
from core.houdini_env import build_houdini_env
from core.project_runtime import ensure_job_scripts, ensure_template_hip


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
        target, error = ensure_template_hip(
            context.project_path,
            pattern=context.filename_pattern or self.descriptor.default_filename,
            custom_template=context.template_path,
            default_template=context.default_template_path,
            launcher_root=context.launcher_root,
        )
        if error:
            return DccCreateResult(None, error)
        if target is not None and context.ensure_runtime_scripts:
            ensure_job_scripts(context.project_path)
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
