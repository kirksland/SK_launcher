from __future__ import annotations

import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

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
from controllers.asset_manager_controller import AssetManagerController
from controllers.projects_controller import ProjectsController
from controllers.client_controller import ClientController
from controllers.board_controller import BoardController
from ui.widgets.project_card import ProjectCard

APP_TITLE = "Skyforge Launcher"
TEST_PIPELINE_ROOT = Path(__file__).resolve().parent / "projects" / "test_pipeline"

class LauncherWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
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
        self._project_watch_enabled = True
        self._asset_watch_enabled = True

        central = QtWidgets.QWidget()
        central.setStyleSheet(
            "QWidget { background: #1f2329; color: #d8dde5; }"
            "QListWidget { background: #1f2329; border: none; }"
            "QLineEdit { background: #2b2f36; border: 1px solid #14171c; padding: 4px 6px; }"
            "QPushButton { background: #2b2f36; border: 1px solid #14171c; padding: 4px 8px; }"
            "QPushButton:hover { background: #323741; }"
            "QComboBox { background: #2b2f36; border: 1px solid #14171c; padding: 2px 6px; }"
        )
        self.setCentralWidget(central)
        outer = QtWidgets.QHBoxLayout(central)

        main_panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(main_panel)
        outer.addWidget(main_panel, 1)

        self.pages = QtWidgets.QStackedWidget()
        layout.addWidget(self.pages, 1)

        from ui.pages.client_page import ClientPage
        from ui.pages.projects_page import ProjectsPage
        from ui.pages.server_page import AssetManagerPage
        from ui.pages.settings_page import SettingsPage
        from ui.pages.board_page import BoardPage

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

        self.sidebar = QtWidgets.QFrame()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setStyleSheet(
            "QFrame {"
            "background: #1f2329;"
            "border-left: 1px solid #0f1216;"
            "}"
        )
        outer.addWidget(self.sidebar, 0)

        side_layout = QtWidgets.QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(16, 18, 16, 18)
        side_layout.setSpacing(12)

        side_title = QtWidgets.QLabel("SKYFORGE")
        side_title.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        title_font = QtGui.QFont()
        title_font.setBold(True)
        title_font.setPointSize(20)
        side_title.setFont(title_font)
        side_title.setStyleSheet("color: #cfd6df;")
        side_layout.addWidget(side_title)

        side_sub = QtWidgets.QLabel("Launcher")
        side_sub.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        sub_font = QtGui.QFont()
        sub_font.setPointSize(14)
        side_sub.setFont(sub_font)
        side_sub.setStyleSheet("color: #9aa3ad;")
        side_layout.addWidget(side_sub)

        side_layout.addSpacing(18)

        side_layout.addStretch(1)

        nav_labels = ["Projects", "Asset Manager", "Board", "Clients", "Settings"]
        nav_buttons: List[QtWidgets.QToolButton] = []
        nav_font = QtGui.QFont()
        nav_font.setPointSize(18)
        for label in nav_labels:
            btn = QtWidgets.QToolButton()
            btn.setText(label)
            btn.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setAutoRaise(True)
            btn.setFont(nav_font)
            btn.setStyleSheet(
                "QToolButton { color: #c6ccd6; padding: 12px 14px; text-align: left; }"
                "QToolButton:hover { background: rgba(255,255,255,30); }"
            )
            btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
            side_layout.addWidget(btn)
            nav_buttons.append(btn)

        side_layout.addStretch(1)

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
        self.asset_controller = AssetManagerController(self)
        self.project_controller = ProjectsController(self)
        self.client_controller = ClientController(self)
        self.board_controller = BoardController(self)
        self.asset_video_box = self.asset_page.asset_video_box
        self.asset_video_layout = self.asset_page.asset_video_layout

        self.board_project_label = self.board_page.project_label
        self.board_add_image_btn = self.board_page.add_image_btn
        self.board_add_note_btn = self.board_page.add_note_btn
        self.board_auto_layout_btn = self.board_page.auto_layout_btn
        self.board_fit_btn = self.board_page.fit_btn
        self.board_save_btn = self.board_page.save_btn
        self.board_load_btn = self.board_page.load_btn
        self.board_page.set_controller(self.board_controller)
        self.board_controller.set_project(None)

        self.client_refresh_btn = self.client_page.refresh_btn
        self.client_list = self.client_page.client_list
        self.client_preview = self.client_page.client_preview
        self.client_info = self.client_page.client_info
        self.client_bind_btn = self.client_page.bind_btn
        self.client_status = self.client_page.status

        self.settings_projects_dir = self.settings_page.settings_projects_dir
        self.settings_server_dir = self.settings_page.settings_server_dir
        self.settings_template_hip = self.settings_page.settings_template_hip
        self.settings_pattern = self.settings_page.settings_pattern
        self.settings_video_backend = self.settings_page.settings_video_backend
        self.settings_use_assoc = self.settings_page.settings_use_assoc
        self.settings_houdini_exe = self.settings_page.settings_houdini_exe
        self.settings_save_btn = self.settings_page.settings_save_btn

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

        self.board_add_image_btn.clicked.connect(self.board_controller.add_image)
        self.board_add_note_btn.clicked.connect(self.board_controller.add_note)
        self.board_auto_layout_btn.clicked.connect(self.board_controller.layout_selection_grid)
        self.board_fit_btn.clicked.connect(self.board_controller.fit_view)
        self.board_save_btn.clicked.connect(self.board_controller.save_board)
        self.board_load_btn.clicked.connect(self.board_controller.load_board)

        self.settings_save_btn.clicked.connect(self.save_settings_from_ui)

        self.asset_controller.apply_asset_shots_size(self.asset_shots_size.currentText(), refresh=False)

        self.project_controller.refresh_projects()
        self.project_controller.refresh_project_watch_paths()
        self.asset_controller.refresh_asset_manager()
        self.client_controller.refresh_client_catalog()
        self.asset_controller.setup_asset_auto_refresh()
        self._asset_watch_enabled = self.asset_auto_refresh.isChecked()
        self.project_controller.setup_project_watcher()
        self.asset_controller.setup_asset_watcher()

    @staticmethod
    def _to_houdini_path(text: str) -> str:
        # Houdini references are happier with forward slashes, even on Windows.
        return text.replace("\\", "/")

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


def main() -> None:
    try:
        app = QtWidgets.QApplication([])
        app_font = app.font()
        if app_font.pointSize() <= 0:
            app_font.setPointSize(10)
            app.setFont(app_font)
        window = LauncherWindow()
        window.show()
        app.exec()
    except Exception:
        log_path = Path(__file__).resolve().parent / "launcher_error.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()

