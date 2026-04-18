from __future__ import annotations

from tools.edit_tools.base import EditToolSpec
from tools.edit_tools.registry import register_edit_tool


def _default_state() -> dict[str, float]:
    return {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0}


def _normalize_state(state: object) -> dict[str, float]:
    settings = dict(state) if isinstance(state, dict) else {}
    try:
        brightness = float(settings.get("brightness", 0.0))
    except Exception:
        brightness = 0.0
    try:
        contrast = float(settings.get("contrast", 1.0))
    except Exception:
        contrast = 1.0
    try:
        saturation = float(settings.get("saturation", 1.0))
    except Exception:
        saturation = 1.0
    return {
        "brightness": max(-1.0, min(1.0, brightness)),
        "contrast": max(0.0, min(2.0, contrast)),
        "saturation": max(0.0, min(2.0, saturation)),
    }


def _is_effective(state: object) -> bool:
    settings = _normalize_state(state)
    return not (
        abs(float(settings["brightness"])) < 1e-6
        and abs(float(settings["contrast"]) - 1.0) < 1e-6
        and abs(float(settings["saturation"]) - 1.0) < 1e-6
    )


register_edit_tool(
    EditToolSpec(
        id="bcs",
        label="BCS",
        supports=("image",),
        default_state_factory=_default_state,
        normalize_state_fn=_normalize_state,
        is_effective_fn=_is_effective,
        order=10,
        tags=("image", "color"),
    )
)

