from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Callable


ToolApplyFn = Callable[[object, dict[str, Any]], object]
_TOOL_REGISTRY: dict[str, ToolApplyFn] = {}
_TOOLS_DISCOVERED = False


def register_tool(tool_id: str, apply_fn: ToolApplyFn) -> None:
    key = str(tool_id or "").strip().lower()
    if not key:
        return
    _TOOL_REGISTRY[key] = apply_fn


def _discover_tools() -> None:
    global _TOOLS_DISCOVERED
    if _TOOLS_DISCOVERED:
        return
    _TOOLS_DISCOVERED = True
    pkg_name = "tools.image_tools"
    pkg_dir = Path(__file__).resolve().parent
    for mod in pkgutil.iter_modules([str(pkg_dir)]):
        name = str(mod.name)
        if name.startswith("_") or name in {"registry", "base"}:
            continue
        try:
            importlib.import_module(f"{pkg_name}.{name}")
        except Exception:
            # Keep app resilient if one plugin fails to import.
            continue


def build_bcs_stack(brightness: float, contrast: float, saturation: float) -> list[dict[str, Any]]:
    return [
        {
            "id": "bcs",
            "enabled": True,
            "settings": {
                "brightness": float(brightness),
                "contrast": float(contrast),
                "saturation": float(saturation),
            },
        }
    ]


def normalize_tool_stack(stack: object) -> list[dict[str, Any]]:
    if not isinstance(stack, list):
        return []
    normalized: list[dict[str, Any]] = []
    for entry in stack:
        if not isinstance(entry, dict):
            continue
        tool_id = str(entry.get("id", "")).strip().lower()
        if not tool_id:
            continue
        normalized.append(
            {
                "id": tool_id,
                "enabled": bool(entry.get("enabled", True)),
                "settings": dict(entry.get("settings", {})) if isinstance(entry.get("settings"), dict) else {},
            }
        )
    return normalized


def extract_bcs_settings(stack: object) -> tuple[float, float, float] | None:
    for entry in normalize_tool_stack(stack):
        if entry.get("id") != "bcs":
            continue
        settings = entry.get("settings", {})
        if not isinstance(settings, dict):
            return None
        try:
            brightness = float(settings.get("brightness", 0.0))
            contrast = float(settings.get("contrast", 1.0))
            saturation = float(settings.get("saturation", 1.0))
        except Exception:
            return None
        return brightness, contrast, saturation
    return None


def apply_image_tool_stack(rgb: object, stack: object) -> object:
    _discover_tools()
    output = rgb
    for entry in normalize_tool_stack(stack):
        if not bool(entry.get("enabled", True)):
            continue
        tool_id = str(entry.get("id", "")).strip().lower()
        apply_fn = _TOOL_REGISTRY.get(tool_id)
        if apply_fn is None:
            continue
        settings = entry.get("settings", {})
        if not isinstance(settings, dict):
            settings = {}
        output = apply_fn(output, settings)
    return output

