from __future__ import annotations

from uuid import uuid4
from typing import Any

from tools.board_tools.edit import get_edit_tool
from tools.board_tools.image import normalize_tool_stack
from .handles import sanitize_crop


def make_tool_entry(tool_id: str) -> dict[str, object]:
    spec = get_edit_tool(tool_id)
    if spec is None:
        return {}
    return {
        "instance_id": _new_instance_id(spec.id),
        "id": spec.id,
        "enabled": True,
        "settings": dict(spec.default_state()),
    }


def _new_instance_id(tool_id: str) -> str:
    key = str(tool_id or "tool").strip().lower() or "tool"
    return f"{key}_{uuid4().hex[:12]}"


def normalize_tool_entry(entry: object) -> dict[str, object]:
    if not isinstance(entry, dict):
        return {}
    tool_id = str(entry.get("id", "")).strip().lower()
    spec = get_edit_tool(tool_id)
    if spec is None:
        return {}
    instance_id = str(entry.get("instance_id", "") or "").strip()
    if not instance_id:
        instance_id = _new_instance_id(spec.id)
    return {
        "instance_id": instance_id,
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


def find_tool_entry_by_instance(stack: object, instance_id: str) -> tuple[int, dict[str, object]] | tuple[int, None]:
    key = str(instance_id or "").strip()
    if not key:
        return -1, None
    for idx, entry in enumerate(normalize_tool_entries(stack)):
        if str(entry.get("instance_id", "")).strip() == key:
            return idx, entry
    return -1, None


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
    crop_entries = [
        entry for entry in normalize_tool_entries(stack)
        if str(entry.get("id", "")).strip().lower() == "crop" and bool(entry.get("enabled", True))
    ]
    if not crop_entries:
        return None
    left = top = right = bottom = 0.0
    for entry in crop_entries:
        settings = entry.get("settings", {})
        if not isinstance(settings, dict):
            continue
        try:
            next_crop = sanitize_crop(
                settings.get("left", 0.0),
                settings.get("top", 0.0),
                settings.get("right", 0.0),
                settings.get("bottom", 0.0),
            )
        except Exception:
            continue
        remaining_w = max(0.01, 1.0 - left - right)
        remaining_h = max(0.01, 1.0 - top - bottom)
        left += remaining_w * next_crop[0]
        right += remaining_w * next_crop[2]
        top += remaining_h * next_crop[1]
        bottom += remaining_h * next_crop[3]
        left, top, right, bottom = sanitize_crop(left, top, right, bottom)
    return left, top, right, bottom


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


def move_tool_to_index(stack: object, source_index: int, target_index: int) -> tuple[list[dict[str, object]], int]:
    entries = normalize_tool_entries(stack)
    if source_index < 0 or source_index >= len(entries):
        return entries, -1 if not entries else 0
    target = max(0, min(int(target_index), len(entries) - 1))
    entry = entries.pop(source_index)
    entries.insert(target, entry)
    return entries, target


def update_tool_instance_settings(
    stack: object,
    instance_id: str,
    settings_update: dict[str, Any],
) -> tuple[list[dict[str, object]], int]:
    entries = normalize_tool_entries(stack)
    key = str(instance_id or "").strip()
    for idx, entry in enumerate(entries):
        if str(entry.get("instance_id", "")).strip() != key:
            continue
        settings = entry.get("settings", {})
        if not isinstance(settings, dict):
            settings = {}
        settings.update(settings_update)
        entry["settings"] = settings
        clean = normalize_tool_entry(entry)
        entries[idx] = clean if clean else entry
        return entries, idx
    return entries, -1 if not entries else 0


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
