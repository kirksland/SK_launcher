from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from core.dcc import DccDescriptor, DccHandler, DccOpenContext, get_dcc


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

    def open_scene(self, scene_path: Path, context: DccOpenContext) -> None:
        os.startfile(str(scene_path))  # type: ignore[attr-defined]


def build_blender_handler() -> BlenderDccHandler:
    descriptor = get_dcc("blender")
    if descriptor is None:
        raise RuntimeError("Blender DCC descriptor is not registered.")
    return BlenderDccHandler(descriptor)

