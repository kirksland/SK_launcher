from __future__ import annotations

from typing import Any

from tools.edit_tools import get_edit_tool
from tools.image_tools.registry import normalize_tool_stack
from .handles import sanitize_crop


def make_tool_entry(tool_id: str) -> dict[str, object]:
    spec = get_edit_tool(tool_id)
    if spec is None:
        return {}
    return {
        "id": spec.id,
        "enabled": True,
        "settings": dict(spec.default_state()),
    }


def normalize_tool_entry(entry: object) -> dict[str, object]:
    if not isinstance(entry, dict):
        return {}
    tool_id = str(entry.get("id", "")).strip().lower()
    spec = get_edit_tool(tool_id)
    if spec is None:
        return {}
    return {
        "id": spec.id,
        "enabled": bool(entry.get("enabled", True)),
        "settings": dict(spec.normalize_state(entry.get("settings", {}))),
    }


def normalize_tool_entries(stack: object) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for entry in normalize_tool_stack(stack):
        clean = normalize_tool_entry(entry)
        if clean:
            normalized.append(clean)
    return normalized


def find_tool_entry(stack: object, tool_id: str) -> dict[str, object] | None:
    key = str(tool_id or "").strip().lower()
    if not key:
        return None
    for entry in normalize_tool_entries(stack):
        if str(entry.get("id", "")).strip().lower() == key:
            return entry
    return None


def get_tool_settings(stack: object, tool_id: str) -> dict[str, Any] | None:
    entry = find_tool_entry(stack, tool_id)
    if entry is None:
        return None
    settings = entry.get("settings", {})
    return dict(settings) if isinstance(settings, dict) else None


def extract_bcs_settings(stack: object) -> tuple[float, float, float] | None:
    settings = get_tool_settings(stack, "bcs")
    if settings is None:
        return None
    try:
        brightness = float(settings.get("brightness", 0.0))
        contrast = float(settings.get("contrast", 1.0))
        saturation = float(settings.get("saturation", 1.0))
    except Exception:
        return None
    return brightness, contrast, saturation


def extract_crop_settings(stack: object) -> tuple[float, float, float, float] | None:
    settings = get_tool_settings(stack, "crop")
    if settings is None:
        return None
    try:
        return sanitize_crop(
            settings.get("left", 0.0),
            settings.get("top", 0.0),
            settings.get("right", 0.0),
            settings.get("bottom", 0.0),
        )
    except Exception:
        return None


def tool_entry_is_effective(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    tool_id = str(entry.get("id", "")).strip().lower()
    spec = get_edit_tool(tool_id)
    if spec is None:
        return bool(entry.get("enabled", True))
    settings = entry.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}
    return spec.is_effective(settings)


def tool_stack_is_effective(stack: object) -> bool:
    tools = normalize_tool_entries(stack)
    if not tools:
        return False
    return any(tool_entry_is_effective(entry) for entry in tools)


def append_tool(stack: object, tool_id: str) -> tuple[list[dict[str, object]], int]:
    entries = normalize_tool_entries(stack)
    new_entry = make_tool_entry(tool_id)
    if not new_entry:
        return entries, -1
    entries.append(new_entry)
    return entries, len(entries) - 1


def remove_tool_at(stack: object, index: int) -> tuple[list[dict[str, object]], int]:
    entries = normalize_tool_entries(stack)
    if index < 0 or index >= len(entries):
        return entries, -1 if not entries else 0
    entries.pop(index)
    if not entries:
        return entries, -1
    return entries, max(0, min(index, len(entries) - 1))


def move_tool(stack: object, index: int, delta: int) -> tuple[list[dict[str, object]], int]:
    entries = normalize_tool_entries(stack)
    target = int(index) + int(delta)
    if index < 0 or index >= len(entries) or target < 0 or target >= len(entries):
        return entries, index if entries else -1
    entries[index], entries[target] = entries[target], entries[index]
    return entries, target


def upsert_tool_settings(
    stack: object,
    tool_id: str,
    settings_update: dict[str, Any],
    *,
    add_if_missing: bool = True,
    insert_at: int | None = None,
) -> tuple[list[dict[str, object]], int]:
    entries = normalize_tool_entries(stack)
    key = str(tool_id or "").strip().lower()
    for idx, entry in enumerate(entries):
        if str(entry.get("id", "")).strip().lower() != key:
            continue
        settings = entry.get("settings", {})
        if not isinstance(settings, dict):
            settings = {}
        settings.update(settings_update)
        entry["settings"] = settings
        clean = normalize_tool_entry(entry)
        entries[idx] = clean if clean else entry
        return entries, idx
    if not add_if_missing:
        return entries, -1 if not entries else 0
    new_entry = make_tool_entry(key)
    if not new_entry:
        return entries, -1 if not entries else 0
    settings = new_entry.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}
    settings.update(settings_update)
    new_entry["settings"] = settings
    new_entry = normalize_tool_entry(new_entry) or new_entry
    if insert_at is None or insert_at < 0 or insert_at > len(entries):
        entries.append(new_entry)
        return entries, len(entries) - 1
    entries.insert(insert_at, new_entry)
    return entries, insert_at
