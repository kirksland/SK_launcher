from __future__ import annotations

from dataclasses import dataclass, field

from .tool_stack import (
    extract_bcs_settings,
    extract_crop_settings,
    get_tool_settings,
    make_tool_entry,
    normalize_tool_entries,
)


def _default_color_adjustments() -> tuple[float, float, float]:
    return 0.0, 1.0, 1.0


def _default_vibrance() -> float:
    return 0.0


def _default_crop_settings() -> tuple[float, float, float, float]:
    return 0.0, 0.0, 0.0, 0.0


def coerce_color_adjustments(override: object) -> tuple[float, float, float]:
    b_def, c_def, s_def = _default_color_adjustments()
    if not isinstance(override, dict):
        return b_def, c_def, s_def
    from_stack = extract_bcs_settings(override.get("tool_stack"))
    if from_stack is not None:
        b, c, s = from_stack
        return (
            max(-1.0, min(1.0, float(b))),
            max(0.0, min(2.0, float(c))),
            max(0.0, min(2.0, float(s))),
        )
    try:
        brightness = float(override.get("brightness", b_def))
    except Exception:
        brightness = b_def
    try:
        contrast = float(override.get("contrast", c_def))
    except Exception:
        contrast = c_def
    try:
        saturation = float(override.get("saturation", s_def))
    except Exception:
        saturation = s_def
    return (
        max(-1.0, min(1.0, brightness)),
        max(0.0, min(2.0, contrast)),
        max(0.0, min(2.0, saturation)),
    )


def default_tool_stack_for_kind(media_kind: str | None) -> list[dict[str, object]]:
    kind = str(media_kind or "").strip().lower()
    default_tool_id = "crop" if kind == "video" else "bcs"
    entry = make_tool_entry(default_tool_id)
    return [entry] if entry else []


def tool_stack_from_override(override: object, media_kind: str | None = None) -> list[dict[str, object]]:
    if isinstance(override, dict):
        stack = normalize_tool_entries(override.get("tool_stack"))
        if stack:
            return stack
    stack = default_tool_stack_for_kind(media_kind)
    brightness, contrast, saturation = coerce_color_adjustments(override)
    if stack and str(stack[0].get("id", "")).strip().lower() == "bcs":
        stack[0]["settings"] = {
            "brightness": float(brightness),
            "contrast": float(contrast),
            "saturation": float(saturation),
        }
    if isinstance(override, dict):
        crop = extract_crop_settings(
            [
                {
                    "id": "crop",
                    "enabled": True,
                    "settings": {
                        "left": override.get("crop_left", 0.0),
                        "top": override.get("crop_top", 0.0),
                        "right": override.get("crop_right", 0.0),
                        "bottom": override.get("crop_bottom", 0.0),
                    },
                }
            ]
        )
        if crop is not None and any(abs(v) > 1e-6 for v in crop):
            stack.append(
                {
                    "id": "crop",
                    "enabled": True,
                    "settings": {
                        "left": crop[0],
                        "top": crop[1],
                        "right": crop[2],
                        "bottom": crop[3],
                    },
                }
            )
    return normalize_tool_entries(stack)


@dataclass(slots=True)
class EditVisualState:
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    vibrance: float = 0.0
    crop_left: float = 0.0
    crop_top: float = 0.0
    crop_right: float = 0.0
    crop_bottom: float = 0.0

    @classmethod
    def defaults(cls) -> "EditVisualState":
        return cls()

    @classmethod
    def from_tool_stack(cls, stack: object) -> "EditVisualState":
        brightness, contrast, saturation = _default_color_adjustments()
        vibrance = _default_vibrance()
        crop_left, crop_top, crop_right, crop_bottom = _default_crop_settings()
        bcs = extract_bcs_settings(stack)
        if bcs is not None:
            brightness, contrast, saturation = bcs
        crop = extract_crop_settings(stack)
        if crop is not None:
            crop_left, crop_top, crop_right, crop_bottom = crop
        vibrance_settings = get_tool_settings(stack, "vibrance")
        if isinstance(vibrance_settings, dict):
            try:
                vibrance = float(vibrance_settings.get("amount", vibrance))
            except Exception:
                vibrance = _default_vibrance()
        return cls(
            brightness=max(-1.0, min(1.0, float(brightness))),
            contrast=max(0.0, min(2.0, float(contrast))),
            saturation=max(0.0, min(2.0, float(saturation))),
            vibrance=max(-1.0, min(1.0, float(vibrance))),
            crop_left=float(crop_left),
            crop_top=float(crop_top),
            crop_right=float(crop_right),
            crop_bottom=float(crop_bottom),
        )

    def apply_to_session(self, session: "EditSessionState") -> None:
        session.image_brightness = float(self.brightness)
        session.image_contrast = float(self.contrast)
        session.image_saturation = float(self.saturation)
        session.image_vibrance = float(self.vibrance)
        session.crop_left = float(self.crop_left)
        session.crop_top = float(self.crop_top)
        session.crop_right = float(self.crop_right)
        session.crop_bottom = float(self.crop_bottom)


@dataclass(slots=True)
class EditSessionState:
    focus_kind: str | None = None
    tool_stack: list[dict[str, object]] = field(default_factory=list)
    selected_tool_index: int = -1
    image_brightness: float = 0.0
    image_contrast: float = 1.0
    image_saturation: float = 1.0
    image_vibrance: float = 0.0
    crop_left: float = 0.0
    crop_top: float = 0.0
    crop_right: float = 0.0
    crop_bottom: float = 0.0

    def reset_visual_adjustments(self) -> None:
        EditVisualState.defaults().apply_to_session(self)
