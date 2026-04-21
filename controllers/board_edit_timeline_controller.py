from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets

from core.board_edit.media_runtime import clamp_playhead, frame_label_text, loop_next_playhead, play_button_label
from core.board_edit.workers import VideoSegmentWorker
from core.board_scene.items import BoardSequenceItem, BoardVideoItem

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional video backend
    cv2 = None  # type: ignore


class BoardEditTimelineController:
    """Owns edit timeline playback, clip splitting, and segment export."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.w = board_controller.w

    def init_video_timeline(self, path: Path) -> None:
        board = self.board
        board._edit_video_path = path
        board._edit_video_playhead = 0
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
        board._edit_video_fps = max(1.0, float(fps))
        board._video_playback.set_fps(board._edit_video_fps)
        board._edit_video_total = max(0, total)
        if board._edit_video_total <= 0:
            board._edit_video_clips = []
            board._edit_selected_clip = -1
            self.w.board_page.edit_timeline.set_data(0, [], 0)
            self.w.board_page.edit_timeline_split_btn.setEnabled(False)
            self.w.board_page.edit_timeline_export_btn.setEnabled(False)
            self.w.board_page.edit_video_status.setText("Timeline unavailable (no frame count).")
            return
        board._edit_video_clips = [(0, board._edit_video_total - 1)]
        board._edit_selected_clip = 0
        self.w.board_page.edit_timeline.set_data(
            board._edit_video_total,
            board._edit_video_clips,
            board._edit_video_playhead,
        )
        self.w.board_page.edit_timeline.set_selected_clip(board._edit_selected_clip)
        self.w.board_page.edit_timeline_split_btn.setEnabled(True)
        self.w.board_page.edit_timeline_export_btn.setEnabled(True)

    def set_frame_label(self, frame: int) -> None:
        if hasattr(self.w.board_page, "edit_timeline_frame_label"):
            self.w.board_page.edit_timeline_frame_label.setText(frame_label_text(frame))

    def apply_sequence_focus_frame(self, frame: int) -> None:
        board = self.board
        if not isinstance(board._focus_item, BoardSequenceItem):
            return
        if not board._edit_seq_frames:
            return
        idx = clamp_playhead(frame, len(board._edit_seq_frames))
        frame_path = board._edit_seq_frames[idx]
        pixmap = board._get_display_pixmap(frame_path, max_dim=board._max_display_dim)
        board._focus_item.set_override_pixmap(pixmap)

    def apply_video_focus_frame(self, frame: int) -> None:
        board = self.board
        if not isinstance(board._focus_item, BoardVideoItem):
            return
        idx = clamp_playhead(frame, board._edit_video_total)
        if board._video_playback.is_playing():
            board._schedule_video_focus_preview(idx, immediate=True)
        else:
            delay = 140 if board._edit_timeline_scrubbing else 40
            board._schedule_video_focus_preview(idx, delay_ms=delay)

    def on_timeline_playhead(self, frame: int) -> None:
        board = self.board
        if board._edit_focus_kind == "sequence":
            self.on_sequence_timeline_playhead(int(frame))
            return
        board._edit_video_playhead = clamp_playhead(int(frame), board._edit_video_total)
        if (
            board._edit_video_controller is not None
            and not board._edit_timeline_scrubbing
            and not board._video_playback.is_playing()
        ):
            board._edit_video_controller.seek_frame(board._edit_video_playhead)
        self.apply_video_focus_frame(board._edit_video_playhead)
        self.set_frame_label(board._edit_video_playhead)

    def on_timeline_scrub_state(self, active: bool) -> None:
        board = self.board
        board._edit_timeline_scrubbing = bool(active)
        if not active and board._edit_focus_kind == "video":
            if board._edit_video_controller is not None:
                board._edit_video_controller.seek_frame(board._edit_video_playhead)
            if isinstance(board._focus_item, BoardVideoItem):
                board._schedule_video_focus_preview(board._edit_video_playhead, immediate=True)

    def on_timeline_selected(self, index: int) -> None:
        self.board._edit_selected_clip = int(index)

    def find_clip_at_playhead(self) -> Optional[int]:
        board = self.board
        for idx, (start, end) in enumerate(board._edit_video_clips):
            if start <= board._edit_video_playhead <= end:
                return idx
        return None

    def split_clip(self) -> None:
        board = self.board
        if not board._edit_video_clips:
            return
        idx = board._edit_selected_clip if board._edit_selected_clip >= 0 else self.find_clip_at_playhead()
        if idx is None:
            return
        start, end = board._edit_video_clips[idx]
        ph = board._edit_video_playhead
        if ph <= start or ph >= end:
            return
        left = (start, ph)
        right = (ph + 1, end)
        board._edit_video_clips[idx:idx + 1] = [left, right]
        board._edit_selected_clip = idx
        self.w.board_page.edit_timeline.set_data(
            board._edit_video_total,
            board._edit_video_clips,
            board._edit_video_playhead,
        )

    def export_clip(self) -> None:
        board = self.board
        if board._edit_video_path is None or not board._edit_video_clips:
            return
        board._log_export_event("Export clip requested.")
        idx = board._edit_selected_clip if board._edit_selected_clip >= 0 else self.find_clip_at_playhead()
        if idx is None:
            board._log_export_event("Export aborted: no clip selected.")
            return
        start, end = board._edit_video_clips[idx]
        board._log_export_event(f"Selected clip {idx}: frames {start}-{end}.")
        if board._segment_thread is not None:
            board._log_export_event("Export aborted: segment thread already running.")
            board._notify("Export already running.")
            return
        if not board._project_root:
            board._log_export_event("Export aborted: no project root.")
            board._notify("Select a project first.")
            return
        assets_dir = board._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        out_dir = assets_dir / f"{board._edit_video_path.stem}_seg_{start}_{end}"
        out_dir.mkdir(parents=True, exist_ok=True)
        board._log_export_event(f"Output directory ready: {out_dir}")

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
        board._log_export_event("Progress dialog shown.")
        board._segment_dialog = dialog
        self.w.board_page.edit_timeline_split_btn.setEnabled(False)
        self.w.board_page.edit_timeline_export_btn.setEnabled(False)

        worker = VideoSegmentWorker(board._edit_video_path, out_dir, start, end)
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        determinate_progress = False

        def _on_status(text: str) -> None:
            board._log_export_event(f"Worker status: {text}")
            if board._segment_dialog is None:
                return
            board._segment_dialog.setLabelText(
                f"{text}\nFrames {start}-{end}\nOutput: {out_dir.name}"
            )

        def _on_progress(current: int, total: int) -> None:
            nonlocal determinate_progress
            if board._segment_dialog is None:
                return
            if not determinate_progress:
                board._segment_dialog.setRange(0, 100)
                determinate_progress = True
                board._log_export_event(f"Progress became determinate: total={total}")
            percent = int((current / max(1, total)) * 100)
            board._segment_dialog.setValue(min(100, max(0, percent)))
            board._segment_dialog.setLabelText(
                f"Exporting frames... {current}/{total}\nFrames {start}-{end}\nOutput: {out_dir.name}"
            )

        def _on_finished(success: bool, out_path: object, error: object) -> None:
            board._log_export_event(f"Worker finished: success={success} out={out_path} error={error}")
            if board._segment_dialog is not None:
                board._segment_dialog.reset()
                board._segment_dialog = None
            board._segment_thread = None
            board._segment_worker = None
            self.w.board_page.edit_timeline_split_btn.setEnabled(True)
            self.w.board_page.edit_timeline_export_btn.setEnabled(True)
            if not success:
                board._notify(str(error or "Export failed."))
                return
            if isinstance(out_path, Path):
                if board._focus_item is not None:
                    board.exit_focus_mode()
                item = board.add_sequence_from_dir(out_path)
                if item is not None:
                    item.setSelected(True)
                    board._reveal_scene_items([item])
                    board.save_board()
                    board._notify("Segment exported as sequence.")
            else:
                board._notify("Export completed.")

        def _on_cancel() -> None:
            board._log_export_event("Cancel requested.")
            if board._segment_dialog is not None:
                board._segment_dialog.setLabelText("Cancelling export...")
            if board._segment_worker is not None:
                board._segment_worker.cancel()

        dialog.canceled.connect(_on_cancel)
        worker.status.connect(_on_status)
        worker.progress.connect(_on_progress)
        worker.finished.connect(_on_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        board._segment_thread = thread
        board._segment_worker = worker

        def _start_export_thread() -> None:
            board._log_export_event("Starting export thread.")
            if board._segment_thread is thread:
                thread.start()

        QtCore.QTimer.singleShot(0, _start_export_thread)

    def on_sequence_timeline_playhead(self, frame: int) -> None:
        board = self.board
        if not board._edit_seq_frames:
            return
        idx = clamp_playhead(int(frame), len(board._edit_seq_frames))
        board._edit_video_playhead = idx
        self.set_frame_label(idx)
        self.apply_sequence_focus_frame(idx)

    def toggle_sequence_play(self) -> None:
        board = self.board
        if not board._edit_seq_frames:
            return
        board._sequence_playback.set_fps(board._edit_seq_fps)
        board._sequence_playback.toggle()

    def on_sequence_play_state_changed(self, playing: bool) -> None:
        if self.board._edit_focus_kind == "sequence":
            self.w.board_page.edit_timeline_play_btn.setText(play_button_label(playing))

    def on_video_play_state_changed(self, playing: bool) -> None:
        if self.board._edit_focus_kind == "video":
            self.w.board_page.edit_timeline_play_btn.setText(play_button_label(playing))

    def toggle_play(self) -> None:
        board = self.board
        if board._edit_focus_kind == "sequence":
            self.toggle_sequence_play()
            return
        if board._edit_focus_kind == "video":
            if board._edit_video_total <= 0:
                return
            board._video_playback.set_fps(board._edit_video_fps)
            board._video_playback.toggle()

    def advance_video_frame(self) -> None:
        board = self.board
        if board._edit_video_total <= 0:
            return
        nxt = loop_next_playhead(board._edit_video_playhead, board._edit_video_total)
        self.w.board_page.edit_timeline.set_playhead(nxt)
        self.on_timeline_playhead(nxt)

    def advance_sequence_frame(self) -> None:
        board = self.board
        if not board._edit_seq_frames:
            return
        nxt = loop_next_playhead(board._edit_video_playhead, len(board._edit_seq_frames))
        self.w.board_page.edit_timeline.set_playhead(nxt)
        self.on_sequence_timeline_playhead(nxt)
