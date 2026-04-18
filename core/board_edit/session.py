from __future__ import annotations

from dataclasses import dataclass, field


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
        self.image_brightness = 0.0
        self.image_contrast = 1.0
        self.image_saturation = 1.0
        self.image_vibrance = 0.0
        self.crop_left = 0.0
        self.crop_top = 0.0
        self.crop_right = 0.0
        self.crop_bottom = 0.0
