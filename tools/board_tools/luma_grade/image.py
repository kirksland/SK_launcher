from __future__ import annotations

import numpy as np  # type: ignore

from tools.board_tools.image import register_tool


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / max(edge1 - edge0, 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _apply_luma_grade(rgb: object, settings: dict) -> object:
    arr = np.asarray(rgb)

    if arr.ndim != 3 or arr.shape[2] < 3:
        return arr

    arr_f = arr[:, :, :3].astype(np.float32) / 255.0

    luma = (
        arr_f[:, :, 0] * 0.2126
        + arr_f[:, :, 1] * 0.7152
        + arr_f[:, :, 2] * 0.0722
    )

    shadows = 1.0 - _smoothstep(0.15, 0.45, luma)
    highlights = _smoothstep(0.55, 0.85, luma)
    midtones = 1.0 - np.maximum(shadows, highlights)
    midtones = np.clip(midtones, 0.0, 1.0)

    def f(key: str, default: float) -> float:
        try:
            return float(settings.get(key, default))
        except Exception:
            return default

    shadow_tint = np.array([
        f("shadow_r", 1.0),
        f("shadow_g", 1.0),
        f("shadow_b", 1.0),
    ], dtype=np.float32)

    midtone_tint = np.array([
        f("midtone_r", 1.0),
        f("midtone_g", 1.0),
        f("midtone_b", 1.0),
    ], dtype=np.float32)

    highlight_tint = np.array([
        f("highlight_r", 1.0),
        f("highlight_g", 1.0),
        f("highlight_b", 1.0),
    ], dtype=np.float32)

    shadow_amount = np.clip(f("shadow_amount", 0.0), -1.0, 1.0)
    midtone_amount = np.clip(f("midtone_amount", 0.0), -1.0, 1.0)
    highlight_amount = np.clip(f("highlight_amount", 0.0), -1.0, 1.0)

    def apply_tint(
        image: np.ndarray,
        mask: np.ndarray,
        tint: np.ndarray,
        amount: float,
    ) -> np.ndarray:
        if abs(amount) < 1e-6:
            return image

        tinted = image * tint[None, None, :]
        blend = mask[:, :, None] * abs(amount)

        if amount >= 0.0:
            return image + (tinted - image) * blend

        inverse_tint = 2.0 - tint
        cooled = image * inverse_tint[None, None, :]
        return image + (cooled - image) * blend

    arr_f = apply_tint(arr_f, shadows, shadow_tint, shadow_amount)
    arr_f = apply_tint(arr_f, midtones, midtone_tint, midtone_amount)
    arr_f = apply_tint(arr_f, highlights, highlight_tint, highlight_amount)

    arr_f = np.clip(arr_f, 0.0, 1.0)
    return (arr_f * 255.0).astype(np.uint8)


register_tool("luma_grade", _apply_luma_grade)