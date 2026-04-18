from __future__ import annotations

from core.board_edit.handles import sanitize_crop
from tools.board_tools.edit import EditToolSpec, ToolUiControlSpec, register_edit_tool


def _default_state() -> dict[str, float]:
    return {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}


def _normalize_state(state: object) -> dict[str, float]:
    settings = dict(state) if isinstance(state, dict) else {}
    left, top, right, bottom = sanitize_crop(
        settings.get("left", 0.0),
        settings.get("top", 0.0),
        settings.get("right", 0.0),
        settings.get("bottom", 0.0),
    )
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
    }


def _is_effective(state: object) -> bool:
    settings = _normalize_state(state)
    return any(abs(float(settings[key])) > 1e-6 for key in ("left", "top", "right", "bottom"))


register_edit_tool(
    EditToolSpec(
        id="crop",
        label="Crop",
        supports=("image", "video", "sequence"),
        default_state_factory=_default_state,
        normalize_state_fn=_normalize_state,
        is_effective_fn=_is_effective,
        order=30,
        tags=("image", "video", "spatial"),
        ui_panel="crop",
        ui_settings_keys=("left", "top", "right", "bottom"),
        ui_controls=(
            ToolUiControlSpec("left", "Left", 0.0, 0.9, display_scale=100.0, display_suffix="%", display_decimals=0),
            ToolUiControlSpec("top", "Top", 0.0, 0.9, display_scale=100.0, display_suffix="%", display_decimals=0),
            ToolUiControlSpec("right", "Right", 0.0, 0.9, display_scale=100.0, display_suffix="%", display_decimals=0),
            ToolUiControlSpec("bottom", "Bottom", 0.0, 0.9, display_scale=100.0, display_suffix="%", display_decimals=0),
        ),
    )
)
