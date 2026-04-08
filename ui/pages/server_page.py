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


class _AssetVersionsList(QtWidgets.QListWidget):
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
        layout = QtWidgets.QVBoxLayout(self)

        # Asset Manager UI (thumbnail library -> details)
        self.asset_pages = QtWidgets.QStackedWidget()
        layout.addWidget(self.asset_pages, 1)

        server_overview = QtWidgets.QWidget()
        overview_layout = QtWidgets.QVBoxLayout(server_overview)
        self.asset_pages.addWidget(server_overview)

        server_header = QtWidgets.QHBoxLayout()
        overview_layout.addLayout(server_header)

        server_title = QtWidgets.QLabel("Asset Manager")
        server_title.setStyleSheet(title_style())
        server_header.addWidget(server_title, 0)

        server_header.addStretch(1)

        self.asset_search_input = QtWidgets.QLineEdit()
        self.asset_search_input.setPlaceholderText("Search asset manager...")
        self.asset_search_input.setClearButtonEnabled(True)
        server_header.addWidget(self.asset_search_input, 0)

        self.asset_refresh_btn = QtWidgets.QPushButton("Refresh")
        server_header.addWidget(self.asset_refresh_btn, 0)

        self.asset_auto_refresh = QtWidgets.QCheckBox("Auto")
        self.asset_auto_refresh.setChecked(True)
        server_header.addWidget(self.asset_auto_refresh, 0)

        self.asset_path_label = QtWidgets.QLabel()
        self.asset_path_label.setText("Asset Manager")
        self.asset_path_label.setStyleSheet(muted_text_style(size_px=11))
        overview_layout.addWidget(self.asset_path_label)

        self.asset_grid = QtWidgets.QListWidget()
        self.asset_grid.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.asset_grid.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.asset_grid.setMovement(QtWidgets.QListView.Movement.Static)
        self.asset_grid.setSpacing(16)
        self.asset_grid.setIconSize(QtCore.QSize(200, 130))
        self.asset_grid.setGridSize(QtCore.QSize(230, 200))
        self.asset_grid.setWordWrap(True)
        self.asset_grid.setStyleSheet(
            "QListWidget::item { background: transparent; border: none; }"
            "QListWidget::item:selected { background: transparent; border: none; }"
            "QListWidget::item:hover { background: transparent; border: none; }"
        )
        self.asset_grid.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        overview_layout.addWidget(self.asset_grid, 1)

        # Details page
        server_details = QtWidgets.QWidget()
        details_layout = QtWidgets.QVBoxLayout(server_details)
        self.asset_pages.addWidget(server_details)

        details_header = QtWidgets.QHBoxLayout()
        details_layout.addLayout(details_header)

        self.asset_back_btn = QtWidgets.QPushButton("Back")
        self.asset_back_btn.clicked.connect(lambda: self.asset_pages.setCurrentIndex(0))
        details_header.addWidget(self.asset_back_btn, 0)

        self.asset_details_title = QtWidgets.QLabel("Project")
        self.asset_details_title.setStyleSheet(title_style(size_px=16))
        details_header.addWidget(self.asset_details_title, 0)

        details_header.addStretch(1)

        details_split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        details_layout.addWidget(details_split, 1)
        details_split.setChildrenCollapsible(False)

        work_panel = QtWidgets.QWidget()
        work_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        work_panel.setStyleSheet(border_only_style())
        col_work = QtWidgets.QVBoxLayout(work_panel)
        details_split.addWidget(work_panel)

        library_label = QtWidgets.QLabel("Library")
        library_label.setStyleSheet("font-weight: bold;")
        col_work.addWidget(library_label)

        search_row = QtWidgets.QHBoxLayout()
        col_work.addLayout(search_row)
        self.asset_entity_search = QtWidgets.QLineEdit()
        self.asset_entity_search.setPlaceholderText("Search shots...")
        self.asset_entity_search.setClearButtonEnabled(True)
        search_row.addWidget(self.asset_entity_search, 1)
        self.asset_open_folder_btn = QtWidgets.QToolButton()
        self.asset_open_folder_btn.setText("Open Folder")
        self.asset_open_folder_btn.setAutoRaise(True)
        self.asset_open_folder_btn.setStyleSheet(tool_button_dark_style(padding="3px 8px"))
        search_row.addWidget(self.asset_open_folder_btn, 0)

        self.asset_work_tabs = QtWidgets.QTabWidget()
        col_work.addWidget(self.asset_work_tabs, 1)

        shots_tab = QtWidgets.QWidget()
        shots_layout = QtWidgets.QVBoxLayout(shots_tab)
        shots_filter_row = QtWidgets.QHBoxLayout()
        shots_layout.addLayout(shots_filter_row)
        shots_filter_label = QtWidgets.QLabel("Filter")
        shots_filter_label.setStyleSheet("font-weight: bold;")
        shots_filter_row.addWidget(shots_filter_label, 0)
        self.asset_shots_filter = QtWidgets.QComboBox()
        shots_filter_row.addWidget(self.asset_shots_filter, 0)
        shots_size_label = QtWidgets.QLabel("Size")
        shots_size_label.setStyleSheet("font-weight: bold;")
        shots_filter_row.addWidget(shots_size_label, 0)
        self.asset_shots_size = QtWidgets.QComboBox()
        self.asset_shots_size.addItems(["Small", "Medium", "Large"])
        self.asset_shots_size.setCurrentText("Medium")
        shots_filter_row.addWidget(self.asset_shots_size, 0)
        shots_filter_row.addStretch(1)
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
        assets_filter_row = QtWidgets.QHBoxLayout()
        assets_layout.addLayout(assets_filter_row)
        assets_filter_label = QtWidgets.QLabel("Filter")
        assets_filter_label.setStyleSheet("font-weight: bold;")
        assets_filter_row.addWidget(assets_filter_label, 0)
        self.asset_assets_filter = QtWidgets.QComboBox()
        assets_filter_row.addWidget(self.asset_assets_filter, 0)
        assets_filter_row.addStretch(1)
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

        preview_panel = QtWidgets.QWidget()
        preview_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        preview_panel.setStyleSheet(border_only_style())
        col_preview = QtWidgets.QVBoxLayout(preview_panel)
        details_split.addWidget(preview_panel)

        details_label = QtWidgets.QLabel("Details")
        details_label.setStyleSheet("font-weight: bold;")
        col_preview.addWidget(details_label)

        preview_label = QtWidgets.QLabel("Preview")
        preview_label.setStyleSheet("font-weight: bold;")
        col_preview.addWidget(preview_label)

        preview_container = QtWidgets.QFrame()
        preview_container.setStyleSheet(panel_style())
        preview_container.setFixedHeight(200)
        preview_container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        preview_layout = QtWidgets.QGridLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        self.asset_preview = QtWidgets.QLabel()
        self.asset_preview.setFixedHeight(200)
        self.asset_preview.setFixedWidth(420)
        self.asset_preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.asset_preview.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        preview_layout.addWidget(self.asset_preview, 0, 0)

        self.asset_prev_btn = QtWidgets.QToolButton()
        self.asset_prev_btn.setText("<")
        self.asset_prev_btn.setAutoRaise(True)
        self.asset_prev_btn.setStyleSheet(tool_button_dark_style(padding="2px 8px"))

        self.asset_next_btn = QtWidgets.QToolButton()
        self.asset_next_btn.setText(">")
        self.asset_next_btn.setAutoRaise(True)
        self.asset_next_btn.setStyleSheet(tool_button_dark_style(padding="2px 8px"))

        self.asset_preview_label = QtWidgets.QLabel("0/0")
        self.asset_preview_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.asset_preview_label.setStyleSheet("color: #c6ccd6; padding: 2px 6px;")

        col_preview.addWidget(preview_container, 0)

        # Hide the static image preview block (keep widgets for controller wiring)
        preview_label.setVisible(False)
        preview_container.setVisible(False)

        self.asset_meta = QtWidgets.QLabel()
        self.asset_meta.setStyleSheet("color: #c6ccd6;")
        self.asset_meta.setWordWrap(True)
        col_preview.addWidget(self.asset_meta, 0)

        self.asset_status = QtWidgets.QLabel("")
        self.asset_status.setWordWrap(True)
        self.asset_status.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.asset_status.setMaximumHeight(40)

        video_label = QtWidgets.QLabel("Video Preview")
        video_label.setStyleSheet("font-weight: bold;")
        col_preview.addWidget(video_label)

        self.asset_video_box = QtWidgets.QFrame()
        self.asset_video_box.setStyleSheet(
            f"background: #1b1f26; border: 1px solid {PALETTE['border']};"
        )
        self.asset_video_layout = QtWidgets.QVBoxLayout(self.asset_video_box)
        self.asset_video_box.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        self.asset_video_controller = VideoController(
            video_backend_pref,
            status_label=self.asset_status,
            preview_label=self.asset_preview_label,
            preview_widget=self.asset_preview,
            parent=self,
        )
        self.asset_video = self.asset_video_controller.widget

        self.asset_video_layout.addWidget(self.asset_video, 1)

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(self.asset_prev_btn, 0)
        controls.addWidget(self.asset_preview_label, 0)
        controls.addWidget(self.asset_next_btn, 0)
        self.asset_play_btn = QtWidgets.QPushButton("Play")
        controls.addWidget(self.asset_play_btn)
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
        col_preview.addWidget(self.asset_video_box, 1)

        details_panel = QtWidgets.QWidget()
        details_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        details_panel.setStyleSheet(border_only_style())
        col_details = QtWidgets.QVBoxLayout(details_panel)
        details_split.addWidget(details_panel)

        details_split.setSizes([320, 360, 260])
        details_split.setStretchFactor(0, 2)
        details_split.setStretchFactor(1, 2)
        details_split.setStretchFactor(2, 1)

        versions_label = QtWidgets.QLabel("Versions")
        versions_label.setStyleSheet("font-weight: bold;")
        versions_row = QtWidgets.QHBoxLayout()
        versions_row.addWidget(versions_label, 0)
        versions_row.addStretch(1)
        self.asset_context_combo = QtWidgets.QComboBox()
        self.asset_context_combo.addItems(
            ["All", "modeling", "lookdev", "layout", "animation", "vfx", "lighting"]
        )
        self.asset_context_combo.setCurrentText("All")
        versions_row.addWidget(self.asset_context_combo, 0)
        col_details.addLayout(versions_row)
        self.asset_versions_list = _AssetVersionsList()
        col_details.addWidget(self.asset_versions_list, 1)

        history_label = QtWidgets.QLabel("History")
        history_label.setStyleSheet("font-weight: bold;")
        col_details.addWidget(history_label)
        self.asset_history_list = QtWidgets.QListWidget()
        col_details.addWidget(self.asset_history_list, 1)

        commit_label = QtWidgets.QLabel("Commit")
        commit_label.setStyleSheet("font-weight: bold;")
        col_details.addWidget(commit_label)
        self.asset_commit_box = QtWidgets.QTextEdit()
        self.asset_commit_box.setPlaceholderText("Commit message...")
        self.asset_commit_box.setFixedHeight(80)
        col_details.addWidget(self.asset_commit_box, 0)

        commit_actions = QtWidgets.QHBoxLayout()
        col_details.addLayout(commit_actions)
        self.asset_commit_btn = QtWidgets.QPushButton("Commit")
        commit_actions.addWidget(self.asset_commit_btn)
        self.asset_push_btn = QtWidgets.QPushButton("Push")
        commit_actions.addWidget(self.asset_push_btn)
        self.asset_fetch_btn = QtWidgets.QPushButton("Fetch")
        commit_actions.addWidget(self.asset_fetch_btn)

        col_details.addWidget(self.asset_status)

