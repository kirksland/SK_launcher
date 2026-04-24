from __future__ import annotations

import html
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets
import ctypes

# Enable OpenEXR codec in OpenCV when available (portable across project moves).
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

from core.settings import (
    DEFAULT_ASSET_SCHEMA,
    DEFAULT_PROJECTS_DIR,
    DEFAULT_TEMPLATE_HIP,
    DEFAULT_SETTINGS,
    active_settings_path,
    is_first_run,
    load_settings,
    normalize_houdini_exe,
    normalize_asset_schema,
    normalize_asset_manager_projects,
    normalize_asset_project_schemas,
    save_settings,
    settings_startup_issues,
)
from core.houdini_env import build_houdini_env
from controllers.asset_manager_controller import AssetManagerController
from controllers.app_command_controller import AppCommandController
from controllers.app_shortcuts_controller import AppShortcutsController
from controllers.projects_controller import ProjectsController
from controllers.client_controller import ClientController
from controllers.process_controller import ProcessController
from controllers.board.command_dispatcher import BoardCommandDispatcher
from controllers.board.controller import BoardController
from ui.widgets.project_card import ProjectCard
from ui.utils.styles import PALETTE, app_stylesheet, combo_dark_style, tool_button_dark_style

APP_TITLE = "Skyforge Launcher"
TEST_PIPELINE_ROOT = Path(__file__).resolve().parent / "projects" / "test_pipeline"
LOG_DIR = Path(__file__).resolve().parent / "logs"
APP_LOG_PATH = LOG_DIR / "launcher.log"


class RuntimeLogBus(QtCore.QObject):
    entry_added = QtCore.Signal(str, str, str)

    def __init__(self, log_path: Path) -> None:
        super().__init__()
        self.log_path = log_path
        self._entries: list[tuple[str, str, str]] = []
        self._max_entries = 1500
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def entries(self) -> list[tuple[str, str, str]]:
        return list(self._entries)

    def append(self, level: str, message: str) -> None:
        normalized = str(message).replace("\r\n", "\n").replace("\r", "\n")
        for raw_line in normalized.split("\n"):
            line = raw_line.rstrip()
            if not line:
                continue
            timestamp = datetime.now().strftime("%H:%M:%S")
            upper_level = level.upper()
            entry = (timestamp, upper_level, line)
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]
            try:
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"{timestamp} [{upper_level}] {line}\n")
            except Exception:
                pass
            self.entry_added.emit(timestamp, upper_level, line)


class StreamRelay:
    def __init__(self, bus: RuntimeLogBus, level: str, fallback: object) -> None:
        self._bus = bus
        self._level = level
        self._fallback = fallback
        self._buffer = ""
        self.encoding = getattr(fallback, "encoding", "utf-8")

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        try:
            if self._fallback is not None:
                self._fallback.write(text)
        except Exception:
            pass
        self._buffer += text.replace("\r\n", "\n").replace("\r", "\n")
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._bus.append(self._level, line)
        return len(text)

    def flush(self) -> None:
        try:
            if self._fallback is not None:
                self._fallback.flush()
        except Exception:
            pass
        if self._buffer.strip():
            self._bus.append(self._level, self._buffer.strip())
        self._buffer = ""

    def isatty(self) -> bool:
        return False


APP_LOG_BUS = RuntimeLogBus(APP_LOG_PATH)
_RUNTIME_LOGGING_INSTALLED = False


def _install_runtime_logging() -> None:
    global _RUNTIME_LOGGING_INSTALLED
    if _RUNTIME_LOGGING_INSTALLED:
        return
    _RUNTIME_LOGGING_INSTALLED = True

    sys.stdout = StreamRelay(APP_LOG_BUS, "info", getattr(sys, "__stdout__", None))
    sys.stderr = StreamRelay(APP_LOG_BUS, "error", getattr(sys, "__stderr__", None))

    def _excepthook(exc_type: type[BaseException], value: BaseException, tb: object) -> None:
        for line in traceback.format_exception(exc_type, value, tb):
            APP_LOG_BUS.append("error", line)

    def _qt_message_handler(mode: QtCore.QtMsgType, _context: object, message: str) -> None:
        level_map = {
            QtCore.QtMsgType.QtDebugMsg: "debug",
            QtCore.QtMsgType.QtInfoMsg: "info",
            QtCore.QtMsgType.QtWarningMsg: "warning",
            QtCore.QtMsgType.QtCriticalMsg: "error",
            QtCore.QtMsgType.QtFatalMsg: "error",
        }
        APP_LOG_BUS.append(level_map.get(mode, "info"), f"Qt: {message}")

    sys.excepthook = _excepthook
    QtCore.qInstallMessageHandler(_qt_message_handler)


class LauncherLogPanel(QtWidgets.QFrame):
    def __init__(self, log_path: Path, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._entries: list[tuple[str, str, str]] = []
        self._log_path = log_path
        self._expanded_height = 220
        self._expanded = False
        self.setStyleSheet(
            "QFrame {"
            "background: #171b21;"
            "border-top: 1px solid #0f1216;"
            "}"
        )
        self.setMinimumHeight(0)
        self.setMaximumHeight(self._expanded_height)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.hide()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)
        title = QtWidgets.QLabel("Console")
        title.setStyleSheet("font-weight: 600; color: #d8dde5;")
        header.addWidget(title, 0)

        self.log_filter = QtWidgets.QComboBox()
        self.log_filter.addItems(["All", "Info", "Warning", "Error", "Debug"])
        self.log_filter.setStyleSheet(combo_dark_style(padding="2px 8px"))
        header.addWidget(self.log_filter, 0)

        self.log_hint = QtWidgets.QLabel(str(log_path))
        self.log_hint.setStyleSheet(f"color: {PALETTE['muted']};")
        header.addWidget(self.log_hint, 1)

        self.log_clear_btn = QtWidgets.QToolButton()
        self.log_clear_btn.setText("Clear View")
        self.log_clear_btn.setAutoRaise(True)
        self.log_clear_btn.setStyleSheet(tool_button_dark_style(padding="2px 8px"))
        header.addWidget(self.log_clear_btn, 0)

        self.log_open_btn = QtWidgets.QToolButton()
        self.log_open_btn.setText("Open Log")
        self.log_open_btn.setAutoRaise(True)
        self.log_open_btn.setStyleSheet(tool_button_dark_style(padding="2px 8px"))
        header.addWidget(self.log_open_btn, 0)
        layout.addLayout(header)

        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setAcceptRichText(True)
        self.log_view.setStyleSheet(
            "QTextEdit {"
            "background: #11151a;"
            "border: 1px solid #222832;"
            "border-radius: 8px;"
            "padding: 8px;"
            "color: #d8dde5;"
            "font-family: Consolas, 'Courier New', monospace;"
            "font-size: 11px;"
            "}"
        )
        layout.addWidget(self.log_view, 1)

        self.log_filter.currentTextChanged.connect(self._rerender)
        self.log_clear_btn.clicked.connect(self._clear_view)
        self.log_open_btn.clicked.connect(self._open_log_file)

    def load_entries(self, entries: list[tuple[str, str, str]]) -> None:
        self._entries = list(entries)
        self._rerender()

    def append_entry(self, timestamp: str, level: str, message: str) -> None:
        entry = (timestamp, level, message)
        self._entries.append(entry)
        if self._matches_filter(level):
            self._append_html(entry)

    def _clear_view(self) -> None:
        self.log_view.clear()

    def _open_log_file(self) -> None:
        if self._log_path.exists():
            os.startfile(str(self._log_path))  # type: ignore[attr-defined]

    def _matches_filter(self, level: str) -> bool:
        selected = self.log_filter.currentText().lower()
        return selected == "all" or level.lower() == selected

    def _append_html(self, entry: tuple[str, str, str]) -> None:
        timestamp, level, message = entry
        colors = {
            "INFO": "#9fd3ff",
            "WARNING": "#ffd166",
            "ERROR": "#ff7b72",
            "DEBUG": "#86d39e",
        }
        color = colors.get(level.upper(), "#d8dde5")
        escaped = html.escape(message)
        self.log_view.append(
            f"<span style='color:#738091;'>[{timestamp}]</span> "
            f"<span style='color:{color}; font-weight:600;'>[{html.escape(level)}]</span> "
            f"<span style='color:#d8dde5;'>{escaped}</span>"
        )

    def _rerender(self) -> None:
        self.log_view.clear()
        for entry in self._entries:
            if self._matches_filter(entry[1]):
                self._append_html(entry)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self.setVisible(self._expanded)

    def expanded_height(self) -> int:
        return self._expanded_height if self._expanded else 0

    def sizeHint(self) -> QtCore.QSize:
        hint = super().sizeHint()
        return QtCore.QSize(hint.width(), self.expanded_height())

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(0, 0)


def _create_startup_splash() -> QtWidgets.QSplashScreen:
    root = Path(__file__).resolve().parent
    splash_image_path = root / "horizontalSF.png"
    pixmap = QtGui.QPixmap(640, 360)
    pixmap.fill(QtGui.QColor("#1b1f25"))

    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.fillRect(0, 0, pixmap.width(), pixmap.height(), QtGui.QColor("#1b1f25"))
    frame_rect = QtCore.QRect(24, 24, pixmap.width() - 48, pixmap.height() - 48)
    painter.fillRect(frame_rect, QtGui.QColor("#23272e"))
    painter.setPen(QtGui.QPen(QtGui.QColor("#2f3640"), 1))
    painter.drawRoundedRect(frame_rect, 16, 16)

    splash_image = QtGui.QPixmap(str(splash_image_path))
    image_rect = QtCore.QRect(frame_rect.left() + 22, frame_rect.top() + 20, frame_rect.width() - 44, 180)
    if not splash_image.isNull():
        scaled_image = splash_image.scaled(
            image_rect.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        source_x = max(0, (scaled_image.width() - image_rect.width()) // 2)
        source_y = max(0, (scaled_image.height() - image_rect.height()) // 2)
        painter.drawPixmap(
            image_rect,
            scaled_image,
            QtCore.QRect(source_x, source_y, image_rect.width(), image_rect.height()),
        )
        painter.fillRect(image_rect, QtGui.QColor(8, 10, 14, 70))
    else:
        painter.fillRect(image_rect, QtGui.QColor("#1a1e24"))

    painter.setPen(QtGui.QColor("#d8dde5"))
    title_font = QtGui.QFont("Segoe UI", 20)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.drawText(
        QtCore.QRect(frame_rect.left() + 24, frame_rect.top() + 222, frame_rect.width() - 48, 34),
        QtCore.Qt.AlignmentFlag.AlignLeft,
        APP_TITLE,
    )

    subtitle_font = QtGui.QFont("Segoe UI", 10)
    painter.setFont(subtitle_font)
    painter.setPen(QtGui.QColor("#9aa3ad"))
    painter.drawText(
        QtCore.QRect(frame_rect.left() + 24, frame_rect.top() + 264, frame_rect.width() - 48, 24),
        QtCore.Qt.AlignmentFlag.AlignLeft,
        "Loading workspace, tools, and media modules...",
    )

    painter.fillRect(frame_rect.left() + 24, frame_rect.top() + 306, frame_rect.width() - 48, 6, QtGui.QColor("#14171c"))
    painter.fillRect(
        frame_rect.left() + 24,
        frame_rect.top() + 306,
        int((frame_rect.width() - 48) * 0.58),
        6,
        QtGui.QColor("#5aa9e6"),
    )
    painter.end()

    splash = QtWidgets.QSplashScreen(pixmap)
    splash.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
    splash.showMessage(
        "Starting...",
        QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignBottom,
        QtGui.QColor("#cfd6df"),
    )
    return splash

class LauncherWindow(QtWidgets.QMainWindow):
    def __init__(self, startup_status: Optional[Callable[[str], None]] = None) -> None:
        super().__init__()
        startup_callback = startup_status or (lambda _message: None)

        def _status(message: str) -> None:
            APP_LOG_BUS.append("info", message)
            startup_callback(message)

        self._startup_status = _status
        self._startup_status("Loading settings...")
        self.setWindowTitle(APP_TITLE)
        icon_dir = Path(__file__).resolve().parent / "config"
        icon_path = icon_dir / "newForge4_256.ico"
        if not icon_path.exists():
            icon_path = icon_dir / "newForge4.ico"
        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))
        self.resize(1280, 620)

        self._settings_path = active_settings_path()
        self._is_first_run = is_first_run(self._settings_path)
        self.settings = load_settings()
        self.projects_dir = Path(self.settings["projects_dir"])
        self.server_repo_dir = Path(self.settings["server_repo_dir"])
        self._template_hip = Path(self.settings["template_hip"])
        self._new_hip_pattern = self.settings["new_hip_pattern"]
        self._use_file_association = bool(self.settings["use_file_association"])
        self._show_splash_screen = bool(self.settings.get("show_splash_screen", True))
        self._houdini_exe = self.settings["houdini_exe"]
        self._video_backend_pref = str(self.settings.get("video_backend", "auto")).strip().lower() or "auto"
        self._asset_manager_projects = normalize_asset_manager_projects(
            self.settings.get("asset_manager_projects", [])
        )
        self._asset_schema = normalize_asset_schema(
            self.settings.get("asset_schema", DEFAULT_ASSET_SCHEMA)
        )
        self._asset_project_schemas = normalize_asset_project_schemas(
            self.settings.get("asset_project_schemas", {})
        )
        self._asset_active_schema = dict(self._asset_schema)
        self.test_pipeline_root = TEST_PIPELINE_ROOT
        self._project_cache: Dict[Path, Tuple[float, List[Path], float]] = {}
        self._asset_cache: Dict[Path, Tuple[float, List[Path], float]] = {}
        self._card_to_item: Dict[ProjectCard, QtWidgets.QListWidgetItem] = {}
        self._project_scene_selection: Dict[Path, Path] = {}
        self._project_watch_enabled = True
        self._asset_watch_enabled = True
        self._startup_status("Building interface...")

        central = QtWidgets.QWidget()
        central.setStyleSheet(app_stylesheet())
        self.setCentralWidget(central)
        outer = QtWidgets.QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        main_panel = QtWidgets.QWidget()
        self._main_panel = main_panel
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
        self.command_controller = AppCommandController()

        self._startup_status("Loading project pages...")
        self.projects_page = ProjectsPage(self.projects_dir)
        self.pages.addWidget(self.projects_page)

        self._startup_status("Loading asset manager...")
        self.asset_page = AssetManagerPage(self._video_backend_pref, parent=self)
        self.pages.addWidget(self.asset_page)

        self._startup_status("Loading board tools...")
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
            self._show_splash_screen,
            self._houdini_exe,
            shortcut_commands=self.command_controller.registry.list(),
            shortcut_overrides=self.settings.get("shortcuts", {}),
        )
        self.pages.addWidget(self.settings_page)

        self.dev_page = DevPage(parent=self)
        self.pages.addWidget(self.dev_page)
        self._startup_status("Connecting controllers...")

        self.log_panel = LauncherLogPanel(APP_LOG_PATH, parent=main_panel)
        self.log_panel.set_expanded(False)
        self.log_panel.load_entries(APP_LOG_BUS.entries)
        APP_LOG_BUS.entry_added.connect(self.log_panel.append_entry)

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
        self.log_toggle_btn = QtWidgets.QToolButton()
        self.log_toggle_btn.setText("Logs")
        self.log_toggle_btn.setCheckable(True)
        self.log_toggle_btn.setAutoRaise(True)
        self.log_toggle_btn.setStyleSheet(tool_button_dark_style(padding="4px 10px"))
        bottom_layout.addWidget(self.log_toggle_btn, 0)
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
        self.log_toggle_btn.toggled.connect(self._set_log_panel_expanded)

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
        self.asset_layout_btn = self.asset_page.asset_layout_btn
        self.asset_refresh_btn = self.asset_page.asset_refresh_btn
        self.asset_auto_refresh = self.asset_page.asset_auto_refresh
        self.asset_onboarding_card = self.asset_page.asset_onboarding_card
        self.asset_onboarding_summary = self.asset_page.asset_onboarding_summary
        self.asset_onboarding_details = self.asset_page.asset_onboarding_details
        self.asset_onboarding_detect_btn = self.asset_page.asset_onboarding_detect_btn
        self.asset_onboarding_default_btn = self.asset_page.asset_onboarding_default_btn
        self.asset_onboarding_merge_library_btn = self.asset_page.asset_onboarding_merge_library_btn
        self.asset_onboarding_manual_btn = self.asset_page.asset_onboarding_manual_btn
        self.asset_onboarding_rescan_btn = self.asset_page.asset_onboarding_rescan_btn
        self.asset_path_label = self.asset_page.asset_path_label
        self.asset_grid = self.asset_page.asset_grid
        self.asset_back_btn = self.asset_page.asset_back_btn
        self.asset_details_title = self.asset_page.asset_details_title
        self.asset_main_split = self.asset_page.asset_main_split
        self.asset_shots_filter = self.asset_page.asset_shots_filter
        self.asset_shots_size = self.asset_page.asset_shots_size
        self.asset_shots_list = self.asset_page.asset_shots_list
        self.asset_assets_filter = self.asset_page.asset_assets_filter
        self.asset_assets_list = self.asset_page.asset_assets_list
        self.asset_library_filter = self.asset_page.asset_library_filter
        self.asset_library_list = self.asset_page.asset_library_list
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
        self.asset_inventory_list = self.asset_page.asset_inventory_list
        self.asset_versions_list = self.asset_inventory_list
        self.asset_inventory_list.setContextMenuPolicy(
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
        self.process_controller = ProcessController(self)
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
        self._layout_overlay_panels()

    def _set_log_panel_expanded(self, expanded: bool) -> None:
        self.log_panel.set_expanded(expanded)
        self._layout_overlay_panels()

    def _layout_overlay_panels(self) -> None:
        main_rect = self._main_panel.rect()
        panel_height = self.log_panel.expanded_height()
        if panel_height <= 0:
            self.log_panel.setGeometry(0, main_rect.height(), main_rect.width(), 0)
            return
        bottom_height = self.log_toggle_btn.parentWidget().height()
        y = max(0, main_rect.height() - bottom_height - panel_height)
        self.log_panel.setGeometry(0, y, main_rect.width(), panel_height)
        self.log_panel.raise_()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_overlay_panels()
        self.command_controller.register_dispatcher("board", BoardCommandDispatcher(self.board_controller))
        self.shortcuts_controller = AppShortcutsController(self, self.command_controller, self.settings)
        self.shortcuts_controller.install()

        self.settings_projects_dir = self.settings_page.settings_projects_dir
        self.settings_server_dir = self.settings_page.settings_server_dir
        self.settings_template_hip = self.settings_page.settings_template_hip
        self.settings_pattern = self.settings_page.settings_pattern
        self.settings_video_backend = self.settings_page.settings_video_backend
        self.settings_use_assoc = self.settings_page.settings_use_assoc
        self.settings_show_splash = self.settings_page.settings_show_splash
        self.settings_houdini_exe = self.settings_page.settings_houdini_exe
        self.settings_save_btn = self.settings_page.settings_save_btn
        self.settings_projects_browse_btn = self.settings_page.settings_projects_browse_btn
        self.settings_server_browse_btn = self.settings_page.settings_server_browse_btn
        self.settings_template_browse_btn = self.settings_page.settings_template_browse_btn
        self.settings_houdini_browse_btn = self.settings_page.settings_houdini_browse_btn

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
        self.asset_layout_btn.clicked.connect(self.asset_controller.reopen_layout_setup)
        self.asset_refresh_btn.clicked.connect(self.asset_controller.refresh_asset_manager)
        self.asset_auto_refresh.toggled.connect(self.asset_controller.toggle_asset_auto_refresh)
        self.asset_grid.itemClicked.connect(self.asset_controller.open_asset_details)
        self.asset_grid.customContextMenuRequested.connect(self.asset_controller.show_asset_manager_context_menu)
        self.asset_shots_filter.currentTextChanged.connect(self.asset_controller.refresh_shots_list)
        self.asset_shots_size.currentTextChanged.connect(self.asset_controller.on_asset_shots_size_changed)
        self.asset_assets_filter.currentTextChanged.connect(self.asset_controller.refresh_assets_list)
        self.asset_library_filter.currentTextChanged.connect(self.asset_controller.refresh_library_list)
        self.asset_entity_search.textChanged.connect(self.asset_controller.refresh_active_list)
        self.asset_open_folder_btn.clicked.connect(self.asset_controller.open_asset_project_folder)
        self.asset_work_tabs.currentChanged.connect(self.asset_controller.on_asset_tab_changed)
        self.asset_shots_list.itemClicked.connect(self.asset_controller.on_asset_entity_clicked)
        self.asset_assets_list.itemClicked.connect(self.asset_controller.on_asset_entity_clicked)
        self.asset_assets_list.customContextMenuRequested.connect(self.asset_controller.show_asset_context_menu)
        self.asset_library_list.itemClicked.connect(self.asset_controller.on_asset_entity_clicked)
        self.asset_library_list.customContextMenuRequested.connect(self.asset_controller.show_asset_context_menu)
        self.asset_prev_btn.clicked.connect(self.asset_controller.prev_preview_image)
        self.asset_next_btn.clicked.connect(self.asset_controller.next_preview_image)
        self.asset_fullscreen_btn.clicked.connect(self.asset_controller.toggle_asset_video_fullscreen)
        self.asset_context_combo.currentTextChanged.connect(self.asset_controller.update_asset_context)
        self.asset_inventory_list.itemClicked.connect(self.asset_controller.on_asset_inventory_clicked)
        self.asset_inventory_list.customContextMenuRequested.connect(
            self.asset_controller.show_asset_inventory_context_menu
        )
        self.asset_commit_btn.clicked.connect(self.asset_controller.asset_placeholder_action)
        self.asset_push_btn.clicked.connect(self.asset_controller.asset_placeholder_action)
        self.asset_fetch_btn.clicked.connect(self.asset_controller.asset_placeholder_action)
        self.asset_onboarding_detect_btn.clicked.connect(self.asset_controller.accept_detected_layout)
        self.asset_onboarding_default_btn.clicked.connect(self.asset_controller.accept_default_layout)
        self.asset_onboarding_merge_library_btn.clicked.connect(
            self.asset_controller.accept_detected_layout_with_library_merged
        )
        self.asset_onboarding_manual_btn.clicked.connect(self.asset_controller.open_manual_layout_mapper)
        self.asset_onboarding_rescan_btn.clicked.connect(self.asset_controller.redetect_layout)

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
        self.settings_projects_browse_btn.clicked.connect(self._browse_settings_projects_dir)
        self.settings_server_browse_btn.clicked.connect(self._browse_settings_server_dir)
        self.settings_template_browse_btn.clicked.connect(self._browse_settings_template_hip)
        self.settings_houdini_browse_btn.clicked.connect(self._browse_settings_houdini_exe)
        self.settings_projects_dir.textChanged.connect(self._refresh_settings_validation)
        self.settings_server_dir.textChanged.connect(self._refresh_settings_validation)
        self.settings_template_hip.textChanged.connect(self._refresh_settings_validation)
        self.settings_houdini_exe.textChanged.connect(self._refresh_settings_validation)
        self.settings_use_assoc.toggled.connect(self._refresh_settings_validation)
        self.dev_add_box_btn.clicked.connect(self._dev_add_box_in_houdini)
        self.dev_picnc_browse_btn.clicked.connect(self._dev_browse_picnc)
        self.dev_picnc_out_browse_btn.clicked.connect(self._dev_browse_picnc_output)
        self.dev_picnc_convert_btn.clicked.connect(self._dev_convert_picnc)

        self.asset_controller.apply_asset_shots_size(self.asset_shots_size.currentText(), refresh=False)

        self._startup_status("Refreshing project data...")
        self.project_controller.refresh_projects()
        self.project_controller.refresh_project_watch_paths()
        self._startup_status("Refreshing asset data...")
        self.asset_controller.refresh_asset_manager()
        self._startup_status("Refreshing client data...")
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
        self._refresh_settings_validation()
        self._startup_status("Finishing startup...")
        QtCore.QTimer.singleShot(0, self._handle_startup_configuration)

    def apply_initial_window_geometry(self) -> None:
        screen = QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos())
        if screen is None:
            screen = self.screen()
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        margin = 40
        target_width = min(self.width(), max(640, available.width() - margin))
        target_height = min(self.height(), max(480, available.height() - margin))
        self.resize(target_width, target_height)
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

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
        if int(index) == 1 and hasattr(self, "asset_controller") and self.asset_controller is not None:
            QtCore.QTimer.singleShot(0, self.asset_controller.ensure_project_context_loaded)
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
        show_splash_screen = self.settings_show_splash.isChecked()
        houdini_exe = normalize_houdini_exe(self.settings_houdini_exe.text())
        resolved_projects_dir = Path(projects_dir) if projects_dir else DEFAULT_PROJECTS_DIR
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
                "projects_dir": str(resolved_projects_dir),
                "server_repo_dir": server_repo_dir,
                "template_hip": template_hip,
                "new_hip_pattern": pattern,
                "use_file_association": use_assoc,
                "show_splash_screen": show_splash_screen,
                "houdini_exe": houdini_exe,
                "video_backend": video_backend,
                "asset_manager_projects": list(self._asset_manager_projects),
                "shortcuts": self.settings_page.shortcut_overrides(),
            }
        )
        save_settings(self.settings)
        self.shortcuts_controller.reload_settings(self.settings)

        self.server_repo_dir = Path(server_repo_dir) if server_repo_dir else Path(DEFAULT_SETTINGS["server_repo_dir"])
        self._template_hip = Path(template_hip) if template_hip else DEFAULT_TEMPLATE_HIP
        self._new_hip_pattern = pattern or "{projectName}_001.hipnc"
        self._use_file_association = bool(use_assoc)
        self._show_splash_screen = bool(show_splash_screen)
        self._houdini_exe = houdini_exe
        self._video_backend_pref = video_backend

        self.apply_projects_dir(resolved_projects_dir, persist=False, sync_settings_field=False)
        self._is_first_run = False
        self.settings_page.set_startup_context(False)
        self._refresh_settings_validation()

    def apply_projects_dir(
        self,
        directory: Path,
        *,
        persist: bool,
        sync_settings_field: bool,
    ) -> None:
        self.projects_dir = Path(directory)
        self.settings["projects_dir"] = str(self.projects_dir)
        if sync_settings_field and hasattr(self, "settings_projects_dir"):
            self.settings_projects_dir.blockSignals(True)
            self.settings_projects_dir.setText(str(self.projects_dir))
            self.settings_projects_dir.blockSignals(False)
        if persist:
            save_settings(self.settings)

        self.path_label.setText(f"Projects: {self.projects_dir}")
        self.project_controller.refresh_projects()
        self.project_controller.refresh_project_watch_paths()
        self.asset_controller.refresh_asset_manager()
        self.asset_controller.refresh_asset_watch_paths()
        self._refresh_settings_validation()

    def _handle_startup_configuration(self) -> None:
        issues = settings_startup_issues(self.settings)
        if not self._is_first_run and not issues:
            return

        self.pages.setCurrentIndex(4)
        if self._is_first_run:
            message = (
                "Skyforge is starting with a fresh configuration.\n\n"
                "Please review the Settings page and confirm your folders before using the app."
            )
        else:
            issue_list = ", ".join(issues)
            message = (
                "Some required paths are missing or invalid.\n\n"
                f"Please review Settings: {issue_list}"
            )
        self.settings_page.set_startup_context(True, message)
        self._refresh_settings_validation()
        APP_LOG_BUS.append("warning", message)
        QtWidgets.QMessageBox.information(self, APP_TITLE, message)

    def _refresh_settings_validation(self) -> None:
        snapshot = {
            "projects_dir": self.settings_projects_dir.text().strip(),
            "server_repo_dir": self.settings_server_dir.text().strip(),
            "template_hip": self.settings_template_hip.text().strip(),
            "use_file_association": self.settings_use_assoc.isChecked(),
            "houdini_exe": normalize_houdini_exe(self.settings_houdini_exe.text()),
        }
        issues = settings_startup_issues(snapshot)
        if issues:
            self.settings_page.set_validation_summary(
                "Configuration incomplete.\nMissing or invalid: " + ", ".join(issues),
                ready=False,
            )
        else:
            self.settings_page.set_validation_summary(
                "Configuration looks ready for startup and distribution tests.",
                ready=True,
            )

    def _browse_settings_projects_dir(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Projects Folder",
            self.settings_projects_dir.text().strip() or str(self.projects_dir),
        )
        if directory:
            self.settings_projects_dir.setText(directory)
            self.apply_projects_dir(Path(directory), persist=False, sync_settings_field=False)

    def _browse_settings_server_dir(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Server Repo Folder",
            self.settings_server_dir.text().strip() or str(self.server_repo_dir),
        )
        if directory:
            self.settings_server_dir.setText(directory)

    def _browse_settings_template_hip(self) -> None:
        path, _selected = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Template Hip",
            self.settings_template_hip.text().strip() or str(Path(__file__).resolve().parent),
            "Houdini Files (*.hip *.hiplc *.hipnc);;All Files (*.*)",
        )
        if path:
            self.settings_template_hip.setText(path)

    def _browse_settings_houdini_exe(self) -> None:
        path, _selected = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select houdini.exe",
            self.settings_houdini_exe.text().strip() or r"C:\Program Files\Side Effects Software",
            "Executable (houdini.exe);;Executable Files (*.exe);;All Files (*.*)",
        )
        if path:
            self.settings_houdini_exe.setText(path)

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
        APP_LOG_BUS.append("warning", message)
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
    _install_runtime_logging()
    APP_LOG_BUS.append("info", "Launching Skyforge...")
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
        startup_settings = load_settings()
        show_splash_screen = bool(startup_settings.get("show_splash_screen", True))
        splash: QtWidgets.QSplashScreen | None = None

        def update_splash(message: str) -> None:
            if splash is None:
                return
            splash.showMessage(
                message,
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignBottom,
                QtGui.QColor("#cfd6df"),
            )
            app.processEvents()

        if show_splash_screen:
            splash = _create_startup_splash()
            splash.show()
            app.processEvents()

        window = LauncherWindow(startup_status=update_splash)
        window.show()
        window.apply_initial_window_geometry()
        if splash is not None:
            splash.finish(window)
        app.exec()
    except Exception:
        details = traceback.format_exc()
        APP_LOG_BUS.append("error", "Skyforge failed to start.")
        APP_LOG_BUS.append("error", details)
        try:
            QtWidgets.QMessageBox.critical(
                None,
                APP_TITLE,
                f"Skyforge failed to start.\n\nSee log:\n{APP_LOG_PATH}",
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()

