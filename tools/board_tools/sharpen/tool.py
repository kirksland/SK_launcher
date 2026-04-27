from __future__ import annotations

from tools.board_tools.edit import EditToolSpec, ToolUiControlSpec, register_edit_tool


def _default_state() -> dict[str, float]:
    return {
        "amount": 0.0,
        "radius": 1.5,
        "threshold": 0.0,
    }


def _clamp(value: object, default: float, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except Exception:
        v = default
    return max(lo, min(hi, v))


def _normalize_state(state: object) -> dict[str, float]:
    settings = dict(state) if isinstance(state, dict) else {}
    return {
        "amount": _clamp(settings.get("amount"), 0.0, 0.0, 3.0),
        "radius": _clamp(settings.get("radius"), 1.5, 0.2, 10.0),
        "threshold": _clamp(settings.get("threshold"), 0.0, 0.0, 1.0),
    }


def _is_effective(state: object) -> bool:
    settings = _normalize_state(state)
    return float(settings["amount"]) > 1e-6


register_edit_tool(
    EditToolSpec(
        id="sharpen",
        label="Sharpen",
        supports=("image",),
        default_state_factory=_default_state,
        normalize_state_fn=_normalize_state,
        is_effective_fn=_is_effective,
        order=80,
        tags=("image", "detail"),
        ui_panel="sharpen",
        ui_settings_keys=("amount", "radius", "threshold"),
        ui_controls=(
            ToolUiControlSpec("amount", "Amount", 0.0, 3.0, display_scale=100.0),
            ToolUiControlSpec("radius", "Radius", 0.2, 10.0, display_scale=1.0, display_suffix=" px"),
            ToolUiControlSpec("threshold", "Threshold", 0.0, 1.0, display_scale=100.0),
        ),
    )
)