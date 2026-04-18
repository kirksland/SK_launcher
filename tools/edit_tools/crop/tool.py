from __future__ import annotations

from tools.edit_tools.base import EditToolSpec
from tools.edit_tools.registry import register_edit_tool


def _default_state() -> dict[str, float]:
    return {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}


def _normalize_state(state: object) -> dict[str, float]:
    settings = dict(state) if isinstance(state, dict) else {}

    def _axis(name: str) -> float:
        try:
            value = float(settings.get(name, 0.0))
        except Exception:
            value = 0.0
        return max(0.0, min(0.95, value))

    left = _axis("left")
    top = _axis("top")
    right = _axis("right")
    bottom = _axis("bottom")
    max_sum = 0.95
    if left + right > max_sum:
        scale = max_sum / max(1e-6, left + right)
        left *= scale
        right *= scale
    if top + bottom > max_sum:
        scale = max_sum / max(1e-6, top + bottom)
        top *= scale
        bottom *= scale
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
    )
)
