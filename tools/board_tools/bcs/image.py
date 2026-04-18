from __future__ import annotations

import numpy as np  # type: ignore

from tools.board_tools.image import register_tool


def _apply_bcs(rgb: object, settings: dict) -> object:
    arr = np.asarray(rgb)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return arr
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
    brightness = max(-1.0, min(1.0, brightness))
    contrast = max(0.0, min(2.0, contrast))
    saturation = max(0.0, min(2.0, saturation))
    arr_f = arr[:, :, :3].astype(np.float32) / 255.0
    arr_f = (arr_f - 0.5) * contrast + 0.5
    arr_f = arr_f + brightness
    luma = arr_f[:, :, 0] * 0.2126 + arr_f[:, :, 1] * 0.7152 + arr_f[:, :, 2] * 0.0722
    arr_f = luma[:, :, None] + (arr_f - luma[:, :, None]) * saturation
    arr_f = np.clip(arr_f, 0.0, 1.0)
    return (arr_f * 255.0).astype(np.uint8)


register_tool("bcs", _apply_bcs)
