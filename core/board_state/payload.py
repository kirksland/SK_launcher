from __future__ import annotations

from typing import Optional

from .migrations import migrate_board_payload


def clone_payload(payload: Optional[dict]) -> dict:
    return migrate_board_payload(payload)


def payload_item_count(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    items = payload.get("items", [])
    if not isinstance(items, list):
        return 0
    return sum(1 for entry in items if isinstance(entry, dict))


def sync_board_state_overrides(board_state: dict, image_overrides: dict[str, dict[str, object]]) -> dict:
    payload = clone_payload(board_state)
    items = payload.get("items", [])
    media_ids = {
        str(entry.get("file", ""))
        for entry in items
        if isinstance(entry, dict) and entry.get("type") in ("image", "video")
    }
    payload["image_display_overrides"] = {
        key: value
        for key, value in image_overrides.items()
        if key in media_ids and isinstance(value, dict)
    }
    return clone_payload(payload)


def parse_image_display_overrides(
    payload: dict,
    *,
    tool_stack_from_override: Callable[[object], list[dict[str, object]]],
) -> dict[str, dict[str, object]]:
    raw = payload.get("image_display_overrides")
    if not isinstance(raw, dict):
        raw = payload.get("image_exr_display_overrides", {})
    parsed: dict[str, dict[str, object]] = {}
    if not isinstance(raw, dict):
        return parsed
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        channel = str(value.get("channel", "")).strip()
        gamma_val = value.get("gamma", 2.2)
        srgb_val = value.get("srgb", True)
        try:
            gamma = float(gamma_val)
        except Exception:
            gamma = 2.2
        tool_stack = tool_stack_from_override(value)
        parsed[key] = {
            "channel": channel,
            "gamma": max(0.1, gamma),
            "srgb": bool(srgb_val),
            "tool_stack": tool_stack,
        }
    return parsed
