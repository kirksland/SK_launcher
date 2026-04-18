from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from .base import EditToolSpec


_TOOL_REGISTRY: dict[str, EditToolSpec] = {}
_TOOLS_DISCOVERED = False


def register_edit_tool(spec: EditToolSpec) -> None:
    tool_id = str(getattr(spec, "id", "") or "").strip().lower()
    if not tool_id:
        return
    _TOOL_REGISTRY[tool_id] = spec


def discover_edit_tools(force: bool = False) -> dict[str, EditToolSpec]:
    global _TOOLS_DISCOVERED
    if _TOOLS_DISCOVERED and not force:
        return dict(_TOOL_REGISTRY)
    if force:
        _TOOL_REGISTRY.clear()
        _TOOLS_DISCOVERED = False
    pkg_name = "tools.edit_tools"
    pkg_dir = Path(__file__).resolve().parent
    for mod in pkgutil.iter_modules([str(pkg_dir)]):
        name = str(mod.name)
        if name.startswith("_") or name in {"base", "registry"}:
            continue
        module_name = f"{pkg_name}.{name}"
        try:
            importlib.import_module(module_name)
        except Exception:
            continue
        try:
            importlib.import_module(f"{module_name}.tool")
        except Exception:
            continue
    _TOOLS_DISCOVERED = True
    return dict(_TOOL_REGISTRY)


def list_edit_tools() -> list[EditToolSpec]:
    discover_edit_tools()
    return sorted(
        _TOOL_REGISTRY.values(),
        key=lambda spec: (int(getattr(spec, "order", 100)), str(spec.label).lower(), str(spec.id)),
    )


def available_tools_for_kind(media_kind: str) -> list[EditToolSpec]:
    return [spec for spec in list_edit_tools() if spec.supports_kind(media_kind)]


def get_edit_tool(tool_id: str) -> EditToolSpec | None:
    discover_edit_tools()
    return _TOOL_REGISTRY.get(str(tool_id or "").strip().lower())

