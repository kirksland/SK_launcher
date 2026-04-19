from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class DccDescriptor:
    id: str
    label: str
    extensions: tuple[str, ...]
    default_filename: str


DCCS: tuple[DccDescriptor, ...] = (
    DccDescriptor("houdini", "Houdini", (".hip", ".hiplc", ".hipnc"), "{projectName}_001.hipnc"),
    DccDescriptor("blender", "Blender", (".blend",), "{projectName}_001.blend"),
    DccDescriptor("maya", "Maya", (".ma", ".mb"), "{projectName}_001.ma"),
    DccDescriptor("3dsmax", "3ds Max", (".max",), "{projectName}_001.max"),
    DccDescriptor("cinema4d", "Cinema 4D", (".c4d",), "{projectName}_001.c4d"),
    DccDescriptor("nuke", "Nuke", (".nk",), "{projectName}_001.nk"),
    DccDescriptor("substance_painter", "Substance Painter", (".spp",), "{projectName}_001.spp"),
    DccDescriptor("mari", "Mari", (".mra",), "{projectName}_001.mra"),
)

DEFAULT_NEW_PROJECT_DCC = "houdini"

_DCC_BY_ID: Dict[str, DccDescriptor] = {dcc.id: dcc for dcc in DCCS}
_DCC_BY_EXTENSION: Dict[str, DccDescriptor] = {
    ext: dcc
    for dcc in DCCS
    for ext in dcc.extensions
}


def iter_dccs() -> Iterable[DccDescriptor]:
    return DCCS


def get_dcc(dcc_id: str) -> Optional[DccDescriptor]:
    return _DCC_BY_ID.get(str(dcc_id).strip().lower())


def detect_dcc_for_path(path: Path) -> Optional[DccDescriptor]:
    return _DCC_BY_EXTENSION.get(path.suffix.lower())


def is_supported_scene_file(path: Path) -> bool:
    return detect_dcc_for_path(path) is not None


def supported_scene_extensions() -> tuple[str, ...]:
    return tuple(_DCC_BY_EXTENSION.keys())


def default_scene_filename(project_name: str, dcc_id: str) -> str:
    descriptor = get_dcc(dcc_id) or get_dcc(DEFAULT_NEW_PROJECT_DCC)
    if descriptor is None:
        return f"{project_name}_001.hipnc"
    try:
        return descriptor.default_filename.format(projectName=project_name)
    except Exception:
        return f"{project_name}_001{descriptor.extensions[0]}"
