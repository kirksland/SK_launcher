from __future__ import annotations

import logging

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_edit.crop_scene import apply_crop_to_item, clear_crop_handle_items
from core.board_edit.media_runtime import play_button_label
from core.board_edit.handles import sanitize_crop
from core.board_scene.items import BoardImageItem, BoardSequenceItem, BoardVideoItem
from tools.board_tools.edit import get_edit_tool
from tools.board_tools.registry import get_board_tool, get_board_tool_scene_runtime

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional video backend
    cv2 = None  # type: ignore


logger = logging.getLogger(__name__)


class BoardEditFocusController:
    """Owns Board edit focus mode and scene-tool interactions."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.w = board_controller.w

    def _log_debug(self, message: str, exc: Exception) -> None:
        logger.debug("%s: %s", message, exc, exc_info=True)

    def _stop_edit_thread(self, attr_name: str) -> None:
        thread = getattr(self.board, attr_name, None)
        if thread is None:
            return
        stop_thread = getattr(self.board, "_stop_qthread", None)
        if callable(stop_thread):
            stop_thread(thread, timeout_ms=1000)
            return
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(1000)
        except Exception as exc:
            self._log_debug(f"Failed to stop {attr_name}", exc)

    def apply_crop_to_focus_item(self) -> None:
        board = self.board
        scene_runtime = self.scene_tool_runtime("crop")
        apply_hook = getattr(scene_runtime, "apply_to_focus_item", None) if scene_runtime is not None else None
        if callable(apply_hook):
            apply_hook(board)
            return
        if not apply_crop_to_item(
            board._focus_item,
            (
                board._edit_crop_left,
                board._edit_crop_top,
                board._edit_crop_right,
                board._edit_crop_bottom,
            ),
        ):
            return
        group = board._find_group_for_item(board._focus_item)
        if group is not None:
            group.update_bounds()
        board._refresh_scene_workspace()
        self.refresh_scene_handles()

    def selected_scene_tool_id(self) -> str:
        selected = self.board._selected_tool_entry()
        selected_id = str(selected.get("id", "")).strip().lower() if isinstance(selected, dict) else ""
        tool_caps = get_board_tool(selected_id)
        if tool_caps is None or not tool_caps.has_scene:
            return ""
        return selected_id

    def scene_tool_runtime(self, tool_id: str | None = None) -> object | None:
        target_id = str(tool_id or "").strip().lower() or self.selected_scene_tool_id()
        if not target_id:
            return None
        return get_board_tool_scene_runtime(target_id)

    def clear_crop_handles(self, *, reset_drag: bool = True) -> None:
        board = self.board
        scene_runtime = self.scene_tool_runtime()
        clear_hook = getattr(scene_runtime, "clear_handles", None) if scene_runtime is not None else None
        if callable(clear_hook):
            clear_hook(board, reset_drag)
            return
        (
            board._focus_handle_frame,
            board._focus_handle_items,
            board._focus_crop_layout,
        ) = clear_crop_handle_items(
            board._scene,
            board._focus_handle_frame,
            board._focus_handle_items,
        )
        if reset_drag:
            board._focus_crop_drag = None

    def crop_handles_active(self) -> bool:
        return self.selected_scene_tool_id() != ""

    def refresh_scene_handles(self) -> None:
        scene_runtime = self.scene_tool_runtime()
        refresh_hook = getattr(scene_runtime, "refresh_handles", None) if scene_runtime is not None else None
        if callable(refresh_hook):
            refresh_hook(self.board)
            return
        self.clear_crop_handles(reset_drag=False)

    def on_scene_tool_panel_changed(self, tool_id: str) -> None:
        scene_runtime = self.scene_tool_runtime(tool_id)
        panel_hook = getattr(scene_runtime, "panel_value_changed", None) if scene_runtime is not None else None
        if callable(panel_hook):
            panel_hook(self.board)
            return
        self.board._on_edit_image_tool_panel_changed(
            tool_id,
            insert_at=getattr(get_edit_tool(tool_id), "stack_insert_at", None),
        )

    def handle_view_mouse_press(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        scene_runtime = self.scene_tool_runtime()
        handler = getattr(scene_runtime, "mouse_press", None) if scene_runtime is not None else None
        if callable(handler):
            return bool(handler(self.board, scene_pos, event))
        return False

    def handle_view_mouse_move(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        scene_runtime = self.scene_tool_runtime()
        handler = getattr(scene_runtime, "mouse_move", None) if scene_runtime is not None else None
        if callable(handler):
            return bool(handler(self.board, scene_pos, event))
        return False

    def handle_view_mouse_release(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        scene_runtime = self.scene_tool_runtime()
        handler = getattr(scene_runtime, "mouse_release", None) if scene_runtime is not None else None
        if callable(handler):
            return bool(handler(self.board, scene_pos, event))
        return False

    def set_current_crop(
        self,
        left: float,
        top: float,
        right: float,
        bottom: float,
        *,
        schedule_preview: bool = True,
    ) -> None:
        board = self.board
        left, top, right, bottom = sanitize_crop(left, top, right, bottom)
        board._edit_crop_left = left
        board._edit_crop_top = top
        board._edit_crop_right = right
        board._edit_crop_bottom = bottom
        self.w.board_page.set_image_tool_panel_state(
            "crop",
            {"left": left, "top": top, "right": right, "bottom": bottom},
        )
        board._set_tool_state_in_stack(
            "crop",
            {"left": left, "top": top, "right": right, "bottom": bottom},
            add_if_missing=True,
        )
        self.apply_crop_to_focus_item()
        if isinstance(board._focus_item, BoardImageItem):
            board._commit_current_focus_image_override()
            if schedule_preview:
                board._schedule_focus_image_preview()
        elif isinstance(board._focus_item, BoardVideoItem):
            board._commit_current_focus_video_override()
            if schedule_preview:
                board._schedule_video_focus_preview(board._edit_video_playhead, immediate=True)

    def enter_focus_mode(self, item: QtWidgets.QGraphicsItem) -> None:
        board = self.board
        if board._focus_item is item:
            return
        self.exit_focus_mode()
        board._focus_item = item
        try:
            self.w.board_page.view.setFocus()
        except Exception as exc:
            self._log_debug("Failed to focus board view", exc)
        scene = board._scene
        for obj in scene.items():
            if obj is item:
                continue
            board._focus_saved[id(obj)] = (obj.isEnabled(), obj.opacity())
            obj.setEnabled(False)
            obj.setOpacity(0.15)
        board._refresh_scene_workspace(extra_rect=item.sceneBoundingRect())
        overlay = QtWidgets.QGraphicsRectItem(scene.sceneRect())
        overlay.setBrush(QtGui.QColor(0, 0, 0, 120))
        overlay.setPen(QtCore.Qt.PenStyle.NoPen)
        overlay.setZValue(9_000)
        scene.addItem(overlay)
        board._focus_overlay = overlay
        item.setZValue(10_000)
        self.w.board_page.set_edit_panel_visible(True)
        board._edit_focus_kind = str(item.data(0) or "")
        self.refresh_scene_handles()

    def exit_focus_mode(self) -> None:
        board = self.board
        if board._focus_item is None:
            return
        self.clear_crop_handles()
        for obj in board._scene.items():
            saved = board._focus_saved.pop(id(obj), None)
            if saved is not None:
                enabled, opacity = saved
                obj.setEnabled(enabled)
                obj.setOpacity(opacity)
        if board._focus_overlay is not None:
            board._scene.removeItem(board._focus_overlay)
            board._focus_overlay = None
        if board._focus_item is not None:
            if isinstance(board._focus_item, BoardImageItem):
                filename = str(board._focus_item.data(1) or "").strip()
                if not filename or filename not in board._image_exr_display_overrides:
                    board._focus_item.set_override_pixmap(None)
                    board._focus_item.set_crop_norm(*board._default_crop_settings())
            if isinstance(board._focus_item, BoardVideoItem):
                filename = str(board._focus_item.data(1) or "").strip()
                override = board._image_exr_display_overrides.get(filename)
                if isinstance(override, dict):
                    board._apply_override_to_video_item(board._focus_item, override)
                else:
                    board._focus_item.set_override_pixmap(None)
                    board._focus_item.set_crop_norm(*board._default_crop_settings())
            if isinstance(board._focus_item, BoardSequenceItem):
                board._focus_item.set_override_pixmap(None)
            board._focus_item.setZValue(0)
        board._focus_item = None
        board._reset_edit_session_for_kind("")
        board._edit_timeline_scrubbing = False
        board._sequence_playback.stop()
        board._video_playback.stop()
        self.w.board_page.edit_timeline_play_btn.setText(play_button_label(False))
        if board._video_preview_timer is not None and board._video_preview_timer.isActive():
            board._video_preview_timer.stop()
        board._video_preview_pending = None
        board._release_focus_video_cap()
        if board._edit_preview_timer is not None and board._edit_preview_timer.isActive():
            board._edit_preview_timer.stop()
        board._edit_preview_timer = None
        board._edit_preview_pending_channel = None
        board._edit_preview_dragging = False
        board._edit_exr_preview_pending_channel = None
        board._edit_exr_preview_pending_max_dim = 0
        board._edit_image_preview_pending_path = None
        board._edit_image_preview_pending_max_dim = 0
        self._stop_edit_thread("_edit_exr_thread")
        board._edit_exr_preview_busy = False
        board._edit_exr_thread = None
        board._edit_exr_worker = None
        self._stop_edit_thread("_edit_image_thread")
        board._edit_image_preview_busy = False
        board._edit_image_thread = None
        board._edit_image_worker = None
        board._edit_image_path = None
        board._edit_exr_path = None
        self.w.board_page.set_image_adjust_controls_visible(False)
        self.w.board_page.set_edit_panel_visible(False)
        self.w.board_page.set_timeline_bar_visible(False)
        self.w.board_page.set_edit_preview_visible(True)

    def ensure_video_cap(self) -> None:
        board = self.board
        if cv2 is None:
            return
        if board._focus_video_path is None:
            return
        if board._focus_video_cap is not None:
            return
        try:
            cap = cv2.VideoCapture(str(board._focus_video_path))
            if cap.isOpened():
                board._focus_video_cap = cap
                board._focus_video_cap_frame_index = -1
        except Exception:
            board._focus_video_cap = None
            board._focus_video_cap_frame_index = -1
            logger.debug("Failed to open focus video capture", exc_info=True)

    def release_video_cap(self) -> None:
        board = self.board
        try:
            if board._focus_video_cap is not None:
                board._focus_video_cap.release()
        except Exception as exc:
            self._log_debug("Failed to release focus video capture", exc)
        board._focus_video_cap = None
        board._focus_video_cap_frame_index = -1

    def schedule_video_preview(self, frame_index: int, delay_ms: int = 40, immediate: bool = False) -> None:
        board = self.board
        board._video_preview_pending = int(frame_index)
        if board._video_preview_timer is None:
            board._video_preview_timer = QtCore.QTimer(self.w)
            board._video_preview_timer.setSingleShot(True)
            board._video_preview_timer.timeout.connect(self.flush_video_preview)
        if immediate:
            if board._video_preview_timer.isActive():
                board._video_preview_timer.stop()
            self.flush_video_preview()
            return
        if not board._video_preview_timer.isActive():
            board._video_preview_timer.start(max(10, int(delay_ms)))

    def flush_video_preview(self) -> None:
        board = self.board
        if board._video_preview_pending is None:
            return
        idx = board._video_preview_pending
        board._video_preview_pending = None
        if not isinstance(board._focus_item, BoardVideoItem):
            return
        self.ensure_video_cap()
        max_dim = board._edit_video_playback_dim if board._video_playback.is_playing() else board._max_display_dim
        pixmap = self.get_video_frame_pixmap(
            idx,
            max_dim=max_dim,
            prefer_fast=board._video_playback.is_playing(),
        )
        if pixmap is not None:
            board._focus_item.set_override_pixmap(pixmap)

    def get_video_frame_pixmap(
        self,
        frame_index: int,
        max_dim: int,
        prefer_fast: bool = False,
    ) -> QtGui.QPixmap | None:
        board = self.board
        if cv2 is None:
            return None
        if board._focus_video_cap is None:
            return None
        try:
            target_frame = max(0, int(frame_index))
            sequential_read = target_frame == (board._focus_video_cap_frame_index + 1)
            if not sequential_read:
                board._focus_video_cap.set(1, target_frame)  # CAP_PROP_POS_FRAMES
            ok, frame = board._focus_video_cap.read()
            if not ok or frame is None:
                return None
            board._focus_video_cap_frame_index = target_frame
            if max_dim > 0:
                h, w = frame.shape[:2]
                largest_dim = max(w, h)
                if largest_dim > max_dim:
                    scale = float(max_dim) / float(largest_dim)
                    new_size = (
                        max(1, int(round(w * scale))),
                        max(1, int(round(h * scale))),
                    )
                    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                    frame = cv2.resize(frame, new_size, interpolation=interpolation)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
            pixmap = QtGui.QPixmap.fromImage(image.copy())
            if not prefer_fast and max_dim > 0 and (pixmap.width() > max_dim or pixmap.height() > max_dim):
                pixmap = pixmap.scaled(
                    max_dim,
                    max_dim,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            return pixmap
        except Exception as exc:
            self._log_debug("Failed to read focus video frame", exc)
            return None
