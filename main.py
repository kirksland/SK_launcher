from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets
import ctypes

# Enable OpenEXR codec in OpenCV when available (portable across project moves).
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

from core.settings import (
    DEFAULT_ASSET_SCHEMA,
    DEFAULT_PROJECTS_DIR,
    DEFAULT_TEMPLATE_HIP,
    DEFAULT_SETTINGS,
    load_settings,
    normalize_houdini_exe,
    normalize_asset_schema,
    normalize_asset_manager_projects,
    save_settings,
)
from core.houdini_env import build_houdini_env
from controllers.asset_manager_controller import AssetManagerController
from controllers.projects_controller import ProjectsController
from controllers.client_controller import ClientController
from controllers.board_controller import BoardController
from ui.widgets.project_card import ProjectCard
from ui.utils.styles import PALETTE, app_stylesheet, tool_button_dark_style

APP_TITLE = "Skyforge Launcher"
TEST_PIPELINE_ROOT = Path(__file__).resolve().parent / "projects" / "test_pipeline"

class LauncherWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        icon_dir = Path(__file__).resolve().parent / "config"
        icon_path = icon_dir / "newForge4_256.ico"
        if not icon_path.exists():
            icon_path = icon_dir / "newForge4.ico"
        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))
        self.resize(1280, 620)

        self.settings = load_settings()
        self.projects_dir = Path(self.settings["projects_dir"])
        self.server_repo_dir = Path(self.settings["server_repo_dir"])
        self._template_hip = Path(self.settings["template_hip"])
        self._new_hip_pattern = self.settings["new_hip_pattern"]
        self._use_file_association = bool(self.settings["use_file_association"])
        self._houdini_exe = self.settings["houdini_exe"]
        self._video_backend_pref = str(self.settings.get("video_backend", "auto")).strip().lower() or "auto"
        self._asset_manager_projects = normalize_asset_manager_projects(
            self.settings.get("asset_manager_projects", [])
        )
        self._asset_schema = normalize_asset_schema(
            self.settings.get("asset_schema", DEFAULT_ASSET_SCHEMA)
        )
        self.test_pipeline_root = TEST_PIPELINE_ROOT
        self._project_cache: Dict[Path, Tuple[float, List[Path], float]] = {}
        self._asset_cache: Dict[Path, Tuple[float, List[Path], float]] = {}
        self._card_to_item: Dict[ProjectCard, QtWidgets.QListWidgetItem] = {}
        self._project_hip_selection: Dict[Path, Path] = {}
        self._project_watch_enabled = True
        self._asset_watch_enabled = True

        central = QtWidgets.QWidget()
        central.setStyleSheet(app_stylesheet())
        self.setCentralWidget(central)
        outer = QtWidgets.QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        main_panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(main_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        outer.addWidget(main_panel, 1)

        self.pages = QtWidgets.QStackedWidget()
        layout.addWidget(self.pages, 1)

        from ui.pages.client_page import ClientPage
        from ui.pages.projects_page import ProjectsPage
        from ui.pages.server_page import AssetManagerPage
        from ui.pages.settings_page import SettingsPage
        from ui.pages.board_page import BoardPage
        from ui.pages.dev_page import DevPage

        self.projects_page = ProjectsPage(self.projects_dir)
        self.pages.addWidget(self.projects_page)

        self.asset_page = AssetManagerPage(self._video_backend_pref, parent=self)
        self.pages.addWidget(self.asset_page)

        self.board_page = BoardPage(parent=self)
        self.pages.addWidget(self.board_page)

        self.client_page = ClientPage(parent=self)
        self.pages.addWidget(self.client_page)

        self.settings_page = SettingsPage(
            self.projects_dir,
            self.server_repo_dir,
            self._template_hip,
            self._new_hip_pattern,
            self._video_backend_pref,
            self._use_file_association,
            self._houdini_exe,
        )
        self.pages.addWidget(self.settings_page)

        self.dev_page = DevPage(parent=self)
        self.pages.addWidget(self.dev_page)

        # Global media controls (bottom-right)
        self.media_group = QtWidgets.QFrame()
        self.media_group.setStyleSheet(
            "QFrame {"
            "background: #23272e;"
            "border: 1px solid #14171c;"
            "border-radius: 10px;"
            "}"
        )
        group_layout = QtWidgets.QHBoxLayout(self.media_group)
        group_layout.setContentsMargins(10, 6, 10, 6)
        group_layout.setSpacing(6)

        self.media_label = QtWidgets.QLabel("Media")
        self.media_label.setStyleSheet(f"color: {PALETTE['muted']};")
        self.media_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        music_icon = QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaVolume)
        self.media_label.setPixmap(music_icon.pixmap(16, 16))
        self.media_label.setToolTip("Global media controls")
        group_layout.addWidget(self.media_label)

        self.media_prev_btn = QtWidgets.QToolButton()
        self.media_prev_btn.setIcon(QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.media_prev_btn.setAutoRaise(True)
        self.media_prev_btn.setToolTip("Previous")
        self.media_prev_btn.setStyleSheet(tool_button_dark_style(padding="4px 8px"))
        group_layout.addWidget(self.media_prev_btn)

        self.media_play_btn = QtWidgets.QToolButton()
        self.media_play_btn.setIcon(QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay))
        self.media_play_btn.setAutoRaise(True)
        self.media_play_btn.setToolTip("Play / Pause")
        self.media_play_btn.setStyleSheet(tool_button_dark_style(padding="4px 8px"))
        group_layout.addWidget(self.media_play_btn)

        self.media_next_btn = QtWidgets.QToolButton()
        self.media_next_btn.setIcon(QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaSkipForward))
        self.media_next_btn.setAutoRaise(True)
        self.media_next_btn.setToolTip("Next")
        self.media_next_btn.setStyleSheet(tool_button_dark_style(padding="4px 8px"))
        group_layout.addWidget(self.media_next_btn)

        nav_labels = ["Projects", "Asset Manager", "Board", "Clients", "Settings", "Dev"]
        nav_buttons: List[QtWidgets.QToolButton] = []
        nav_font = QtGui.QFont()
        nav_font.setPointSize(14)

        bottom_bar = QtWidgets.QFrame()
        bottom_bar.setFixedHeight(48)
        bottom_bar.setStyleSheet(
            "QFrame {"
            "background: #1f2329;"
            "border-top: 1px solid #0f1216;"
            "}"
        )
        bottom_layout = QtWidgets.QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(10, 4, 10, 4)
        bottom_layout.setSpacing(10)
        layout.addWidget(bottom_bar, 0)

        nav_container = QtWidgets.QFrame()
        nav_row = QtWidgets.QHBoxLayout(nav_container)
        nav_row.setContentsMargins(0, 0, 0, 0)
        nav_row.setSpacing(6)

        for label in nav_labels:
            btn = QtWidgets.QToolButton()
            btn.setText(label)
            btn.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setAutoRaise(True)
            btn.setFont(nav_font)
            btn.setStyleSheet(
                "QToolButton { color: #c6ccd6; padding: 6px 10px; }"
                "QToolButton:hover { background: rgba(255,255,255,30); }"
            )
            btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
            nav_row.addWidget(btn)
            nav_buttons.append(btn)

        bottom_layout.addStretch(1)
        bottom_layout.addWidget(nav_container, 0)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self.media_group, 0)

        # Wire nav
        if nav_buttons:
            nav_buttons[0].clicked.connect(lambda: self.pages.setCurrentIndex(0))
        if len(nav_buttons) > 1:
            nav_buttons[1].clicked.connect(lambda: self.pages.setCurrentIndex(1))
        if len(nav_buttons) > 2:
            nav_buttons[2].clicked.connect(lambda: self.pages.setCurrentIndex(2))
        if len(nav_buttons) > 3:
            nav_buttons[3].clicked.connect(lambda: self.pages.setCurrentIndex(3))
        if len(nav_buttons) > 4:
            nav_buttons[4].clicked.connect(lambda: self.pages.setCurrentIndex(4))
        if len(nav_buttons) > 5:
            nav_buttons[5].clicked.connect(lambda: self.pages.setCurrentIndex(5))

        self._nav_clients_btn = nav_buttons[3] if len(nav_buttons) > 3 else None
        self._nav_clients_label = "Clients"
        self._nav_clients_badge: Optional[QtWidgets.QFrame] = None
        if self._nav_clients_btn is not None:
            badge = QtWidgets.QFrame(self._nav_clients_btn)
            badge.setFixedSize(8, 8)
            badge.setStyleSheet("background: #e03b3b; border-radius: 4px;")
            badge.setVisible(False)
            self._nav_clients_badge = badge
            self._nav_clients_btn.installEventFilter(self)
            self._position_clients_badge()

        self.path_label = self.projects_page.path_label
        self.browse_btn = self.projects_page.browse_btn
        self.refresh_btn = self.projects_page.refresh_btn
        self.new_btn = self.projects_page.new_btn
        self.search_input = self.projects_page.search_input
        self.sort_combo = self.projects_page.sort_combo
        self.project_grid = self.projects_page.project_grid
        self.open_btn = self.projects_page.open_btn
        self.add_asset_btn = self.projects_page.add_asset_btn
        self.remove_asset_btn = self.projects_page.remove_asset_btn
        self.status = self.projects_page.status
        self.project_detail_panel = self.projects_page.detail_panel
        self.project_detail_tree = self.projects_page.detail_tree
        self.project_detail_title = self.projects_page.detail_title
        self.project_detail_open_btn = self.projects_page.detail_open_btn
        self.project_detail_close_btn = self.projects_page.detail_close_btn

        self.asset_pages = self.asset_page.asset_pages
        self.asset_search_input = self.asset_page.asset_search_input
        self.asset_refresh_btn = self.asset_page.asset_refresh_btn
        self.asset_auto_refresh = self.asset_page.asset_auto_refresh
        self.asset_path_label = self.asset_page.asset_path_label
        self.asset_grid = self.asset_page.asset_grid
        self.asset_back_btn = self.asset_page.asset_back_btn
        self.asset_details_title = self.asset_page.asset_details_title
        self.asset_shots_filter = self.asset_page.asset_shots_filter
        self.asset_shots_size = self.asset_page.asset_shots_size
        self.asset_shots_list = self.asset_page.asset_shots_list
        self.asset_assets_filter = self.asset_page.asset_assets_filter
        self.asset_assets_list = self.asset_page.asset_assets_list
        self.asset_entity_search = self.asset_page.asset_entity_search
        self.asset_open_folder_btn = self.asset_page.asset_open_folder_btn
        self.asset_work_tabs = self.asset_page.asset_work_tabs
        self.asset_preview = self.asset_page.asset_preview
        self.asset_prev_btn = self.asset_page.asset_prev_btn
        self.asset_next_btn = self.asset_page.asset_next_btn
        self.asset_preview_label = self.asset_page.asset_preview_label
        self.asset_meta = self.asset_page.asset_meta
        self.asset_status = self.asset_page.asset_status
        self.asset_video = self.asset_page.asset_video
        self.asset_play_btn = self.asset_page.asset_play_btn
        self.asset_fullscreen_btn = self.asset_page.asset_fullscreen_btn
        self.asset_video_slider = self.asset_page.asset_video_slider
        self.asset_context_combo = self.asset_page.asset_context_combo
        self.asset_versions_list = self.asset_page.asset_versions_list
        self.asset_versions_list.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.asset_history_list = self.asset_page.asset_history_list
        self.asset_commit_box = self.asset_page.asset_commit_box
        self.asset_commit_btn = self.asset_page.asset_commit_btn
        self.asset_push_btn = self.asset_page.asset_push_btn
        self.asset_fetch_btn = self.asset_page.asset_fetch_btn
        self.asset_video_controller = self.asset_page.asset_video_controller

        self.client_refresh_btn = self.client_page.refresh_btn
        self.client_list = self.client_page.client_list
        self.client_info = self.client_page.client_info
        self.client_bind_btn = self.client_page.bind_btn
        self.client_status = self.client_page.status
        self.client_sync_status = self.client_page.client_sync_status
        self.client_sync_local_path = self.client_page.client_sync_local_path
        self.client_sync_server_path = self.client_page.client_sync_server_path
        self.client_tree = self.client_page.client_tree
        self.client_sync_push_list = self.client_page.client_sync_push_list
        self.client_sync_pull_list = self.client_page.client_sync_pull_list
        self.client_sync_conflicts_list = self.client_page.client_sync_conflicts_list
        self.client_sync_preview_btn = self.client_page.client_sync_preview_btn
        self.client_sync_pull_btn = self.client_page.client_sync_pull_btn
        self.client_sync_push_btn = self.client_page.client_sync_push_btn
        self.client_sync_btn = self.client_page.client_sync_btn
        self.client_sync_open_btn = self.client_page.client_sync_open_btn
        self.client_sync_baseline_btn = self.client_page.client_sync_baseline_btn
        self.client_conflict_keep_local_btn = self.client_page.client_conflict_keep_local_btn
        self.client_conflict_keep_server_btn = self.client_page.client_conflict_keep_server_btn
        self.client_conflict_keep_both_btn = self.client_page.client_conflict_keep_both_btn

        self.asset_controller = AssetManagerController(self)
        self.project_controller = ProjectsController(self)
        self.client_controller = ClientController(self)
        self.board_controller = BoardController(self)
        self.asset_video_box = self.asset_page.asset_video_box
        self.asset_video_layout = self.asset_page.asset_video_layout

        self.board_project_label = self.board_page.project_label
        self.board_add_image_btn = self.board_page.add_image_btn
        self.board_add_video_btn = self.board_page.add_video_btn
        self.board_auto_layout_btn = self.board_page.auto_layout_btn
        self.board_fit_btn = self.board_page.fit_btn
        self.board_save_btn = self.board_page.save_btn
        self.board_load_btn = self.board_page.load_btn
        self.board_page.set_controller(self.board_controller)
        self.board_controller.set_project(None)

        self.settings_projects_dir = self.settings_page.settings_projects_dir
        self.settings_server_dir = self.settings_page.settings_server_dir
        self.settings_template_hip = self.settings_page.settings_template_hip
        self.settings_pattern = self.settings_page.settings_pattern
        self.settings_video_backend = self.settings_page.settings_video_backend
        self.settings_use_assoc = self.settings_page.settings_use_assoc
        self.settings_houdini_exe = self.settings_page.settings_houdini_exe
        self.settings_save_btn = self.settings_page.settings_save_btn

        self.dev_add_box_btn = self.dev_page.add_box_btn
        self.dev_status = self.dev_page.status
        self.dev_silent_check = self.dev_page.silent_check
        self.dev_picnc_input = self.dev_page.picnc_input
        self.dev_picnc_browse_btn = self.dev_page.picnc_browse_btn
        self.dev_picnc_out_combo = self.dev_page.picnc_out_combo
        self.dev_picnc_out_dir = self.dev_page.picnc_out_dir
        self.dev_picnc_out_browse_btn = self.dev_page.picnc_out_browse_btn
        self.dev_picnc_convert_btn = self.dev_page.picnc_convert_btn

        self._asset_shot_size_map = {
            "Small": QtCore.QSize(140, 84),
            "Medium": QtCore.QSize(180, 110),
            "Large": QtCore.QSize(240, 150),
        }
        self._asset_video_fullscreen_dialog: Optional[QtWidgets.QDialog] = None
        self._asset_video_original_layout: Optional[QtWidgets.QLayout] = None

        self.browse_btn.clicked.connect(self.project_controller.browse_projects_dir)
        self.refresh_btn.clicked.connect(self.project_controller.refresh_projects)
        self.new_btn.clicked.connect(self.project_controller.create_project)
        self.search_input.textChanged.connect(self.project_controller.refresh_projects)
        self.sort_combo.currentIndexChanged.connect(self.project_controller.refresh_projects)
        self.project_grid.itemDoubleClicked.connect(self.project_controller.open_selected_project)
        self.project_grid.currentItemChanged.connect(self.project_controller.on_project_selected)
        self.open_btn.clicked.connect(self.project_controller.open_selected_project)
        self.project_detail_open_btn.clicked.connect(self.project_controller.open_selected_project_folder)
        self.project_detail_close_btn.clicked.connect(self.project_controller.close_project_detail_panel)
        self.add_asset_btn.clicked.connect(self.add_selected_project_to_asset_manager)
        self.remove_asset_btn.clicked.connect(self.remove_selected_project_from_asset_manager)

        self.asset_search_input.textChanged.connect(self.asset_controller.refresh_asset_manager)
        self.asset_refresh_btn.clicked.connect(self.asset_controller.refresh_asset_manager)
        self.asset_auto_refresh.toggled.connect(self.asset_controller.toggle_asset_auto_refresh)
        self.asset_grid.itemClicked.connect(self.asset_controller.open_asset_details)
        self.asset_grid.customContextMenuRequested.connect(self.asset_controller.show_asset_manager_context_menu)
        self.asset_shots_filter.currentTextChanged.connect(self.asset_controller.refresh_shots_list)
        self.asset_shots_size.currentTextChanged.connect(self.asset_controller.on_asset_shots_size_changed)
        self.asset_assets_filter.currentTextChanged.connect(self.asset_controller.refresh_assets_list)
        self.asset_entity_search.textChanged.connect(self.asset_controller.refresh_active_list)
        self.asset_open_folder_btn.clicked.connect(self.asset_controller.open_asset_project_folder)
        self.asset_work_tabs.currentChanged.connect(self.asset_controller.on_asset_tab_changed)
        self.asset_shots_list.itemClicked.connect(self.asset_controller.on_asset_entity_clicked)
        self.asset_assets_list.itemClicked.connect(self.asset_controller.on_asset_entity_clicked)
        self.asset_assets_list.customContextMenuRequested.connect(self.asset_controller.show_asset_context_menu)
        self.asset_prev_btn.clicked.connect(self.asset_controller.prev_preview_image)
        self.asset_next_btn.clicked.connect(self.asset_controller.next_preview_image)
        self.asset_fullscreen_btn.clicked.connect(self.asset_controller.toggle_asset_video_fullscreen)
        self.asset_context_combo.currentTextChanged.connect(self.asset_controller.update_asset_context)
        self.asset_versions_list.itemClicked.connect(self.asset_controller.on_asset_version_clicked)
        self.asset_versions_list.customContextMenuRequested.connect(
            self.asset_controller.show_asset_version_context_menu
        )
        self.asset_commit_btn.clicked.connect(self.asset_controller.asset_placeholder_action)
        self.asset_push_btn.clicked.connect(self.asset_controller.asset_placeholder_action)
        self.asset_fetch_btn.clicked.connect(self.asset_controller.asset_placeholder_action)

        self.client_refresh_btn.clicked.connect(self.client_controller.refresh_client_catalog)
        self.client_bind_btn.clicked.connect(self.client_controller.clone_client_project)
        self.client_list.itemClicked.connect(self.client_controller.on_client_project_selected)
        self.client_sync_preview_btn.clicked.connect(self.client_controller.preview_client_project)
        self.client_sync_pull_btn.clicked.connect(self.client_controller.pull_client_project)
        self.client_sync_push_btn.clicked.connect(self.client_controller.push_client_project)
        self.client_sync_btn.clicked.connect(self.client_controller.sync_client_project)
        self.client_sync_open_btn.clicked.connect(self.client_controller.open_local_project_folder)
        self.client_sync_baseline_btn.clicked.connect(self.client_controller.save_sync_baseline)
        self.client_conflict_keep_local_btn.clicked.connect(
            lambda: self.client_controller.resolve_conflicts("local")
        )
        self.client_conflict_keep_server_btn.clicked.connect(
            lambda: self.client_controller.resolve_conflicts("server")
        )
        self.client_conflict_keep_both_btn.clicked.connect(
            lambda: self.client_controller.resolve_conflicts("both")
        )

        self.board_add_image_btn.clicked.connect(self.board_controller.add_image)
        self.board_add_video_btn.clicked.connect(self.board_controller.add_video)
        self.board_auto_layout_btn.clicked.connect(self.board_controller.layout_selection_grid)
        self.board_fit_btn.clicked.connect(self.board_controller.fit_view)
        self.board_save_btn.clicked.connect(self.board_controller.save_board)
        self.board_load_btn.clicked.connect(self.board_controller.load_board)
        self.pages.currentChanged.connect(self._on_main_page_changed)

        self.settings_save_btn.clicked.connect(self.save_settings_from_ui)
        self.dev_add_box_btn.clicked.connect(self._dev_add_box_in_houdini)
        self.dev_picnc_browse_btn.clicked.connect(self._dev_browse_picnc)
        self.dev_picnc_out_browse_btn.clicked.connect(self._dev_browse_picnc_output)
        self.dev_picnc_convert_btn.clicked.connect(self._dev_convert_picnc)

        self.asset_controller.apply_asset_shots_size(self.asset_shots_size.currentText(), refresh=False)

        self.project_controller.refresh_projects()
        self.project_controller.refresh_project_watch_paths()
        self.asset_controller.refresh_asset_manager()
        self.client_controller.refresh_client_catalog()
        self.asset_controller.setup_asset_auto_refresh()
        self._asset_watch_enabled = self.asset_auto_refresh.isChecked()
        self.project_controller.setup_project_watcher()
        self.asset_controller.setup_asset_watcher()

        self.media_prev_btn.clicked.connect(self._media_prev)
        self.media_play_btn.clicked.connect(self._media_play_pause)
        self.media_next_btn.clicked.connect(self._media_next)

        status = self.statusBar()
        status.setStyleSheet("QStatusBar { background: #1f2329; color: #9aa3ad; }")
        status.setSizeGripEnabled(False)
        status.hide()


    @staticmethod
    def _to_houdini_path(text: str) -> str:
        # Houdini references are happier with forward slashes, even on Windows.
        return text.replace("\\", "/")

    @staticmethod
    def _send_media_key(vk_code: int) -> None:
        try:
            user32 = ctypes.windll.user32
            user32.keybd_event(vk_code, 0, 0, 0)
            QtCore.QThread.msleep(20)
            user32.keybd_event(vk_code, 0, 2, 0)
        except Exception as exc:
            print(f"[MEDIA] Failed to send key {vk_code}: {exc}")

    def _media_play_pause(self) -> None:
        # VK_MEDIA_PLAY_PAUSE = 0xB3
        self._send_media_key(0xB3)

    def _media_next(self) -> None:
        # VK_MEDIA_NEXT_TRACK = 0xB0
        self._send_media_key(0xB0)

    def _media_prev(self) -> None:
        # VK_MEDIA_PREV_TRACK = 0xB1
        self._send_media_key(0xB1)

    def _on_main_page_changed(self, index: int) -> None:
        # Ensure board visuals/overrides are freshly applied when entering the Board page.
        if int(index) == 2 and hasattr(self, "board_controller") and self.board_controller is not None:
            QtCore.QTimer.singleShot(0, self.board_controller.ensure_board_loaded)

    def set_clients_badge(self, enabled: bool) -> None:
        if self._nav_clients_btn is None or self._nav_clients_badge is None:
            return
        self._nav_clients_badge.setVisible(bool(enabled))
        self._position_clients_badge()

    def _position_clients_badge(self) -> None:
        if self._nav_clients_btn is None or self._nav_clients_badge is None:
            return
        x = max(0, self._nav_clients_btn.width() - 14)
        y = 8
        self._nav_clients_badge.move(x, y)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self._nav_clients_btn and event.type() in (
            QtCore.QEvent.Type.Resize,
            QtCore.QEvent.Type.Show,
            QtCore.QEvent.Type.Move,
        ):
            self._position_clients_badge()
        return super().eventFilter(obj, event)


    def save_settings_from_ui(self) -> None:
        projects_dir = self.settings_projects_dir.text().strip()
        server_repo_dir = self.settings_server_dir.text().strip()
        template_hip = self.settings_template_hip.text().strip()
        pattern = self.settings_pattern.text().strip()
        use_assoc = self.settings_use_assoc.isChecked()
        houdini_exe = normalize_houdini_exe(self.settings_houdini_exe.text())
        backend_label = self.settings_video_backend.currentText().strip().lower()
        if backend_label == "opencv":
            video_backend = "opencv"
        elif backend_label == "qt":
            video_backend = "qt"
        elif backend_label == "off":
            video_backend = "none"
        else:
            video_backend = "auto"

        self.settings.update(
            {
                "projects_dir": projects_dir,
                "server_repo_dir": server_repo_dir,
                "template_hip": template_hip,
                "new_hip_pattern": pattern,
                "use_file_association": use_assoc,
                "houdini_exe": houdini_exe,
                "video_backend": video_backend,
                "asset_manager_projects": list(self._asset_manager_projects),
            }
        )
        save_settings(self.settings)

        self.projects_dir = Path(projects_dir) if projects_dir else DEFAULT_PROJECTS_DIR
        self.server_repo_dir = Path(server_repo_dir) if server_repo_dir else Path(DEFAULT_SETTINGS["server_repo_dir"])
        self._template_hip = Path(template_hip) if template_hip else DEFAULT_TEMPLATE_HIP
        self._new_hip_pattern = pattern or "{projectName}_001.hipnc"
        self._use_file_association = bool(use_assoc)
        self._houdini_exe = houdini_exe
        self._video_backend_pref = video_backend

        self.path_label.setText(f"Projects: {self.projects_dir}")
        self.project_controller.refresh_projects()
        self.asset_controller.refresh_asset_manager()
        self.project_controller.refresh_project_watch_paths()
        self.asset_controller.refresh_asset_watch_paths()

    def add_selected_project_to_asset_manager(self) -> None:
        item = self.project_grid.currentItem()
        if item is None:
            self._warn("Select a project first.")
            return
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            self._warn("Select a project first.")
            return
        project_path = str(path_text)
        for entry in self._asset_manager_projects:
            if entry.get("local_path") == project_path:
                self.status.setText("Already in Asset Manager.")
                return
        self._asset_manager_projects.append({"local_path": project_path, "client_id": None})
        self.settings["asset_manager_projects"] = list(self._asset_manager_projects)
        save_settings(self.settings)
        self.asset_controller.refresh_asset_manager()
        self.status.setText("Added to Asset Manager.")

    def remove_selected_project_from_asset_manager(self) -> None:
        item = self.project_grid.currentItem()
        if item is None:
            self._warn("Select a project first.")
            return
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            self._warn("Select a project first.")
            return
        project_path = str(path_text)
        before = len(self._asset_manager_projects)
        self._asset_manager_projects = [
            e for e in self._asset_manager_projects if e.get("local_path") != project_path
        ]
        if len(self._asset_manager_projects) == before:
            self.status.setText("Not in Asset Manager.")
            return
        self.settings["asset_manager_projects"] = list(self._asset_manager_projects)
        save_settings(self.settings)
        self.asset_controller.refresh_asset_manager()
        self.status.setText("Removed from Asset Manager.")

    def _warn(self, message: str) -> None:
        QtWidgets.QMessageBox.warning(self, APP_TITLE, message)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        try:
            if hasattr(self, "board_controller") and self.board_controller is not None:
                self.board_controller.save_board()
                self.board_controller.shutdown()
        except Exception:
            pass
        super().closeEvent(event)

    def _dev_add_box_in_houdini(self) -> None:
        import subprocess
        import tempfile
        import os

        houdini_exe = self._houdini_exe
        if not houdini_exe:
            self.dev_status.setText("Houdini executable not set in Settings.")
            return
        houdini_path = Path(houdini_exe)
        if not houdini_path.exists():
            self.dev_status.setText("Houdini executable path is invalid.")
            return
        hython = houdini_path.with_name("hython.exe")
        if not hython.exists():
            self.dev_status.setText("hython.exe not found next to Houdini.")
            return

        running = False
        try:
            out = subprocess.check_output(["tasklist"], text=True, stderr=subprocess.STDOUT)
            for name in ("houdini.exe", "houdinifx.exe", "houdiniindie.exe"):
                if name.lower() in out.lower():
                    running = True
                    break
        except Exception:
            pass

        temp_dir = Path(tempfile.gettempdir()) / "skyforge_dev"
        temp_dir.mkdir(parents=True, exist_ok=True)
        hip_path = temp_dir / "dev_box.hipnc"
        script = (
            "import hou\n"
            "obj = hou.node('/obj')\n"
            "geo = obj.createNode('geo', 'dev_box')\n"
            "for c in geo.children():\n"
            "    c.destroy()\n"
            "box = geo.createNode('box', 'box1')\n"
            "box.setDisplayFlag(True)\n"
            "box.setRenderFlag(True)\n"
            "geo.layoutChildren()\n"
            f"hou.hipFile.save(r'''{hip_path}''')\n"
        )
        try:
            houdini_env = build_houdini_env(
                base_env=os.environ,
                launcher_root=Path(__file__).resolve().parent,
            )
            subprocess.check_call([str(hython), "-c", script], env=houdini_env)
        except Exception as exc:
            self.dev_status.setText(f"Failed to run hython: {exc}")
            return

        if not self.dev_silent_check.isChecked():
            if not running:
                confirm = QtWidgets.QMessageBox.question(
                    self,
                    APP_TITLE,
                    "Houdini is not running. Open Houdini to view the test Box?",
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                )
                if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
                    self.dev_status.setText("Test Box created (silent).")
                    return
            try:
                subprocess.Popen([str(houdini_path), str(hip_path)], env=houdini_env)
            except Exception as exc:
                self.dev_status.setText(f"Failed to launch Houdini: {exc}")
                return
            self.dev_status.setText("Opened Houdini with a test Box.")
        else:
            self.dev_status.setText("Test Box created (silent).")

    def _dev_browse_picnc(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select PICNC",
            "",
            "Houdini PIC (*.picnc *.pic)",
        )
        if path:
            self.dev_picnc_input.setText(path)

    def _dev_browse_picnc_output(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            "",
        )
        if directory:
            self.dev_picnc_out_dir.setText(directory)

    def _dev_convert_picnc(self) -> None:
        import subprocess
        import tempfile

        source = self.dev_picnc_input.text().strip()
        if not source:
            self.dev_status.setText("Select a .picnc first.")
            return
        src_path = Path(source)
        if not src_path.exists():
            self.dev_status.setText("Source file not found.")
            return
        houdini_exe = self._houdini_exe
        if not houdini_exe:
            self.dev_status.setText("Houdini executable not set in Settings.")
            return
        houdini_path = Path(houdini_exe)
        if not houdini_path.exists():
            self.dev_status.setText("Houdini executable path is invalid.")
            return
        iconvert = houdini_path.with_name("iconvert.exe")
        if not iconvert.exists():
            self.dev_status.setText("iconvert.exe not found next to Houdini.")
            return
        ext = self.dev_picnc_out_combo.currentText().strip().lower()
        if ext not in ("jpg", "exr"):
            ext = "jpg"
        out_dir_text = self.dev_picnc_out_dir.text().strip()
        out_dir = Path(out_dir_text) if out_dir_text else Path(tempfile.gettempdir()) / "skyforge_dev"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{src_path.stem}.{ext}"
        try:
            houdini_env = build_houdini_env(
                base_env=os.environ,
                launcher_root=Path(__file__).resolve().parent,
            )
            subprocess.check_call([str(iconvert), str(src_path), str(out_path)], env=houdini_env)
        except Exception as exc:
            self.dev_status.setText(f"iconvert failed: {exc}")
            return
        self.dev_status.setText(f"Converted to: {out_path}")


def main() -> None:
    try:
        try:
            # Ensure Windows uses the correct icon in titlebar/taskbar.
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Skyforge.Launcher")
        except Exception:
            pass
        app = QtWidgets.QApplication([])
        icon_dir = Path(__file__).resolve().parent / "config"
        icon_path = icon_dir / "newForge4_256.ico"
        if not icon_path.exists():
            icon_path = icon_dir / "newForge4.ico"
        if icon_path.exists():
            app.setWindowIcon(QtGui.QIcon(str(icon_path)))
        app_font = app.font()
        if app_font.pointSize() <= 0:
            app_font.setPointSize(10)
            app.setFont(app_font)
        window = LauncherWindow()
        window.show()
        app.exec()
    except Exception:
        log_path = Path(__file__).resolve().parent / "launcher_error.log"
        try:
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            print(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()

