from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_edit.handles import (
    CropHandleDragState,
    CropHandleLayout,
    apply_crop_drag,
    build_crop_handle_layout,
    hit_test_crop_handle,
)


def is_crop_scene_target(item: object) -> bool:
    return callable(getattr(item, "set_crop_norm", None)) and callable(getattr(item, "sceneBoundingRect", None))


def crop_handles_active(item: object, selected_panel: str) -> bool:
    return str(selected_panel or "").strip().lower() == "crop" and is_crop_scene_target(item)


def focus_item_base_size(item: object) -> Optional[QtCore.QSizeF]:
    if item is None:
        return None
    base_size = getattr(item, "_base_size", None)
    if isinstance(base_size, QtCore.QSizeF):
        return QtCore.QSizeF(base_size)
    bounding_rect = getattr(item, "boundingRect", None)
    if not callable(bounding_rect):
        return None
    rect = bounding_rect()
    if not isinstance(rect, QtCore.QRectF) or rect.isNull():
        return None
    return QtCore.QSizeF(rect.width(), rect.height())


def apply_crop_to_item(item: object, crop: tuple[float, float, float, float]) -> bool:
    if not is_crop_scene_target(item):
        return False
    item.set_crop_norm(*crop)
    return True


def clear_crop_handle_items(
    scene: QtWidgets.QGraphicsScene,
    frame_item: QtWidgets.QGraphicsRectItem | None,
    handle_items: dict[str, QtWidgets.QGraphicsRectItem],
) -> tuple[None, dict[str, QtWidgets.QGraphicsRectItem], None]:
    if frame_item is not None and frame_item.scene() is not None:
        scene.removeItem(frame_item)
    for item in list(handle_items.values()):
        if item.scene() is not None:
            scene.removeItem(item)
    return None, {}, None


def create_crop_handle_items(
    scene: QtWidgets.QGraphicsScene,
    target_rect: QtCore.QRectF,
    *,
    handle_size: float = 12.0,
) -> tuple[QtWidgets.QGraphicsRectItem, dict[str, QtWidgets.QGraphicsRectItem], CropHandleLayout]:
    layout = build_crop_handle_layout(target_rect, handle_size=handle_size)
    frame = QtWidgets.QGraphicsRectItem(layout.frame_rect)
    frame.setPen(QtGui.QPen(QtGui.QColor("#f2c14e"), 1.5, QtCore.Qt.PenStyle.DashLine))
    frame.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    frame.setZValue(10_020)
    scene.addItem(frame)
    handle_items: dict[str, QtWidgets.QGraphicsRectItem] = {}
    for role, rect in layout.handle_rects.items():
        handle = QtWidgets.QGraphicsRectItem(rect)
        handle.setPen(QtGui.QPen(QtGui.QColor("#f2c14e"), 1))
        handle.setBrush(QtGui.QBrush(QtGui.QColor("#1d2128")))
        handle.setZValue(10_021)
        scene.addItem(handle)
        handle_items[role] = handle
    return frame, handle_items, layout


def begin_crop_handle_drag(
    item: object,
    layout: CropHandleLayout | None,
    scene_pos: QtCore.QPointF,
    crop: tuple[float, float, float, float],
) -> CropHandleDragState | None:
    if layout is None:
        return None
    role = hit_test_crop_handle(layout, scene_pos)
    if role is None:
        return None
    base_size = focus_item_base_size(item)
    if base_size is None:
        return None
    return CropHandleDragState(
        role=role,
        start_scene_pos=QtCore.QPointF(scene_pos),
        start_crop=crop,
        base_size=base_size,
    )


def crop_values_from_drag(
    drag_state: CropHandleDragState | None,
    scene_pos: QtCore.QPointF,
) -> tuple[float, float, float, float] | None:
    if drag_state is None:
        return None
    delta = QtCore.QPointF(
        scene_pos.x() - drag_state.start_scene_pos.x(),
        scene_pos.y() - drag_state.start_scene_pos.y(),
    )
    return apply_crop_drag(
        drag_state.role,
        drag_state.start_crop,
        delta,
        drag_state.base_size,
    )
