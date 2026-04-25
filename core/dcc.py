from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Protocol


@dataclass(frozen=True)
class DccDescriptor:
    id: str
    label: str
    extensions: tuple[str, ...]
    default_filename: str


@dataclass(frozen=True)
class DccOpenContext:
    project_path: Path
    launcher_root: Path
    use_file_association: bool = True
    executable: str = ""


class DccHandler(Protocol):
    descriptor: DccDescriptor

    def supports_path(self, path: Path) -> bool: ...

    def default_scene_filename(self, project_name: str) -> str: ...

    def open_scene(self, scene_path: Path, context: DccOpenContext) -> None: ...


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
_HANDLER_FACTORIES: Dict[str, Callable[[], DccHandler]] = {}
_HANDLER_CACHE: Dict[str, DccHandler] = {}
_BUILTINS_REGISTERED = False


def _ensure_builtin_handlers() -> None:
    global _BUILTINS_REGISTERED
    if _BUILTINS_REGISTERED:
        return
    _BUILTINS_REGISTERED = True
    from core.dcc_handlers.blender import build_blender_handler
    from core.dcc_handlers.houdini import build_houdini_handler

    register_dcc_handler("houdini", build_houdini_handler)
    register_dcc_handler("blender", build_blender_handler)


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


def register_dcc_handler(dcc_id: str, factory: Callable[[], DccHandler]) -> None:
    token = str(dcc_id).strip().lower()
    if not token:
        raise ValueError("DCC handler id cannot be empty.")
    if token not in _DCC_BY_ID:
        raise ValueError(f"Unknown DCC id: {dcc_id}")
    _HANDLER_FACTORIES[token] = factory
    _HANDLER_CACHE.pop(token, None)


def get_dcc_handler(dcc_id: str) -> Optional[DccHandler]:
    _ensure_builtin_handlers()
    token = str(dcc_id).strip().lower()
    if not token:
        return None
    cached = _HANDLER_CACHE.get(token)
    if cached is not None:
        return cached
    factory = _HANDLER_FACTORIES.get(token)
    if factory is None:
        return None
    handler = factory()
    _HANDLER_CACHE[token] = handler
    return handler


def handler_for_path(path: Path) -> Optional[DccHandler]:
    descriptor = detect_dcc_for_path(path)
    if descriptor is None:
        return None
    return get_dcc_handler(descriptor.id)


def open_scene_with_dcc(scene_path: Path, context: DccOpenContext) -> None:
    handler = handler_for_path(scene_path)
    if handler is None:
        raise RuntimeError(f"Unsupported scene file: {scene_path.name}")
    handler.open_scene(scene_path, context)

