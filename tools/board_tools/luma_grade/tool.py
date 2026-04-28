from __future__ import annotations

from tools.board_tools.edit import EditToolSpec, ToolUiControlSpec, register_edit_tool


def _default_state() -> dict[str, float]:
    return {
        "shadow_r": 1.0,
        "shadow_g": 1.0,
        "shadow_b": 1.0,
        "shadow_amount": 0.0,

        "midtone_r": 1.0,
        "midtone_g": 1.0,
        "midtone_b": 1.0,
        "midtone_amount": 0.0,

        "highlight_r": 1.0,
        "highlight_g": 1.0,
        "highlight_b": 1.0,
        "highlight_amount": 0.0,
    }


def _clamp(value: object, default: float, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except Exception:
        v = default
    return max(lo, min(hi, v))


def _normalize_state(state: object) -> dict[str, float]:
    settings = dict(state) if isinstance(state, dict) else {}
    defaults = _default_state()

    return {
        "shadow_r": _clamp(settings.get("shadow_r"), defaults["shadow_r"], 0.0, 2.0),
        "shadow_g": _clamp(settings.get("shadow_g"), defaults["shadow_g"], 0.0, 2.0),
        "shadow_b": _clamp(settings.get("shadow_b"), defaults["shadow_b"], 0.0, 2.0),
        "shadow_amount": _clamp(settings.get("shadow_amount"), 0.0, -1.0, 1.0),

        "midtone_r": _clamp(settings.get("midtone_r"), defaults["midtone_r"], 0.0, 2.0),
        "midtone_g": _clamp(settings.get("midtone_g"), defaults["midtone_g"], 0.0, 2.0),
        "midtone_b": _clamp(settings.get("midtone_b"), defaults["midtone_b"], 0.0, 2.0),
        "midtone_amount": _clamp(settings.get("midtone_amount"), 0.0, -1.0, 1.0),

        "highlight_r": _clamp(settings.get("highlight_r"), defaults["highlight_r"], 0.0, 2.0),
        "highlight_g": _clamp(settings.get("highlight_g"), defaults["highlight_g"], 0.0, 2.0),
        "highlight_b": _clamp(settings.get("highlight_b"), defaults["highlight_b"], 0.0, 2.0),
        "highlight_amount": _clamp(settings.get("highlight_amount"), 0.0, -1.0, 1.0),
    }


def _is_effective(state: object) -> bool:
    s = _normalize_state(state)
    return any(
        abs(float(s[key])) > 1e-6
        for key in ("shadow_amount", "midtone_amount", "highlight_amount")
    )


register_edit_tool(
    EditToolSpec(
        id="luma_grade",
        label="Luma Grade",
        supports=("image",),
        default_state_factory=_default_state,
        normalize_state_fn=_normalize_state,
        is_effective_fn=_is_effective,
        order=25,
        tags=("image", "color", "grading"),
        ui_panel="luma_grade",
        ui_settings_keys=tuple(_default_state().keys()),
        ui_controls=(
            ToolUiControlSpec("shadow_amount", "Shadows Amount", -1.0, 1.0, display_scale=100.0, display_signed=True),
            ToolUiControlSpec("shadow_r", "Shadows Red", 0.0, 2.0, display_scale=100.0),
            ToolUiControlSpec("shadow_g", "Shadows Green", 0.0, 2.0, display_scale=100.0),
            ToolUiControlSpec("shadow_b", "Shadows Blue", 0.0, 2.0, display_scale=100.0),

            ToolUiControlSpec("midtone_amount", "Midtones Amount", -1.0, 1.0, display_scale=100.0, display_signed=True),
            ToolUiControlSpec("midtone_r", "Midtones Red", 0.0, 2.0, display_scale=100.0),
            ToolUiControlSpec("midtone_g", "Midtones Green", 0.0, 2.0, display_scale=100.0),
            ToolUiControlSpec("midtone_b", "Midtones Blue", 0.0, 2.0, display_scale=100.0),

            ToolUiControlSpec("highlight_amount", "Highlights Amount", -1.0, 1.0, display_scale=100.0, display_signed=True),
            ToolUiControlSpec("highlight_r", "Highlights Red", 0.0, 2.0, display_scale=100.0),
            ToolUiControlSpec("highlight_g", "Highlights Green", 0.0, 2.0, display_scale=100.0),
            ToolUiControlSpec("highlight_b", "Highlights Blue", 0.0, 2.0, display_scale=100.0),
        ),
    )
)