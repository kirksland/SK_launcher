from __future__ import annotations

import json
from typing import Any


BOARD_SCHEMA_VERSION = 1


def migrate_board_payload(payload: object) -> dict[str, Any]:
    cloned = _json_clone(payload)
    if not isinstance(cloned, dict):
        cloned = {}

    items = cloned.get("items", [])
    if not isinstance(items, list):
        items = []
    cloned["items"] = [item for item in items if isinstance(item, dict)]

    overrides = cloned.get("image_display_overrides")
    if not isinstance(overrides, dict):
        legacy_overrides = cloned.get("image_exr_display_overrides")
        overrides = legacy_overrides if isinstance(legacy_overrides, dict) else {}
    cloned["image_display_overrides"] = {
        str(key): value
        for key, value in overrides.items()
        if isinstance(key, str) and isinstance(value, dict)
    }
    cloned.pop("image_exr_display_overrides", None)

    cloned["schema_version"] = BOARD_SCHEMA_VERSION
    return cloned


def _json_clone(payload: object) -> object:
    try:
        return json.loads(json.dumps(payload))
    except Exception:
        return None
