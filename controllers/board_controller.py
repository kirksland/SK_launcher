from __future__ import annotations

import os
import json
import time
import uuid
import shutil
import urllib.request
from collections import deque
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from core.board_edit.crop_scene import (
    apply_crop_to_item,
    begin_crop_handle_drag,
    clear_crop_handle_items,
    create_crop_handle_items,
    crop_handles_active,
    crop_values_from_drag,
)
from core.board_edit.handles import (
    CropHandleDragState,
    CropHandleLayout,
    sanitize_crop,
)
from core.board_edit.panels import default_panel_state, normalize_panel_state, panel_state_map_for_tools
from core.board_edit.media_runtime import (
    SequencePlaybackRuntime,
    VideoPlaybackRuntime,
    clamp_playhead,
    frame_label_text,
    loop_next_playhead,
    play_button_label,
)
from core.board_edit.workers import (
    ExrChannelPreviewWorker,
    ExrInfoWorker,
    ImageAdjustPreviewWorker,
    UiBridge,
    VideoSegmentWorker,
    VideoToSequenceWorker,
)
from core.board_edit.session import (
    EditSessionState,
    EditVisualState,
    coerce_color_adjustments,
    default_tool_stack_for_kind,
    tool_stack_from_override,
)
from core.board_edit.tool_stack import (
    append_tool,
    make_tool_entry,
    move_tool,
    normalize_tool_entries,
    remove_tool_at,
    tool_stack_is_effective,
    upsert_tool_settings,
)
from core.board_apply_runtime import BoardApplyRuntime
from core.board_io import backup_board_payload, board_path, load_board_payload, save_board_payload
from core.board_media_cache import BoardMediaCache
from controllers.board_group_actions_controller import BoardGroupActionsController
from controllers.board_groups_controller import BoardGroupsController
from core.board_state import (
    ApplyPayloadState,
    apply_exr_preview_result,
    apply_image_adjust_preview_result,
    apply_pending_groups_to_scene,
    apply_image_override_to_item,
    apply_preview_payload_to_item,
    apply_video_override_to_item,
    build_group_item,
    build_scene_item_from_entry,
    clone_payload,
    commit_image_override,
    commit_video_override,
    parse_image_display_overrides,
    payload_item_count,
    preview_payload_to_pixmap,
    prepare_apply_state,
    rename_override_key,
    reapply_scene_overrides,
    register_built_item,
    sync_board_state_overrides,
)
from core.board_scene.dialogs import NoteTextEditor, PopupOutsideCloseFilter
from core.board_scene.groups import (
    build_rename_destination,
    collapse_items_by_group,
    serialize_group_members,
)
from core.board_scene.items import BoardGroupItem, BoardImageItem, BoardNoteItem, BoardSequenceItem, BoardVideoItem
from core.houdini_env import build_houdini_env
from tools.board_tools.edit import available_tools_for_kind, discover_edit_tools, get_edit_tool, list_edit_tools
from tools.board_tools.image import apply_image_tool_stack, build_bcs_stack, normalize_tool_stack
from tools.board_tools.registry import get_board_tool, get_board_tool_scene_runtime
from video.player import VideoController

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional video backend
    cv2 = None  # type: ignore

try:  # Optional OpenEXR header access for channels/metadata.
    import OpenEXR  # type: ignore
    import Imath  # type: ignore
except Exception:  # pragma: no cover - optional exr backend
    OpenEXR = None  # type: ignore
    Imath = None  # type: ignore

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".exr"}
PIC_EXTS = {".pic", ".picnc"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _sanitize_crop_settings(left: float, top: float, right: float, bottom: float) -> tuple[float, float, float, float]:
    return sanitize_crop(left, top, right, bottom)


class BoardController:
    def __init__(self, window: QtWidgets.QMainWindow) -> None:
        self.w = window
        self._project_root: Optional[Path] = None
        self._loaded_project_root: Optional[Path] = None
        self._board_state_loaded: bool = False
        self._dirty = False
        self._loading = False
        self._saving = False
        self._last_save_ts = 0.0
        self._board_state: dict = {"items": [], "image_display_overrides": {}}
        self._media_cache = BoardMediaCache(max_display_dim=2048)
        self._history: list[str] = []
        self._history_index = -1
        self._history_timer: Optional[QtCore.QTimer] = None
        self._post_load_reapply_timer: Optional[QtCore.QTimer] = None
        self._apply_state = ApplyPayloadState()
        self._apply_runtime = BoardApplyRuntime(self.w, self._apply_state, self._apply_payload_batch)
        self._scene_interaction_depth = 0
        self._convert_thread: Optional[QtCore.QThread] = None
        self._convert_worker: Optional[VideoToSequenceWorker] = None
        self._convert_dialog: Optional[QtWidgets.QProgressDialog] = None
        self._edit_video_controller: Optional[VideoController] = None
        self._edit_seq_frames: list[Path] = []
        self._edit_seq_dir: Optional[Path] = None
        self._edit_seq_fps: int = 24
        self._edit_video_fps: float = 24.0
        self._edit_video_playback_dim: int = 960
        self._edit_video_path: Optional[Path] = None
        self._edit_video_total: int = 0
        self._edit_video_playhead: int = 0
        self._edit_video_clips: list[tuple[int, int]] = []
        self._edit_selected_clip: int = -1
        self._edit_timeline_scrubbing: bool = False
        self._edit_exr_path: Optional[Path] = None
        self._edit_exr_channels: list[str] = []
        self._edit_exr_thread: Optional[QtCore.QThread] = None
        self._edit_exr_worker: Optional[ExrChannelPreviewWorker] = None
        self._edit_exr_gamma: float = 2.2
        self._edit_exr_srgb: bool = True
        self._edit_exr_channel: Optional[str] = None
        self._edit_session = EditSessionState()
        self._edit_image_path: Optional[Path] = None
        self._edit_tool_specs = discover_edit_tools()
        self._edit_tool_defs: list[tuple[str, str]] = []
        self._edit_image_thread: Optional[QtCore.QThread] = None
        self._edit_image_worker: Optional[ImageAdjustPreviewWorker] = None
        self._edit_preview_timer: Optional[QtCore.QTimer] = None
        self._edit_preview_pending_channel: Optional[str] = None
        self._edit_preview_dragging: bool = False
        self._edit_preview_fast_dim: int = 640
        self._edit_preview_full_dim: int = 1280
        self._edit_exr_preview_busy: bool = False
        self._edit_exr_preview_pending_channel: Optional[str] = None
        self._edit_exr_preview_pending_max_dim: int = 0
        self._edit_image_preview_busy: bool = False
        self._edit_image_preview_pending_path: Optional[Path] = None
        self._edit_image_preview_pending_max_dim: int = 0
        self._image_exr_display_overrides: dict[str, dict[str, object]] = {}
        self._exr_item_preview_threads: list[QtCore.QThread] = []
        self._exr_item_preview_workers: list[QtCore.QObject] = []
        self._ui_bridge = UiBridge(self, self.w)
        self._segment_thread: Optional[QtCore.QThread] = None
        self._segment_worker: Optional[VideoSegmentWorker] = None
        self._segment_dialog: Optional[QtWidgets.QProgressDialog] = None
        self._sequence_playback = SequencePlaybackRuntime(self.w)
        self._sequence_playback.tick.connect(self._advance_edit_sequence_frame)
        self._sequence_playback.stateChanged.connect(self._on_sequence_play_state_changed)
        self._video_playback = VideoPlaybackRuntime(self.w)
        self._video_playback.tick.connect(self._advance_edit_video_frame)
        self._video_playback.stateChanged.connect(self._on_video_play_state_changed)
        self._scene = self.w.board_page.scene
        self._scene.changed.connect(self._on_scene_changed)
        self._scene.selectionChanged.connect(self._on_scene_selection_changed)
        self._group_actions = BoardGroupActionsController(self)
        self._groups_panel = BoardGroupsController(self)
        self.w.board_page.edit_timeline_play_btn.clicked.connect(self._toggle_edit_timeline_play)
        self.w.board_page.edit_sequence_timeline.playheadChanged.connect(self._on_edit_sequence_timeline_playhead)
        self.w.board_page.edit_timeline.playheadChanged.connect(self._on_edit_timeline_playhead)
        self.w.board_page.edit_timeline.scrubStateChanged.connect(self._on_edit_timeline_scrub_state)
        self.w.board_page.edit_timeline.selectedClipChanged.connect(self._on_edit_timeline_selected)
        self.w.board_page.edit_timeline_split_btn.clicked.connect(self._split_edit_clip)
        self.w.board_page.edit_timeline_export_btn.clicked.connect(self._export_edit_clip)
        self.w.board_page.edit_exr_channel_combo.currentIndexChanged.connect(self._on_edit_exr_channel_changed)
        self.w.board_page.edit_exr_gamma_slider.valueChanged.connect(self._on_edit_exr_gamma_changed)
        self.w.board_page.edit_exr_srgb_check.toggled.connect(self._on_edit_exr_gamma_changed)
        self._connect_edit_tool_panel_signals()
        self.w.board_page.edit_exr_gamma_slider.sliderPressed.connect(self._on_edit_preview_slider_pressed)
        self.w.board_page.edit_exr_gamma_slider.sliderReleased.connect(self._on_edit_preview_slider_released)
        self.w.board_page.edit_image_adjust_reset_btn.clicked.connect(self._reset_edit_image_adjustments)
        self.w.board_page.edit_image_tool_list.currentRowChanged.connect(self._on_edit_tool_stack_selection_changed)
        self.w.board_page.imageToolAddRequested.connect(self._on_edit_tool_stack_add_clicked)
        self.w.board_page.imageToolRemoveRequested.connect(self._on_edit_tool_stack_remove_index)
        self.w.board_page.edit_image_tool_up_btn.clicked.connect(self._on_edit_tool_stack_up_clicked)
        self.w.board_page.edit_image_tool_down_btn.clicked.connect(self._on_edit_tool_stack_down_clicked)
        self._focus_item: Optional[QtWidgets.QGraphicsItem] = None
        self._focus_overlay: Optional[QtWidgets.QGraphicsRectItem] = None
        self._focus_handle_frame: Optional[QtWidgets.QGraphicsRectItem] = None
        self._focus_handle_items: dict[str, QtWidgets.QGraphicsRectItem] = {}
        self._focus_crop_layout: Optional[CropHandleLayout] = None
        self._focus_crop_drag: Optional[CropHandleDragState] = None
        self._focus_saved: dict[int, tuple[bool, float]] = {}
        self._focus_video_path: Optional[Path] = None
        self._focus_video_cap = None
        self._focus_video_cap_frame_index: int = -1
        self._video_preview_timer: Optional[QtCore.QTimer] = None
        self._video_preview_pending: Optional[int] = None
        self._shutting_down: bool = False

    def refresh_edit_tool_registry(self) -> dict[str, object]:
        self._edit_tool_specs = discover_edit_tools(force=True)
        self._sync_edit_tool_defs_for_kind(str(self._edit_focus_kind or "image"))
        return dict(self._edit_tool_specs)

    def available_edit_tools(self, media_kind: str) -> list[dict[str, object]]:
        return [
            {
                "id": spec.id,
                "label": spec.label,
                "supports": tuple(spec.supports),
                "tags": tuple(spec.tags),
            }
            for spec in available_tools_for_kind(media_kind)
        ]

    def default_edit_tool_state(self, tool_id: str) -> dict[str, object]:
        spec = get_edit_tool(tool_id)
        if spec is None:
            return {}
        return {
            "id": spec.id,
            "enabled": True,
            "settings": dict(spec.default_state()),
        }

    def normalize_edit_tool_state(self, entry: object) -> dict[str, object]:
        entries = normalize_tool_entries([entry])
        return entries[0] if entries else {}

    def _sync_edit_tool_defs_for_kind(self, media_kind: str) -> None:
        tools = available_tools_for_kind(media_kind)
        self._edit_tool_defs = [(spec.id, spec.label) for spec in tools]

    def _reset_edit_session_for_kind(self, media_kind: str) -> None:
        self.edit_session.focus_kind = str(media_kind or "").strip().lower() or None
        self.edit_session.tool_stack = []
        self.edit_session.selected_tool_index = -1
        self.edit_session.reset_visual_adjustments()

    def _stop_qthread(self, thread: Optional[QtCore.QThread], timeout_ms: int = 1000) -> None:
        if thread is None:
            return
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(int(timeout_ms))
        except Exception:
            pass

    @property
    def edit_session(self) -> EditSessionState:
        return self._edit_session

    @property
    def _edit_focus_kind(self) -> Optional[str]:
        return self._edit_session.focus_kind

    @_edit_focus_kind.setter
    def _edit_focus_kind(self, value: Optional[str]) -> None:
        self._edit_session.focus_kind = str(value) if value is not None else None

    @property
    def _edit_tool_stack(self) -> list[dict[str, object]]:
        return self._edit_session.tool_stack

    @_edit_tool_stack.setter
    def _edit_tool_stack(self, value: list[dict[str, object]]) -> None:
        self._edit_session.tool_stack = list(value) if isinstance(value, list) else []

    @property
    def _edit_selected_tool_index(self) -> int:
        return int(self._edit_session.selected_tool_index)

    @_edit_selected_tool_index.setter
    def _edit_selected_tool_index(self, value: int) -> None:
        try:
            self._edit_session.selected_tool_index = int(value)
        except Exception:
            self._edit_session.selected_tool_index = -1

    @property
    def _edit_image_brightness(self) -> float:
        return float(self._edit_session.image_brightness)

    @_edit_image_brightness.setter
    def _edit_image_brightness(self, value: float) -> None:
        self._edit_session.image_brightness = float(value)

    @property
    def _edit_image_contrast(self) -> float:
        return float(self._edit_session.image_contrast)

    @_edit_image_contrast.setter
    def _edit_image_contrast(self, value: float) -> None:
        self._edit_session.image_contrast = float(value)

    @property
    def _edit_image_saturation(self) -> float:
        return float(self._edit_session.image_saturation)

    @_edit_image_saturation.setter
    def _edit_image_saturation(self, value: float) -> None:
        self._edit_session.image_saturation = float(value)

    @property
    def _edit_image_vibrance(self) -> float:
        return float(self._edit_session.image_vibrance)

    @_edit_image_vibrance.setter
    def _edit_image_vibrance(self, value: float) -> None:
        self._edit_session.image_vibrance = float(value)

    @property
    def _edit_crop_left(self) -> float:
        return float(self._edit_session.crop_left)

    @_edit_crop_left.setter
    def _edit_crop_left(self, value: float) -> None:
        self._edit_session.crop_left = float(value)

    @property
    def _edit_crop_top(self) -> float:
        return float(self._edit_session.crop_top)

    @_edit_crop_top.setter
    def _edit_crop_top(self, value: float) -> None:
        self._edit_session.crop_top = float(value)

    @property
    def _edit_crop_right(self) -> float:
        return float(self._edit_session.crop_right)

    @_edit_crop_right.setter
    def _edit_crop_right(self, value: float) -> None:
        self._edit_session.crop_right = float(value)

    @property
    def _edit_crop_bottom(self) -> float:
        return float(self._edit_session.crop_bottom)

    @_edit_crop_bottom.setter
    def _edit_crop_bottom(self, value: float) -> None:
        self._edit_session.crop_bottom = float(value)

    @property
    def _max_display_dim(self) -> int:
        return self._media_cache.max_display_dim

    @_max_display_dim.setter
    def _max_display_dim(self, value: int) -> None:
        self._media_cache.max_display_dim = int(value)

    @property
    def _low_quality(self) -> bool:
        return self._media_cache.low_quality

    @_low_quality.setter
    def _low_quality(self, value: bool) -> None:
        self._media_cache.low_quality = bool(value)

    @property
    def _visible_images(self) -> set[int]:
        return self._media_cache.visible_images

    @_visible_images.setter
    def _visible_images(self, value: set[int]) -> None:
        self._media_cache.visible_images = set(value)

    def _log_export_event(self, message: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[EXPORT] {stamp} {message}"
        print(line)
        try:
            log_path = Path(__file__).resolve().parents[1] / "board_export.log"
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            pass

    @staticmethod
    def _clone_payload(payload: Optional[dict]) -> dict:
        return clone_payload(payload)

    def _sync_board_state_from_scene(self) -> dict:
        payload = self._build_payload()
        self._board_state = self._clone_payload(payload)
        return self._clone_payload(self._board_state)

    def _current_board_state(self) -> dict:
        return self._clone_payload(self._board_state)

    def _set_board_state(self, payload: Optional[dict]) -> dict:
        self._board_state = self._clone_payload(payload)
        return self._clone_payload(self._board_state)

    def _sync_board_state_overrides(self) -> dict:
        self._board_state = sync_board_state_overrides(self._board_state, self._image_exr_display_overrides)
        return self._clone_payload(self._board_state)

    def _commit_scene_mutation(
        self,
        *,
        history: bool = True,
        save: bool = False,
        reveal_items: Optional[list[QtWidgets.QGraphicsItem]] = None,
        update_groups: bool = True,
    ) -> dict:
        if update_groups:
            self._schedule_group_tree_update()
        state = self._sync_board_state_from_scene()
        self._refresh_scene_workspace()
        self._dirty = True
        if history:
            self._schedule_history_snapshot()
        if reveal_items:
            self._reveal_scene_items(reveal_items)
        if save:
            self.save_board()
        return state

    def begin_scene_interaction(self) -> None:
        self._scene_interaction_depth += 1

    def end_scene_interaction(self, *, history: bool = True, update_groups: bool = True) -> dict:
        if self._scene_interaction_depth > 0:
            self._scene_interaction_depth -= 1
        if self._scene_interaction_depth > 0:
            return self._clone_payload(self._board_state)
        return self._commit_scene_mutation(history=history, update_groups=update_groups)

    def ensure_board_loaded(self) -> None:
        if self._project_root is None:
            return
        if self._board_state_loaded and self._loaded_project_root == self._project_root:
            return
        self.w.board_page.project_label.setText(f"Project: {self._project_root.name} (loading...)")
        self.load_board()

    def _board_page_is_active(self) -> bool:
        pages = getattr(self.w, "pages", None)
        if pages is None:
            return False
        try:
            return int(pages.currentIndex()) == 2
        except Exception:
            return False

    def _ui_alive(self) -> bool:
        if self._shutting_down:
            return False
        try:
            _ = self.w.board_page.groups_tree
            return self._scene_alive()
        except Exception:
            return False

    def _scene_alive(self) -> bool:
        if self._shutting_down:
            return False
        try:
            _ = self._scene.views()
            return True
        except Exception:
            return False

    def _group_tree_is_editing(self) -> bool:
        return self._groups_panel.is_editing()

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            self._scene.changed.disconnect(self._on_scene_changed)
        except Exception:
            pass
        try:
            self._scene.selectionChanged.disconnect(self._on_scene_selection_changed)
        except Exception:
            pass
        self._groups_panel.shutdown()
        try:
            if self._history_timer is not None and self._history_timer.isActive():
                self._history_timer.stop()
        except Exception:
            pass
        self._history_timer = None
        try:
            if self._post_load_reapply_timer is not None and self._post_load_reapply_timer.isActive():
                self._post_load_reapply_timer.stop()
        except Exception:
            pass
        self._post_load_reapply_timer = None
        self._apply_runtime.cancel()
        try:
            if self._edit_preview_timer is not None and self._edit_preview_timer.isActive():
                self._edit_preview_timer.stop()
        except Exception:
            pass
        self._edit_preview_timer = None
        try:
            if self._video_preview_timer is not None and self._video_preview_timer.isActive():
                self._video_preview_timer.stop()
        except Exception:
            pass
        self._video_preview_timer = None
        self._stop_qthread(self._convert_thread, timeout_ms=1500)
        self._convert_thread = None
        self._convert_worker = None
        self._stop_qthread(self._segment_thread, timeout_ms=1500)
        self._segment_thread = None
        self._segment_worker = None
        self._stop_qthread(self._edit_exr_thread, timeout_ms=1000)
        self._edit_exr_thread = None
        self._edit_exr_worker = None
        try:
            info_thread = getattr(self.w.board_page, "_edit_exr_thread", None)
            self._stop_qthread(info_thread, timeout_ms=1000)
            self.w.board_page._edit_exr_thread = None  # type: ignore[attr-defined]
            self.w.board_page._edit_exr_worker = None  # type: ignore[attr-defined]
        except Exception:
            pass
        self._stop_qthread(self._edit_image_thread, timeout_ms=1000)
        self._edit_image_thread = None
        self._edit_image_worker = None
        for thread in list(self._exr_item_preview_threads):
            self._stop_qthread(thread, timeout_ms=800)
        self._exr_item_preview_threads.clear()
        self._exr_item_preview_workers.clear()

    def set_project(self, project_root: Optional[Path]) -> None:
        if project_root is None and self._project_root is not None:
            now = time.time()
            if now - self._last_save_ts < 1.0:
                return
        if self._project_root and self._dirty:
            self.save_board()
        project_changed = project_root != self._project_root
        if project_changed:
            self._cancel_pending_board_load()
            self._media_cache.reset_project_scoped()
        self._project_root = project_root
        enabled = project_root is not None
        self.w.board_add_image_btn.setEnabled(enabled)
        if hasattr(self.w, "board_add_video_btn"):
            self.w.board_add_video_btn.setEnabled(enabled)
        self.w.board_save_btn.setEnabled(enabled)
        self.w.board_load_btn.setEnabled(enabled)
        self.w.board_fit_btn.setEnabled(enabled)
        if project_root:
            base_label = f"Project: {project_root.name}"
            self._apply_state.base_label = base_label
            self.w.board_page.project_label.setText(
                f"{base_label} (loading...)" if self._board_page_is_active() else f"{base_label} (ready)"
            )
            if project_changed:
                self._loaded_project_root = None
                self._board_state_loaded = False
                self._set_board_state({"items": [], "image_display_overrides": {}})
            if self._board_page_is_active():
                self._schedule_board_load()
            if self._history_index < 0:
                self._reset_history(self._current_board_state())
        else:
            self.w.board_page.project_label.setText("No project selected")
            self._scene.clear()
            self._set_board_state({"items": [], "image_display_overrides": {}})
            self._loaded_project_root = None
            self._board_state_loaded = False
        self._dirty = False

    def _cancel_pending_board_load(self) -> None:
        self._apply_runtime.cancel()
        self._loading = False
        try:
            self._scene.blockSignals(False)
        except Exception:
            pass
        if hasattr(self.w.board_page, "set_loading_overlay"):
            self.w.board_page.set_loading_overlay(False)

    def add_image(self) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.w,
            "Add Image",
            str(self._project_root),
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.exr)",
        )
        if not path:
            return
        src = Path(path)
        self.add_image_from_path(src)

    def add_image_from_path(
        self, src: Path, scene_pos: Optional[QtCore.QPointF] = None
    ) -> Optional[QtWidgets.QGraphicsPixmapItem]:
        if not self._project_root:
            print("[BOARD] No project root set")
            return None
        if not src.is_file():
            print(f"[BOARD] Not a file: {src}")
            return None
        assets_dir = self._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / src.name
        print(f"[BOARD] Import image: {src} -> {dest}")
        if src.resolve() != dest.resolve():
            try:
                shutil.copy2(src, dest)
            except Exception as exc:
                print(f"[BOARD] Copy failed: {exc}")
                self._notify(f"Failed to copy image:\n{exc}")
                return None
        item = BoardImageItem(self, dest)
        if item.boundingRect().isNull():
            print("[BOARD] Pixmap is null")
            self._notify("Failed to load image.")
            return None
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setData(0, "image")
        item.setData(1, dest.name)
        if scene_pos is None:
            scene_pos = self._current_view_scene_center()
        item.setPos(scene_pos)
        logical_w = item.boundingRect().width()
        if logical_w > 600:
            scale = 600 / max(1.0, logical_w)
            item.setScale(scale)
        self._scene.addItem(item)
        self._commit_scene_mutation(history=False, update_groups=False)
        self._update_view_quality()
        self.update_visible_items()
        self._schedule_history_snapshot()
        return item

    def add_image_from_url(self, url: str, scene_pos: Optional[QtCore.QPointF] = None) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        confirm = QtWidgets.QMessageBox.question(
            self.w,
            "Import Web Image",
            f"Download and import this image?\n{url}",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        assets_dir = self._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        safe_name = QtCore.QUrl(url).fileName() or f"web_{uuid.uuid4().hex}.png"
        dest = assets_dir / safe_name
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:
            self._notify(f"Failed to download image:\n{exc}")
            return
        self.add_image_from_path(dest, scene_pos=scene_pos)

    def add_image_from_image_data(self, image_data, scene_pos: Optional[QtCore.QPointF] = None) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        confirm = QtWidgets.QMessageBox.question(
            self.w,
            "Import Dropped Image",
            "Import the dropped image into the board?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        image = None
        if isinstance(image_data, QtGui.QImage):
            image = image_data
        elif isinstance(image_data, QtGui.QPixmap):
            image = image_data.toImage()
        if image is None or image.isNull():
            self._notify("Dropped image data is not valid.")
            return
        assets_dir = self._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / f"web_{uuid.uuid4().hex}.png"
        try:
            if not image.save(str(dest), "PNG"):
                self._notify("Failed to save dropped image.")
                return
        except Exception as exc:
            self._notify(f"Failed to save dropped image:\n{exc}")
            return
        self.add_image_from_path(dest, scene_pos=scene_pos)

    def add_video(self) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.w,
            "Add Video",
            str(self._project_root),
            "Videos (*.mp4 *.mov *.avi *.mkv *.webm)",
        )
        if not path:
            return
        self.add_video_from_path(Path(path))

    def add_video_from_path(
        self, src: Path, scene_pos: Optional[QtCore.QPointF] = None
    ) -> Optional[QtWidgets.QGraphicsItem]:
        if not self._project_root:
            print("[BOARD] No project root set")
            return None
        if not src.is_file():
            print(f"[BOARD] Not a file: {src}")
            return None
        assets_dir = self._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / src.name
        print(f"[BOARD] Import video: {src} -> {dest}")
        if src.resolve() != dest.resolve():
            try:
                shutil.copy2(src, dest)
            except Exception as exc:
                print(f"[BOARD] Copy failed: {exc}")
                self._notify(f"Failed to copy video:\n{exc}")
                return None
        item = BoardVideoItem(self, dest)
        if item.boundingRect().isNull():
            self._notify("Failed to load video thumbnail.")
            return None
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setData(0, "video")
        item.setData(1, dest.name)
        if scene_pos is None:
            scene_pos = self._current_view_scene_center()
        item.setPos(scene_pos)
        logical_w = item.boundingRect().width()
        if logical_w > 600:
            scale = 600 / max(1.0, logical_w)
            item.setScale(scale)
        self._scene.addItem(item)
        self._commit_scene_mutation(history=False, update_groups=False)
        self._update_view_quality()
        self._schedule_history_snapshot()
        return item

    def _find_iconvert(self) -> Optional[Path]:
        houdini_exe = getattr(self.w, "_houdini_exe", "")
        if not houdini_exe:
            return None
        houdini_path = Path(str(houdini_exe))
        if not houdini_path.exists():
            return None
        iconvert = houdini_path.with_name("iconvert.exe")
        if iconvert.exists():
            return iconvert
        return None

    def convert_picnc_interactive(
        self,
        src_path: Optional[Path] = None,
        scene_pos: Optional[QtCore.QPointF] = None,
    ) -> Optional[QtWidgets.QGraphicsPixmapItem]:
        iconvert = self._find_iconvert()
        if iconvert is None:
            self._notify("iconvert.exe not found. Set Houdini path in Settings.")
            return None
        if src_path is None:
            src_path_str, _ = QtWidgets.QFileDialog.getOpenFileName(
                self.w,
                "Select PICNC",
                "",
                "Houdini PIC (*.picnc *.pic)",
            )
            if not src_path_str:
                return None
            src_path = Path(src_path_str)
        choice = QtWidgets.QMessageBox.question(
            self.w,
            "Convert PICNC",
            "Choose output format:",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        # Yes = JPG, No = EXR
        ext = "jpg" if choice == QtWidgets.QMessageBox.StandardButton.Yes else "exr"
        default_dir = None
        if self._project_root is not None:
            default_dir = self._project_root / ".skyforge_board_assets" / ".converted"
        default_name = src_path.stem + f".{ext}"
        if default_dir is not None:
            try:
                default_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                default_dir = None
        default_path = str(default_dir / default_name) if default_dir is not None else default_name
        out_path_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.w,
            "Save Converted File",
            default_path,
            "Images (*.jpg *.jpeg *.exr)",
        )
        if not out_path_str:
            return None
        out_path = Path(out_path_str)
        try:
            import subprocess
            houdini_env = build_houdini_env(
                base_env=os.environ,
                launcher_root=Path(__file__).resolve().parents[1],
            )
            subprocess.check_call([str(iconvert), str(src_path), str(out_path)], env=houdini_env)
        except Exception as exc:
            self._notify(f"iconvert failed:\n{exc}")
            return None
        self._notify(f"Converted: {out_path.name}")
        if out_path.suffix.lower() in IMAGE_EXTS:
            return self.add_image_from_path(out_path, scene_pos=scene_pos)
        return None

    def add_paths_from_selection(
        self, paths: list[Path], scene_pos: Optional[QtCore.QPointF] = None
    ) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        if not paths:
            return
        if scene_pos is None:
            scene_pos = self._current_view_scene_center()
        added = 0
        added_items: list[QtWidgets.QGraphicsItem] = []
        added_images: list[BoardImageItem] = []
        offset = QtCore.QPointF(30.0, 30.0)
        current_pos = QtCore.QPointF(scene_pos)
        for path in paths:
            item = None
            if path.is_file():
                if self._is_video_file(path):
                    item = self.add_video_from_path(path, scene_pos=current_pos)
                elif self._is_image_file(path):
                    item = self.add_image_from_path(path, scene_pos=current_pos)
                    if isinstance(item, BoardImageItem):
                        added_images.append(item)
                elif self._is_pic_file(path):
                    item = self.convert_picnc_interactive(path, scene_pos=current_pos)
                    if isinstance(item, BoardImageItem):
                        added_images.append(item)
            elif path.exists() and path.is_dir():
                item = self.add_sequence_from_dir(path, scene_pos=current_pos)
            if item is not None:
                added += 1
                added_items.append(item)
                current_pos = QtCore.QPointF(current_pos.x() + offset.x(), current_pos.y() + offset.y())
        if added == 0:
            self._notify("No supported media found in selection.")
            return
        if added_images:
            prev_selected = list(self._scene.selectedItems())
            for sel in prev_selected:
                sel.setSelected(False)
            for img in added_images:
                img.setSelected(True)
            self.layout_selection_grid()
            for img in added_images:
                img.setSelected(False)
            for sel in prev_selected:
                sel.setSelected(True)
        self._commit_scene_mutation(
            history=True,
            save=True,
            reveal_items=added_items,
            update_groups=True,
        )

    def add_sequence(self) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(
            self.w,
            "Add Image Sequence",
            str(self._project_root),
        )
        if not dir_path:
            return
        self.add_sequence_from_dir(Path(dir_path))

    def add_sequence_from_dir(
        self, dir_path: Path, scene_pos: Optional[QtCore.QPointF] = None
    ) -> Optional[QtWidgets.QGraphicsItem]:
        if not self._project_root:
            print("[BOARD] No project root set")
            return None
        if not dir_path.exists() or not dir_path.is_dir():
            print(f"[BOARD] Not a directory: {dir_path}")
            return None
        frames = self._sequence_frame_paths(dir_path)
        if not frames:
            self._notify("No image frames found in directory.")
            return None
        item = BoardSequenceItem(self, dir_path)
        if item.boundingRect().isNull():
            self._notify("Failed to load sequence thumbnail.")
            return None
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setData(0, "sequence")
        item.setData(1, self._relative_to_project(dir_path))
        if scene_pos is None:
            scene_pos = self._current_view_scene_center()
        item.setPos(scene_pos)
        logical_w = item.boundingRect().width()
        if logical_w > 600:
            scale = 600 / max(1.0, logical_w)
            item.setScale(scale)
        self._scene.addItem(item)
        self._commit_scene_mutation(history=False, update_groups=False)
        self._update_view_quality()
        self._schedule_history_snapshot()
        return item

    def convert_video_to_sequence(self, item: QtWidgets.QGraphicsItem) -> None:
        if item.data(0) != "video":
            return
        if not self._project_root:
            self._notify("Select a project first.")
            return
        if self._convert_thread is not None:
            self._notify("A conversion is already running.")
            return
        filename = str(item.data(1))
        video_path = self._project_root / ".skyforge_board_assets" / filename
        if not video_path.exists():
            self._notify("Video file not found.")
            return
        out_dir = self._project_root / ".skyforge_board_assets" / f"{video_path.stem}_seq"
        out_dir.mkdir(parents=True, exist_ok=True)
        self._notify("Converting video to sequence...")

        dialog = QtWidgets.QProgressDialog("Converting video...", "Cancel", 0, 100, self.w)
        dialog.setWindowTitle("Video Conversion")
        dialog.setMinimumDuration(200)
        dialog.setValue(0)
        dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self._convert_dialog = dialog

        worker = VideoToSequenceWorker(video_path, out_dir)
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)

        def _on_progress(current: int, total: int) -> None:
            if self._convert_dialog is None:
                return
            if total > 0:
                percent = int((current / max(1, total)) * 100)
                self._convert_dialog.setValue(min(100, max(0, percent)))
                self._convert_dialog.setLabelText(f"Extracting frames... {current}/{total}")
            else:
                self._convert_dialog.setValue(min(100, current % 100))
                self._convert_dialog.setLabelText(f"Extracting frames... {current}")
            QtWidgets.QApplication.processEvents()

        def _on_finished(success: bool, out_path: object, error: object) -> None:
            if self._convert_dialog is not None:
                self._convert_dialog.reset()
                self._convert_dialog = None
            self._convert_thread = None
            self._convert_worker = None
            if not success:
                self._notify(str(error or "Conversion failed."))
                return
            if not isinstance(out_path, Path):
                self._notify("Conversion failed.")
                return
            scene_pos = item.pos()
            scale = item.scale()
            group = self._find_group_for_item(item)
            self._scene.removeItem(item)
            seq_item = self.add_sequence_from_dir(out_path, scene_pos=scene_pos)
            if seq_item is not None:
                seq_item.setScale(scale)
                if group is not None:
                    group.add_member(seq_item)
                    group.update_bounds()
            self._commit_scene_mutation(history=True, update_groups=True)
            self._notify("Video converted to sequence.")

        def _on_cancel() -> None:
            if self._convert_worker is not None:
                self._convert_worker.cancel()

        dialog.canceled.connect(_on_cancel)
        worker.progress.connect(_on_progress)
        worker.finished.connect(_on_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._convert_thread = thread
        self._convert_worker = worker
        thread.start()

    def _extract_video_frames(self, video_path: Path, out_dir: Path) -> bool:
        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                cap.release()
                return False
            idx = 0
            stem = video_path.stem
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                frame_name = f"{stem}_{idx:04d}.png"
                frame_path = out_dir / frame_name
                cv2.imwrite(str(frame_path), frame)
                idx += 1
            cap.release()
            return idx > 0
        except Exception:
            return False

    def add_note(self) -> None:
        self.add_note_at(None)

    def add_note_at(self, scene_pos: Optional[QtCore.QPointF]) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        item = BoardNoteItem("New note...")
        item.setData(0, "note")
        if scene_pos is None:
            scene_pos = self._current_view_scene_center()
        item.setPos(scene_pos)
        item.setSelected(True)
        self._scene.addItem(item)
        self._commit_scene_mutation(history=False, update_groups=True)
        self.edit_note(item)

    def add_group(self) -> None:
        self._group_actions.add_group()

    def ungroup_selected(self) -> None:
        self._group_actions.ungroup_selected()

    def try_add_item_to_group(
        self, item: QtWidgets.QGraphicsItem, scene_pos: Optional[QtCore.QPointF]
    ) -> None:
        self._group_actions.try_add_item_to_group(item, scene_pos)

    def handle_item_drop(self, items: list[QtWidgets.QGraphicsItem]) -> None:
        self._group_actions.handle_item_drop(items)

    def delete_selected_items(self) -> None:
        selected = list(self._scene.selectedItems())
        if not selected:
            return
        self.begin_scene_interaction()
        try:
            for item in selected:
                if item.scene() is self._scene:
                    self._scene.removeItem(item)
            self._prune_empty_groups()
        finally:
            self.end_scene_interaction(history=True, update_groups=True)

    def remove_selected_from_groups(self) -> None:
        self._group_actions.remove_selected_from_groups()

    def add_selected_to_group(self, group_key: int) -> None:
        self._groups_panel.add_selected_to_group(group_key)

    def _add_selected_items_to_group_ref(self, group: BoardGroupItem) -> None:
        self._group_actions.add_selected_items_to_group_ref(group)

    def select_group_members(self, group_item: BoardGroupItem) -> None:
        self._group_actions.select_group_members(group_item)

    def _groups(self) -> list[BoardGroupItem]:
        return self._group_actions.groups()

    def _prune_empty_groups(self) -> bool:
        return self._group_actions.prune_empty_groups()

    def _find_group_for_item(self, item: QtWidgets.QGraphicsItem) -> Optional[BoardGroupItem]:
        return self._group_actions.find_group_for_item(item)

    def fit_view(self) -> None:
        self._refresh_scene_workspace()
        rect = self._scene.itemsBoundingRect()
        if rect.isNull():
            return
        self.w.board_page.view.fitInView(rect.adjusted(-80, -80, 80, 80), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def _current_view_scene_center(self) -> QtCore.QPointF:
        view = self.w.board_page.view
        viewport_rect = view.viewport().rect()
        if viewport_rect.isNull():
            return self._scene.sceneRect().center()
        return view.mapToScene(viewport_rect.center())

    def _workspace_item_bounds(self) -> QtCore.QRectF:
        rect = QtCore.QRectF()
        for item in self._scene.items():
            if item is self._focus_overlay:
                continue
            kind = item.data(0)
            if kind not in {"image", "video", "sequence", "note", "group"}:
                continue
            rect = rect.united(item.sceneBoundingRect())
        return rect

    def _refresh_scene_workspace(self, extra_rect: Optional[QtCore.QRectF] = None) -> None:
        workspace = self._workspace_item_bounds()
        if extra_rect is not None and extra_rect.isValid() and not extra_rect.isNull():
            workspace = workspace.united(extra_rect)
        view_pad = 4000.0
        min_half_extent = 5000.0
        center = self._current_view_scene_center()
        viewport_rect = QtCore.QRectF(
            center.x() - view_pad,
            center.y() - view_pad,
            view_pad * 2.0,
            view_pad * 2.0,
        )
        base_rect = QtCore.QRectF(
            -min_half_extent,
            -min_half_extent,
            min_half_extent * 2.0,
            min_half_extent * 2.0,
        )
        if workspace.isNull():
            workspace = viewport_rect
        else:
            workspace = workspace.united(viewport_rect)
        workspace = workspace.united(base_rect).adjusted(-view_pad, -view_pad, view_pad, view_pad)
        if workspace.isValid() and not workspace.isNull():
            self._scene.setSceneRect(workspace)

    def _reveal_scene_items(self, items: list[QtWidgets.QGraphicsItem]) -> None:
        if not items:
            return
        rect = QtCore.QRectF()
        for item in items:
            if item is None or item.scene() is not self._scene:
                continue
            rect = rect.united(item.sceneBoundingRect())
        if rect.isNull():
            return
        self._refresh_scene_workspace(extra_rect=rect)
        view = self.w.board_page.view
        margins = 80
        view.ensureVisible(rect.adjusted(-margins, -margins, margins, margins))

    def layout_selection_grid(self) -> None:
        items = [i for i in self._scene.selectedItems() if isinstance(i, QtWidgets.QGraphicsItem)]
        if not items:
            items = [
                i
                for i in self._scene.items()
                if isinstance(i, (BoardImageItem, BoardVideoItem, BoardSequenceItem))
            ]
        if not items:
            self._notify("Select items to layout.")
            return

        # Treat grouped items as a single block to avoid breaking group layout.
        items = collapse_items_by_group(items, self._groups())

        spacing = 12.0
        bounds = QtCore.QRectF()
        for item in items:
            bounds = bounds.united(item.sceneBoundingRect())
        target_width = max(600.0, bounds.width())

        widths = sorted([i.sceneBoundingRect().width() for i in items])
        median_w = widths[len(widths) // 2] if widths else 200.0
        cols = max(2, int((target_width + spacing) / max(1.0, median_w + spacing)))

        col_width = (target_width - spacing * (cols - 1)) / max(1, cols)
        col_heights = [bounds.top() for _ in range(cols)]
        col_x = [bounds.left() + c * (col_width + spacing) for c in range(cols)]

        items_sorted = sorted(items, key=lambda i: i.sceneBoundingRect().height(), reverse=True)

        for item in items_sorted:
            rect = item.sceneBoundingRect()
            if rect.width() > 0 and not isinstance(item, BoardGroupItem):
                scale_factor = col_width / rect.width()
                item.setScale(item.scale() * scale_factor)
                rect = item.sceneBoundingRect()
            col_idx = min(range(cols), key=lambda i: col_heights[i])
            x = col_x[col_idx]
            y = col_heights[col_idx]
            item.setPos(item.pos() + QtCore.QPointF(x - rect.left(), y - rect.top()))
            col_heights[col_idx] = y + rect.height() + spacing
        self._commit_scene_mutation(history=True, update_groups=True)

    def save_board(self) -> None:
        if not self._project_root:
            return
        path = board_path(self._project_root)
        existing_payload = load_board_payload(self._project_root)
        if self._should_block_empty_board_save(existing_payload):
            backup_board_payload(self._project_root, existing_payload, "blocked-empty-save")
            print(f"[BOARD] Skipped suspicious empty save: {path}")
            self._notify(
                "Skipped board save to avoid overwriting an existing board with an empty scene."
            )
            return
        self._commit_current_focus_image_override()
        data = self._sync_board_state_overrides()
        try:
            self._saving = True
            self._last_save_ts = time.time()
            save_board_payload(self._project_root, data)
            self._dirty = False
            self._loaded_project_root = self._project_root
            self._board_state_loaded = True
        except Exception as exc:
            self._notify(f"Failed to save board:\n{exc}")
        finally:
            QtCore.QTimer.singleShot(100, self._clear_saving)

    def _clear_saving(self) -> None:
        self._saving = False

    @staticmethod
    def _payload_item_count(payload: object) -> int:
        return payload_item_count(payload)

    def _board_load_in_progress(self) -> bool:
        return self._loading or self._apply_runtime.in_progress()

    def _should_block_empty_board_save(self, existing_payload: Optional[dict]) -> bool:
        if not self._project_root:
            return False
        current_count = self._payload_item_count(self._current_board_state())
        existing_count = self._payload_item_count(existing_payload)
        if current_count != 0 or existing_count <= 0:
            return False
        if self._board_load_in_progress():
            return True
        return not self._dirty

    def load_board(self) -> None:
        if not self._project_root:
            return
        load_generation = self._apply_runtime.generation
        path = board_path(self._project_root)
        if self._saving:
            return
        print(f"[BOARD] Load board: {path}")
        self._loading = True
        self.w.board_page.set_loading_overlay(True, f"Reading {self._project_root.name} board data...")
        if not path.exists():
            payload = {"items": [], "image_display_overrides": {}}
            if load_generation != self._apply_runtime.generation:
                return
            self._set_board_state(payload)
            self._loaded_project_root = self._project_root
            self._board_state_loaded = True
            self._start_apply_payload(payload)
            return
        payload = load_board_payload(self._project_root)
        if payload is None:
            self._loading = False
            self.w.board_page.set_loading_overlay(False)
            return
        if load_generation != self._apply_runtime.generation:
            return
        payload = self._set_board_state(payload)
        self._loaded_project_root = self._project_root
        self._board_state_loaded = True
        self._start_apply_payload(payload)

    def _schedule_board_load(self) -> None:
        # Defer heavy loading to keep UI responsive on click.
        QtCore.QTimer.singleShot(40, self.ensure_board_loaded)

    def _parse_image_display_overrides(self, payload: dict) -> dict[str, dict[str, object]]:
        return parse_image_display_overrides(
            payload,
            coerce_color_adjustments=self._coerce_color_adjustments,
            tool_stack_from_override=self._tool_stack_from_override,
        )

    def _start_apply_payload(self, payload: dict) -> None:
        payload = self._set_board_state(payload)
        total = payload_item_count(payload)
        self.w.board_page.set_loading_overlay(
            True,
            f"Rebuilding {total} board item(s)...",
        )
        self._scene.blockSignals(True)
        self._scene.clear()
        self._image_exr_display_overrides = prepare_apply_state(
            self._apply_state,
            payload,
            parse_overrides=self._parse_image_display_overrides,
        )
        print(f"[BOARD] Apply payload start: {len(self._apply_state.queue)} items")
        self._apply_runtime.start(total)

    def _apply_payload_batch(self) -> None:
        if not self._apply_runtime.is_current():
            return
        batch_size = 20
        count = 0
        assets_dir = self._project_root / ".skyforge_board_assets" if self._project_root else None
        if self._apply_runtime.total:
            self.w.board_page.set_loading_overlay(
                True,
                f"Rebuilding board items... {self._apply_runtime.done_count()}/{self._apply_runtime.total}",
            )
        while self._apply_state.queue and count < batch_size:
            entry = self._apply_state.queue.popleft()
            count += 1
            built = build_scene_item_from_entry(
                entry,
                controller=self,
                assets_dir=assets_dir,
                resolve_project_path=self._resolve_project_path,
            )
            if built is None:
                continue
            kind, payload_or_item = built
            if kind == "group":
                self._apply_state.pending_groups.append(entry)
                continue
            item = payload_or_item
            self._scene.addItem(item)
            register_built_item(
                self._apply_state,
                entry,
                kind,
                item,
                image_overrides=self._image_exr_display_overrides,
                apply_image_override=self._apply_override_to_image_item,
                apply_video_override=self._apply_override_to_video_item,
            )

        if self._apply_state.queue:
            self._apply_runtime.schedule_next(10)
            return

        apply_pending_groups_to_scene(
            self._apply_state,
            self._scene,
            build_group_item=build_group_item,
        )
        self._scene.blockSignals(False)
        self._dirty = False
        self._loading = False
        applied_state = self._sync_board_state_from_scene()
        self._refresh_scene_workspace()
        self._update_view_quality()
        self.update_visible_items()
        self._reset_history(applied_state)
        if self._apply_state.base_label:
            self.w.board_page.project_label.setText(self._apply_state.base_label)
        self.w.board_page.set_loading_overlay(False)
        QtCore.QTimer.singleShot(0, self._fit_view_after_load)
        self._schedule_post_load_reapply()

    def _apply_override_to_image_item(self, item: BoardImageItem, override: dict[str, object]) -> None:
        apply_image_override_to_item(
            item,
            override,
            coerce_color_adjustments=self._coerce_color_adjustments,
            tool_stack_from_override=self._tool_stack_from_override,
            default_crop_settings=self._default_crop_settings,
            tool_stack_is_effective=self._tool_stack_is_effective,
            queue_exr_display_for_item=self._queue_exr_display_for_item,
            queue_image_adjust_for_item=self._queue_image_adjust_for_item,
        )

    def _apply_override_to_video_item(self, item: BoardVideoItem, override: dict[str, object]) -> None:
        apply_video_override_to_item(
            item,
            override,
            tool_stack_from_override=self._tool_stack_from_override,
            default_crop_settings=self._default_crop_settings,
            get_video_frame_pixmap=self._get_video_frame_pixmap,
        )

    def _schedule_post_load_reapply(self) -> None:
        if not self._ui_alive():
            return
        if self._post_load_reapply_timer is None:
            self._post_load_reapply_timer = QtCore.QTimer(self.w)
            self._post_load_reapply_timer.setSingleShot(True)
            self._post_load_reapply_timer.timeout.connect(self._reapply_image_overrides_for_scene)
        self._post_load_reapply_timer.start(250)

    def _reapply_image_overrides_for_scene(self) -> None:
        self._post_load_reapply_timer = None
        if not self._ui_alive() or self._loading:
            return
        reapply_scene_overrides(
            list(self._scene.items()),
            self._image_exr_display_overrides,
            apply_image_override=self._apply_override_to_image_item,
            apply_video_override=self._apply_override_to_video_item,
            image_type=BoardImageItem,
            video_type=BoardVideoItem,
        )

    def _fit_view_after_load(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if rect.isNull():
            return
        self.fit_view()
        view = self.w.board_page.view
        zoom = view.transform().m11()
        if zoom < 0.02:
            view.resetTransform()
            view.centerOn(rect.center())

    def edit_note(self, item: BoardNoteItem, global_pos: Optional[QtCore.QPoint] = None) -> None:
        dialog = QtWidgets.QDialog(self.w)
        dialog.setWindowFlags(QtCore.Qt.WindowType.Tool | QtCore.Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setMinimumWidth(320)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        text_edit = NoteTextEditor()
        text_edit.set_text(item.text_item.toPlainText())
        text_edit.setMinimumHeight(140)
        layout.addWidget(text_edit, 1)

        options = QtWidgets.QHBoxLayout()
        layout.addLayout(options)

        size_label = QtWidgets.QLabel("Font")
        options.addWidget(size_label)
        size_spin = QtWidgets.QSpinBox()
        size_spin.setRange(8, 64)
        size_spin.setValue(item.note_data().get("font_size", 12))
        options.addWidget(size_spin)

        align_label = QtWidgets.QLabel("Align")
        options.addWidget(align_label)
        align_combo = QtWidgets.QComboBox()
        align_combo.addItems(["Left", "Center"])
        align_combo.setCurrentText("Center" if item.note_data().get("align") == "center" else "Left")
        options.addWidget(align_combo)

        color_btn = QtWidgets.QPushButton("Background")
        options.addWidget(color_btn)
        color_preview = QtWidgets.QFrame()
        color_preview.setFixedSize(24, 24)
        color_preview.setStyleSheet(f"background: {item.note_data().get('bg', '#99000000')}; border: 1px solid #333;")
        options.addWidget(color_preview)
        options.addStretch(1)

        selected_color = QtGui.QColor(item.note_data().get("bg", "#99000000"))
        applied = False

        def pick_color() -> None:
            nonlocal selected_color
            popup_filter.block_outside_close = True
            color = QtWidgets.QColorDialog.getColor(selected_color, self.w, "Pick background color")
            popup_filter.block_outside_close = False
            if color.isValid():
                selected_color = color
                color_preview.setStyleSheet(
                    f"background: {color.name(QtGui.QColor.NameFormat.HexArgb)}; border: 1px solid #333;"
                )
                preview_align = (
                    QtCore.Qt.AlignmentFlag.AlignHCenter
                    if align_combo.currentText() == "Center"
                    else QtCore.Qt.AlignmentFlag.AlignLeft
                )
                item.set_note_style(size_spin.value(), preview_align, selected_color)
                self._dirty = True

        def apply_changes() -> None:
            nonlocal applied
            if applied:
                return
            if item.scene() is None:
                return
            applied = True
            align_flag = (
                QtCore.Qt.AlignmentFlag.AlignHCenter
                if align_combo.currentText() == "Center"
                else QtCore.Qt.AlignmentFlag.AlignLeft
            )
            item.set_text(text_edit.text())
            item.set_note_style(size_spin.value(), align_flag, selected_color)
            self._commit_scene_mutation(history=True, update_groups=True)

        color_btn.clicked.connect(pick_color)
        dialog.finished.connect(lambda _result: apply_changes())

        popup_filter = PopupOutsideCloseFilter(dialog, apply_changes)
        QtWidgets.QApplication.instance().installEventFilter(popup_filter)

        def cleanup() -> None:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.removeEventFilter(popup_filter)

        dialog.finished.connect(lambda _result: cleanup())

        if global_pos is None:
            view = self.w.board_page.view
            scene_pos = item.sceneBoundingRect().topLeft()
            view_pos = view.mapFromScene(scene_pos)
            global_pos = view.viewport().mapToGlobal(view_pos)
        dialog.adjustSize()
        target = global_pos + QtCore.QPoint(12, 12)
        screen = QtGui.QGuiApplication.screenAt(target)
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            dlg = dialog.frameGeometry()
            x = max(geom.left() + 8, min(target.x(), geom.right() - dlg.width() - 8))
            y = max(geom.top() + 8, min(target.y(), geom.bottom() - dlg.height() - 8))
            target = QtCore.QPoint(x, y)
        dialog.move(target)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        QtCore.QTimer.singleShot(0, text_edit.setFocus)

    def open_media_item(self, item: QtWidgets.QGraphicsItem) -> None:
        kind = item.data(0)
        if kind == "video":
            if not self._project_root:
                self._notify("Select a project first.")
                return
            filename = str(item.data(1))
            path = self._project_root / ".skyforge_board_assets" / filename
            if not path.exists():
                self._notify("Video file not found.")
                return
            self.enter_focus_mode(item)
            self._show_edit_panel_for_video(path)
        elif kind == "sequence":
            dir_text = str(item.data(1))
            dir_path = self._resolve_project_path(dir_text)
            if not dir_path.exists():
                self._notify("Sequence directory not found.")
                return
            self.enter_focus_mode(item)
            self._show_edit_panel_for_sequence(dir_path)

    def open_image_item(self, item: QtWidgets.QGraphicsItem) -> None:
        if item.data(0) != "image":
            return
        if not self._project_root:
            self._notify("Select a project first.")
            return
        filename = str(item.data(1))
        path = self._project_root / ".skyforge_board_assets" / filename
        if not path.exists():
            self._notify("Image file not found.")
            return
        self.enter_focus_mode(item)
        self._show_edit_panel_for_image(path)

    def _open_video_dialog(self, path: Path) -> None:
        dialog = QtWidgets.QDialog(self.w)
        dialog.setWindowTitle(f"Video: {path.name}")
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.resize(860, 540)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        status = QtWidgets.QLabel("")
        status.setStyleSheet("color: #9aa3ad;")
        layout.addWidget(status, 0)

        preview_label = QtWidgets.QLabel(path.name)
        preview_label.setStyleSheet("color: #c6ccd6; font-weight: bold;")

        preview_widget = QtWidgets.QLabel("")
        backend_pref = getattr(self.w, "_video_backend_pref", "auto")
        controller = VideoController(
            backend_pref,
            status_label=status,
            preview_label=preview_label,
            preview_widget=preview_widget,
            parent=dialog,
        )
        dialog._video_controller = controller  # type: ignore[attr-defined]
        layout.addWidget(controller.widget, 1)

        controls = QtWidgets.QHBoxLayout()
        play_btn = QtWidgets.QPushButton("Play")
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(0, 0)
        controls.addWidget(play_btn, 0)
        controls.addWidget(slider, 1)
        layout.addLayout(controls)

        controller.bind_controls(play_btn, slider)
        controller.play_path(path)

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _show_edit_panel_for_video(self, path: Path) -> None:
        self._edit_image_path = None
        self._reset_edit_session_for_kind("video")
        self._sync_edit_tool_defs_for_kind("video")
        self._edit_tool_stack = [self._tool_entry_from_id("crop")]
        self._edit_selected_tool_index = 0
        if isinstance(self._focus_item, BoardVideoItem):
            filename = str(self._focus_item.data(1) or "").strip()
            override = self._image_exr_display_overrides.get(filename)
            self._edit_tool_stack = self._tool_stack_from_override(override)
        self.w.board_page.set_image_adjust_controls_visible(True)
        self._sync_tool_stack_ui()
        self._apply_crop_to_focus_item()
        self.w.board_page.edit_timeline_play_btn.setText(play_button_label(False))
        self._video_playback.stop()
        info = [
            f"Type: Video",
            f"Name: {path.name}",
            f"Path: {path}",
        ]
        self.w.board_page.set_edit_panel_content(
            "Edit Mode: Video",
            info,
            list_items=None,
            footer="Edit/export options will appear here.",
        )
        self._ensure_edit_video_controller()
        if self._edit_video_controller is not None:
            self.w.board_page.show_edit_preview_video()
            self._edit_video_controller.preview_first_frame(path)
            self._edit_video_controller.load_path(path)
        self.w.board_page.edit_timeline_play_btn.setText(play_button_label(False))
        self._focus_video_path = path
        self._ensure_focus_video_cap()
        self._init_edit_video_timeline(path)
        self.w.board_page.set_timeline_bar_visible(True)
        self.w.board_page.set_edit_preview_visible(False)
        self._edit_focus_kind = "video"

    def _show_edit_panel_for_sequence(self, dir_path: Path) -> None:
        self._edit_image_path = None
        self.w.board_page.set_image_adjust_controls_visible(False)
        self.w.board_page.edit_timeline_play_btn.setText(play_button_label(False))
        frames = self._sequence_frame_paths(dir_path)
        info = [
            "Type: Sequence",
            f"Name: {dir_path.name}",
            f"Frames: {len(frames)}",
            f"Path: {dir_path}",
        ]
        self.w.board_page.set_edit_panel_content(
            "Edit Mode: Sequence",
            info,
            list_items=None,
            footer="Edit/export options will appear here.",
        )
        self._edit_seq_frames = frames
        self._edit_seq_dir = dir_path
        self._sequence_playback.stop()
        self._sequence_playback.set_fps(self._edit_seq_fps)
        self.w.board_page.edit_timeline_play_btn.setText(play_button_label(False))
        self._edit_video_playhead = 0
        if frames:
            self.w.board_page.edit_sequence_timeline.set_data(len(frames), [(0, len(frames) - 1)], 0)
            self.w.board_page.edit_sequence_frame_label.setText("Frame: 0")
        else:
            self.w.board_page.edit_sequence_timeline.set_data(0, [], 0)
            self.w.board_page.edit_sequence_frame_label.setText("Frame: 0")
        # Use the main timeline bar for sequences as well
        self.w.board_page.edit_timeline.set_data(len(frames), [(0, max(0, len(frames) - 1))], 0)
        self.w.board_page.set_timeline_bar_visible(True)
        self._edit_focus_kind = "sequence"
        self.w.board_page.set_edit_preview_visible(False)
        self._on_edit_sequence_timeline_playhead(0)

    def _show_edit_panel_for_image(self, path: Path) -> None:
        size = self._get_image_size(path)
        info = [
            f"{path.name}",
            f"{size.width()} x {size.height()}",
        ]
        self._edit_image_path = path
        self._reset_edit_session_for_kind("image")
        self._sync_edit_tool_defs_for_kind("image")
        self._edit_tool_stack = build_bcs_stack(*self._default_color_adjustments())
        self._edit_selected_tool_index = 0
        EditVisualState.defaults().apply_to_session(self._edit_session)
        if isinstance(self._focus_item, BoardImageItem):
            filename = str(self._focus_item.data(1) or "").strip()
            override = self._image_exr_display_overrides.get(filename)
            self._edit_tool_stack = self._tool_stack_from_override(override)
            EditVisualState.from_tool_stack(self._edit_tool_stack).apply_to_session(self._edit_session)
        self.w.board_page.set_image_adjust_controls_visible(True)
        self._sync_tool_stack_ui()
        self._apply_crop_to_focus_item()
        preview = self._get_display_pixmap(path, max_dim=1024)
        self.w.board_page.show_edit_preview_image(preview)
        if path.suffix.lower() == ".exr":
            self._edit_exr_path = path
            self._edit_exr_channels = []
            self._edit_exr_channel = None
            if isinstance(self._focus_item, BoardImageItem):
                filename = str(self._focus_item.data(1) or "").strip()
                override = self._image_exr_display_overrides.get(filename)
                if isinstance(override, dict):
                    channel = str(override.get("channel", "")).strip()
                    if channel:
                        self._edit_exr_channel = channel
                    try:
                        self._edit_exr_gamma = max(0.1, float(override.get("gamma", self._edit_exr_gamma)))
                    except Exception:
                        pass
                    self._edit_exr_srgb = bool(override.get("srgb", self._edit_exr_srgb))
            self.w.board_page.set_exr_channel_row_visible(True)
            self.w.board_page.set_exr_gamma_label(self._edit_exr_gamma)
            self.w.board_page.edit_exr_srgb_check.setChecked(self._edit_exr_srgb)
            self.w.board_page.edit_exr_gamma_slider.setValue(int(self._edit_exr_gamma * 10))
            self.w.board_page.set_edit_panel_content(
                "Edit Mode: Image",
                info,
                list_items=["Loading channels..."],
                footer="",
            )
            self._load_exr_channels_into_panel(path)
        else:
            self._edit_exr_path = None
            self._edit_exr_channels = []
            self._edit_exr_channel = None
            self.w.board_page.set_exr_channel_row_visible(False)
            self.w.board_page.set_edit_panel_content(
                "Edit Mode: Image",
                info,
                list_items=None,
                footer="",
            )
        self.w.board_page.set_timeline_bar_visible(False)
        self.w.board_page.set_edit_preview_visible(False)
        self._edit_focus_kind = "image"

    def _ensure_edit_video_controller(self) -> None:
        if self._edit_video_controller is not None:
            return
        backend_pref = getattr(self.w, "_video_backend_pref", "auto")
        status_label = self.w.board_page.edit_video_status
        preview_label = QtWidgets.QLabel("Video")
        preview_widget = QtWidgets.QLabel("")
        controller = VideoController(
            backend_pref,
            status_label=status_label,
            preview_label=preview_label,
            preview_widget=preview_widget,
            parent=self.w.board_page,
        )
        self._edit_video_controller = controller
        host_layout = self.w.board_page.edit_video_host_layout
        host_layout.addWidget(controller.widget)
        controller.bind_controls(None, None)

    def _init_edit_video_timeline(self, path: Path) -> None:
        self._edit_video_path = path
        self._edit_video_playhead = 0
        total = 0
        fps = 24.0
        if cv2 is not None:
            try:
                cap = cv2.VideoCapture(str(path))
                if cap.isOpened():
                    total = int(cap.get(7) or 0)  # CAP_PROP_FRAME_COUNT
                    fps = float(cap.get(5) or 24.0)  # CAP_PROP_FPS
                cap.release()
            except Exception:
                total = 0
                fps = 24.0
        self._edit_video_fps = max(1.0, float(fps))
        self._video_playback.set_fps(self._edit_video_fps)
        self._edit_video_total = max(0, total)
        if self._edit_video_total <= 0:
            self._edit_video_clips = []
            self._edit_selected_clip = -1
            self.w.board_page.edit_timeline.set_data(0, [], 0)
            self.w.board_page.edit_timeline_split_btn.setEnabled(False)
            self.w.board_page.edit_timeline_export_btn.setEnabled(False)
            self.w.board_page.edit_video_status.setText("Timeline unavailable (no frame count).")
            return
        self._edit_video_clips = [(0, self._edit_video_total - 1)]
        self._edit_selected_clip = 0
        self.w.board_page.edit_timeline.set_data(
            self._edit_video_total,
            self._edit_video_clips,
            self._edit_video_playhead,
        )
        self.w.board_page.edit_timeline.set_selected_clip(self._edit_selected_clip)
        self.w.board_page.edit_timeline_split_btn.setEnabled(True)
        self.w.board_page.edit_timeline_export_btn.setEnabled(True)

    def _set_edit_timeline_frame_label(self, frame: int) -> None:
        if hasattr(self.w.board_page, "edit_timeline_frame_label"):
            self.w.board_page.edit_timeline_frame_label.setText(frame_label_text(frame))

    def _apply_sequence_focus_frame(self, frame: int) -> None:
        if not isinstance(self._focus_item, BoardSequenceItem):
            return
        if not self._edit_seq_frames:
            return
        idx = clamp_playhead(frame, len(self._edit_seq_frames))
        frame_path = self._edit_seq_frames[idx]
        pixmap = self._get_display_pixmap(frame_path, max_dim=self._max_display_dim)
        self._focus_item.set_override_pixmap(pixmap)

    def _apply_video_focus_frame(self, frame: int) -> None:
        if not isinstance(self._focus_item, BoardVideoItem):
            return
        idx = clamp_playhead(frame, self._edit_video_total)
        if self._video_playback.is_playing():
            self._schedule_video_focus_preview(idx, immediate=True)
        else:
            delay = 140 if self._edit_timeline_scrubbing else 40
            self._schedule_video_focus_preview(idx, delay_ms=delay)

    def _on_edit_timeline_playhead(self, frame: int) -> None:
        if self._edit_focus_kind == "sequence":
            self._on_edit_sequence_timeline_playhead(int(frame))
            return
        self._edit_video_playhead = clamp_playhead(int(frame), self._edit_video_total)
        if (
            self._edit_video_controller is not None
            and not self._edit_timeline_scrubbing
            and not self._video_playback.is_playing()
        ):
            self._edit_video_controller.seek_frame(self._edit_video_playhead)
        self._apply_video_focus_frame(self._edit_video_playhead)
        self._set_edit_timeline_frame_label(self._edit_video_playhead)

    def _on_edit_timeline_scrub_state(self, active: bool) -> None:
        self._edit_timeline_scrubbing = bool(active)
        if not active and self._edit_focus_kind == "video":
            if self._edit_video_controller is not None:
                self._edit_video_controller.seek_frame(self._edit_video_playhead)
            if isinstance(self._focus_item, BoardVideoItem):
                self._schedule_video_focus_preview(self._edit_video_playhead, immediate=True)

    def _on_edit_timeline_selected(self, index: int) -> None:
        self._edit_selected_clip = int(index)

    def _find_clip_at_playhead(self) -> Optional[int]:
        for idx, (start, end) in enumerate(self._edit_video_clips):
            if start <= self._edit_video_playhead <= end:
                return idx
        return None

    def _split_edit_clip(self) -> None:
        if not self._edit_video_clips:
            return
        idx = self._edit_selected_clip if self._edit_selected_clip >= 0 else self._find_clip_at_playhead()
        if idx is None:
            return
        start, end = self._edit_video_clips[idx]
        ph = self._edit_video_playhead
        if ph <= start or ph >= end:
            return
        left = (start, ph)
        right = (ph + 1, end)
        self._edit_video_clips[idx:idx + 1] = [left, right]
        self._edit_selected_clip = idx
        self.w.board_page.edit_timeline.set_data(
            self._edit_video_total,
            self._edit_video_clips,
            self._edit_video_playhead,
        )

    def _export_edit_clip(self) -> None:
        if self._edit_video_path is None or not self._edit_video_clips:
            return
        self._log_export_event("Export clip requested.")
        idx = self._edit_selected_clip if self._edit_selected_clip >= 0 else self._find_clip_at_playhead()
        if idx is None:
            self._log_export_event("Export aborted: no clip selected.")
            return
        start, end = self._edit_video_clips[idx]
        self._log_export_event(f"Selected clip {idx}: frames {start}-{end}.")
        if self._segment_thread is not None:
            self._log_export_event("Export aborted: segment thread already running.")
            self._notify("Export already running.")
            return
        if not self._project_root:
            self._log_export_event("Export aborted: no project root.")
            self._notify("Select a project first.")
            return
        assets_dir = self._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        out_dir = assets_dir / f"{self._edit_video_path.stem}_seg_{start}_{end}"
        out_dir.mkdir(parents=True, exist_ok=True)
        self._log_export_event(f"Output directory ready: {out_dir}")

        dialog = QtWidgets.QProgressDialog("Exporting segment...", "Cancel", 0, 100, self.w)
        dialog.setWindowTitle("Export Segment")
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setRange(0, 0)
        dialog.setValue(0)
        dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        dialog.setLabelText(
            f"Preparing export for frames {start}-{end}...\nOutput: {out_dir.name}"
        )
        dialog.show()
        self._log_export_event("Progress dialog shown.")
        self._segment_dialog = dialog
        self.w.board_page.edit_timeline_split_btn.setEnabled(False)
        self.w.board_page.edit_timeline_export_btn.setEnabled(False)

        worker = VideoSegmentWorker(self._edit_video_path, out_dir, start, end)
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        determinate_progress = False

        def _on_status(text: str) -> None:
            self._log_export_event(f"Worker status: {text}")
            if self._segment_dialog is None:
                return
            self._segment_dialog.setLabelText(
                f"{text}\nFrames {start}-{end}\nOutput: {out_dir.name}"
            )

        def _on_progress(current: int, total: int) -> None:
            nonlocal determinate_progress
            if self._segment_dialog is None:
                return
            if not determinate_progress:
                self._segment_dialog.setRange(0, 100)
                determinate_progress = True
                self._log_export_event(f"Progress became determinate: total={total}")
            percent = int((current / max(1, total)) * 100)
            self._segment_dialog.setValue(min(100, max(0, percent)))
            self._segment_dialog.setLabelText(
                f"Exporting frames... {current}/{total}\nFrames {start}-{end}\nOutput: {out_dir.name}"
            )

        def _on_finished(success: bool, out_path: object, error: object) -> None:
            self._log_export_event(f"Worker finished: success={success} out={out_path} error={error}")
            if self._segment_dialog is not None:
                self._segment_dialog.reset()
                self._segment_dialog = None
            self._segment_thread = None
            self._segment_worker = None
            self.w.board_page.edit_timeline_split_btn.setEnabled(True)
            self.w.board_page.edit_timeline_export_btn.setEnabled(True)
            if not success:
                self._notify(str(error or "Export failed."))
                return
            if isinstance(out_path, Path):
                if self._focus_item is not None:
                    self.exit_focus_mode()
                item = self.add_sequence_from_dir(out_path)
                if item is not None:
                    item.setSelected(True)
                    self._reveal_scene_items([item])
                    self.save_board()
                    self._notify("Segment exported as sequence.")
            else:
                self._notify("Export completed.")

        def _on_cancel() -> None:
            self._log_export_event("Cancel requested.")
            if self._segment_dialog is not None:
                self._segment_dialog.setLabelText("Cancelling export...")
            if self._segment_worker is not None:
                self._segment_worker.cancel()

        dialog.canceled.connect(_on_cancel)
        worker.status.connect(_on_status)
        worker.progress.connect(_on_progress)
        worker.finished.connect(_on_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._segment_thread = thread
        self._segment_worker = worker

        def _start_export_thread() -> None:
            self._log_export_event("Starting export thread.")
            if self._segment_thread is thread:
                thread.start()

        QtCore.QTimer.singleShot(0, _start_export_thread)

    def _on_edit_sequence_timeline_playhead(self, frame: int) -> None:
        if not self._edit_seq_frames:
            return
        idx = clamp_playhead(int(frame), len(self._edit_seq_frames))
        self._edit_video_playhead = idx
        self._set_edit_timeline_frame_label(idx)
        self._apply_sequence_focus_frame(idx)

    def _toggle_edit_sequence_play(self) -> None:
        if not self._edit_seq_frames:
            return
        self._sequence_playback.set_fps(self._edit_seq_fps)
        self._sequence_playback.toggle()

    def _on_sequence_play_state_changed(self, playing: bool) -> None:
        if self._edit_focus_kind == "sequence":
            self.w.board_page.edit_timeline_play_btn.setText(play_button_label(playing))

    def _on_video_play_state_changed(self, playing: bool) -> None:
        if self._edit_focus_kind == "video":
            self.w.board_page.edit_timeline_play_btn.setText(play_button_label(playing))

    def _toggle_edit_timeline_play(self) -> None:
        if self._edit_focus_kind == "sequence":
            self._toggle_edit_sequence_play()
            return
        if self._edit_focus_kind == "video":
            if self._edit_video_total <= 0:
                return
            self._video_playback.set_fps(self._edit_video_fps)
            self._video_playback.toggle()

    def _advance_edit_video_frame(self) -> None:
        if self._edit_video_total <= 0:
            return
        nxt = loop_next_playhead(self._edit_video_playhead, self._edit_video_total)
        self.w.board_page.edit_timeline.set_playhead(nxt)
        self._on_edit_timeline_playhead(nxt)

    def _advance_edit_sequence_frame(self) -> None:
        if not self._edit_seq_frames:
            return
        nxt = loop_next_playhead(self._edit_video_playhead, len(self._edit_seq_frames))
        self.w.board_page.edit_timeline.set_playhead(nxt)
        self._on_edit_sequence_timeline_playhead(nxt)

    def _load_exr_channels_into_panel(self, path: Path) -> None:
        worker = ExrInfoWorker(path)
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        self.w.board_page._edit_exr_thread = thread  # type: ignore[attr-defined]
        self.w.board_page._edit_exr_worker = worker  # type: ignore[attr-defined]
        worker.finished.connect(self._ui_bridge.on_exr_info_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @staticmethod
    def _build_exr_channel_options(channels: list[str]) -> tuple[list[tuple[str, str]], Optional[str]]:
        clean = [str(c) for c in channels]
        lower_map = {c.lower(): c for c in clean}
        groups: dict[str, set[str]] = {}
        for ch in clean:
            if "." in ch:
                prefix, suffix = ch.rsplit(".", 1)
            else:
                prefix, suffix = "", ch
            suffix_up = suffix.upper()
            if suffix_up in ("R", "G", "B", "A"):
                groups.setdefault(prefix, set()).add(suffix_up)
        options: list[tuple[str, str]] = []
        default_value: Optional[str] = None

        def add_option(label: str, value: str) -> None:
            nonlocal default_value
            options.append((label, value))
            if default_value is None:
                default_value = value

        # Prefer beauty in root group
        root = groups.get("", set())
        if {"R", "G", "B"}.issubset(root):
            add_option("Beauty (RGB)", "RGB")
            if "A" in root:
                add_option("Beauty (RGBA)", "RGBA")

        # Other groups
        for prefix, chans in sorted(groups.items()):
            if prefix == "":
                continue
            if {"R", "G", "B"}.issubset(chans):
                add_option(f"{prefix} (RGB)", f"{prefix}.RGB")
                if "A" in chans:
                    add_option(f"{prefix} (RGBA)", f"{prefix}.RGBA")

        # Raw channels
        for ch in clean:
            add_option(ch, ch)

        # Default to beauty if available
        for label, value in options:
            if value in ("RGB", "RGBA"):
                default_value = value
                break
        return options, default_value

    @staticmethod
    def _default_color_adjustments() -> tuple[float, float, float]:
        return 0.0, 1.0, 1.0

    @staticmethod
    def _default_vibrance() -> float:
        return 0.0

    @staticmethod
    def _default_crop_settings() -> tuple[float, float, float, float]:
        return 0.0, 0.0, 0.0, 0.0

    def _default_edit_tool_stack(self) -> list[dict[str, object]]:
        self._sync_edit_tool_defs_for_kind(str(self._edit_focus_kind or "image"))
        tools = default_tool_stack_for_kind(self._edit_focus_kind)
        return tools or build_bcs_stack(*self._default_color_adjustments())

    def _ensure_edit_tool_stack(self) -> None:
        self._sync_edit_tool_defs_for_kind(str(self._edit_focus_kind or "image"))
        tools = normalize_tool_entries(self._edit_tool_stack)
        if not tools:
            tools = self._default_edit_tool_stack()
        self._edit_tool_stack = [dict(t) for t in tools]
        if self._edit_selected_tool_index < 0 or self._edit_selected_tool_index >= len(self._edit_tool_stack):
            self._edit_selected_tool_index = 0

    def _tool_label_for_id(self, tool_id: str) -> str:
        key = str(tool_id or "").strip().lower()
        for tid, label in self._edit_tool_defs:
            if tid == key:
                return label
        spec = get_edit_tool(key)
        if spec is not None:
            return spec.label
        return key or "Tool"

    def _tool_entry_from_id(self, tool_id: str) -> dict[str, object]:
        entry = make_tool_entry(tool_id)
        if entry:
            return entry
        b, c, s = self._default_color_adjustments()
        return {
            "id": "bcs",
            "enabled": True,
            "settings": {"brightness": b, "contrast": c, "saturation": s},
        }

    def _selected_tool_entry(self) -> Optional[dict[str, object]]:
        if self._edit_selected_tool_index < 0 or self._edit_selected_tool_index >= len(self._edit_tool_stack):
            return None
        entry = self._edit_tool_stack[self._edit_selected_tool_index]
        return entry if isinstance(entry, dict) else None

    def _tool_panel_for_id(self, tool_id: str) -> str:
        spec = get_edit_tool(tool_id)
        if spec is None:
            return ""
        return str(getattr(spec, "ui_panel", "") or "").strip().lower()

    def _selected_tool_panel(self) -> str:
        selected = self._selected_tool_entry()
        selected_id = str(selected.get("id", "")).strip().lower() if isinstance(selected, dict) else ""
        return self._tool_panel_for_id(selected_id)

    def _tool_panel_state_for_id(self, tool_id: str) -> dict[str, object]:
        spec = get_edit_tool(tool_id)
        if spec is None:
            return {}
        panel = str(getattr(spec, "ui_panel", "") or "").strip().lower()
        if not panel:
            return {}
        raw_state = self.w.board_page.current_image_tool_panel_state(panel)
        return normalize_panel_state(tool_id, raw_state)

    def _connect_edit_tool_panel_signals(self) -> None:
        for spec in list_edit_tools():
            tool_id = str(getattr(spec, "id", "") or "").strip().lower()
            if not tool_id:
                continue
            tool_caps = get_board_tool(tool_id)
            has_scene = bool(getattr(tool_caps, "has_scene", False))
            for control in getattr(spec, "ui_controls", ()):
                slider = self.w.board_page.image_tool_control_slider(getattr(control, "key", ""))
                if slider is None:
                    continue
                if has_scene:
                    slider.valueChanged.connect(
                        lambda *_args, current_tool_id=tool_id: self._on_edit_scene_tool_panel_changed(current_tool_id)
                    )
                else:
                    slider.valueChanged.connect(
                        lambda *_args, current_tool_id=tool_id: self._on_edit_image_tool_panel_changed(
                            current_tool_id,
                            insert_at=getattr(get_edit_tool(current_tool_id), "stack_insert_at", None),
                        )
                    )
                slider.sliderPressed.connect(self._on_edit_preview_slider_pressed)
                slider.sliderReleased.connect(self._on_edit_preview_slider_released)

    def _sync_edit_values_from_tool_stack(self) -> None:
        EditVisualState.from_tool_stack(self._edit_tool_stack).apply_to_session(self._edit_session)

    def _sync_tool_stack_ui(self) -> None:
        self._ensure_edit_tool_stack()
        self._sync_edit_values_from_tool_stack()
        self.w.board_page.set_image_tool_add_options(
            [(label, tool_id) for tool_id, label in self._edit_tool_defs]
        )
        rows = []
        for entry in self._edit_tool_stack:
            tool_id = str(entry.get("id", "tool")).strip().lower()
            enabled = bool(entry.get("enabled", True))
            rows.append((self._tool_label_for_id(tool_id), enabled))
        self.w.board_page.set_image_tool_stack_items(rows, self._edit_selected_tool_index)
        for panel, state in panel_state_map_for_tools((tool_id for tool_id, _label in self._edit_tool_defs), self._edit_tool_stack).items():
            self.w.board_page.set_image_tool_panel_state(panel, state)
        selected_panel = self._selected_tool_panel()
        self.w.board_page.set_active_image_tool_panel(selected_panel)
        self._refresh_focus_scene_handles()

    def _current_edit_tool_stack(self) -> list[dict[str, object]]:
        self._ensure_edit_tool_stack()
        return normalize_tool_stack(self._edit_tool_stack)

    def _tool_stack_from_override(self, override: object) -> list[dict[str, object]]:
        return tool_stack_from_override(override, self._edit_focus_kind)

    def _coerce_color_adjustments(self, override: object) -> tuple[float, float, float]:
        return coerce_color_adjustments(override)

    def _color_adjustments_are_default(self, brightness: float, contrast: float, saturation: float) -> bool:
        b_def, c_def, s_def = self._default_color_adjustments()
        return (
            abs(float(brightness) - b_def) < 1e-6
            and abs(float(contrast) - c_def) < 1e-6
            and abs(float(saturation) - s_def) < 1e-6
        )

    def _tool_stack_is_effective(
        self,
        stack: object,
        brightness: float,
        contrast: float,
        saturation: float,
    ) -> bool:
        if not normalize_tool_stack(stack):
            return not self._color_adjustments_are_default(brightness, contrast, saturation)
        return tool_stack_is_effective(stack)

    def _set_tool_state_in_stack(
        self,
        tool_id: str,
        settings: dict[str, object],
        *,
        add_if_missing: bool = True,
        insert_at: int | None = None,
    ) -> None:
        self._ensure_edit_tool_stack()
        entries, idx = upsert_tool_settings(
            self._edit_tool_stack,
            tool_id,
            settings,
            add_if_missing=add_if_missing,
            insert_at=insert_at,
        )
        self._edit_tool_stack = entries
        if idx >= 0:
            self._edit_selected_tool_index = idx

    def _sync_tool_panel_to_stack(self, tool_id: str, *, add_if_missing: bool = True, insert_at: int | None = None) -> None:
        settings = self._tool_panel_state_for_id(tool_id)
        self._set_tool_state_in_stack(
            tool_id,
            settings,
            add_if_missing=add_if_missing,
            insert_at=insert_at,
        )

    def _on_edit_tool_stack_selection_changed(self, row: int) -> None:
        self._edit_selected_tool_index = int(row)
        self._sync_tool_stack_ui()

    def _on_edit_tool_stack_add_clicked(self, tool_id: object = None) -> None:
        if self._edit_image_path is None:
            return
        if tool_id is None:
            tool_id = self.w.board_page.current_image_tool_add_id()
        tool_id = str(tool_id or "").strip().lower()
        if not tool_id:
            return
        self._ensure_edit_tool_stack()
        entries, idx = append_tool(self._edit_tool_stack, tool_id)
        self._edit_tool_stack = entries
        if idx >= 0:
            self._edit_selected_tool_index = idx
        self._sync_tool_stack_ui()
        self._schedule_edit_preview_update(channel=str(self._edit_exr_channel or ""))

    def _on_edit_tool_stack_remove_index(self, idx: int) -> None:
        if self._edit_image_path is None:
            return
        self._remove_edit_tool_stack_index(int(idx))

    def _remove_edit_tool_stack_index(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._edit_tool_stack):
            return
        entries, next_idx = remove_tool_at(self._edit_tool_stack, idx)
        self._edit_tool_stack = entries
        if not self._edit_tool_stack:
            self._edit_tool_stack = self._default_edit_tool_stack()
            self._edit_selected_tool_index = 0
        else:
            self._edit_selected_tool_index = next_idx
        self._sync_tool_stack_ui()
        if isinstance(self._focus_item, BoardVideoItem):
            self._commit_current_focus_video_override()
            self._apply_crop_to_focus_item()
            self._schedule_video_focus_preview(self._edit_video_playhead, immediate=True)
        else:
            self._schedule_edit_preview_update(channel=str(self._edit_exr_channel or ""))

    def _on_edit_tool_stack_up_clicked(self) -> None:
        idx = self.w.board_page.current_image_tool_stack_index()
        if idx <= 0 or idx >= len(self._edit_tool_stack):
            return
        entries, next_idx = move_tool(self._edit_tool_stack, idx, -1)
        self._edit_tool_stack = entries
        self._edit_selected_tool_index = next_idx
        self._sync_tool_stack_ui()
        self._schedule_edit_preview_update(channel=str(self._edit_exr_channel or ""))

    def _on_edit_tool_stack_down_clicked(self) -> None:
        idx = self.w.board_page.current_image_tool_stack_index()
        if idx < 0 or idx >= len(self._edit_tool_stack) - 1:
            return
        entries, next_idx = move_tool(self._edit_tool_stack, idx, 1)
        self._edit_tool_stack = entries
        self._edit_selected_tool_index = next_idx
        self._sync_tool_stack_ui()
        self._schedule_edit_preview_update(channel=str(self._edit_exr_channel or ""))

    def _sync_edit_session_from_panel_state(self, tool_id: str, state: dict[str, object]) -> None:
        key = str(tool_id or "").strip().lower()
        if key == "bcs":
            self._edit_image_brightness = float(state.get("brightness", 0.0))
            self._edit_image_contrast = float(state.get("contrast", 1.0))
            self._edit_image_saturation = float(state.get("saturation", 1.0))
            self.w.board_page.set_image_adjust_labels(
                self._edit_image_brightness,
                self._edit_image_contrast,
                self._edit_image_saturation,
            )
            return
        if key == "vibrance":
            self._edit_image_vibrance = float(state.get("amount", 0.0))
            self.w.board_page.set_image_tool_panel_state("vibrance", {"amount": self._edit_image_vibrance})

    def _schedule_focus_image_preview(self) -> None:
        if self._edit_image_path is None or not isinstance(self._focus_item, BoardImageItem):
            return
        if self._edit_exr_path is not None:
            channel = self.w.board_page.current_exr_channel_value()
            if channel:
                self._edit_exr_channel = str(channel)
                self._schedule_edit_preview_update(channel=str(channel))
            return
        self._schedule_edit_preview_update()

    def _on_edit_image_tool_panel_changed(
        self,
        tool_id: str,
        *,
        insert_at: int | None = None,
    ) -> None:
        panel_state = self._tool_panel_state_for_id(tool_id)
        self._sync_edit_session_from_panel_state(tool_id, panel_state)
        self._sync_tool_panel_to_stack(tool_id, insert_at=insert_at)
        self._commit_current_focus_image_override()
        self._schedule_focus_image_preview()

    def _on_edit_image_adjust_changed(self, *_: object) -> None:
        self._on_edit_image_tool_panel_changed("bcs", insert_at=0)

    def _on_edit_image_vibrance_changed(self, *_: object) -> None:
        self._on_edit_image_tool_panel_changed("vibrance")

    def _apply_crop_to_focus_item(self) -> None:
        scene_runtime = self._scene_tool_runtime("crop")
        apply_hook = getattr(scene_runtime, "apply_to_focus_item", None) if scene_runtime is not None else None
        if callable(apply_hook):
            apply_hook(self)
            return
        if not apply_crop_to_item(
            self._focus_item,
            (
                self._edit_crop_left,
                self._edit_crop_top,
                self._edit_crop_right,
                self._edit_crop_bottom,
            ),
        ):
            return
        group = self._find_group_for_item(self._focus_item)
        if group is not None:
            group.update_bounds()
        self._refresh_scene_workspace()
        self._refresh_focus_scene_handles()

    def _selected_scene_tool_id(self) -> str:
        selected = self._selected_tool_entry()
        selected_id = str(selected.get("id", "")).strip().lower() if isinstance(selected, dict) else ""
        tool_caps = get_board_tool(selected_id)
        if tool_caps is None or not tool_caps.has_scene:
            return ""
        return selected_id

    def _scene_tool_runtime(self, tool_id: str | None = None) -> object | None:
        target_id = str(tool_id or "").strip().lower() or self._selected_scene_tool_id()
        if not target_id:
            return None
        return get_board_tool_scene_runtime(target_id)

    def _clear_focus_crop_handles(self, *, reset_drag: bool = True) -> None:
        scene_runtime = self._scene_tool_runtime()
        clear_hook = getattr(scene_runtime, "clear_handles", None) if scene_runtime is not None else None
        if callable(clear_hook):
            clear_hook(self, reset_drag)
            return
        (
            self._focus_handle_frame,
            self._focus_handle_items,
            self._focus_crop_layout,
        ) = clear_crop_handle_items(
            self._scene,
            self._focus_handle_frame,
            self._focus_handle_items,
        )
        if reset_drag:
            self._focus_crop_drag = None

    def _crop_handles_active(self) -> bool:
        return self._selected_scene_tool_id() != ""

    def _refresh_focus_scene_handles(self) -> None:
        scene_runtime = self._scene_tool_runtime()
        refresh_hook = getattr(scene_runtime, "refresh_handles", None) if scene_runtime is not None else None
        if callable(refresh_hook):
            refresh_hook(self)
            return
        self._clear_focus_crop_handles(reset_drag=False)

    def _refresh_focus_crop_handles(self) -> None:
        self._refresh_focus_scene_handles()

    def _on_edit_scene_tool_panel_changed(self, tool_id: str) -> None:
        scene_runtime = self._scene_tool_runtime(tool_id)
        panel_hook = getattr(scene_runtime, "panel_value_changed", None) if scene_runtime is not None else None
        if callable(panel_hook):
            panel_hook(self)
            return
        self._on_edit_image_tool_panel_changed(
            tool_id,
            insert_at=getattr(get_edit_tool(tool_id), "stack_insert_at", None),
        )

    def handle_view_mouse_press(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        scene_runtime = self._scene_tool_runtime()
        handler = getattr(scene_runtime, "mouse_press", None) if scene_runtime is not None else None
        if callable(handler):
            return bool(handler(self, scene_pos, event))
        return False

    def handle_view_mouse_move(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        scene_runtime = self._scene_tool_runtime()
        handler = getattr(scene_runtime, "mouse_move", None) if scene_runtime is not None else None
        if callable(handler):
            return bool(handler(self, scene_pos, event))
        return False

    def handle_view_mouse_release(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        scene_runtime = self._scene_tool_runtime()
        handler = getattr(scene_runtime, "mouse_release", None) if scene_runtime is not None else None
        if callable(handler):
            return bool(handler(self, scene_pos, event))
        return False

    def _set_current_crop(
        self,
        left: float,
        top: float,
        right: float,
        bottom: float,
        *,
        schedule_preview: bool = True,
    ) -> None:
        left, top, right, bottom = _sanitize_crop_settings(left, top, right, bottom)
        self._edit_crop_left = left
        self._edit_crop_top = top
        self._edit_crop_right = right
        self._edit_crop_bottom = bottom
        self.w.board_page.set_image_tool_panel_state(
            "crop",
            {"left": left, "top": top, "right": right, "bottom": bottom},
        )
        self._set_tool_state_in_stack(
            "crop",
            {"left": left, "top": top, "right": right, "bottom": bottom},
            add_if_missing=True,
        )
        self._apply_crop_to_focus_item()
        if isinstance(self._focus_item, BoardImageItem):
            self._commit_current_focus_image_override()
            if schedule_preview:
                self._schedule_focus_image_preview()
        elif isinstance(self._focus_item, BoardVideoItem):
            self._commit_current_focus_video_override()
            if schedule_preview:
                self._schedule_video_focus_preview(self._edit_video_playhead, immediate=True)

    def _on_edit_crop_changed(self, *_: object) -> None:
        self._on_edit_scene_tool_panel_changed("crop")

    def _reset_edit_image_adjustments(self) -> None:
        for tool_id, add_if_missing, insert_at in (
            ("bcs", True, 0),
            ("vibrance", False, None),
            ("crop", False, None),
        ):
            spec = get_edit_tool(tool_id)
            if spec is None:
                continue
            panel = str(getattr(spec, "ui_panel", "") or "").strip().lower()
            state = default_panel_state(tool_id)
            if panel:
                self.w.board_page.set_image_tool_panel_state(panel, state)
            self._set_tool_state_in_stack(
                tool_id,
                state,
                add_if_missing=add_if_missing,
                insert_at=insert_at,
            )
        self._apply_crop_to_focus_item()
        if isinstance(self._focus_item, BoardVideoItem):
            self._commit_current_focus_video_override()
            self._schedule_video_focus_preview(self._edit_video_playhead, immediate=True)
            return
        self._on_edit_image_adjust_changed()

    def _on_edit_preview_slider_pressed(self) -> None:
        self._edit_preview_dragging = True

    def _on_edit_preview_slider_released(self) -> None:
        self._edit_preview_dragging = False
        self._schedule_edit_preview_update()

    def _schedule_edit_preview_update(self, channel: Optional[str] = None) -> None:
        if channel:
            self._edit_preview_pending_channel = str(channel)
        if self._edit_preview_timer is None:
            self._edit_preview_timer = QtCore.QTimer(self.w)
            self._edit_preview_timer.setSingleShot(True)
            self._edit_preview_timer.timeout.connect(self._flush_edit_preview_update)
        self._edit_preview_timer.start(60)

    def _flush_edit_preview_update(self) -> None:
        self._edit_preview_timer = None
        max_dim = self._edit_preview_fast_dim if self._edit_preview_dragging else self._edit_preview_full_dim
        if self._edit_exr_path is not None:
            channel = str(
                self._edit_preview_pending_channel
                or self._edit_exr_channel
                or self.w.board_page.current_exr_channel_value()
                or ""
            ).strip()
            self._edit_preview_pending_channel = None
            if channel:
                self._queue_exr_channel_preview(channel, max_dim=max_dim)
            return
        self._edit_preview_pending_channel = None
        if self._edit_image_path is not None:
            self._queue_image_adjust_preview(self._edit_image_path, max_dim=max_dim)

    def _on_edit_exr_channel_changed(self, _index: int) -> None:
        channel = self.w.board_page.current_exr_channel_value()
        if not channel:
            return
        self._edit_exr_channel = str(channel)
        self._commit_current_focus_image_override()
        self._schedule_edit_preview_update(channel=str(channel))

    def _on_edit_exr_gamma_changed(self, *_: object) -> None:
        self._edit_exr_gamma = self.w.board_page.current_exr_gamma()
        self._edit_exr_srgb = self.w.board_page.current_exr_srgb_enabled()
        self.w.board_page.set_exr_gamma_label(self._edit_exr_gamma)
        self._commit_current_focus_image_override()
        if self._edit_exr_path is None:
            return
        channel = self.w.board_page.current_exr_channel_value()
        if channel:
            self._edit_exr_channel = str(channel)
            self._schedule_edit_preview_update(channel=str(channel))

    def _commit_current_focus_image_override(self) -> None:
        if not isinstance(self._focus_item, BoardImageItem):
            return
        filename = str(self._focus_item.data(1) or "").strip()
        if not filename:
            return
        tool_stack = self._current_edit_tool_stack()
        effective = self._tool_stack_is_effective(
            tool_stack,
            self._edit_image_brightness,
            self._edit_image_contrast,
            self._edit_image_saturation,
        )
        if commit_image_override(
            self._image_exr_display_overrides,
            filename,
            current=self._image_exr_display_overrides.get(filename),
            effective=effective,
            brightness=self._edit_image_brightness,
            contrast=self._edit_image_contrast,
            saturation=self._edit_image_saturation,
            crop_left=self._edit_crop_left,
            crop_top=self._edit_crop_top,
            crop_right=self._edit_crop_right,
            crop_bottom=self._edit_crop_bottom,
            tool_stack=tool_stack,
            exr_channel=self._edit_exr_channel if self._edit_exr_path is not None else None,
            exr_gamma=self._edit_exr_gamma if self._edit_exr_path is not None else None,
            exr_srgb=self._edit_exr_srgb if self._edit_exr_path is not None else None,
        ):
            self._sync_board_state_overrides()
            self._dirty = True

    def _commit_current_focus_video_override(self) -> None:
        if not isinstance(self._focus_item, BoardVideoItem):
            return
        filename = str(self._focus_item.data(1) or "").strip()
        if not filename:
            return
        tool_stack = self._current_edit_tool_stack()
        if commit_video_override(
            self._image_exr_display_overrides,
            filename,
            current=self._image_exr_display_overrides.get(filename),
            effective=self._tool_stack_is_effective(tool_stack, 0.0, 1.0, 1.0),
            crop_left=self._edit_crop_left,
            crop_top=self._edit_crop_top,
            crop_right=self._edit_crop_right,
            crop_bottom=self._edit_crop_bottom,
            tool_stack=tool_stack,
        ):
            self._sync_board_state_overrides()
            self._dirty = True

    def _handle_exr_info_finished(
        self, success: bool, channels_obj: object, size_obj: object, note_obj: object
    ) -> None:
        if self._edit_exr_path is None:
            return
        path = self._edit_exr_path
        channels = channels_obj if isinstance(channels_obj, list) else []
        size = size_obj if isinstance(size_obj, QtCore.QSize) else None
        note = str(note_obj or "")
        info_lines = [
            "Type: EXR",
            f"Name: {path.name}",
        ]
        if size is not None:
            info_lines.append(f"Size: {size.width()} x {size.height()}")
        info_lines.append(f"Path: {path}")
        footer = note or "Channels"
        if success and channels:
            self._edit_exr_channels = [str(c) for c in channels]
            options, default_value = self._build_exr_channel_options(self._edit_exr_channels)
            self.w.board_page.set_exr_channels(options)
            self.w.board_page.set_edit_panel_content(
                "Edit Mode: Image",
                info_lines,
                list_items=[str(c) for c in channels],
                footer=footer,
            )
            if default_value is None and self._edit_exr_channels:
                default_value = self._edit_exr_channels[0]
            preferred_channel = str(self._edit_exr_channel or "").strip()
            if preferred_channel:
                available_values = [value for _label, value in options]
                if preferred_channel in available_values:
                    default_value = preferred_channel
                elif preferred_channel in self._edit_exr_channels:
                    default_value = preferred_channel
            if default_value:
                self._edit_exr_channel = str(default_value)
                # Set combo selection to default
                combo = self.w.board_page.edit_exr_channel_combo
                idx = combo.findData(default_value)
                if idx < 0:
                    idx = combo.findText(default_value)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                self._queue_exr_channel_preview(default_value)
        elif success:
            self.w.board_page.set_edit_panel_content(
                "Edit Mode: Image",
                info_lines,
                list_items=["No channels found."],
                footer=footer,
            )
        else:
            self._edit_exr_channels = []
            self.w.board_page.set_exr_channels([])
            self.w.board_page.set_edit_panel_content(
                "Edit Mode: Image",
                info_lines,
                list_items=["Failed to read EXR."],
                footer=str(note_obj or "Failed to read EXR."),
            )

    def _handle_exr_preview_finished(
        self, success: bool, channel: str, payload: object, error: object
    ) -> None:
        if success:
            if isinstance(self._focus_item, BoardImageItem):
                filename = str(self._focus_item.data(1) or "").strip()
                if apply_exr_preview_result(
                    self._image_exr_display_overrides,
                    self._focus_item,
                    filename,
                    payload=payload,
                    channel=str(self._edit_exr_channel or channel or ""),
                    gamma=self._edit_exr_gamma,
                    srgb=self._edit_exr_srgb,
                    brightness=self._edit_image_brightness,
                    contrast=self._edit_image_contrast,
                    saturation=self._edit_image_saturation,
                    tool_stack=self._current_edit_tool_stack(),
                ):
                    self._sync_board_state_overrides()
                    self._dirty = True
                    return
            else:
                pixmap = preview_payload_to_pixmap(payload)
                if pixmap is not None:
                    self.w.board_page.show_edit_preview_image(pixmap, label=f"Channel: {channel}")
                    return
        msg = str(error or "Failed to render channel.")
        self.w.board_page.edit_footer.setText(msg)

    def _handle_image_adjust_preview_finished(self, success: bool, payload: object, error: object) -> None:
        if success:
            if isinstance(self._focus_item, BoardImageItem):
                current_stack = self._current_edit_tool_stack()
                if apply_image_adjust_preview_result(
                    self._image_exr_display_overrides,
                    self._focus_item,
                    str(self._focus_item.data(1) or "").strip(),
                    payload=payload,
                    effective=self._tool_stack_is_effective(
                        current_stack,
                        self._edit_image_brightness,
                        self._edit_image_contrast,
                        self._edit_image_saturation,
                    ),
                    current=self._image_exr_display_overrides.get(str(self._focus_item.data(1) or "").strip()),
                    brightness=self._edit_image_brightness,
                    contrast=self._edit_image_contrast,
                    saturation=self._edit_image_saturation,
                    tool_stack=current_stack,
                ):
                    self._sync_board_state_overrides()
                    self._dirty = True
                    return
            else:
                pixmap = preview_payload_to_pixmap(payload)
                if pixmap is not None:
                    self.w.board_page.show_edit_preview_image(pixmap, label="Image adjustments")
                    return
        msg = str(error or "Failed to render image adjustments.")
        self.w.board_page.edit_footer.setText(msg)

    def enter_focus_mode(self, item: QtWidgets.QGraphicsItem) -> None:
        if self._focus_item is item:
            return
        self.exit_focus_mode()
        self._focus_item = item
        try:
            self.w.board_page.view.setFocus()
        except Exception:
            pass
        scene = self._scene
        # Dim non-focused items and disable interaction.
        for obj in scene.items():
            if obj is item:
                continue
            self._focus_saved[id(obj)] = (obj.isEnabled(), obj.opacity())
            obj.setEnabled(False)
            obj.setOpacity(0.15)
        # Add overlay
        self._refresh_scene_workspace(extra_rect=item.sceneBoundingRect())
        overlay = QtWidgets.QGraphicsRectItem(scene.sceneRect())
        overlay.setBrush(QtGui.QColor(0, 0, 0, 120))
        overlay.setPen(QtCore.Qt.PenStyle.NoPen)
        overlay.setZValue(9_000)
        scene.addItem(overlay)
        self._focus_overlay = overlay
        # Bring focused item to front
        item.setZValue(10_000)
        self.w.board_page.set_edit_panel_visible(True)
        self._edit_focus_kind = str(item.data(0) or "")
        self._refresh_focus_crop_handles()

    def exit_focus_mode(self) -> None:
        if self._focus_item is None:
            return
        self._clear_focus_crop_handles()
        # Restore item states
        for obj in self._scene.items():
            saved = self._focus_saved.pop(id(obj), None)
            if saved is not None:
                enabled, opacity = saved
                obj.setEnabled(enabled)
                obj.setOpacity(opacity)
        if self._focus_overlay is not None:
            self._scene.removeItem(self._focus_overlay)
            self._focus_overlay = None
        if self._focus_item is not None:
            if isinstance(self._focus_item, BoardImageItem):
                filename = str(self._focus_item.data(1) or "").strip()
                if not filename or filename not in self._image_exr_display_overrides:
                    self._focus_item.set_override_pixmap(None)
                    self._focus_item.set_crop_norm(*self._default_crop_settings())
            if isinstance(self._focus_item, BoardVideoItem):
                filename = str(self._focus_item.data(1) or "").strip()
                override = self._image_exr_display_overrides.get(filename)
                if isinstance(override, dict):
                    self._apply_override_to_video_item(self._focus_item, override)
                else:
                    self._focus_item.set_override_pixmap(None)
                    self._focus_item.set_crop_norm(*self._default_crop_settings())
            if isinstance(self._focus_item, BoardSequenceItem):
                self._focus_item.set_override_pixmap(None)
            self._focus_item.setZValue(0)
        self._focus_item = None
        self._reset_edit_session_for_kind("")
        self._edit_timeline_scrubbing = False
        self._sequence_playback.stop()
        self._video_playback.stop()
        self.w.board_page.edit_timeline_play_btn.setText(play_button_label(False))
        if self._video_preview_timer is not None and self._video_preview_timer.isActive():
            self._video_preview_timer.stop()
        self._video_preview_pending = None
        self._release_focus_video_cap()
        if self._edit_preview_timer is not None and self._edit_preview_timer.isActive():
            self._edit_preview_timer.stop()
        self._edit_preview_timer = None
        self._edit_preview_pending_channel = None
        self._edit_preview_dragging = False
        self._edit_exr_preview_pending_channel = None
        self._edit_exr_preview_pending_max_dim = 0
        self._edit_image_preview_pending_path = None
        self._edit_image_preview_pending_max_dim = 0
        if self._edit_exr_thread is not None:
            try:
                self._edit_exr_thread.quit()
                self._edit_exr_thread.wait(1000)
            except Exception:
                pass
        self._edit_exr_preview_busy = False
        self._edit_exr_thread = None
        self._edit_exr_worker = None
        if self._edit_image_thread is not None:
            try:
                self._edit_image_thread.quit()
                self._edit_image_thread.wait(1000)
            except Exception:
                pass
        self._edit_image_preview_busy = False
        self._edit_image_thread = None
        self._edit_image_worker = None
        self._edit_image_path = None
        self._edit_exr_path = None
        self.w.board_page.set_image_adjust_controls_visible(False)
        self.w.board_page.set_edit_panel_visible(False)
        self.w.board_page.set_timeline_bar_visible(False)
        self.w.board_page.set_edit_preview_visible(True)

    def _queue_exr_channel_preview(self, channel: str, max_dim: int = 0) -> None:
        if self._edit_exr_path is None:
            return
        if self._edit_exr_preview_busy:
            self._edit_exr_preview_pending_channel = str(channel)
            self._edit_exr_preview_pending_max_dim = int(max_dim)
            return
        worker = ExrChannelPreviewWorker(
            self._edit_exr_path,
            channel,
            self._edit_exr_gamma,
            self._edit_exr_srgb,
            self._edit_image_brightness,
            self._edit_image_contrast,
            self._edit_image_saturation,
            int(max_dim),
            self._current_edit_tool_stack(),
        )
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        self._edit_exr_preview_busy = True
        self._edit_exr_thread = thread
        self._edit_exr_worker = worker
        worker.finished.connect(self._ui_bridge.on_exr_preview_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_edit_exr_preview_cycle_finished)
        thread.start()

    def _on_edit_exr_preview_cycle_finished(self) -> None:
        self._edit_exr_preview_busy = False
        self._edit_exr_thread = None
        self._edit_exr_worker = None
        pending_channel = self._edit_exr_preview_pending_channel
        pending_dim = self._edit_exr_preview_pending_max_dim
        self._edit_exr_preview_pending_channel = None
        self._edit_exr_preview_pending_max_dim = 0
        if self._edit_exr_path is not None and pending_channel:
            self._queue_exr_channel_preview(pending_channel, max_dim=pending_dim)

    def _queue_exr_display_for_item(
        self,
        item: BoardImageItem,
        channel: str,
        gamma: float,
        srgb: bool,
        brightness: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        tool_stack: object = None,
    ) -> None:
        if item.scene() is None:
            return
        path = item.file_path()
        if path.suffix.lower() != ".exr":
            return
        worker = ExrChannelPreviewWorker(
            path,
            str(channel),
            float(gamma),
            bool(srgb),
            float(brightness),
            float(contrast),
            float(saturation),
            1024,
            tool_stack,
        )
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        self._exr_item_preview_threads.append(thread)
        self._exr_item_preview_workers.append(worker)

        def _on_finished(success: bool, _channel: str, payload: object, _error: object) -> None:
            if success:
                apply_preview_payload_to_item(item, payload)

        worker.finished.connect(_on_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def _cleanup() -> None:
            try:
                self._exr_item_preview_threads.remove(thread)
            except ValueError:
                pass
            try:
                self._exr_item_preview_workers.remove(worker)
            except ValueError:
                pass

        thread.finished.connect(_cleanup)
        thread.start()

    def _queue_image_adjust_preview(self, path: Path, max_dim: int = 0) -> None:
        if self._edit_image_preview_busy:
            self._edit_image_preview_pending_path = path
            self._edit_image_preview_pending_max_dim = int(max_dim)
            return
        worker = ImageAdjustPreviewWorker(
            path,
            self._edit_image_brightness,
            self._edit_image_contrast,
            self._edit_image_saturation,
            int(max_dim),
            self._current_edit_tool_stack(),
        )
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        self._edit_image_preview_busy = True
        self._edit_image_thread = thread
        self._edit_image_worker = worker
        worker.finished.connect(self._handle_image_adjust_preview_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_edit_image_preview_cycle_finished)
        thread.start()

    def _on_edit_image_preview_cycle_finished(self) -> None:
        self._edit_image_preview_busy = False
        self._edit_image_thread = None
        self._edit_image_worker = None
        pending_path = self._edit_image_preview_pending_path
        pending_dim = self._edit_image_preview_pending_max_dim
        self._edit_image_preview_pending_path = None
        self._edit_image_preview_pending_max_dim = 0
        if pending_path is not None and self._edit_image_path is not None:
            self._queue_image_adjust_preview(pending_path, max_dim=pending_dim)

    def _queue_image_adjust_for_item(
        self,
        item: BoardImageItem,
        brightness: float,
        contrast: float,
        saturation: float,
        tool_stack: object = None,
    ) -> None:
        if item.scene() is None:
            return
        path = item.file_path()
        if path.suffix.lower() == ".exr":
            return
        worker = ImageAdjustPreviewWorker(
            path,
            float(brightness),
            float(contrast),
            float(saturation),
            1024,
            tool_stack,
        )
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        self._exr_item_preview_threads.append(thread)
        self._exr_item_preview_workers.append(worker)

        def _on_finished(success: bool, payload: object, _error: object) -> None:
            if success:
                apply_preview_payload_to_item(item, payload)

        worker.finished.connect(_on_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def _cleanup() -> None:
            try:
                self._exr_item_preview_threads.remove(thread)
            except ValueError:
                pass
            try:
                self._exr_item_preview_workers.remove(worker)
            except ValueError:
                pass

        thread.finished.connect(_cleanup)
        thread.start()

    def _on_scene_changed(self) -> None:
        if self._loading:
            return
        if self._saving:
            return
        if self._group_tree_is_editing():
            return
        self._prune_empty_groups()
        if self._scene_interaction_depth > 0:
            self._refresh_scene_workspace()
            self._update_view_quality()
            return
        self._sync_board_state_from_scene()
        self._refresh_scene_workspace()
        self._dirty = True
        self._update_view_quality()
        self._schedule_history_snapshot()
        self._schedule_group_tree_update()

    def _get_display_pixmap(self, path: Path, max_dim: Optional[int] = None) -> QtGui.QPixmap:
        try:
            mtime = path.stat().st_mtime
        except Exception:
            return QtGui.QPixmap(str(path))
        if max_dim is None:
            max_dim = self._max_display_dim
        key = (path, max_dim)
        cached = self._media_cache.cached_pixmap(self._media_cache.pixmaps, path, max_dim, mtime)
        if cached is not None:
            return cached
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull() and path.suffix.lower() == ".exr":
            pixmap = self._get_exr_pixmap(path, max_dim)
        if not pixmap.isNull():
            if pixmap.width() > max_dim or pixmap.height() > max_dim:
                pixmap = pixmap.scaled(
                    max_dim,
                    max_dim,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
        return self._media_cache.store_pixmap(self._media_cache.pixmaps, path, max_dim, mtime, pixmap)

    def _get_thumb_cache_dir(self) -> Optional[Path]:
        return self._media_cache.project_thumb_cache_dir(self._project_root)

    def _exr_cache_key(self, path: Path, max_dim: int) -> Optional[Path]:
        return self._media_cache.exr_cache_path(self._project_root, path, max_dim)

    def _get_exr_pixmap(self, path: Path, max_dim: int) -> QtGui.QPixmap:
        cache_path = self._exr_cache_key(path, max_dim)
        if cache_path is not None and cache_path.exists():
            cached = QtGui.QPixmap(str(cache_path))
            if not cached.isNull():
                return cached
        if cv2 is None:
            return self._build_media_placeholder("EXR", f"{path.name}\n(OpenCV missing)")
        if not os.environ.get("OPENCV_IO_ENABLE_OPENEXR"):
            return self._build_media_placeholder("EXR", "OpenEXR codec disabled")
        try:
            import numpy as np  # type: ignore
        except Exception:
            return self._build_media_placeholder("EXR", path.name)
        try:
            img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        except Exception:
            img = None
        if img is None:
            return self._build_media_placeholder("EXR", "Failed to read EXR")
        if img.ndim == 2:
            img = np.stack([img, img, img], axis=-1)
        if img.ndim == 3 and img.shape[2] == 1:
            img = np.repeat(img, 3, axis=2)
        if img.ndim == 3 and img.shape[2] >= 3:
            img = img[:, :, :3]
        # Normalize to 8-bit for display.
        if img.dtype != np.uint8:
            img_f = img.astype(np.float32)
            max_val = float(np.nanmax(img_f)) if img_f.size else 1.0
            if max_val <= 1.0:
                img_f = img_f * 255.0
            else:
                img_f = (img_f / max_val) * 255.0
            img = np.clip(img_f, 0, 255).astype(np.uint8)
        # OpenCV uses BGR; convert to RGB for Qt.
        try:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        except Exception:
            pass
        h, w = img.shape[:2]
        bytes_per_line = img.shape[2] * w
        qimage = QtGui.QImage(img.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(qimage.copy())
        if pixmap.width() > max_dim or pixmap.height() > max_dim:
            pixmap = pixmap.scaled(
                max_dim,
                max_dim,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        if cache_path is not None:
            try:
                pixmap.save(str(cache_path), "PNG")
            except Exception:
                pass
        return pixmap

    def _get_image_size(self, path: Path, fallback: Optional[QtCore.QSize] = None) -> QtCore.QSize:
        if path.suffix.lower() == ".exr":
            if OpenEXR is not None:
                try:
                    exr = OpenEXR.InputFile(str(path))
                    header = exr.header()
                    dw = header.get("dataWindow")
                    if dw is not None:
                        w = int(dw.max.x - dw.min.x + 1)
                        h = int(dw.max.y - dw.min.y + 1)
                        return QtCore.QSize(w, h)
                except Exception:
                    pass
            if cv2 is not None:
                try:
                    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                    if img is not None:
                        return QtCore.QSize(int(img.shape[1]), int(img.shape[0]))
                except Exception:
                    pass
        try:
            reader = QtGui.QImageReader(str(path))
            size = reader.size()
            if size.isValid():
                return size
        except Exception:
            pass
        if fallback is not None and fallback.isValid():
            return fallback
        return QtCore.QSize(1, 1)

    def _build_media_placeholder(self, label: str, subtitle: str) -> QtGui.QPixmap:
        size = QtCore.QSize(320, 180)
        pixmap = QtGui.QPixmap(size)
        pixmap.fill(QtGui.QColor("#22262d"))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtGui.QPen(QtGui.QColor("#3a404a"), 2))
        painter.drawRoundedRect(pixmap.rect().adjusted(2, 2, -2, -2), 10, 10)
        painter.setPen(QtGui.QColor("#d6d9df"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(20)
        painter.setFont(font)
        painter.drawText(pixmap.rect().adjusted(0, -10, 0, -10), QtCore.Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(QtGui.QColor("#9aa3ad"))
        font.setBold(False)
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(
            pixmap.rect().adjusted(12, 120, -12, -12),
            QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap,
            subtitle,
        )
        painter.end()
        return pixmap

    def _get_video_thumbnail(self, path: Path, max_dim: int) -> QtGui.QPixmap:
        try:
            mtime = path.stat().st_mtime
        except Exception:
            return self._build_media_placeholder("VIDEO", path.name)
        key = (path, max_dim)
        cached = self._media_cache.cached_pixmap(self._media_cache.video_thumbnails, path, max_dim, mtime)
        if cached is not None:
            return cached
        if cv2 is None:
            return self._build_media_placeholder("VIDEO", path.name)
        pixmap = QtGui.QPixmap()
        try:
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                cap.release()
                return self._build_media_placeholder("VIDEO", path.name)
            ok, frame = cap.read()
            cap.release()
            if ok and frame is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
                pixmap = QtGui.QPixmap.fromImage(image)
        except Exception:
            pixmap = QtGui.QPixmap()
        if pixmap.isNull():
            pixmap = self._build_media_placeholder("VIDEO", path.name)
        else:
            if pixmap.width() > max_dim or pixmap.height() > max_dim:
                pixmap = pixmap.scaled(
                    max_dim,
                    max_dim,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
        return self._media_cache.store_pixmap(
            self._media_cache.video_thumbnails,
            path,
            max_dim,
            mtime,
            pixmap,
        )

    def _get_video_frame_pixmap(self, path: Path, frame_index: int, max_dim: int) -> Optional[QtGui.QPixmap]:
        if cv2 is None:
            return None
        try:
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                cap.release()
                return None
            cap.set(1, int(frame_index))  # CAP_PROP_POS_FRAMES
            ok, frame = cap.read()
            cap.release()
            if not ok or frame is None:
                return None
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
            pixmap = QtGui.QPixmap.fromImage(image)
            if pixmap.width() > max_dim or pixmap.height() > max_dim:
                pixmap = pixmap.scaled(
                    max_dim,
                    max_dim,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            return pixmap
        except Exception:
            return None

    def _ensure_focus_video_cap(self) -> None:
        if cv2 is None:
            return
        if self._focus_video_path is None:
            return
        if self._focus_video_cap is not None:
            return
        try:
            cap = cv2.VideoCapture(str(self._focus_video_path))
            if cap.isOpened():
                self._focus_video_cap = cap
                self._focus_video_cap_frame_index = -1
        except Exception:
            self._focus_video_cap = None
            self._focus_video_cap_frame_index = -1

    def _release_focus_video_cap(self) -> None:
        try:
            if self._focus_video_cap is not None:
                self._focus_video_cap.release()
        except Exception:
            pass
        self._focus_video_cap = None
        self._focus_video_cap_frame_index = -1

    def _schedule_video_focus_preview(self, frame_index: int, delay_ms: int = 40, immediate: bool = False) -> None:
        self._video_preview_pending = int(frame_index)
        if self._video_preview_timer is None:
            self._video_preview_timer = QtCore.QTimer(self.w)
            self._video_preview_timer.setSingleShot(True)
            self._video_preview_timer.timeout.connect(self._flush_video_focus_preview)
        if immediate:
            if self._video_preview_timer.isActive():
                self._video_preview_timer.stop()
            self._flush_video_focus_preview()
            return
        if not self._video_preview_timer.isActive():
            self._video_preview_timer.start(max(10, int(delay_ms)))

    def _flush_video_focus_preview(self) -> None:
        if self._video_preview_pending is None:
            return
        idx = self._video_preview_pending
        self._video_preview_pending = None
        if not isinstance(self._focus_item, BoardVideoItem):
            return
        self._ensure_focus_video_cap()
        max_dim = self._edit_video_playback_dim if self._video_playback.is_playing() else self._max_display_dim
        pixmap = self._get_focus_video_frame_pixmap(
            idx,
            max_dim=max_dim,
            prefer_fast=self._video_playback.is_playing(),
        )
        if pixmap is not None:
            self._focus_item.set_override_pixmap(pixmap)

    def _get_focus_video_frame_pixmap(
        self,
        frame_index: int,
        max_dim: int,
        prefer_fast: bool = False,
    ) -> Optional[QtGui.QPixmap]:
        if cv2 is None:
            return None
        if self._focus_video_cap is None:
            return None
        try:
            target_frame = max(0, int(frame_index))
            sequential_read = target_frame == (self._focus_video_cap_frame_index + 1)
            if not sequential_read:
                self._focus_video_cap.set(1, target_frame)  # CAP_PROP_POS_FRAMES
            ok, frame = self._focus_video_cap.read()
            if not ok or frame is None:
                return None
            self._focus_video_cap_frame_index = target_frame
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
        except Exception:
            return None

    def _sequence_frame_paths(self, dir_path: Path) -> list[Path]:
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        frames = [p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
        return sorted(frames, key=lambda p: p.name)

    def _get_sequence_thumbnail(self, dir_path: Path, max_dim: int) -> QtGui.QPixmap:
        try:
            mtime = dir_path.stat().st_mtime
        except Exception:
            return self._build_media_placeholder("SEQ", dir_path.name)
        key = (dir_path, max_dim)
        cached = self._media_cache.cached_pixmap(self._media_cache.sequence_thumbnails, dir_path, max_dim, mtime)
        if cached is not None:
            return cached
        frames = self._sequence_frame_paths(dir_path)
        if not frames:
            return self._build_media_placeholder("SEQ", dir_path.name)
        pixmap = self._get_display_pixmap(frames[0], max_dim)
        if pixmap.isNull():
            pixmap = self._build_media_placeholder("SEQ", dir_path.name)
        return self._media_cache.store_pixmap(
            self._media_cache.sequence_thumbnails,
            dir_path,
            max_dim,
            mtime,
            pixmap,
        )

    def _is_video_file(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in VIDEO_EXTS

    def _is_image_file(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in IMAGE_EXTS

    def _is_pic_file(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in PIC_EXTS

    def _relative_to_project(self, path: Path) -> str:
        if self._project_root is None:
            return str(path)
        try:
            return str(path.relative_to(self._project_root))
        except Exception:
            return str(path)

    def _resolve_project_path(self, path_text: str) -> Path:
        p = Path(path_text)
        if p.is_absolute() or self._project_root is None:
            return p
        return self._project_root / p

    def _update_view_quality(self) -> None:
        view = self.w.board_page.view
        item_count = sum(
            1
            for i in self._scene.items()
            if i.data(0) in ("image", "note", "video", "sequence", "group")
        )
        low_quality = item_count >= 200
        if low_quality == self._low_quality:
            return
        self._low_quality = low_quality
        if low_quality:
            view.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing, False)
            view.setRenderHints(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
            view.setRenderHints(QtGui.QPainter.RenderHint.TextAntialiasing, False)
        else:
            view.setRenderHints(
                QtGui.QPainter.RenderHint.Antialiasing
                | QtGui.QPainter.RenderHint.SmoothPixmapTransform
                | QtGui.QPainter.RenderHint.TextAntialiasing
            )

    def update_visible_items(self) -> None:
        view = self.w.board_page.view
        visible_rect = view.mapToScene(view.viewport().rect()).boundingRect().adjusted(-200, -200, 200, 200)
        zoom = view.transform().m11()
        want_full = zoom >= 0.45
        new_visible: set[int] = set()
        for item in self._scene.items(visible_rect):
            if isinstance(item, BoardImageItem):
                new_visible.add(id(item))
                item.set_quality("full" if want_full else "proxy")
        for item_id in list(self._visible_images - new_visible):
            for item in self._scene.items():
                if id(item) == item_id and isinstance(item, BoardImageItem):
                    item.set_quality("proxy")
                    break
        self._visible_images = new_visible

    def undo(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        payload = self._set_board_state(json.loads(self._history[self._history_index]))
        self._loading = True
        self._scene.blockSignals(True)
        self._scene.clear()
        self._apply_payload(payload)
        self._scene.blockSignals(False)
        self._loading = False
        self._refresh_scene_workspace()
        self._dirty = True
        self._update_view_quality()
        self.update_visible_items()

    def redo(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        payload = self._set_board_state(json.loads(self._history[self._history_index]))
        self._loading = True
        self._scene.blockSignals(True)
        self._scene.clear()
        self._apply_payload(payload)
        self._scene.blockSignals(False)
        self._loading = False
        self._refresh_scene_workspace()
        self._dirty = True
        self._update_view_quality()
        self.update_visible_items()

    def _build_payload(self) -> dict:
        data = {"items": []}
        image_ids: set[str] = set()
        for item in self._scene.items():
            kind = item.data(0)
            if kind == "image":
                file_id = str(item.data(1))
                image_ids.add(file_id)
                data["items"].append({
                    "type": "image",
                    "file": file_id,
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "scale": item.scale(),
                })
            elif kind == "video":
                data["items"].append({
                    "type": "video",
                    "file": str(item.data(1)),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "scale": item.scale(),
                })
            elif kind == "sequence":
                data["items"].append({
                    "type": "sequence",
                    "dir": str(item.data(1)),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "scale": item.scale(),
                })
            elif kind == "note" and isinstance(item, BoardNoteItem):
                data["items"].append({
                    "type": "note",
                    **item.note_data(),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                })
            elif kind == "group" and isinstance(item, BoardGroupItem):
                members = serialize_group_members(item, BoardNoteItem)
                if not members:
                    continue
                data["items"].append({
                    "type": "group",
                    "color": item.color_hex(),
                    "members": members,
                })
        media_ids = set(image_ids)
        media_ids.update(
            str(item.data(1) or "")
            for item in self._scene.items()
            if item.data(0) == "video"
        )
        data["image_display_overrides"] = {
            key: value
            for key, value in self._image_exr_display_overrides.items()
            if key in media_ids and isinstance(value, dict)
        }
        return data

    def _apply_payload(self, payload: dict) -> None:
        assets_dir = self._project_root / ".skyforge_board_assets" if self._project_root else None
        self._image_exr_display_overrides = self._parse_image_display_overrides(payload)
        image_map: dict[str, QtWidgets.QGraphicsPixmapItem] = {}
        video_map: dict[str, QtWidgets.QGraphicsItem] = {}
        sequence_map: dict[str, QtWidgets.QGraphicsItem] = {}
        note_map: dict[str, BoardNoteItem] = {}
        pending_groups = []
        for entry in payload.get("items", []):
            if entry.get("type") == "image" and assets_dir is not None:
                filename = entry.get("file", "")
                path = assets_dir / filename
                item = BoardImageItem(self, path)
                if item.boundingRect().isNull():
                    continue
                item.setFlags(
                    QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
                )
                item.setTransformOriginPoint(item.boundingRect().center())
                item.setData(0, "image")
                item.setData(1, filename)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                self._scene.addItem(item)
                if filename:
                    image_map[str(filename)] = item
                    override = self._image_exr_display_overrides.get(str(filename))
                    if isinstance(override, dict):
                        self._apply_override_to_image_item(item, override)
            elif entry.get("type") == "video" and assets_dir is not None:
                filename = entry.get("file", "")
                path = assets_dir / filename
                item = BoardVideoItem(self, path)
                if item.boundingRect().isNull():
                    continue
                item.setFlags(
                    QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
                )
                item.setTransformOriginPoint(item.boundingRect().center())
                item.setData(0, "video")
                item.setData(1, filename)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                self._scene.addItem(item)
                if filename:
                    video_map[str(filename)] = item
                    override = self._image_exr_display_overrides.get(str(filename))
                    if isinstance(override, dict):
                        self._apply_override_to_video_item(item, override)
            elif entry.get("type") == "sequence":
                dir_text = str(entry.get("dir", ""))
                dir_path = self._resolve_project_path(dir_text)
                item = BoardSequenceItem(self, dir_path)
                if item.boundingRect().isNull():
                    continue
                item.setFlags(
                    QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
                )
                item.setTransformOriginPoint(item.boundingRect().center())
                item.setData(0, "sequence")
                item.setData(1, dir_text)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                self._scene.addItem(item)
                if dir_text:
                    sequence_map[str(dir_text)] = item
            elif entry.get("type") == "note":
                item = BoardNoteItem(entry.get("text", ""))
                align = entry.get("align", "left")
                align_flag = QtCore.Qt.AlignmentFlag.AlignHCenter if align == "center" else QtCore.Qt.AlignmentFlag.AlignLeft
                bg = entry.get("bg", "#99000000")
                item.set_note_style(int(entry.get("font_size", 12)), align_flag, QtGui.QColor(bg))
                item.setScale(float(entry.get("scale", 1.0)))
                item.setData(0, "note")
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                note_id = entry.get("id") or uuid.uuid4().hex
                item.set_note_id(str(note_id))
                self._scene.addItem(item)
                note_map[item.note_id()] = item
            elif entry.get("type") == "group":
                pending_groups.append(entry)
        for entry in pending_groups:
            color = QtGui.QColor(entry.get("color", "#4aa3ff"))
            group = BoardGroupItem(color)
            group.setData(0, "group")
            self._scene.addItem(group)
            for ref in entry.get("members", []):
                if isinstance(ref, str):
                    item = image_map.get(str(ref))
                    if item is not None:
                        group.add_member(item)
                    continue
                if isinstance(ref, dict):
                    r_type = ref.get("type")
                    r_id = str(ref.get("id", ""))
                    if r_type == "image":
                        item = image_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
                    elif r_type == "video":
                        item = video_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
                    elif r_type == "sequence":
                        item = sequence_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
                    elif r_type == "note":
                        item = note_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
            group.update_bounds()

    def _schedule_history_snapshot(self) -> None:
        if self._loading or self._saving:
            return
        if self._history_timer is not None:
            return
        self._history_timer = QtCore.QTimer(self.w)
        self._history_timer.setSingleShot(True)
        self._history_timer.timeout.connect(self._capture_history_snapshot)
        self._history_timer.start(250)

    def _capture_history_snapshot(self) -> None:
        self._history_timer = None
        payload = self._current_board_state()
        serialized = json.dumps(payload, sort_keys=True)
        if self._history and self._history[self._history_index] == serialized:
            return
        if self._history_index < len(self._history) - 1:
            self._history = self._history[: self._history_index + 1]
        self._history.append(serialized)
        self._history_index = len(self._history) - 1

    def _reset_history(self, payload: dict) -> None:
        payload = self._set_board_state(payload)
        serialized = json.dumps(payload, sort_keys=True)
        self._history = [serialized]
        self._history_index = 0

    def _schedule_group_tree_update(self) -> None:
        self._groups_panel.schedule_update()

    def _update_group_tree(self) -> None:
        self._groups_panel.update_tree()

    def _sync_tree_selection_from_scene(self) -> None:
        self._groups_panel.sync_tree_selection_from_scene()

    def _on_scene_selection_changed(self) -> None:
        self._groups_panel.on_scene_selection_changed()

    def _find_scene_item_for_tree_info(self, info: tuple) -> Optional[QtWidgets.QGraphicsItem]:
        return self._groups_panel.find_scene_item_for_tree_info(info)

    def _select_tree_info_target(self, info: tuple) -> None:
        self._groups_panel.select_tree_info_target(info)

    def _tree_info_path(self, info: tuple) -> Optional[Path]:
        return self._groups_panel.tree_info_path(info)

    def show_groups_tree_context_menu(self, pos: QtCore.QPoint) -> bool:
        return self._groups_panel.show_context_menu(pos)

    def rename_group_tree_entry(self, info: tuple, desired_name: Optional[str] = None) -> bool:
        if not self._ui_alive():
            return False
        if self._project_root is None:
            self._notify("Select a project first.")
            return False
        kind = str(info[0]) if info else ""
        if kind not in ("image", "video", "sequence"):
            return False
        item = self._find_scene_item_for_tree_info(info)
        if item is None:
            self._notify("Item not found.")
            return False
        src_path = self._tree_info_path(info)
        if src_path is None or not src_path.exists():
            self._notify("Source file not found.")
            return False

        if kind in ("image", "video"):
            if desired_name is None:
                default_name = src_path.stem
                new_base, ok = QtWidgets.QInputDialog.getText(
                    self.w,
                    "Rename File",
                    "New file name (extension preserved):",
                    QtWidgets.QLineEdit.EchoMode.Normal,
                    default_name,
                )
                if not ok:
                    return False
            else:
                new_base = desired_name
            dest_path, error = build_rename_destination(kind, src_path, str(new_base))
        else:
            if desired_name is None:
                default_name = src_path.name
                new_name, ok = QtWidgets.QInputDialog.getText(
                    self.w,
                    "Rename Sequence Folder",
                    "New folder name:",
                    QtWidgets.QLineEdit.EchoMode.Normal,
                    default_name,
                )
                if not ok:
                    return False
            else:
                new_name = desired_name
            dest_path, error = build_rename_destination(kind, src_path, str(new_name))

        if error:
            self._notify(error)
            return False
        if dest_path is None:
            return False
        try:
            src_path.rename(dest_path)
        except Exception as exc:
            self._notify(f"Rename failed:\n{exc}")
            return False

        if kind == "image":
            old_name = str(item.data(1) or "")
            item.setData(1, dest_path.name)
            if isinstance(item, BoardImageItem):
                item.set_file_path(dest_path)
            if self._edit_image_path == src_path:
                self._edit_image_path = dest_path
            if self._edit_exr_path == src_path:
                self._edit_exr_path = dest_path
            rename_override_key(self._image_exr_display_overrides, old_name, dest_path.name)
        elif kind == "video":
            old_name = str(item.data(1) or "")
            item.setData(1, dest_path.name)
            if isinstance(item, BoardVideoItem):
                item.set_file_path(dest_path)
            if self._focus_video_path == src_path:
                self._focus_video_path = dest_path
            if self._edit_video_path == src_path:
                self._edit_video_path = dest_path
            rename_override_key(self._image_exr_display_overrides, old_name, dest_path.name)
        elif kind == "sequence":
            rel = self._relative_to_project(dest_path)
            item.setData(1, rel)
            if isinstance(item, BoardSequenceItem):
                item.set_dir_path(dest_path)
            if self._edit_seq_dir == src_path:
                self._edit_seq_dir = dest_path
                self._edit_seq_frames = self._sequence_frame_paths(dest_path)

        self._commit_scene_mutation(history=True, update_groups=True)
        self._notify(f"Renamed to: {dest_path.name}")
        return True

    def _notify(self, text: str) -> None:
        self.w.asset_status.setText(text)
