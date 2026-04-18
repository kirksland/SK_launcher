from __future__ import annotations

import numpy as np  # type: ignore

from tools.board_tools.image import register_tool


def _apply_vibrance(rgb: object, settings: dict) -> object:
    arr = np.asarray(rgb)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return arr
    try:
        amount = float(settings.get("amount", 0.0))
    except Exception:
        amount = 0.0
    amount = max(-1.0, min(1.0, amount))
    arr_f = arr[:, :, :3].astype(np.float32) / 255.0
    max_c = np.max(arr_f, axis=2)
    min_c = np.min(arr_f, axis=2)
    sat = max_c - min_c
    luma = arr_f[:, :, 0] * 0.2126 + arr_f[:, :, 1] * 0.7152 + arr_f[:, :, 2] * 0.0722
    factor = 1.0 + amount * (1.0 - sat)
    arr_f = luma[:, :, None] + (arr_f - luma[:, :, None]) * factor[:, :, None]
    arr_f = np.clip(arr_f, 0.0, 1.0)
    return (arr_f * 255.0).astype(np.uint8)


register_tool("vibrance", _apply_vibrance)
