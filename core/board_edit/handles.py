from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore


def sanitize_crop(left: float, top: float, right: float, bottom: float) -> tuple[float, float, float, float]:
    try:
        left = float(left)
    except Exception:
        left = 0.0
    try:
        top = float(top)
    except Exception:
        top = 0.0
    try:
        right = float(right)
    except Exception:
        right = 0.0
    try:
        bottom = float(bottom)
    except Exception:
        bottom = 0.0
    left = max(0.0, min(0.95, left))
    top = max(0.0, min(0.95, top))
    right = max(0.0, min(0.95, right))
    bottom = max(0.0, min(0.95, bottom))
    max_sum = 0.95
    if left + right > max_sum:
        scale = max_sum / max(1e-6, left + right)
        left *= scale
        right *= scale
    if top + bottom > max_sum:
        scale = max_sum / max(1e-6, top + bottom)
        top *= scale
        bottom *= scale
    return left, top, right, bottom


@dataclass(slots=True)
class CropHandleLayout:
    frame_rect: QtCore.QRectF
    handle_rects: dict[str, QtCore.QRectF]


@dataclass(slots=True)
class CropHandleDragState:
    role: str
    start_scene_pos: QtCore.QPointF
    start_crop: tuple[float, float, float, float]
    base_size: QtCore.QSizeF


def build_crop_handle_layout(target_rect: QtCore.QRectF, handle_size: float = 12.0) -> CropHandleLayout:
    hs = float(handle_size)
    half = hs * 0.5
    left = target_rect.left()
    right = target_rect.right()
    top = target_rect.top()
    bottom = target_rect.bottom()
    cx = target_rect.center().x()
    cy = target_rect.center().y()
    handles = {
        "top_left": QtCore.QRectF(left - half, top - half, hs, hs),
        "top": QtCore.QRectF(cx - half, top - half, hs, hs),
        "top_right": QtCore.QRectF(right - half, top - half, hs, hs),
        "left": QtCore.QRectF(left - half, cy - half, hs, hs),
        "right": QtCore.QRectF(right - half, cy - half, hs, hs),
        "bottom_left": QtCore.QRectF(left - half, bottom - half, hs, hs),
        "bottom": QtCore.QRectF(cx - half, bottom - half, hs, hs),
        "bottom_right": QtCore.QRectF(right - half, bottom - half, hs, hs),
    }
    return CropHandleLayout(frame_rect=QtCore.QRectF(target_rect), handle_rects=handles)


def hit_test_crop_handle(layout: CropHandleLayout, scene_pos: QtCore.QPointF) -> str | None:
    for role, rect in layout.handle_rects.items():
        if rect.contains(scene_pos):
            return role
    return None


def apply_crop_drag(
    role: str,
    start_crop: tuple[float, float, float, float],
    delta_scene: QtCore.QPointF,
    base_size: QtCore.QSizeF,
) -> tuple[float, float, float, float]:
    left, top, right, bottom = start_crop
    bw = max(1.0, float(base_size.width()))
    bh = max(1.0, float(base_size.height()))
    dx = float(delta_scene.x()) / bw
    dy = float(delta_scene.y()) / bh
    if "left" in role:
        left += dx
    if "right" in role:
        right -= dx
    if "top" in role:
        top += dy
    if "bottom" in role:
        bottom -= dy
    return sanitize_crop(left, top, right, bottom)
