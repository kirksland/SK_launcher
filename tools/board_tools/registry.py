from __future__ import annotations

import importlib
import pkgutil
import sys
from dataclasses import dataclass
from pathlib import Path

@dataclass(slots=True, frozen=True)
class BoardToolCapabilities:
    tool_id: str
    package_name: str
    has_tool: bool
    has_image: bool
    has_scene: bool


_BOARD_TOOLS_DISCOVERED = False
_BOARD_TOOL_CAPABILITIES: dict[str, BoardToolCapabilities] = {}


def discover_board_tools(force: bool = False) -> dict[str, BoardToolCapabilities]:
    global _BOARD_TOOLS_DISCOVERED
    if _BOARD_TOOLS_DISCOVERED and not force:
        return dict(_BOARD_TOOL_CAPABILITIES)
    if force:
        _BOARD_TOOL_CAPABILITIES.clear()
        _BOARD_TOOLS_DISCOVERED = False

    pkg_name = "tools.board_tools"
    pkg_dir = Path(__file__).resolve().parent
    if not pkg_dir.exists():
        return {}

    for mod in pkgutil.iter_modules([str(pkg_dir)]):
        name = str(mod.name)
        if name.startswith("_") or name in {"registry", "base", "edit", "image"}:
            continue
        package_name = f"{pkg_name}.{name}"
        package = _import_or_reload(package_name, force=force)
        if package is None:
            continue
        has_tool = _import_or_reload(f"{package_name}.tool", force=force) is not None
        has_image = _import_or_reload(f"{package_name}.image", force=force) is not None
        has_scene = _import_or_reload(f"{package_name}.scene", force=force) is not None
        _BOARD_TOOL_CAPABILITIES[name] = BoardToolCapabilities(
            tool_id=name,
            package_name=package_name,
            has_tool=has_tool,
            has_image=has_image,
            has_scene=has_scene,
        )

    _BOARD_TOOLS_DISCOVERED = True
    return dict(_BOARD_TOOL_CAPABILITIES)


def list_board_tools() -> list[BoardToolCapabilities]:
    return sorted(discover_board_tools().values(), key=lambda spec: spec.tool_id)


def get_board_tool(tool_id: str) -> BoardToolCapabilities | None:
    discover_board_tools()
    return _BOARD_TOOL_CAPABILITIES.get(str(tool_id or "").strip().lower())


def get_board_tool_scene_module(tool_id: str) -> object | None:
    spec = get_board_tool(tool_id)
    if spec is None or not spec.has_scene:
        return None
    return _import_or_reload(f"{spec.package_name}.scene", force=False)


def get_board_tool_scene_runtime(tool_id: str) -> BoardToolSceneRuntime | None:
    module = get_board_tool_scene_module(tool_id)
    runtime = getattr(module, "SCENE_RUNTIME", None) if module is not None else None
    return runtime if _is_scene_runtime(runtime) else None


def _import_or_reload(module_name: str, *, force: bool) -> object | None:
    try:
        if force and module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)
    except Exception:
        return None


def _is_scene_runtime(runtime: object) -> bool:
    required_attrs = (
        "refresh_handles",
        "clear_handles",
        "panel_value_changed",
        "mouse_press",
        "mouse_move",
        "mouse_release",
    )
    return all(callable(getattr(runtime, attr, None)) for attr in required_attrs)
