from __future__ import annotations

import numpy as np  # type: ignore

from tools.board_tools.image import register_tool


def _gaussian_kernel_1d(radius: float) -> np.ndarray:
    sigma = max(float(radius), 0.2)
    half_size = max(1, int(np.ceil(sigma * 3.0)))
    x = np.arange(-half_size, half_size + 1, dtype=np.float32)
    kernel = np.exp(-(x * x) / (2.0 * sigma * sigma))
    kernel /= np.sum(kernel)
    return kernel.astype(np.float32)


def _blur_axis(arr: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
    pad = len(kernel) // 2

    if axis == 0:
        padded = np.pad(arr, ((pad, pad), (0, 0), (0, 0)), mode="edge")
        out = np.zeros_like(arr, dtype=np.float32)
        for i, w in enumerate(kernel):
            out += padded[i:i + arr.shape[0], :, :] * float(w)
        return out

    padded = np.pad(arr, ((0, 0), (pad, pad), (0, 0)), mode="edge")
    out = np.zeros_like(arr, dtype=np.float32)
    for i, w in enumerate(kernel):
        out += padded[:, i:i + arr.shape[1], :] * float(w)
    return out


def _gaussian_blur(arr: np.ndarray, radius: float) -> np.ndarray:
    kernel = _gaussian_kernel_1d(radius)
    blurred = _blur_axis(arr, kernel, axis=1)
    blurred = _blur_axis(blurred, kernel, axis=0)
    return blurred


def _apply_sharpen(rgb: object, settings: dict) -> object:
    arr = np.asarray(rgb)

    if arr.ndim != 3 or arr.shape[2] < 3:
        return arr

    def f(key: str, default: float) -> float:
        try:
            return float(settings.get(key, default))
        except Exception:
            return default

    amount = max(0.0, min(3.0, f("amount", 0.0)))
    radius = max(0.2, min(10.0, f("radius", 1.5)))
    threshold = max(0.0, min(1.0, f("threshold", 0.0)))

    if amount <= 1e-6:
        return arr

    rgb_f = arr[:, :, :3].astype(np.float32) / 255.0

    blurred = _gaussian_blur(rgb_f, radius)
    detail = rgb_f - blurred

    if threshold > 1e-6:
        strength = np.max(np.abs(detail), axis=2)
        mask = strength > threshold
        detail = detail * mask[:, :, None]

    sharpened = rgb_f + detail * amount
    sharpened = np.clip(sharpened, 0.0, 1.0)

    out = arr.copy()
    out[:, :, :3] = (sharpened * 255.0).astype(np.uint8)
    return out


register_tool("sharpen", _apply_sharpen)