from __future__ import annotations

import logging

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_edit.media_runtime import play_button_label
from core.board_scene.items import BoardImageItem, BoardSequenceItem, BoardVideoItem
from tools.board_tools.edit import get_edit_tool
from tools.board_tools.registry import get_board_tool, get_board_tool_scene_runtime, list_board_tools

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional video backend
    cv2 = None  # type: ignore


logger = logging.getLogger(__name__)


class BoardEditFocusController:
    """Owns Board edit focus mode and scene-tool interactions."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.edit = board_controller.edit_context
        self.w = board_controller.w
        self._active_scene_tool_id = ""
        self._scene_tool_states: dict[str, object] = {}

    def scene_tool_state(self, tool_id: str, factory: object) -> object:
        key = str(tool_id or "").strip().lower()
        if not key:
            raise ValueError("tool_id is required")
        if key not in self._scene_tool_states:
            if not callable(factory):
                raise TypeError("factory must be callable")
            self._scene_tool_states[key] = factory()
        return self._scene_tool_states[key]

    def focus_item(self) -> QtWidgets.QGraphicsItem | None:
        item = self.board._focus_item
        return item if isinstance(item, QtWidgets.QGraphicsItem) else None

    def graphics_scene(self) -> QtWidgets.QGraphicsScene:
        return self.board._scene

    def selected_tool_panel(self) -> str:
        return self.board._selected_tool_panel()

    def tool_panel_state(self, tool_id: str) -> dict[str, object]:
        return self.board._tool_panel_state_for_id(tool_id)

    def set_tool_panel_state(self, tool_id: str, state: dict[str, object]) -> None:
        spec = get_edit_tool(tool_id)
        panel = str(getattr(spec, "ui_panel", "") or "").strip().lower() if spec is not None else ""
        if panel:
            self.w.board_page.set_image_tool_panel_state(panel, state)

    def set_tool_stack_state(self, tool_id: str, state: dict[str, object], *, add_if_missing: bool = True) -> None:
        self.board._set_tool_state_in_stack(tool_id, state, add_if_missing=add_if_missing)
        self.board._sync_edit_values_from_tool_stack()

    def update_scene_tool_settings(
        self,
        tool_id: str,
        settings: dict[str, object],
        *,
        schedule_preview: bool = True,
    ) -> None:
        spec = get_edit_tool(tool_id)
        normalized = spec.normalize_state(settings) if spec is not None else dict(settings)
        self.set_tool_panel_state(tool_id, normalized)
        self.set_tool_stack_state(tool_id, normalized, add_if_missing=True)
        self.apply_scene_tool_to_focus_item()
        self.commit_focus_override()
        if schedule_preview:
            self.schedule_focus_preview()

    def find_group_for_item(self, item: QtWidgets.QGraphicsItem | None) -> object | None:
        if item is None:
            return None
        return self.board._find_group_for_item(item)

    def refresh_workspace(self, extra_rect: QtCore.QRectF | None = None) -> None:
        self.board._refresh_scene_workspace(extra_rect=extra_rect)

    def commit_focus_override(self) -> None:
        item = self.focus_item()
        if isinstance(item, BoardImageItem):
            self.board._commit_current_focus_image_override()
        elif isinstance(item, BoardVideoItem):
            self.board._commit_current_focus_video_override()

    def schedule_focus_preview(self) -> None:
        item = self.focus_item()
        if isinstance(item, BoardVideoItem):
            self.board._schedule_video_focus_preview(self.board._edit_video_playhead, immediate=True)
            return
        if isinstance(item, BoardImageItem):
            if self.board._edit_exr_path is not None:
                channel = self.w.board_page.current_exr_channel_value()
                if channel:
                    self.board._edit_exr_channel = str(channel)
                    self.board._schedule_edit_preview_update(channel=str(channel))
                return
            self.board._schedule_edit_preview_update()

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

    def apply_scene_tool_to_focus_item(self) -> None:
        for tool_id in self.scene_tool_stack_ids():
            scene_runtime = self.scene_tool_runtime(tool_id)
            apply_hook = getattr(scene_runtime, "apply_to_focus_item", None) if scene_runtime is not None else None
            if callable(apply_hook):
                apply_hook(self)

    def reset_scene_tool_state_for_focus_item(self) -> None:
        for tool in list_board_tools():
            if not bool(getattr(tool, "has_scene", False)):
                continue
            scene_runtime = get_board_tool_scene_runtime(getattr(tool, "tool_id", ""))
            reset_hook = getattr(scene_runtime, "reset_focus_item", None) if scene_runtime is not None else None
            if callable(reset_hook):
                reset_hook(self)

    def scene_tool_stack_ids(self) -> list[str]:
        result: list[str] = []
        for entry in self.edit.stack:
            if not isinstance(entry, dict):
                continue
            tool_id = str(entry.get("id", "")).strip().lower()
            if not tool_id or tool_id in result:
                continue
            tool_caps = get_board_tool(tool_id)
            if tool_caps is not None and tool_caps.has_scene:
                result.append(tool_id)
        selected = self.selected_scene_tool_id()
        if selected and selected not in result:
            result.append(selected)
        return result

    def selected_scene_tool_id(self) -> str:
        selected = self.edit.selected_tool_entry()
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

    def clear_scene_tool_handles(self, *, reset_drag: bool = True) -> None:
        tool_id = self.selected_scene_tool_id() or self._active_scene_tool_id
        scene_runtime = self.scene_tool_runtime(tool_id)
        clear_hook = getattr(scene_runtime, "clear_handles", None) if scene_runtime is not None else None
        if callable(clear_hook):
            clear_hook(self, reset_drag)
        if reset_drag or not self.selected_scene_tool_id():
            self._active_scene_tool_id = ""

    def scene_tool_handles_active(self) -> bool:
        return self.selected_scene_tool_id() != ""

    def refresh_scene_handles(self) -> None:
        selected_tool_id = self.selected_scene_tool_id()
        if self._active_scene_tool_id and self._active_scene_tool_id != selected_tool_id:
            self.clear_scene_tool_handles(reset_drag=True)
        self._active_scene_tool_id = selected_tool_id
        scene_runtime = self.scene_tool_runtime()
        refresh_hook = getattr(scene_runtime, "refresh_handles", None) if scene_runtime is not None else None
        if callable(refresh_hook):
            refresh_hook(self)
            return
        self.clear_scene_tool_handles(reset_drag=False)

    def on_scene_tool_panel_changed(self, tool_id: str) -> None:
        scene_runtime = self.scene_tool_runtime(tool_id)
        panel_hook = getattr(scene_runtime, "panel_value_changed", None) if scene_runtime is not None else None
        if callable(panel_hook):
            self._active_scene_tool_id = str(tool_id or "").strip().lower()
            panel_hook(self)
            return
        self.board._on_edit_image_tool_panel_changed(
            tool_id,
            insert_at=getattr(get_edit_tool(tool_id), "stack_insert_at", None),
        )

    def handle_view_mouse_press(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        scene_runtime = self.scene_tool_runtime()
        handler = getattr(scene_runtime, "mouse_press", None) if scene_runtime is not None else None
        if callable(handler):
            return bool(handler(self, scene_pos, event))
        return False

    def handle_view_mouse_move(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        scene_runtime = self.scene_tool_runtime()
        handler = getattr(scene_runtime, "mouse_move", None) if scene_runtime is not None else None
        if callable(handler):
            return bool(handler(self, scene_pos, event))
        return False

    def handle_view_mouse_release(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        scene_runtime = self.scene_tool_runtime()
        handler = getattr(scene_runtime, "mouse_release", None) if scene_runtime is not None else None
        if callable(handler):
            return bool(handler(self, scene_pos, event))
        return False

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
        self.edit.focus_kind = str(item.data(0) or "")
        self.refresh_scene_handles()

    def exit_focus_mode(self) -> None:
        board = self.board
        if board._focus_item is None:
            return
        self.clear_scene_tool_handles()
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
                    self.reset_scene_tool_state_for_focus_item()
            if isinstance(board._focus_item, BoardVideoItem):
                filename = str(board._focus_item.data(1) or "").strip()
                override = board._image_exr_display_overrides.get(filename)
                if isinstance(override, dict):
                    board._apply_override_to_video_item(board._focus_item, override)
                else:
                    board._focus_item.set_override_pixmap(None)
                    self.reset_scene_tool_state_for_focus_item()
            if isinstance(board._focus_item, BoardSequenceItem):
                board._focus_item.set_override_pixmap(None)
            board._focus_item.setZValue(0)
        board._focus_item = None
        self.edit.reset_for_kind("")
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
