from __future__ import annotations

from tools.board_tools.edit import EditToolSpec, ToolUiControlSpec, register_edit_tool


def _default_state() -> dict[str, float]:
    return {"amount": 0.0}


def _normalize_state(state: object) -> dict[str, float]:
    settings = dict(state) if isinstance(state, dict) else {}
    try:
        amount = float(settings.get("amount", 0.0))
    except Exception:
        amount = 0.0
    return {"amount": max(-1.0, min(1.0, amount))}


def _is_effective(state: object) -> bool:
    settings = _normalize_state(state)
    return abs(float(settings["amount"])) > 1e-6


register_edit_tool(
    EditToolSpec(
        id="vibrance",
        label="Vibrance",
        supports=("image",),
        default_state_factory=_default_state,
        normalize_state_fn=_normalize_state,
        is_effective_fn=_is_effective,
        order=20,
        tags=("image", "color"),
        ui_panel="vibrance",
        ui_settings_keys=("amount",),
        ui_controls=(
            ToolUiControlSpec("amount", "Vibrance", -1.0, 1.0, display_signed=True),
        ),
    )
)
