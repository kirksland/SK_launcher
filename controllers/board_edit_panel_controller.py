from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from core.board_edit.media_runtime import play_button_label
from core.board_scene.items import BoardImageItem, BoardVideoItem
from video.player import VideoController


class BoardEditPanelController:
    """Owns opening media into focus mode and populating the edit panel."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.w = board_controller.w

    def open_media_item(self, item: QtWidgets.QGraphicsItem) -> None:
        board = self.board
        kind = item.data(0)
        if kind == "video":
            if not board._project_root:
                board._notify("Select a project first.")
                return
            filename = str(item.data(1))
            path = board._project_root / ".skyforge_board_assets" / filename
            if not path.exists():
                board._notify("Video file not found.")
                return
            board.enter_focus_mode(item)
            self.show_panel_for_video(path)
        elif kind == "sequence":
            dir_text = str(item.data(1))
            dir_path = board._resolve_project_path(dir_text)
            if not dir_path.exists():
                board._notify("Sequence directory not found.")
                return
            board.enter_focus_mode(item)
            self.show_panel_for_sequence(dir_path)

    def open_image_item(self, item: QtWidgets.QGraphicsItem) -> None:
        board = self.board
        if item.data(0) != "image":
            return
        if not board._project_root:
            board._notify("Select a project first.")
            return
        filename = str(item.data(1))
        path = board._project_root / ".skyforge_board_assets" / filename
        if not path.exists():
            board._notify("Image file not found.")
            return
        board.enter_focus_mode(item)
        self.show_panel_for_image(path)

    def open_video_dialog(self, path: Path) -> None:
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

    def show_panel_for_video(self, path: Path) -> None:
        board = self.board
        edit = board.edit_context
        board._edit_image_path = None
        board._reset_edit_session_for_kind("video")
        board._sync_edit_tool_defs_for_kind("video")
        edit.stack = board._default_edit_tool_stack()
        edit.selected_index = 0
        if isinstance(board._focus_item, BoardVideoItem):
            filename = str(board._focus_item.data(1) or "").strip()
            override = board._image_exr_display_overrides.get(filename)
            edit.stack = board._tool_stack_from_override(override)
        self.w.board_page.set_image_adjust_controls_visible(True)
        board._sync_tool_stack_ui()
        board._apply_scene_tool_to_focus_item()
        self.w.board_page.edit_timeline_play_btn.setText(play_button_label(False))
        board._video_playback.stop()
        info = [
            "Type: Video",
            f"Name: {path.name}",
            f"Path: {path}",
        ]
        self.w.board_page.set_edit_panel_content(
            "Edit Mode: Video",
            info,
            list_items=None,
            footer="Edit/export options will appear here.",
        )
        self.ensure_video_controller()
        if board._edit_video_controller is not None:
            self.w.board_page.show_edit_preview_video()
            board._edit_video_controller.preview_first_frame(path)
            board._edit_video_controller.load_path(path)
        self.w.board_page.edit_timeline_play_btn.setText(play_button_label(False))
        board._focus_video_path = path
        board._ensure_focus_video_cap()
        board._init_edit_video_timeline(path)
        self.w.board_page.set_timeline_bar_visible(True)
        self.w.board_page.set_edit_preview_visible(False)
        edit.focus_kind = "video"

    def show_panel_for_sequence(self, dir_path: Path) -> None:
        board = self.board
        edit = board.edit_context
        board._edit_image_path = None
        self.w.board_page.set_image_adjust_controls_visible(False)
        self.w.board_page.edit_timeline_play_btn.setText(play_button_label(False))
        frames = board._sequence_frame_paths(dir_path)
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
        board._edit_seq_frames = frames
        board._edit_seq_dir = dir_path
        board._sequence_playback.stop()
        board._sequence_playback.set_fps(board._edit_seq_fps)
        self.w.board_page.edit_timeline_play_btn.setText(play_button_label(False))
        board._edit_video_playhead = 0
        if frames:
            self.w.board_page.edit_sequence_timeline.set_data(len(frames), [(0, len(frames) - 1)], 0)
            self.w.board_page.edit_sequence_frame_label.setText("Frame: 0")
        else:
            self.w.board_page.edit_sequence_timeline.set_data(0, [], 0)
            self.w.board_page.edit_sequence_frame_label.setText("Frame: 0")
        self.w.board_page.edit_timeline.set_data(len(frames), [(0, max(0, len(frames) - 1))], 0)
        self.w.board_page.set_timeline_bar_visible(True)
        edit.focus_kind = "sequence"
        self.w.board_page.set_edit_preview_visible(False)
        board._on_edit_sequence_timeline_playhead(0)

    def show_panel_for_image(self, path: Path) -> None:
        board = self.board
        edit = board.edit_context
        size = board._get_image_size(path)
        info = [
            f"{path.name}",
            f"{size.width()} x {size.height()}",
        ]
        board._edit_image_path = path
        board._reset_edit_session_for_kind("image")
        board._sync_edit_tool_defs_for_kind("image")
        edit.stack = board._default_edit_tool_stack()
        edit.selected_index = 0
        board._sync_edit_values_from_tool_stack()
        if isinstance(board._focus_item, BoardImageItem):
            filename = str(board._focus_item.data(1) or "").strip()
            override = board._image_exr_display_overrides.get(filename)
            edit.stack = board._tool_stack_from_override(override)
            board._sync_edit_values_from_tool_stack()
        self.w.board_page.set_image_adjust_controls_visible(True)
        board._sync_tool_stack_ui()
        board._apply_scene_tool_to_focus_item()
        preview = board._get_display_pixmap(path, max_dim=1024)
        self.w.board_page.show_edit_preview_image(preview)
        if path.suffix.lower() == ".exr":
            board._edit_exr_path = path
            board._edit_exr_channels = []
            board._edit_exr_channel = None
            if isinstance(board._focus_item, BoardImageItem):
                filename = str(board._focus_item.data(1) or "").strip()
                override = board._image_exr_display_overrides.get(filename)
                if isinstance(override, dict):
                    channel = str(override.get("channel", "")).strip()
                    if channel:
                        board._edit_exr_channel = channel
                    try:
                        board._edit_exr_gamma = max(0.1, float(override.get("gamma", board._edit_exr_gamma)))
                    except Exception:
                        pass
                    board._edit_exr_srgb = bool(override.get("srgb", board._edit_exr_srgb))
            self.w.board_page.set_exr_channel_row_visible(True)
            self.w.board_page.set_exr_gamma_label(board._edit_exr_gamma)
            self.w.board_page.edit_exr_srgb_check.setChecked(board._edit_exr_srgb)
            self.w.board_page.edit_exr_gamma_slider.setValue(int(board._edit_exr_gamma * 10))
            self.w.board_page.set_edit_panel_content(
                "Edit Mode: Image",
                info,
                list_items=["Loading channels..."],
                footer="",
            )
            board._load_exr_channels_into_panel(path)
        else:
            board._edit_exr_path = None
            board._edit_exr_channels = []
            board._edit_exr_channel = None
            self.w.board_page.set_exr_channel_row_visible(False)
            self.w.board_page.set_edit_panel_content(
                "Edit Mode: Image",
                info,
                list_items=None,
                footer="",
            )
        self.w.board_page.set_timeline_bar_visible(False)
        self.w.board_page.set_edit_preview_visible(False)
        edit.focus_kind = "image"

    def ensure_video_controller(self) -> None:
        board = self.board
        if board._edit_video_controller is not None:
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
        board._edit_video_controller = controller
        host_layout = self.w.board_page.edit_video_host_layout
        host_layout.addWidget(controller.widget)
        controller.bind_controls(None, None)
