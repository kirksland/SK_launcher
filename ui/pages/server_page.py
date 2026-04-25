from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets

from ui.utils.styles import (
    PALETTE,
    border_only_style,
    muted_text_style,
    panel_style,
    tool_button_dark_style,
    title_style,
)

from video.player import VideoController


class _AssetInventoryList(QtWidgets.QListWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

    def mimeData(self, items: list[QtWidgets.QListWidgetItem]) -> QtCore.QMimeData:  # type: ignore[override]
        mime = QtCore.QMimeData()
        urls: list[QtCore.QUrl] = []
        for item in items:
            path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if not path_text:
                continue
            urls.append(QtCore.QUrl.fromLocalFile(str(path_text)))
        if urls:
            mime.setUrls(urls)
            mime.setText(urls[0].toLocalFile())
        return mime


class AssetManagerPage(QtWidgets.QWidget):
    def __init__(self, video_backend_pref: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        self.asset_pages = QtWidgets.QStackedWidget()
        self.asset_pages.setStyleSheet("QStackedWidget { background: transparent; }")
        root.addWidget(self.asset_pages, 1)

        overview_page = QtWidgets.QWidget()
        overview_layout = QtWidgets.QVBoxLayout(overview_page)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(10)
        intro_title = QtWidgets.QLabel("Asset Manager")
        intro_title.setStyleSheet(title_style())
        overview_layout.addWidget(intro_title)
        intro_text = QtWidgets.QLabel(
            "Select a project from the browser to inspect shots, assets, published versions and previews."
        )
        intro_text.setWordWrap(True)
        intro_text.setStyleSheet(muted_text_style())
        overview_layout.addWidget(intro_text)
        overview_layout.addStretch(1)
        self.asset_pages.addWidget(overview_page)

        browser_page = QtWidgets.QWidget()
        browser_layout = QtWidgets.QVBoxLayout(browser_page)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        browser_layout.setSpacing(12)
        self.asset_pages.addWidget(browser_page)

        topbar = QtWidgets.QHBoxLayout()
        browser_layout.addLayout(topbar)

        title_block = QtWidgets.QVBoxLayout()
        title_block.setSpacing(2)
        server_title = QtWidgets.QLabel("Asset Manager")
        server_title.setStyleSheet(title_style())
        title_block.addWidget(server_title)
        self.asset_path_label = QtWidgets.QLabel("Browse projects, then inspect shots or assets.")
        self.asset_path_label.setStyleSheet(muted_text_style(size_px=11))
        self.asset_path_label.setWordWrap(True)
        title_block.addWidget(self.asset_path_label)
        topbar.addLayout(title_block, 1)

        top_controls = QtWidgets.QHBoxLayout()
        top_controls.setSpacing(8)
        self.asset_search_input = QtWidgets.QLineEdit()
        self.asset_search_input.setPlaceholderText("Search projects in asset manager...")
        self.asset_search_input.setClearButtonEnabled(True)
        self.asset_search_input.setVisible(False)
        top_controls.addWidget(self.asset_search_input, 1)
        self.asset_layout_btn = QtWidgets.QToolButton()
        self.asset_layout_btn.setText("Layout")
        self.asset_layout_btn.setAutoRaise(True)
        self.asset_layout_btn.setStyleSheet(tool_button_dark_style(padding="3px 8px"))
        self.asset_layout_btn.setToolTip("Review or replace the current project asset layout.")
        top_controls.addWidget(self.asset_layout_btn, 0)
        self.asset_refresh_btn = QtWidgets.QPushButton("Refresh")
        top_controls.addWidget(self.asset_refresh_btn, 0)
        self.asset_auto_refresh = QtWidgets.QCheckBox("Auto")
        self.asset_auto_refresh.setChecked(True)
        top_controls.addWidget(self.asset_auto_refresh, 0)
        topbar.addLayout(top_controls, 1)

        self.asset_back_btn = QtWidgets.QPushButton("Back")
        self.asset_back_btn.setVisible(False)
        browser_layout.addWidget(self.asset_back_btn, 0)

        self.asset_layout_toolbar = QtWidgets.QHBoxLayout()
        self.asset_layout_toolbar.setSpacing(8)
        self.asset_project_toggle_btn = QtWidgets.QToolButton()
        self.asset_project_toggle_btn.setText("Hide Projects")
        self.asset_project_toggle_btn.setCheckable(True)
        self.asset_project_toggle_btn.setChecked(False)
        self.asset_project_toggle_btn.setAutoRaise(True)
        self.asset_project_toggle_btn.setStyleSheet(tool_button_dark_style(padding="3px 8px"))
        self.asset_project_toggle_btn.setToolTip("Collapse or expand the project rail.")
        self.asset_project_toggle_btn.setVisible(False)
        self.asset_layout_toolbar.addWidget(self.asset_project_toggle_btn, 0)
        self.asset_layout_hint = QtWidgets.QLabel("Projects stay available, but can collapse once a project is chosen.")
        self.asset_layout_hint.setStyleSheet(muted_text_style(size_px=11))
        self.asset_layout_hint.setVisible(False)
        self.asset_layout_toolbar.addWidget(self.asset_layout_hint, 0)
        self.asset_layout_toolbar.addStretch(1)
        browser_layout.addLayout(self.asset_layout_toolbar)

        self.asset_onboarding_card = QtWidgets.QFrame()
        self.asset_onboarding_card.setStyleSheet(
            "QFrame {"
            "background: rgba(255, 214, 102, 0.08);"
            "border: 1px solid rgba(255, 214, 102, 0.24);"
            "border-radius: 10px;"
            "}"
        )
        onboarding_layout = QtWidgets.QVBoxLayout(self.asset_onboarding_card)
        onboarding_layout.setContentsMargins(14, 12, 14, 12)
        onboarding_layout.setSpacing(8)
        onboarding_title = QtWidgets.QLabel("Project Layout Setup")
        onboarding_title.setStyleSheet("font-weight: 600; color: #d8dde5;")
        onboarding_layout.addWidget(onboarding_title, 0)
        self.asset_onboarding_summary = QtWidgets.QLabel("")
        self.asset_onboarding_summary.setWordWrap(True)
        self.asset_onboarding_summary.setStyleSheet("color: #d8dde5;")
        onboarding_layout.addWidget(self.asset_onboarding_summary, 0)
        self.asset_onboarding_details = QtWidgets.QLabel("")
        self.asset_onboarding_details.setWordWrap(True)
        self.asset_onboarding_details.setStyleSheet(muted_text_style(size_px=11))
        onboarding_layout.addWidget(self.asset_onboarding_details, 0)
        onboarding_actions = QtWidgets.QHBoxLayout()
        onboarding_actions.setSpacing(8)
        self.asset_onboarding_detect_btn = QtWidgets.QPushButton("Use Detected Layout")
        onboarding_actions.addWidget(self.asset_onboarding_detect_btn, 0)
        self.asset_onboarding_default_btn = QtWidgets.QPushButton("Use Default Layout")
        onboarding_actions.addWidget(self.asset_onboarding_default_btn, 0)
        self.asset_onboarding_merge_library_btn = QtWidgets.QToolButton()
        self.asset_onboarding_merge_library_btn.setText("Merge Library into Assets")
        self.asset_onboarding_merge_library_btn.setAutoRaise(True)
        self.asset_onboarding_merge_library_btn.setStyleSheet(tool_button_dark_style(padding="3px 8px"))
        self.asset_onboarding_merge_library_btn.setToolTip(
            "Use this when source files are part of your working asset list, not a separate library."
        )
        onboarding_actions.addWidget(self.asset_onboarding_merge_library_btn, 0)
        self.asset_onboarding_manual_btn = QtWidgets.QToolButton()
        self.asset_onboarding_manual_btn.setText("Manual Map")
        self.asset_onboarding_manual_btn.setAutoRaise(True)
        self.asset_onboarding_manual_btn.setStyleSheet(tool_button_dark_style(padding="3px 8px"))
        self.asset_onboarding_manual_btn.setToolTip(
            "Manually assign project folders to Shots, Assets or Library."
        )
        onboarding_actions.addWidget(self.asset_onboarding_manual_btn, 0)
        self.asset_onboarding_rescan_btn = QtWidgets.QToolButton()
        self.asset_onboarding_rescan_btn.setText("Re-scan")
        self.asset_onboarding_rescan_btn.setAutoRaise(True)
        self.asset_onboarding_rescan_btn.setStyleSheet(tool_button_dark_style(padding="3px 8px"))
        onboarding_actions.addWidget(self.asset_onboarding_rescan_btn, 0)
        onboarding_actions.addStretch(1)
        onboarding_layout.addLayout(onboarding_actions)
        self.asset_onboarding_card.setVisible(False)
        browser_layout.addWidget(self.asset_onboarding_card, 0)

        self.asset_main_split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.asset_main_split.setChildrenCollapsible(False)
        browser_layout.addWidget(self.asset_main_split, 1)

        self.asset_project_panel = self._make_panel("Projects", "Choose the synced project you want to browse.")
        project_layout = self.asset_project_panel.layout()  # type: ignore[assignment]
        project_actions = QtWidgets.QHBoxLayout()
        project_actions.setSpacing(8)
        self.asset_details_title = QtWidgets.QLabel("No project selected")
        self.asset_details_title.setStyleSheet("font-weight: 600; color: #d8dde5;")
        project_actions.addWidget(self.asset_details_title, 1)
        project_layout.addLayout(project_actions)

        self.asset_grid = QtWidgets.QListWidget()
        self.asset_grid.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.asset_grid.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.asset_grid.setMovement(QtWidgets.QListView.Movement.Static)
        self.asset_grid.setSpacing(14)
        self.asset_grid.setIconSize(QtCore.QSize(190, 120))
        self.asset_grid.setGridSize(QtCore.QSize(220, 188))
        self.asset_grid.setWordWrap(True)
        self.asset_grid.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.asset_grid.setStyleSheet(
            "QListWidget { background: transparent; border: none; }"
            "QListWidget::item { background: transparent; border: none; }"
            "QListWidget::item:selected { background: transparent; border: none; }"
            "QListWidget::item:hover { background: transparent; border: none; }"
        )
        project_layout.addWidget(self.asset_grid, 1)
        self.asset_main_split.addWidget(self.asset_project_panel)
        self.asset_project_panel.setVisible(False)

        entity_panel = self._make_panel("Library", "Filter the current project and drill down into shots or assets.")
        entity_layout = entity_panel.layout()  # type: ignore[assignment]
        entity_toolbar = QtWidgets.QHBoxLayout()
        entity_toolbar.setSpacing(8)
        self.asset_entity_search = QtWidgets.QLineEdit()
        self.asset_entity_search.setPlaceholderText("Search shots...")
        self.asset_entity_search.setClearButtonEnabled(True)
        entity_toolbar.addWidget(self.asset_entity_search, 1)
        self.asset_open_folder_btn = QtWidgets.QToolButton()
        self.asset_open_folder_btn.setText("Open Folder")
        self.asset_open_folder_btn.setAutoRaise(True)
        self.asset_open_folder_btn.setStyleSheet(tool_button_dark_style(padding="3px 8px"))
        entity_toolbar.addWidget(self.asset_open_folder_btn, 0)
        entity_layout.addLayout(entity_toolbar)

        self.asset_work_tabs = QtWidgets.QTabWidget()
        self.asset_work_tabs.setDocumentMode(True)
        self.asset_work_tabs.setStyleSheet(
            "QTabWidget::pane { border: none; }"
            "QTabBar::tab {"
            "background: rgba(255,255,255,0.04);"
            "border: 1px solid rgba(255,255,255,0.08);"
            "border-bottom: none;"
            "padding: 8px 12px;"
            "margin-right: 4px;"
            "border-top-left-radius: 6px;"
            "border-top-right-radius: 6px;"
            "color: #9aa3ad;"
            "}"
            "QTabBar::tab:selected {"
            "background: rgba(255,255,255,0.08);"
            "color: #d8dde5;"
            "}"
        )
        entity_layout.addWidget(self.asset_work_tabs, 1)

        shots_tab = QtWidgets.QWidget()
        shots_layout = QtWidgets.QVBoxLayout(shots_tab)
        shots_layout.setContentsMargins(0, 10, 0, 0)
        shots_layout.setSpacing(10)
        shots_filter_row = QtWidgets.QHBoxLayout()
        shots_filter_row.setSpacing(8)
        shots_filter_label = QtWidgets.QLabel("Group")
        shots_filter_label.setStyleSheet(muted_text_style())
        shots_filter_row.addWidget(shots_filter_label, 0)
        self.asset_shots_filter = QtWidgets.QComboBox()
        shots_filter_row.addWidget(self.asset_shots_filter, 0)
        shots_size_label = QtWidgets.QLabel("Density")
        shots_size_label.setStyleSheet(muted_text_style())
        shots_filter_row.addWidget(shots_size_label, 0)
        self.asset_shots_size = QtWidgets.QComboBox()
        self.asset_shots_size.addItems(["Small", "Medium", "Large"])
        self.asset_shots_size.setCurrentText("Medium")
        shots_filter_row.addWidget(self.asset_shots_size, 0)
        shots_filter_row.addStretch(1)
        shots_layout.addLayout(shots_filter_row)
        self.asset_shots_list = QtWidgets.QListWidget()
        self.asset_shots_list.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.asset_shots_list.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.asset_shots_list.setMovement(QtWidgets.QListView.Movement.Static)
        self.asset_shots_list.setSpacing(12)
        self.asset_shots_list.setIconSize(QtCore.QSize(180, 110))
        self.asset_shots_list.setGridSize(QtCore.QSize(200, 150))
        self.asset_shots_list.setWordWrap(True)
        shots_layout.addWidget(self.asset_shots_list, 1)
        self.asset_work_tabs.addTab(shots_tab, "Shots")

        assets_tab = QtWidgets.QWidget()
        assets_layout = QtWidgets.QVBoxLayout(assets_tab)
        assets_layout.setContentsMargins(0, 10, 0, 0)
        assets_layout.setSpacing(10)
        assets_filter_row = QtWidgets.QHBoxLayout()
        assets_filter_row.setSpacing(8)
        assets_filter_label = QtWidgets.QLabel("Group")
        assets_filter_label.setStyleSheet(muted_text_style())
        assets_filter_row.addWidget(assets_filter_label, 0)
        self.asset_assets_filter = QtWidgets.QComboBox()
        assets_filter_row.addWidget(self.asset_assets_filter, 0)
        assets_filter_row.addStretch(1)
        assets_layout.addLayout(assets_filter_row)
        self.asset_assets_list = QtWidgets.QListWidget()
        self.asset_assets_list.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.asset_assets_list.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.asset_assets_list.setMovement(QtWidgets.QListView.Movement.Static)
        self.asset_assets_list.setSpacing(12)
        self.asset_assets_list.setIconSize(QtCore.QSize(180, 110))
        self.asset_assets_list.setGridSize(QtCore.QSize(200, 150))
        self.asset_assets_list.setWordWrap(True)
        self.asset_assets_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        assets_layout.addWidget(self.asset_assets_list, 1)
        self.asset_work_tabs.addTab(assets_tab, "Assets")

        library_tab = QtWidgets.QWidget()
        library_layout = QtWidgets.QVBoxLayout(library_tab)
        library_layout.setContentsMargins(0, 10, 0, 0)
        library_layout.setSpacing(10)
        library_filter_row = QtWidgets.QHBoxLayout()
        library_filter_row.setSpacing(8)
        library_filter_label = QtWidgets.QLabel("Group")
        library_filter_label.setStyleSheet(muted_text_style())
        library_filter_row.addWidget(library_filter_label, 0)
        self.asset_library_filter = QtWidgets.QComboBox()
        library_filter_row.addWidget(self.asset_library_filter, 0)
        library_filter_row.addStretch(1)
        library_layout.addLayout(library_filter_row)
        self.asset_library_list = QtWidgets.QListWidget()
        self.asset_library_list.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.asset_library_list.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.asset_library_list.setMovement(QtWidgets.QListView.Movement.Static)
        self.asset_library_list.setSpacing(12)
        self.asset_library_list.setIconSize(QtCore.QSize(180, 110))
        self.asset_library_list.setGridSize(QtCore.QSize(200, 150))
        self.asset_library_list.setWordWrap(True)
        self.asset_library_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        library_layout.addWidget(self.asset_library_list, 1)
        self.asset_work_tabs.addTab(library_tab, "Library")
        self.asset_main_split.addWidget(entity_panel)

        inspector_panel = self._make_panel("Inspector", "")
        inspector_layout = inspector_panel.layout()  # type: ignore[assignment]

        self.asset_selection_summary = QtWidgets.QLabel("No entity selected")
        self.asset_selection_summary.setStyleSheet("color: #d8dde5; font-weight: 600;")
        self.asset_selection_summary.setVisible(False)

        meta_frame = QtWidgets.QFrame()
        meta_frame.setStyleSheet(panel_style())
        meta_layout = QtWidgets.QVBoxLayout(meta_frame)
        meta_layout.setContentsMargins(10, 10, 10, 10)
        meta_layout.setSpacing(8)
        self.asset_meta = QtWidgets.QLabel("Select a shot or asset to view details.")
        self.asset_meta.setStyleSheet("color: #c6ccd6;")
        self.asset_meta.setWordWrap(True)
        meta_layout.addWidget(self.asset_meta, 0)
        inspector_layout.addWidget(meta_frame, 0)
        meta_frame.setVisible(False)

        self.asset_inspector_tabs = QtWidgets.QTabWidget()
        self.asset_inspector_tabs.setDocumentMode(True)
        self.asset_inspector_tabs.setStyleSheet(
            "QTabWidget::pane { border: none; }"
            "QTabBar::tab {"
            "background: rgba(255,255,255,0.04);"
            "border: 1px solid rgba(255,255,255,0.08);"
            "border-bottom: none;"
            "padding: 7px 12px;"
            "margin-right: 4px;"
            "border-top-left-radius: 6px;"
            "border-top-right-radius: 6px;"
            "color: #9aa3ad;"
            "}"
            "QTabBar::tab:selected {"
            "background: rgba(255,255,255,0.08);"
            "color: #d8dde5;"
            "}"
        )
        inspector_layout.addWidget(self.asset_inspector_tabs, 1)

        preview_tab = QtWidgets.QWidget()
        preview_tab_layout = QtWidgets.QVBoxLayout(preview_tab)
        preview_tab_layout.setContentsMargins(0, 4, 0, 0)
        preview_tab_layout.setSpacing(10)

        pipeline_frame = QtWidgets.QFrame()
        pipeline_frame.setStyleSheet(panel_style())
        pipeline_layout = QtWidgets.QVBoxLayout(pipeline_frame)
        pipeline_layout.setContentsMargins(10, 10, 10, 10)
        pipeline_layout.setSpacing(8)
        pipeline_title = QtWidgets.QLabel("Pipeline Status")
        pipeline_title.setStyleSheet("font-weight: 600; color: #d8dde5;")
        pipeline_layout.addWidget(pipeline_title, 0)
        self.asset_pipeline_summary = QtWidgets.QLabel("No pipeline inspection available.")
        self.asset_pipeline_summary.setStyleSheet("color: #c6ccd6;")
        self.asset_pipeline_summary.setWordWrap(True)
        pipeline_layout.addWidget(self.asset_pipeline_summary, 0)
        self.asset_pipeline_list = QtWidgets.QListWidget()
        self.asset_pipeline_list.setMaximumHeight(132)
        pipeline_layout.addWidget(self.asset_pipeline_list, 0)
        process_title = QtWidgets.QLabel("Available Processes")
        process_title.setStyleSheet("font-weight: 600; color: #d8dde5;")
        pipeline_layout.addWidget(process_title, 0)
        self.asset_pipeline_process_list = QtWidgets.QListWidget()
        self.asset_pipeline_process_list.setMaximumHeight(120)
        pipeline_layout.addWidget(self.asset_pipeline_process_list, 0)
        self.asset_pipeline_process_summary = QtWidgets.QLabel("Select a process to inspect what it would prepare.")
        self.asset_pipeline_process_summary.setStyleSheet("color: #c6ccd6;")
        self.asset_pipeline_process_summary.setWordWrap(True)
        pipeline_layout.addWidget(self.asset_pipeline_process_summary, 0)
        pipeline_actions = QtWidgets.QHBoxLayout()
        pipeline_actions.setSpacing(8)
        self.asset_pipeline_run_btn = QtWidgets.QPushButton("Run Selected Process")
        self.asset_pipeline_run_btn.setEnabled(False)
        pipeline_actions.addWidget(self.asset_pipeline_run_btn, 0)
        pipeline_actions.addStretch(1)
        pipeline_layout.addLayout(pipeline_actions)
        self.asset_pipeline_run_summary = QtWidgets.QLabel("No process execution yet.")
        self.asset_pipeline_run_summary.setStyleSheet("color: #c6ccd6;")
        self.asset_pipeline_run_summary.setWordWrap(True)
        pipeline_layout.addWidget(self.asset_pipeline_run_summary, 0)
        artifact_title = QtWidgets.QLabel("Produced Artifacts")
        artifact_title.setStyleSheet("font-weight: 600; color: #d8dde5;")
        pipeline_layout.addWidget(artifact_title, 0)
        self.asset_pipeline_artifact_list = QtWidgets.QListWidget()
        self.asset_pipeline_artifact_list.setMaximumHeight(120)
        pipeline_layout.addWidget(self.asset_pipeline_artifact_list, 0)
        self.asset_pipeline_artifact_list.addItem("No produced artifacts yet")

        self.asset_preview = QtWidgets.QLabel()
        self.asset_preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.asset_preview.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        self.asset_status = QtWidgets.QLabel("")
        self.asset_status.setWordWrap(True)
        self.asset_status.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.asset_status.setMaximumHeight(42)

        self.asset_video_box = QtWidgets.QFrame()
        self.asset_video_box.setStyleSheet(
            f"background: #1b1f26; border: 1px solid {PALETTE['border']}; border-radius: 8px;"
        )
        self.asset_video_layout = QtWidgets.QVBoxLayout(self.asset_video_box)
        self.asset_video_layout.setContentsMargins(8, 8, 8, 8)
        self.asset_video_layout.setSpacing(8)
        self.asset_video_box.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        self.asset_video_controller = VideoController(
            video_backend_pref,
            status_label=self.asset_status,
            preview_label=None,
            preview_widget=self.asset_preview,
            parent=self,
        )
        self.asset_video = self.asset_video_controller.widget
        preview_header = QtWidgets.QHBoxLayout()
        preview_title = QtWidgets.QLabel("Preview")
        preview_title.setStyleSheet("font-weight: 600;")
        preview_header.addWidget(preview_title, 0)
        preview_header.addStretch(1)
        self.asset_preview_label = QtWidgets.QLabel("0/0")
        self.asset_preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.asset_preview_label.setStyleSheet("color: #c6ccd6; padding: 2px 6px;")
        preview_header.addWidget(self.asset_preview_label, 0)
        self.asset_video_layout.addLayout(preview_header)
        self.asset_video_layout.addWidget(self.asset_video, 1)

        controls = QtWidgets.QHBoxLayout()
        controls.setSpacing(8)
        self.asset_prev_btn = QtWidgets.QToolButton()
        self.asset_prev_btn.setText("<")
        self.asset_prev_btn.setAutoRaise(True)
        self.asset_prev_btn.setStyleSheet(tool_button_dark_style(padding="2px 8px"))
        controls.addWidget(self.asset_prev_btn, 0)
        self.asset_next_btn = QtWidgets.QToolButton()
        self.asset_next_btn.setText(">")
        self.asset_next_btn.setAutoRaise(True)
        self.asset_next_btn.setStyleSheet(tool_button_dark_style(padding="2px 8px"))
        controls.addWidget(self.asset_next_btn, 0)
        self.asset_play_btn = QtWidgets.QPushButton("Play")
        controls.addWidget(self.asset_play_btn, 0)
        self.asset_fullscreen_btn = QtWidgets.QToolButton()
        self.asset_fullscreen_btn.setText("Full")
        self.asset_fullscreen_btn.setAutoRaise(True)
        self.asset_fullscreen_btn.setStyleSheet(tool_button_dark_style(padding="2px 6px"))
        controls.addWidget(self.asset_fullscreen_btn, 0)
        self.asset_video_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.asset_video_slider.setRange(0, 0)
        controls.addWidget(self.asset_video_slider, 1)
        self.asset_video_controller.bind_controls(self.asset_play_btn, self.asset_video_slider)
        self.asset_video_layout.addLayout(controls)
        preview_tab_layout.addWidget(self.asset_video_box, 1)

        pipeline_tab = QtWidgets.QWidget()
        pipeline_tab_layout = QtWidgets.QVBoxLayout(pipeline_tab)
        pipeline_tab_layout.setContentsMargins(0, 4, 0, 0)
        pipeline_tab_layout.setSpacing(10)
        pipeline_tab_layout.addWidget(pipeline_frame, 1)

        self.asset_inspector_tabs.addTab(preview_tab, "Preview")
        self.asset_inspector_tabs.addTab(pipeline_tab, "Pipeline")

        versions_panel = self._make_panel("Inventory", "")
        versions_layout = versions_panel.layout()  # type: ignore[assignment]
        versions_header = QtWidgets.QHBoxLayout()
        self.asset_context_combo = QtWidgets.QComboBox()
        self.asset_context_combo.addItems(
            ["All", "modeling", "lookdev", "layout", "animation", "vfx", "lighting"]
        )
        self.asset_context_combo.setCurrentText("All")
        versions_header.addWidget(self.asset_context_combo, 0)
        versions_header.addStretch(1)
        self.asset_inventory_hint = QtWidgets.QLabel("Inventory")
        self.asset_inventory_hint.setStyleSheet(muted_text_style(size_px=11))
        self.asset_inventory_hint.setVisible(False)
        versions_header.addWidget(self.asset_inventory_hint, 0)
        versions_layout.addLayout(versions_header)
        self.asset_inventory_list = _AssetInventoryList()
        self.asset_versions_hint = self.asset_inventory_hint
        self.asset_versions_list = self.asset_inventory_list
        versions_layout.addWidget(self.asset_inventory_list, 1)
        inspector_layout.addWidget(versions_panel, 1)

        history_panel = self._make_panel("Notes", "Quick notes and git actions for the current entity are grouped here for now.")
        history_layout = history_panel.layout()  # type: ignore[assignment]
        self.asset_history_list = QtWidgets.QListWidget()
        history_layout.addWidget(self.asset_history_list, 1)
        self.asset_commit_box = QtWidgets.QTextEdit()
        self.asset_commit_box.setPlaceholderText("Git actions are not wired yet. Use this space for a future commit note.")
        self.asset_commit_box.setFixedHeight(72)
        history_layout.addWidget(self.asset_commit_box, 0)
        commit_actions = QtWidgets.QHBoxLayout()
        self.asset_commit_btn = QtWidgets.QPushButton("Commit")
        self.asset_commit_btn.setEnabled(False)
        commit_actions.addWidget(self.asset_commit_btn)
        self.asset_push_btn = QtWidgets.QPushButton("Push")
        self.asset_push_btn.setEnabled(False)
        commit_actions.addWidget(self.asset_push_btn)
        self.asset_fetch_btn = QtWidgets.QPushButton("Fetch")
        self.asset_fetch_btn.setEnabled(False)
        commit_actions.addWidget(self.asset_fetch_btn)
        history_layout.addLayout(commit_actions)
        history_layout.addWidget(self.asset_status, 0)
        inspector_layout.addWidget(history_panel, 1)
        history_panel.setVisible(False)

        self.asset_main_split.addWidget(inspector_panel)
        self.asset_main_split.setSizes([0, 560, 560])
        self.asset_main_split.setStretchFactor(0, 0)
        self.asset_main_split.setStretchFactor(1, 2)
        self.asset_main_split.setStretchFactor(2, 2)

        self.asset_pages.setCurrentIndex(1)
        self.asset_project_toggle_btn.toggled.connect(self.set_project_panel_collapsed)

    def _make_panel(self, title: str, description: str) -> QtWidgets.QFrame:
        panel = QtWidgets.QFrame()
        panel.setStyleSheet(
            "QFrame {"
            "background: rgba(255,255,255,0.03);"
            "border: 1px solid rgba(255,255,255,0.07);"
            "border-radius: 10px;"
            "}"
        )
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-weight: 600; color: #d8dde5;")
        if description:
            panel.setToolTip(description)
            title_label.setToolTip(description)
        layout.addWidget(title_label)
        desc_label = QtWidgets.QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(muted_text_style(size_px=11))
        desc_label.setVisible(False)
        layout.addWidget(desc_label)
        return panel

    def set_project_panel_collapsed(self, collapsed: bool) -> None:
        if not hasattr(self, "asset_main_split"):
            return
        is_collapsed = bool(collapsed)
        self.asset_project_panel.setMaximumWidth(56 if is_collapsed else 16777215)
        self.asset_project_panel.setMinimumWidth(56 if is_collapsed else 220)
        self.asset_grid.setVisible(not is_collapsed)
        self.asset_details_title.setVisible(not is_collapsed)
        self.asset_project_toggle_btn.setText("Show Projects" if is_collapsed else "Hide Projects")
        if is_collapsed:
            self.asset_main_split.setSizes([56, 560, 560])
        else:
            self.asset_main_split.setSizes([280, 470, 470])
