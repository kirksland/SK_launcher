from __future__ import annotations

from typing import Any, Iterable

from tools.edit_tools import get_edit_tool, list_edit_tools

from .tool_stack import get_tool_settings


def _filter_spec_state(spec: Any, state: dict[str, Any]) -> dict[str, Any]:
    keys = tuple(str(key).strip() for key in getattr(spec, "ui_settings_keys", ()) if str(key).strip())
    if not keys:
        return dict(state)
    return {key: state[key] for key in keys if key in state}


def default_panel_state(tool_id: str) -> dict[str, Any]:
    spec = get_edit_tool(tool_id)
    if spec is None:
        return {}
    return _filter_spec_state(spec, spec.default_state())


def normalize_panel_state(tool_id: str, state: object) -> dict[str, Any]:
    spec = get_edit_tool(tool_id)
    if spec is None:
        return {}
    normalized = spec.normalize_state(state)
    return _filter_spec_state(spec, normalized if isinstance(normalized, dict) else {})


def panel_state_for_tool(tool_id: str, stack: object) -> dict[str, Any]:
    settings = get_tool_settings(stack, tool_id)
    if settings is None:
        return default_panel_state(tool_id)
    return normalize_panel_state(tool_id, settings)


def panel_state_map_for_tools(tool_ids: Iterable[str], stack: object) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for tool_id in tool_ids:
        spec = get_edit_tool(tool_id)
        if spec is None:
            continue
        panel = str(getattr(spec, "ui_panel", "") or "").strip().lower()
        if not panel:
            continue
        result[panel] = panel_state_for_tool(tool_id, stack)
    return result


def tool_spec_for_panel(panel: str) -> Any | None:
    key = str(panel or "").strip().lower()
    if not key:
        return None
    for spec in list_edit_tools():
        if str(getattr(spec, "ui_panel", "") or "").strip().lower() == key:
            return spec
    return None
