from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_edit.handles import (
    CropHandleDragState,
    CropHandleLayout,
    apply_crop_drag,
    build_crop_handle_layout,
    hit_test_crop_handle,
)
from tools.board_tools.base import BoardToolSceneHost, BoardToolSceneRuntime


TOOL_ID = "crop"


@dataclass(slots=True)
class CropSceneState:
    frame_item: QtWidgets.QGraphicsRectItem | None = None
    handle_items: dict[str, QtWidgets.QGraphicsRectItem] = field(default_factory=dict)
    layout: CropHandleLayout | None = None
    drag: CropHandleDragState | None = None


def crop_state(host: BoardToolSceneHost) -> CropSceneState:
    state_factory = getattr(host, "scene_tool_state", None)
    if not callable(state_factory):
        raise TypeError("scene tool host does not expose scene_tool_state")
    state = state_factory(TOOL_ID, CropSceneState)
    if not isinstance(state, CropSceneState):
        raise TypeError("crop scene state has invalid type")
    return state


def is_crop_scene_target(item: object) -> bool:
    return callable(getattr(item, "set_crop_norm", None)) and callable(getattr(item, "sceneBoundingRect", None))


def crop_handles_active(item: object, selected_panel: str) -> bool:
    return str(selected_panel or "").strip().lower() == "crop" and is_crop_scene_target(item)


def crop_settings_tuple(settings: object) -> tuple[float, float, float, float]:
    values = dict(settings) if isinstance(settings, dict) else {}
    return (
        float(values.get("left", 0.0)),
        float(values.get("top", 0.0)),
        float(values.get("right", 0.0)),
        float(values.get("bottom", 0.0)),
    )


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


def clear_controller_handles(host: BoardToolSceneHost, *, reset_drag: bool = True) -> None:
    state = crop_state(host)
    (
        state.frame_item,
        state.handle_items,
        state.layout,
    ) = clear_crop_handle_items(
        host.graphics_scene(),
        state.frame_item,
        state.handle_items,
    )
    if reset_drag:
        state.drag = None


def refresh_controller_handles(host: BoardToolSceneHost) -> None:
    state = crop_state(host)
    clear_controller_handles(host, reset_drag=False)
    item = host.focus_item()
    if not crop_handles_active(item, host.selected_tool_panel()):
        return
    (
        state.frame_item,
        state.handle_items,
        state.layout,
    ) = create_crop_handle_items(
        host.graphics_scene(),
        item.sceneBoundingRect(),
        handle_size=12.0,
    )


def handle_panel_value_changed(host: BoardToolSceneHost) -> None:
    panel_state = host.tool_panel_state(TOOL_ID)
    left = float(panel_state.get("left", 0.0))
    top = float(panel_state.get("top", 0.0))
    right = float(panel_state.get("right", 0.0))
    bottom = float(panel_state.get("bottom", 0.0))
    host.update_scene_tool_settings(
        TOOL_ID,
        {"left": left, "top": top, "right": right, "bottom": bottom},
        schedule_preview=True,
    )


def handle_mouse_press(host: BoardToolSceneHost, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
    state = crop_state(host)
    item = host.focus_item()
    if event.button() != QtCore.Qt.MouseButton.LeftButton:
        return False
    if not crop_handles_active(item, host.selected_tool_panel()):
        return False
    layout = state.layout
    if layout is None:
        refresh_controller_handles(host)
        layout = state.layout
    if layout is None:
        return False
    crop = crop_settings_tuple(host.tool_panel_state(TOOL_ID))
    state.drag = begin_crop_handle_drag(
        item,
        layout,
        scene_pos,
        crop,
    )
    return state.drag is not None


def handle_mouse_move(host: BoardToolSceneHost, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
    state = crop_state(host)
    crop = crop_values_from_drag(state.drag, scene_pos)
    if crop is None:
        return False
    left, top, right, bottom = crop
    host.update_scene_tool_settings(
        TOOL_ID,
        {"left": left, "top": top, "right": right, "bottom": bottom},
        schedule_preview=False,
    )
    return True


def handle_mouse_release(host: BoardToolSceneHost, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
    state = crop_state(host)
    if state.drag is None:
        return False
    state.drag = None
    refresh_controller_handles(host)
    host.schedule_focus_preview()
    return True


def apply_to_focus_item(host: BoardToolSceneHost) -> bool:
    item = host.focus_item()
    if not apply_crop_to_item(
        item,
        crop_settings_tuple(host.tool_panel_state(TOOL_ID)),
    ):
        return False
    group = host.find_group_for_item(item)
    if group is not None:
        group.update_bounds()
    host.refresh_workspace()
    refresh_controller_handles(host)
    return True


def reset_focus_item(host: BoardToolSceneHost) -> bool:
    item = host.focus_item()
    if not apply_crop_to_item(item, (0.0, 0.0, 0.0, 0.0)):
        return False
    group = host.find_group_for_item(item)
    if group is not None:
        group.update_bounds()
    return True


SCENE_RUNTIME = BoardToolSceneRuntime(
    refresh_handles=refresh_controller_handles,
    clear_handles=lambda host, reset_drag: clear_controller_handles(host, reset_drag=reset_drag),
    panel_value_changed=handle_panel_value_changed,
    mouse_press=handle_mouse_press,
    mouse_move=handle_mouse_move,
    mouse_release=handle_mouse_release,
    apply_to_focus_item=apply_to_focus_item,
    reset_focus_item=reset_focus_item,
)
