from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore

from core.board_edit.workers import ExrChannelPreviewWorker, ExrInfoWorker, ImageAdjustPreviewWorker
from core.board_preview import PreviewRequest
from core.board_scene.items import BoardImageItem
from core.board_state import (
    apply_exr_preview_result,
    apply_image_adjust_preview_result,
    apply_preview_payload_to_item,
    preview_payload_to_pixmap,
)


class BoardEditPreviewController:
    """Owns edit preview scheduling and preview worker lifecycles."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.w = board_controller.w

    def on_slider_pressed(self) -> None:
        self.board._edit_preview_dragging = True

    def on_slider_released(self) -> None:
        self.board._edit_preview_dragging = False
        self.schedule_update()

    def schedule_update(self, channel: Optional[str] = None) -> None:
        board = self.board
        if channel:
            board._edit_preview_pending_channel = str(channel)
        if board._edit_preview_timer is None:
            board._edit_preview_timer = QtCore.QTimer(self.w)
            board._edit_preview_timer.setSingleShot(True)
            board._edit_preview_timer.timeout.connect(self.flush_update)
        board._edit_preview_timer.start(60)

    def flush_update(self) -> None:
        board = self.board
        board._edit_preview_timer = None
        max_dim = board._edit_preview_fast_dim if board._edit_preview_dragging else board._edit_preview_full_dim
        if board._edit_exr_path is not None:
            channel = str(
                board._edit_preview_pending_channel
                or board._edit_exr_channel
                or self.w.board_page.current_exr_channel_value()
                or ""
            ).strip()
            board._edit_preview_pending_channel = None
            if channel:
                self.queue_exr_channel_preview(channel, max_dim=max_dim)
            return
        board._edit_preview_pending_channel = None
        if board._edit_image_path is not None:
            self.queue_image_adjust_preview(board._edit_image_path, max_dim=max_dim)

    def handle_exr_info_finished(
        self, success: bool, channels_obj: object, size_obj: object, note_obj: object
    ) -> None:
        board = self.board
        if board._edit_exr_path is None:
            return
        path = board._edit_exr_path
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
            board._edit_exr_channels = [str(c) for c in channels]
            options, default_value = self.build_exr_channel_options(board._edit_exr_channels)
            self.w.board_page.set_exr_channels(options)
            self.w.board_page.set_edit_panel_content(
                "Edit Mode: Image",
                info_lines,
                list_items=[str(c) for c in channels],
                footer=footer,
            )
            if default_value is None and board._edit_exr_channels:
                default_value = board._edit_exr_channels[0]
            preferred_channel = str(board._edit_exr_channel or "").strip()
            if preferred_channel:
                available_values = [value for _label, value in options]
                if preferred_channel in available_values:
                    default_value = preferred_channel
                elif preferred_channel in board._edit_exr_channels:
                    default_value = preferred_channel
            if default_value:
                board._edit_exr_channel = str(default_value)
                combo = self.w.board_page.edit_exr_channel_combo
                idx = combo.findData(default_value)
                if idx < 0:
                    idx = combo.findText(default_value)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                self.queue_exr_channel_preview(default_value)
        elif success:
            self.w.board_page.set_edit_panel_content(
                "Edit Mode: Image",
                info_lines,
                list_items=["No channels found."],
                footer=footer,
            )
        else:
            board._edit_exr_channels = []
            self.w.board_page.set_exr_channels([])
            self.w.board_page.set_edit_panel_content(
                "Edit Mode: Image",
                info_lines,
                list_items=["Failed to read EXR."],
                footer=str(note_obj or "Failed to read EXR."),
            )

    def handle_exr_preview_finished(
        self, success: bool, channel: str, payload: object, error: object
    ) -> None:
        board = self.board
        if success:
            if isinstance(board._focus_item, BoardImageItem):
                filename = str(board._focus_item.data(1) or "").strip()
                if apply_exr_preview_result(
                    board._image_exr_display_overrides,
                    board._focus_item,
                    filename,
                    payload=payload,
                    channel=str(board._edit_exr_channel or channel or ""),
                    gamma=board._edit_exr_gamma,
                    srgb=board._edit_exr_srgb,
                    tool_stack=board.current_edit_tool_stack(),
                ):
                    board._sync_board_state_overrides()
                    board._dirty = True
                    return
            else:
                pixmap = preview_payload_to_pixmap(payload)
                if pixmap is not None:
                    self.w.board_page.show_edit_preview_image(pixmap, label=f"Channel: {channel}")
                    return
        msg = str(error or "Failed to render channel.")
        self.w.board_page.edit_footer.setText(msg)

    def handle_exr_preview_finished_if_current(
        self,
        request_key: str,
        success: bool,
        channel: str,
        payload: object,
        error: object,
    ) -> None:
        if request_key != getattr(self.board, "_edit_exr_preview_request_key", None):
            return
        self.handle_exr_preview_finished(success, channel, payload, error)

    def handle_image_adjust_preview_finished(self, success: bool, payload: object, error: object) -> None:
        board = self.board
        if success:
            visual = board.edit_visual_state()
            if isinstance(board._focus_item, BoardImageItem):
                current_stack = board.current_edit_tool_stack()
                if apply_image_adjust_preview_result(
                    board._image_exr_display_overrides,
                    board._focus_item,
                    str(board._focus_item.data(1) or "").strip(),
                    payload=payload,
                    effective=board.edit_tool_stack_is_effective(
                        current_stack,
                        visual.brightness,
                        visual.contrast,
                        visual.saturation,
                    ),
                    current=board._image_exr_display_overrides.get(str(board._focus_item.data(1) or "").strip()),
                    tool_stack=current_stack,
                ):
                    board._sync_board_state_overrides()
                    board._dirty = True
                    return
            else:
                pixmap = preview_payload_to_pixmap(payload)
                if pixmap is not None:
                    self.w.board_page.show_edit_preview_image(pixmap, label="Image adjustments")
                    return
        msg = str(error or "Failed to render image adjustments.")
        self.w.board_page.edit_footer.setText(msg)

    def handle_image_adjust_preview_finished_if_current(
        self,
        request_key: str,
        success: bool,
        payload: object,
        error: object,
    ) -> None:
        if request_key != getattr(self.board, "_edit_image_preview_request_key", None):
            return
        self.handle_image_adjust_preview_finished(success, payload, error)

    def load_exr_channels_into_panel(self, path: Path) -> None:
        worker = ExrInfoWorker(path)
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        self.w.board_page._edit_exr_thread = thread  # type: ignore[attr-defined]
        self.w.board_page._edit_exr_worker = worker  # type: ignore[attr-defined]
        worker.finished.connect(self.board._ui_bridge.on_exr_info_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @staticmethod
    def build_exr_channel_options(channels: list[str]) -> tuple[list[tuple[str, str]], Optional[str]]:
        clean = [str(c) for c in channels]
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

        root = groups.get("", set())
        if {"R", "G", "B"}.issubset(root):
            add_option("Beauty (RGB)", "RGB")
            if "A" in root:
                add_option("Beauty (RGBA)", "RGBA")

        for prefix, chans in sorted(groups.items()):
            if prefix == "":
                continue
            if {"R", "G", "B"}.issubset(chans):
                add_option(f"{prefix} (RGB)", f"{prefix}.RGB")
                if "A" in chans:
                    add_option(f"{prefix} (RGBA)", f"{prefix}.RGBA")

        for ch in clean:
            add_option(ch, ch)

        for _label, value in options:
            if value in ("RGB", "RGBA"):
                default_value = value
                break
        return options, default_value

    def queue_exr_channel_preview(self, channel: str, max_dim: int = 0) -> None:
        board = self.board
        if board._edit_exr_path is None:
            return
        if board._edit_exr_preview_busy:
            board._edit_exr_preview_pending_channel = str(channel)
            board._edit_exr_preview_pending_max_dim = int(max_dim)
            return
        tool_stack = board.current_edit_tool_stack()
        request = PreviewRequest.from_path(
            kind="exr_channel",
            media_kind="image",
            source_path=board._edit_exr_path,
            settings={
                "channel": channel,
                "gamma": board._edit_exr_gamma,
                "srgb": board._edit_exr_srgb,
                "max_dim": int(max_dim),
                "tool_stack": tool_stack,
            },
        )
        worker = ExrChannelPreviewWorker(
            board._edit_exr_path,
            channel,
            board._edit_exr_gamma,
            board._edit_exr_srgb,
            int(max_dim),
            tool_stack,
        )
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        board._edit_exr_preview_busy = True
        board._edit_exr_preview_request_key = request.key
        board._edit_exr_thread = thread
        board._edit_exr_worker = worker
        worker.finished.connect(
            lambda success, finished_channel, payload, error, request_key=request.key: (
                self.handle_exr_preview_finished_if_current(
                    request_key,
                    success,
                    finished_channel,
                    payload,
                    error,
                )
            )
        )
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.on_exr_preview_cycle_finished)
        thread.start()

    def on_exr_preview_cycle_finished(self) -> None:
        board = self.board
        board._edit_exr_preview_busy = False
        board._edit_exr_thread = None
        board._edit_exr_worker = None
        board._edit_exr_preview_request_key = None
        pending_channel = board._edit_exr_preview_pending_channel
        pending_dim = board._edit_exr_preview_pending_max_dim
        board._edit_exr_preview_pending_channel = None
        board._edit_exr_preview_pending_max_dim = 0
        if board._edit_exr_path is not None and pending_channel:
            self.queue_exr_channel_preview(pending_channel, max_dim=pending_dim)

    def queue_exr_display_for_item(
        self,
        item: BoardImageItem,
        channel: str,
        gamma: float,
        srgb: bool,
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
            1024,
            tool_stack,
        )
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        self._track_item_preview_worker(thread, worker)

        def _on_finished(success: bool, _channel: str, payload: object, _error: object) -> None:
            if success:
                apply_preview_payload_to_item(item, payload)

        worker.finished.connect(_on_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._untrack_item_preview_worker(thread, worker))
        thread.start()

    def queue_image_adjust_preview(self, path: Path, max_dim: int = 0) -> None:
        board = self.board
        if board._edit_image_preview_busy:
            board._edit_image_preview_pending_path = path
            board._edit_image_preview_pending_max_dim = int(max_dim)
            return
        tool_stack = board.current_edit_tool_stack()
        request = PreviewRequest.from_path(
            kind="image_adjust",
            media_kind="image",
            source_path=path,
            settings={"max_dim": int(max_dim), "tool_stack": tool_stack},
        )
        worker = ImageAdjustPreviewWorker(
            path,
            int(max_dim),
            tool_stack,
        )
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        board._edit_image_preview_busy = True
        board._edit_image_preview_request_key = request.key
        board._edit_image_thread = thread
        board._edit_image_worker = worker
        worker.finished.connect(
            lambda success, payload, error, request_key=request.key: (
                self.handle_image_adjust_preview_finished_if_current(
                    request_key,
                    success,
                    payload,
                    error,
                )
            )
        )
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.on_image_preview_cycle_finished)
        thread.start()

    def on_image_preview_cycle_finished(self) -> None:
        board = self.board
        board._edit_image_preview_busy = False
        board._edit_image_thread = None
        board._edit_image_worker = None
        board._edit_image_preview_request_key = None
        pending_path = board._edit_image_preview_pending_path
        pending_dim = board._edit_image_preview_pending_max_dim
        board._edit_image_preview_pending_path = None
        board._edit_image_preview_pending_max_dim = 0
        if pending_path is not None and board._edit_image_path is not None:
            self.queue_image_adjust_preview(pending_path, max_dim=pending_dim)

    def queue_image_adjust_for_item(
        self,
        item: BoardImageItem,
        tool_stack: object = None,
    ) -> None:
        if item.scene() is None:
            return
        path = item.file_path()
        if path.suffix.lower() == ".exr":
            return
        worker = ImageAdjustPreviewWorker(
            path,
            1024,
            tool_stack,
        )
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)
        self._track_item_preview_worker(thread, worker)

        def _on_finished(success: bool, payload: object, _error: object) -> None:
            if success:
                apply_preview_payload_to_item(item, payload)

        worker.finished.connect(_on_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._untrack_item_preview_worker(thread, worker))
        thread.start()

    def _track_item_preview_worker(self, thread: QtCore.QThread, worker: object) -> None:
        self.board._exr_item_preview_threads.append(thread)
        self.board._exr_item_preview_workers.append(worker)

    def _untrack_item_preview_worker(self, thread: QtCore.QThread, worker: object) -> None:
        try:
            self.board._exr_item_preview_threads.remove(thread)
        except ValueError:
            pass
        try:
            self.board._exr_item_preview_workers.remove(worker)
        except ValueError:
            pass
