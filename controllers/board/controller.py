from __future__ import annotations

import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets
from core.board_actions import (
    BoardAction,
    BoardInteractionSession,
    BoardMutationHooks,
    BoardMutationResult,
    commit_board_action,
)
from core.board_edit.context import BoardEditContext
from core.board_edit.media_runtime import SequencePlaybackRuntime, VideoPlaybackRuntime
from core.board_edit.workers import UiBridge
from core.board_preview import PreviewRuntimeState
from core.board_edit.session import EditSessionState
from core.board_apply_runtime import BoardApplyRuntime
from core.board_io import backup_board_payload, board_path, load_board_payload, save_board_payload
from core.board_media_cache import BoardMediaCache
from controllers.board.edit_focus_controller import BoardEditFocusController
from controllers.board.edit_panel_controller import BoardEditPanelController
from controllers.board.edit_preview_controller import BoardEditPreviewController
from controllers.board.edit_timeline_controller import BoardEditTimelineController
from controllers.board.edit_tools_controller import BoardEditToolsController
from controllers.board.group_actions_controller import BoardGroupActionsController
from controllers.board.groups_controller import BoardGroupsController
from controllers.board.history_controller import BoardHistoryController
from controllers.board.legacy_payload_controller import BoardLegacyPayloadController
from controllers.board.media_import_controller import BoardMediaImportController
from controllers.board.media_render_controller import BoardMediaRenderController
from controllers.board.notes_controller import BoardNotesController
from controllers.board.scene_view_controller import BoardSceneViewController
from core.board_state import (
    ApplyPayloadState,
    apply_pending_groups_to_scene,
    apply_image_override_to_item,
    apply_video_override_to_item,
    build_group_item,
    build_scene_item_from_entry,
    clone_payload,
    commit_image_override,
    commit_video_override,
    parse_image_display_overrides,
    payload_item_count,
    prepare_apply_state,
    rename_override_key,
    reapply_scene_overrides,
    register_built_item,
    sync_board_state_overrides,
)
from core.board_scene.groups import build_rename_destination
from core.board_scene.items import BoardGroupItem, BoardImageItem, BoardNoteItem, BoardSequenceItem, BoardVideoItem
from tools.board_tools.edit import discover_edit_tools
from tools.board_tools.image import apply_image_tool_stack
from tools.board_tools.validation import (
    BoardToolContractIssue,
    format_board_tool_contract_issues,
    validate_board_tool_contracts,
)


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.board_edit.workers import ExrChannelPreviewWorker, ImageAdjustPreviewWorker, VideoSegmentWorker, VideoToSequenceWorker
    from video.player import VideoController

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
        self._media_render = BoardMediaRenderController(self)
        self._scene_view = BoardSceneViewController(self)
        self._history: list[str] = []
        self._history_index = -1
        self._history_timer: Optional[QtCore.QTimer] = None
        self._post_load_reapply_timer: Optional[QtCore.QTimer] = None
        self._apply_state = ApplyPayloadState()
        self._apply_runtime = BoardApplyRuntime(self.w, self._apply_state, self._apply_payload_batch)
        self._legacy_payload = BoardLegacyPayloadController(self)
        self._scene_interaction_depth = 0
        self._scene_interaction = BoardInteractionSession()
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
        self._edit_context = BoardEditContext(self._edit_session)
        self._edit_image_path: Optional[Path] = None
        self._board_tool_contract_issues: list[BoardToolContractIssue] = []
        self._edit_tool_specs = discover_edit_tools()
        self._edit_tools = BoardEditToolsController(self)
        self.validate_board_tool_contracts(notify=False)
        self._edit_timeline = BoardEditTimelineController(self)
        self._edit_preview = BoardEditPreviewController(self)
        self._edit_focus = BoardEditFocusController(self)
        self._edit_panel = BoardEditPanelController(self)
        self._media_import = BoardMediaImportController(self)
        self._notes = BoardNotesController(self)
        self._history_controller = BoardHistoryController(self)
        self._edit_image_thread: Optional[QtCore.QThread] = None
        self._edit_image_worker: Optional[ImageAdjustPreviewWorker] = None
        self._edit_preview_timer: Optional[QtCore.QTimer] = None
        self._edit_preview_pending_channel: Optional[str] = None
        self._edit_preview_dragging: bool = False
        self._edit_preview_fast_dim: int = 640
        self._edit_preview_full_dim: int = 1280
        self._edit_exr_preview_busy: bool = False
        self._edit_exr_preview_runtime = PreviewRuntimeState()
        self._edit_exr_preview_request_key: Optional[str] = None
        self._edit_exr_preview_pending_channel: Optional[str] = None
        self._edit_exr_preview_pending_max_dim: int = 0
        self._edit_image_preview_busy: bool = False
        self._edit_image_preview_runtime = PreviewRuntimeState()
        self._edit_image_preview_request_key: Optional[str] = None
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
        self._focus_saved: dict[int, tuple[bool, float]] = {}
        self._focus_video_path: Optional[Path] = None
        self._focus_video_cap = None
        self._focus_video_cap_frame_index: int = -1
        self._video_preview_timer: Optional[QtCore.QTimer] = None
        self._video_preview_pending: Optional[int] = None
        self._shutting_down: bool = False

    def refresh_edit_tool_registry(self) -> dict[str, object]:
        specs = self._edit_tools.refresh_registry()
        self.validate_board_tool_contracts(force=False, notify=True)
        return specs

    def validate_board_tool_contracts(self, *, force: bool = False, notify: bool = True) -> list[BoardToolContractIssue]:
        issues = validate_board_tool_contracts(force=force)
        self._board_tool_contract_issues = list(issues)
        if not issues:
            return []
        for line in format_board_tool_contract_issues(issues):
            logger.warning("Board tool contract issue: %s", line)
        if notify:
            self._notify(f"Board tools: {len(issues)} contract issue(s). Check logs.")
        return list(issues)

    def available_edit_tools(self, media_kind: str) -> list[dict[str, object]]:
        return self._edit_tools.available_tools(media_kind)

    def default_edit_tool_state(self, tool_id: str) -> dict[str, object]:
        return self._edit_tools.default_tool_state(tool_id)

    def normalize_edit_tool_state(self, entry: object) -> dict[str, object]:
        return self._edit_tools.normalize_tool_state(entry)

    def _sync_edit_tool_defs_for_kind(self, media_kind: str) -> None:
        self._edit_tools.sync_defs_for_kind(media_kind)

    def prepare_edit_tools_for_kind(self, media_kind: str, override: object = None) -> None:
        self._edit_tools.prepare_stack_for_kind(media_kind, override=override)

    def current_edit_tool_stack(self) -> list[dict[str, object]]:
        return self._edit_tools.current_stack()

    def edit_visual_state(self):
        return self._edit_tools.visual_state()

    def edit_tool_stack_is_effective(
        self,
        stack: object,
        brightness: float,
        contrast: float,
        saturation: float,
    ) -> bool:
        return self._edit_tools.stack_is_effective(stack, brightness, contrast, saturation)

    def _reset_edit_session_for_kind(self, media_kind: str) -> None:
        self.edit_context.reset_for_kind(media_kind)

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
    def edit_context(self) -> BoardEditContext:
        return self._edit_context

    @property
    def _edit_focus_kind(self) -> Optional[str]:
        return self._edit_context.focus_kind

    @_edit_focus_kind.setter
    def _edit_focus_kind(self, value: Optional[str]) -> None:
        self._edit_context.focus_kind = value

    @property
    def _edit_tool_stack(self) -> list[dict[str, object]]:
        return self._edit_context.stack

    @_edit_tool_stack.setter
    def _edit_tool_stack(self, value: list[dict[str, object]]) -> None:
        self._edit_context.stack = value

    @property
    def _edit_selected_tool_index(self) -> int:
        return self._edit_context.selected_index

    @_edit_selected_tool_index.setter
    def _edit_selected_tool_index(self, value: int) -> None:
        self._edit_context.selected_index = value

    @property
    def _edit_tool_defs(self) -> list[tuple[str, str]]:
        return self._edit_context.tool_defs

    @_edit_tool_defs.setter
    def _edit_tool_defs(self, value: list[tuple[str, str]]) -> None:
        self._edit_context.set_tool_defs(value)

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
        kind: str = "scene_mutation",
        history_label: str | None = None,
        history: bool = True,
        save: bool = False,
        reveal_items: Optional[list[QtWidgets.QGraphicsItem]] = None,
        update_groups: bool = True,
    ) -> dict:
        action = BoardAction(
            kind=kind,
            history_label=history_label,
            affects_history=history,
            should_save=save,
            update_groups=update_groups,
        )
        result = self.commit_board_action(action, reveal_items=reveal_items)
        return dict(result.state)

    def commit_board_action(
        self,
        action: BoardAction,
        *,
        reveal_items: Optional[list[QtWidgets.QGraphicsItem]] = None,
    ) -> BoardMutationResult:
        return commit_board_action(
            action,
            BoardMutationHooks(
                sync_state=self._sync_board_state_from_scene,
                refresh_workspace=self._refresh_scene_workspace,
                mark_dirty=self._mark_board_dirty,
                schedule_history=self._schedule_history_snapshot,
                schedule_groups=self._schedule_group_tree_update,
                reveal_items=self._reveal_scene_items,
                save=self.save_board,
            ),
            reveal_items=reveal_items,
        )

    def _mark_board_dirty(self) -> None:
        self._dirty = True

    def begin_scene_interaction(
        self,
        *,
        kind: str = "scene_interaction",
        history_label: str | None = None,
    ) -> None:
        self._scene_interaction.begin(kind=kind, history_label=history_label)
        self._scene_interaction_depth = self._scene_interaction.depth

    def end_scene_interaction(self, *, history: bool = True, update_groups: bool = True) -> dict:
        action = self._scene_interaction.end_action(history=history, update_groups=update_groups)
        self._scene_interaction_depth = self._scene_interaction.depth
        if action is None:
            return self._clone_payload(self._board_state)
        result = self.commit_board_action(action)
        return dict(result.state)

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
        self._media_import.add_image()

    def add_image_from_path(
        self, src: Path, scene_pos: Optional[QtCore.QPointF] = None
    ) -> Optional[QtWidgets.QGraphicsPixmapItem]:
        return self._media_import.add_image_from_path(src, scene_pos=scene_pos)

    def add_image_from_url(self, url: str, scene_pos: Optional[QtCore.QPointF] = None) -> None:
        self._media_import.add_image_from_url(url, scene_pos=scene_pos)

    def add_image_from_image_data(self, image_data, scene_pos: Optional[QtCore.QPointF] = None) -> None:
        self._media_import.add_image_from_image_data(image_data, scene_pos=scene_pos)

    def add_video(self) -> None:
        self._media_import.add_video()

    def add_video_from_path(
        self, src: Path, scene_pos: Optional[QtCore.QPointF] = None
    ) -> Optional[QtWidgets.QGraphicsItem]:
        return self._media_import.add_video_from_path(src, scene_pos=scene_pos)

    def _find_iconvert(self) -> Optional[Path]:
        return self._media_import.find_iconvert()

    def convert_picnc_interactive(
        self,
        src_path: Optional[Path] = None,
        scene_pos: Optional[QtCore.QPointF] = None,
    ) -> Optional[QtWidgets.QGraphicsPixmapItem]:
        return self._media_import.convert_picnc_interactive(src_path, scene_pos=scene_pos)

    def add_paths_from_selection(
        self, paths: list[Path], scene_pos: Optional[QtCore.QPointF] = None
    ) -> None:
        self._media_import.add_paths_from_selection(paths, scene_pos=scene_pos)

    def add_sequence(self) -> None:
        self._media_import.add_sequence()

    def add_sequence_from_dir(
        self, dir_path: Path, scene_pos: Optional[QtCore.QPointF] = None
    ) -> Optional[QtWidgets.QGraphicsItem]:
        return self._media_import.add_sequence_from_dir(dir_path, scene_pos=scene_pos)

    def convert_video_to_sequence(self, item: QtWidgets.QGraphicsItem) -> None:
        self._media_import.convert_video_to_sequence(item)

    def _extract_video_frames(self, video_path: Path, out_dir: Path) -> bool:
        return self._media_import.extract_video_frames(video_path, out_dir)

    def add_note(self) -> None:
        self._notes.add_note()

    def add_note_at(self, scene_pos: Optional[QtCore.QPointF]) -> None:
        self._notes.add_note_at(scene_pos)

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
        self.begin_scene_interaction(kind="delete_selection", history_label="Delete selection")
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
        self._scene_view.fit_view()

    def _current_view_scene_center(self) -> QtCore.QPointF:
        return self._scene_view.current_view_scene_center()

    def _workspace_item_bounds(self) -> QtCore.QRectF:
        return self._scene_view.workspace_item_bounds()

    def _refresh_scene_workspace(self, extra_rect: Optional[QtCore.QRectF] = None) -> None:
        self._scene_view.refresh_scene_workspace(extra_rect=extra_rect)

    def _reveal_scene_items(self, items: list[QtWidgets.QGraphicsItem]) -> None:
        self._scene_view.reveal_scene_items(items)

    def layout_selection_grid(self, *, commit: bool = True) -> None:
        self._scene_view.layout_selection_grid(commit=commit)

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
            tool_stack_is_effective=self._tool_stack_is_effective,
            queue_exr_display_for_item=self._queue_exr_display_for_item,
            queue_image_adjust_for_item=self._queue_image_adjust_for_item,
        )

    def _apply_override_to_video_item(self, item: BoardVideoItem, override: dict[str, object]) -> None:
        apply_video_override_to_item(
            item,
            override,
            tool_stack_from_override=self._tool_stack_from_override,
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
        self._notes.edit_note(item, global_pos=global_pos)

    def open_media_item(self, item: QtWidgets.QGraphicsItem) -> None:
        self._edit_panel.open_media_item(item)

    def open_image_item(self, item: QtWidgets.QGraphicsItem) -> None:
        self._edit_panel.open_image_item(item)

    def _open_video_dialog(self, path: Path) -> None:
        self._edit_panel.open_video_dialog(path)

    def _show_edit_panel_for_video(self, path: Path) -> None:
        self._edit_panel.show_panel_for_video(path)

    def _show_edit_panel_for_sequence(self, dir_path: Path) -> None:
        self._edit_panel.show_panel_for_sequence(dir_path)

    def _show_edit_panel_for_image(self, path: Path) -> None:
        self._edit_panel.show_panel_for_image(path)

    def _ensure_edit_video_controller(self) -> None:
        self._edit_panel.ensure_video_controller()

    def _init_edit_video_timeline(self, path: Path) -> None:
        self._edit_timeline.init_video_timeline(path)

    def _set_edit_timeline_frame_label(self, frame: int) -> None:
        self._edit_timeline.set_frame_label(frame)

    def _apply_sequence_focus_frame(self, frame: int) -> None:
        self._edit_timeline.apply_sequence_focus_frame(frame)

    def _apply_video_focus_frame(self, frame: int) -> None:
        self._edit_timeline.apply_video_focus_frame(frame)

    def _on_edit_timeline_playhead(self, frame: int) -> None:
        self._edit_timeline.on_timeline_playhead(frame)

    def _on_edit_timeline_scrub_state(self, active: bool) -> None:
        self._edit_timeline.on_timeline_scrub_state(active)

    def _on_edit_timeline_selected(self, index: int) -> None:
        self._edit_timeline.on_timeline_selected(index)

    def _find_clip_at_playhead(self) -> Optional[int]:
        return self._edit_timeline.find_clip_at_playhead()

    def _split_edit_clip(self) -> None:
        self._edit_timeline.split_clip()

    def _export_edit_clip(self) -> None:
        self._edit_timeline.export_clip()

    def _on_edit_sequence_timeline_playhead(self, frame: int) -> None:
        self._edit_timeline.on_sequence_timeline_playhead(frame)

    def _toggle_edit_sequence_play(self) -> None:
        self._edit_timeline.toggle_sequence_play()

    def _on_sequence_play_state_changed(self, playing: bool) -> None:
        self._edit_timeline.on_sequence_play_state_changed(playing)

    def _on_video_play_state_changed(self, playing: bool) -> None:
        self._edit_timeline.on_video_play_state_changed(playing)

    def _toggle_edit_timeline_play(self) -> None:
        self._edit_timeline.toggle_play()

    def _advance_edit_video_frame(self) -> None:
        self._edit_timeline.advance_video_frame()

    def _advance_edit_sequence_frame(self) -> None:
        self._edit_timeline.advance_sequence_frame()

    def _load_exr_channels_into_panel(self, path: Path) -> None:
        self._edit_preview.load_exr_channels_into_panel(path)

    @staticmethod
    def _build_exr_channel_options(channels: list[str]) -> tuple[list[tuple[str, str]], Optional[str]]:
        return BoardEditPreviewController.build_exr_channel_options(channels)

    def _default_edit_tool_stack(self) -> list[dict[str, object]]:
        return self._edit_tools.default_stack()

    def _ensure_edit_tool_stack(self) -> None:
        self._edit_tools.ensure_stack()

    def _tool_label_for_id(self, tool_id: str) -> str:
        return self._edit_tools.tool_label_for_id(tool_id)

    def _tool_entry_from_id(self, tool_id: str) -> dict[str, object]:
        return self._edit_tools.tool_entry_from_id(tool_id)

    def _selected_tool_entry(self) -> Optional[dict[str, object]]:
        return self._edit_tools.selected_tool_entry()

    def _tool_panel_for_id(self, tool_id: str) -> str:
        return self._edit_tools.tool_panel_for_id(tool_id)

    def _selected_tool_panel(self) -> str:
        return self._edit_tools.selected_tool_panel()

    def _tool_panel_state_for_id(self, tool_id: str) -> dict[str, object]:
        return self._edit_tools.panel_state_for_id(tool_id)

    def _connect_edit_tool_panel_signals(self) -> None:
        self._edit_tools.connect_panel_signals()

    def _sync_edit_values_from_tool_stack(self) -> None:
        self._edit_tools.sync_values_from_stack()

    def _edit_visual_state(self):
        return self.edit_visual_state()

    def _sync_tool_stack_ui(self) -> None:
        self._edit_tools.sync_stack_ui()

    def _current_edit_tool_stack(self) -> list[dict[str, object]]:
        return self.current_edit_tool_stack()

    def _tool_stack_from_override(self, override: object) -> list[dict[str, object]]:
        return self._edit_tools.stack_from_override(override)

    def _coerce_color_adjustments(self, override: object) -> tuple[float, float, float]:
        return self._edit_tools.coerce_color_adjustments(override)

    def _tool_stack_is_effective(
        self,
        stack: object,
        brightness: float,
        contrast: float,
        saturation: float,
    ) -> bool:
        return self.edit_tool_stack_is_effective(stack, brightness, contrast, saturation)

    def _set_tool_state_in_stack(
        self,
        tool_id: str,
        settings: dict[str, object],
        *,
        add_if_missing: bool = True,
        insert_at: int | None = None,
    ) -> None:
        self._edit_tools.set_tool_state(
            tool_id,
            settings,
            add_if_missing=add_if_missing,
            insert_at=insert_at,
        )

    def _sync_tool_panel_to_stack(self, tool_id: str, *, add_if_missing: bool = True, insert_at: int | None = None) -> None:
        self._edit_tools.sync_panel_to_stack(
            tool_id,
            add_if_missing=add_if_missing,
            insert_at=insert_at,
        )

    def _on_edit_tool_stack_selection_changed(self, row: int) -> None:
        self._edit_tools.on_stack_selection_changed(row)

    def _on_edit_tool_stack_add_clicked(self, tool_id: object = None) -> None:
        self._edit_tools.on_stack_add_clicked(tool_id)

    def _on_edit_tool_stack_remove_index(self, idx: int) -> None:
        self._edit_tools.on_stack_remove_index(idx)

    def _remove_edit_tool_stack_index(self, idx: int) -> None:
        self._edit_tools.remove_stack_index(idx)

    def _on_edit_tool_stack_up_clicked(self) -> None:
        self._edit_tools.on_stack_up_clicked()

    def _on_edit_tool_stack_down_clicked(self) -> None:
        self._edit_tools.on_stack_down_clicked()

    def _schedule_focus_image_preview(self) -> None:
        self._edit_tools.schedule_focus_image_preview()

    def _on_edit_image_tool_panel_changed(
        self,
        tool_id: str,
        *,
        insert_at: int | None = None,
    ) -> None:
        self._edit_tools.on_image_tool_panel_changed(tool_id, insert_at=insert_at)

    def _apply_scene_tool_to_focus_item(self) -> None:
        self._edit_focus.apply_scene_tool_to_focus_item()

    def _selected_scene_tool_id(self) -> str:
        return self._edit_focus.selected_scene_tool_id()

    def _scene_tool_runtime(self, tool_id: str | None = None) -> object | None:
        return self._edit_focus.scene_tool_runtime(tool_id)

    def _clear_focus_scene_tool_handles(self, *, reset_drag: bool = True) -> None:
        self._edit_focus.clear_scene_tool_handles(reset_drag=reset_drag)

    def _scene_tool_handles_active(self) -> bool:
        return self._edit_focus.scene_tool_handles_active()

    def _refresh_focus_scene_handles(self) -> None:
        self._edit_focus.refresh_scene_handles()

    def _on_edit_scene_tool_panel_changed(self, tool_id: str) -> None:
        self._edit_focus.on_scene_tool_panel_changed(tool_id)

    def handle_view_mouse_press(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        return self._edit_focus.handle_view_mouse_press(scene_pos, event)

    def handle_view_mouse_move(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        return self._edit_focus.handle_view_mouse_move(scene_pos, event)

    def handle_view_mouse_release(self, scene_pos: QtCore.QPointF, event: QtGui.QMouseEvent) -> bool:
        return self._edit_focus.handle_view_mouse_release(scene_pos, event)

    def _reset_edit_image_adjustments(self) -> None:
        self._edit_tools.reset_settings()

    def _on_edit_preview_slider_pressed(self) -> None:
        self._edit_preview.on_slider_pressed()

    def _on_edit_preview_slider_released(self) -> None:
        self._edit_preview.on_slider_released()

    def _schedule_edit_preview_update(self, channel: Optional[str] = None) -> None:
        self._edit_preview.schedule_update(channel)

    def _flush_edit_preview_update(self) -> None:
        self._edit_preview.flush_update()

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
        visual = self._edit_visual_state()
        effective = self._tool_stack_is_effective(
            tool_stack,
            visual.brightness,
            visual.contrast,
            visual.saturation,
        )
        if commit_image_override(
            self._image_exr_display_overrides,
            filename,
            current=self._image_exr_display_overrides.get(filename),
            effective=effective,
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
            tool_stack=tool_stack,
        ):
            self._sync_board_state_overrides()
            self._dirty = True

    def _handle_exr_info_finished(
        self, success: bool, channels_obj: object, size_obj: object, note_obj: object
    ) -> None:
        self._edit_preview.handle_exr_info_finished(success, channels_obj, size_obj, note_obj)

    def _handle_exr_preview_finished(
        self, success: bool, channel: str, payload: object, error: object
    ) -> None:
        self._edit_preview.handle_exr_preview_finished(success, channel, payload, error)

    def _handle_image_adjust_preview_finished(self, success: bool, payload: object, error: object) -> None:
        self._edit_preview.handle_image_adjust_preview_finished(success, payload, error)

    def enter_focus_mode(self, item: QtWidgets.QGraphicsItem) -> None:
        self._edit_focus.enter_focus_mode(item)

    def exit_focus_mode(self) -> None:
        self._edit_focus.exit_focus_mode()

    def _queue_exr_channel_preview(self, channel: str, max_dim: int = 0) -> None:
        self._edit_preview.queue_exr_channel_preview(channel, max_dim=max_dim)

    def _on_edit_exr_preview_cycle_finished(self) -> None:
        self._edit_preview.on_exr_preview_cycle_finished()

    def _queue_exr_display_for_item(
        self,
        item: BoardImageItem,
        channel: str,
        gamma: float,
        srgb: bool,
        tool_stack: object = None,
    ) -> None:
        self._edit_preview.queue_exr_display_for_item(
            item,
            channel,
            gamma,
            srgb,
            tool_stack=tool_stack,
        )

    def _queue_image_adjust_preview(self, path: Path, max_dim: int = 0) -> None:
        self._edit_preview.queue_image_adjust_preview(path, max_dim=max_dim)

    def _on_edit_image_preview_cycle_finished(self) -> None:
        self._edit_preview.on_image_preview_cycle_finished()

    def _queue_image_adjust_for_item(
        self,
        item: BoardImageItem,
        tool_stack: object = None,
    ) -> None:
        self._edit_preview.queue_image_adjust_for_item(
            item,
            tool_stack=tool_stack,
        )

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
        return self._media_render.get_display_pixmap(path, max_dim=max_dim)

    def _get_thumb_cache_dir(self) -> Optional[Path]:
        return self._media_render.get_thumb_cache_dir()

    def _exr_cache_key(self, path: Path, max_dim: int) -> Optional[Path]:
        return self._media_render.exr_cache_key(path, max_dim)

    def _get_exr_pixmap(self, path: Path, max_dim: int) -> QtGui.QPixmap:
        return self._media_render.get_exr_pixmap(path, max_dim)

    def _get_image_size(self, path: Path, fallback: Optional[QtCore.QSize] = None) -> QtCore.QSize:
        return self._media_render.get_image_size(path, fallback=fallback)

    def _build_media_placeholder(self, label: str, subtitle: str) -> QtGui.QPixmap:
        return self._media_render.build_media_placeholder(label, subtitle)

    def _get_video_thumbnail(self, path: Path, max_dim: int) -> QtGui.QPixmap:
        return self._media_render.get_video_thumbnail(path, max_dim)

    def _get_video_frame_pixmap(self, path: Path, frame_index: int, max_dim: int) -> Optional[QtGui.QPixmap]:
        return self._media_render.get_video_frame_pixmap(path, frame_index, max_dim)

    def _ensure_focus_video_cap(self) -> None:
        self._edit_focus.ensure_video_cap()

    def _release_focus_video_cap(self) -> None:
        self._edit_focus.release_video_cap()

    def _schedule_video_focus_preview(self, frame_index: int, delay_ms: int = 40, immediate: bool = False) -> None:
        self._edit_focus.schedule_video_preview(frame_index, delay_ms=delay_ms, immediate=immediate)

    def _flush_video_focus_preview(self) -> None:
        self._edit_focus.flush_video_preview()

    def _get_focus_video_frame_pixmap(
        self,
        frame_index: int,
        max_dim: int,
        prefer_fast: bool = False,
    ) -> Optional[QtGui.QPixmap]:
        return self._edit_focus.get_video_frame_pixmap(
            frame_index,
            max_dim=max_dim,
            prefer_fast=prefer_fast,
        )

    def _sequence_frame_paths(self, dir_path: Path) -> list[Path]:
        return self._media_render.sequence_frame_paths(dir_path)

    def _get_sequence_thumbnail(self, dir_path: Path, max_dim: int) -> QtGui.QPixmap:
        return self._media_render.get_sequence_thumbnail(dir_path, max_dim)

    def _is_video_file(self, path: Path) -> bool:
        return self._media_render.is_video_file(path)

    def _is_image_file(self, path: Path) -> bool:
        return self._media_render.is_image_file(path)

    def _is_pic_file(self, path: Path) -> bool:
        return self._media_render.is_pic_file(path)

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
        self._scene_view.update_view_quality()

    def update_visible_items(self) -> None:
        self._scene_view.update_visible_items()

    def undo(self) -> None:
        self._history_controller.undo()

    def redo(self) -> None:
        self._history_controller.redo()

    def _build_payload(self) -> dict:
        return self._legacy_payload.build_payload()

    def _apply_payload(self, payload: dict) -> None:
        self._legacy_payload.apply_payload(payload)

    def _schedule_history_snapshot(self) -> None:
        self._history_controller.schedule_snapshot()

    def _capture_history_snapshot(self) -> None:
        self._history_controller.capture_snapshot()

    def _reset_history(self, payload: dict) -> None:
        self._history_controller.reset(payload)

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
