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
from core.board_scene.items import BoardImageItem, BoardVideoItem
from tools.board_tools.base import BoardToolSceneRuntime


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


def clear_controller_handles(controller: object, *, reset_drag: bool = True) -> None:
    (
        controller._focus_handle_frame,
        controller._focus_handle_items,
        controller._focus_crop_layout,
    ) = clear_crop_handle_items(
        controller._scene,
        controller._focus_handle_frame,
        controller._focus_handle_items,
    )
    if reset_drag:
        controller._focus_crop_drag = None


def refresh_controller_handles(controller: object) -> None:
    clear_controller_handles(controller, reset_drag=False)
    if not crop_handles_active(controller._focus_item, controller._selected_tool_panel()):
        return
    if controller._focus_item is None:
        return
    (
        controller._focus_handle_frame,
        controller._focus_handle_items,
        controller._focus_crop_layout,
    ) = create_crop_handle_items(
        controller._scene,
        controller._focus_item.sceneBoundingRect(),
        handle_size=12.0,
    )


def handle_panel_value_changed(controller: object) -> None:
    panel_state = controller._tool_panel_state_for_id("crop")
    left = float(panel_state.get("left", 0.0))
    top = float(panel_state.get("top", 0.0))
    right = float(panel_state.get("right", 0.0))
    bottom = float(panel_state.get("bottom", 0.0))
    controller._set_current_crop(left, top, right, bottom, schedule_preview=True)


def handle_mouse_press(controller: object, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
    if event.button() != QtCore.Qt.MouseButton.LeftButton:
        return False
    if not crop_handles_active(controller._focus_item, controller._selected_tool_panel()):
        return False
    layout = controller._focus_crop_layout
    if layout is None:
        refresh_controller_handles(controller)
        layout = controller._focus_crop_layout
    if layout is None:
        return False
    controller._focus_crop_drag = begin_crop_handle_drag(
        controller._focus_item,
        layout,
        scene_pos,
        (
            controller._edit_crop_left,
            controller._edit_crop_top,
            controller._edit_crop_right,
            controller._edit_crop_bottom,
        ),
    )
    return controller._focus_crop_drag is not None


def handle_mouse_move(controller: object, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
    crop = crop_values_from_drag(controller._focus_crop_drag, scene_pos)
    if crop is None:
        return False
    left, top, right, bottom = crop
    controller._set_current_crop(left, top, right, bottom, schedule_preview=False)
    return True


def handle_mouse_release(controller: object, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
    if controller._focus_crop_drag is None:
        return False
    controller._focus_crop_drag = None
    refresh_controller_handles(controller)
    if isinstance(controller._focus_item, BoardVideoItem):
        controller._schedule_video_focus_preview(controller._edit_video_playhead, immediate=True)
    elif isinstance(controller._focus_item, BoardImageItem):
        if controller._edit_exr_path is not None:
            channel = controller.w.board_page.current_exr_channel_value()
            if channel:
                controller._edit_exr_channel = str(channel)
                controller._schedule_edit_preview_update(channel=str(channel))
        else:
            controller._schedule_edit_preview_update()
    return True


def apply_to_focus_item(controller: object) -> bool:
    if not apply_crop_to_item(
        controller._focus_item,
        (
            controller._edit_crop_left,
            controller._edit_crop_top,
            controller._edit_crop_right,
            controller._edit_crop_bottom,
        ),
    ):
        return False
    group = controller._find_group_for_item(controller._focus_item)
    if group is not None:
        group.update_bounds()
    controller._refresh_scene_workspace()
    refresh_controller_handles(controller)
    return True


SCENE_RUNTIME = BoardToolSceneRuntime(
    refresh_handles=refresh_controller_handles,
    clear_handles=lambda controller, reset_drag: clear_controller_handles(controller, reset_drag=reset_drag),
    panel_value_changed=handle_panel_value_changed,
    mouse_press=handle_mouse_press,
    mouse_move=handle_mouse_move,
    mouse_release=handle_mouse_release,
    apply_to_focus_item=apply_to_focus_item,
)
