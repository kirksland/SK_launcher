from __future__ import annotations

from typing import Any, Callable

from tools.board_tools.registry import discover_board_tools


ToolApplyFn = Callable[[object, dict[str, Any]], object]
_TOOL_REGISTRY: dict[str, ToolApplyFn] = {}
_TOOLS_DISCOVERED = False


def register_tool(tool_id: str, apply_fn: ToolApplyFn) -> None:
    key = str(tool_id or "").strip().lower()
    if not key:
        return
    _TOOL_REGISTRY[key] = apply_fn


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


def extract_crop_settings(stack: object) -> tuple[float, float, float, float] | None:
    for entry in normalize_tool_stack(stack):
        if entry.get("id") != "crop":
            continue
        settings = entry.get("settings", {})
        if not isinstance(settings, dict):
            return None
        try:
            left = float(settings.get("left", 0.0))
            top = float(settings.get("top", 0.0))
            right = float(settings.get("right", 0.0))
            bottom = float(settings.get("bottom", 0.0))
        except Exception:
            return None
        return left, top, right, bottom
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


def _discover_tools() -> None:
    global _TOOLS_DISCOVERED
    if _TOOLS_DISCOVERED:
        return
    _TOOLS_DISCOVERED = True
    discover_board_tools()
