from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


class ProjectsPage(QtWidgets.QWidget):
    def __init__(self, projects_dir: Path, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)

        header = QtWidgets.QHBoxLayout()
        layout.addLayout(header)

        title_block = QtWidgets.QVBoxLayout()
        header.addLayout(title_block, 1)

        title = QtWidgets.QLabel("Projects")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title_block.addWidget(title)

        self.path_label = QtWidgets.QLabel()
        self.path_label.setText(f"Projects: {projects_dir}")
        title_block.addWidget(self.path_label)

        self.browse_btn = QtWidgets.QPushButton("Browse...")
        header.addWidget(self.browse_btn)

        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        header.addWidget(self.refresh_btn)

        self.new_btn = QtWidgets.QPushButton("New Project")
        header.addWidget(self.new_btn)

        controls = QtWidgets.QHBoxLayout()
        layout.addLayout(controls)

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search projects...")
        self.search_input.setClearButtonEnabled(True)
        controls.addWidget(self.search_input, 1)

        self.sort_combo = QtWidgets.QComboBox()
        self.sort_combo.addItems(["Name (A-Z)", "Date (Newest)"])
        self.sort_combo.setCurrentText("Date (Newest)")
        controls.addWidget(self.sort_combo)

        content = QtWidgets.QHBoxLayout()
        layout.addLayout(content, 1)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        content.addWidget(splitter, 1)

        self.project_grid = QtWidgets.QListWidget()
        self.project_grid.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.project_grid.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.project_grid.setMovement(QtWidgets.QListView.Movement.Static)
        self.project_grid.setSpacing(16)
        self.project_grid.setIconSize(QtCore.QSize(200, 130))
        self.project_grid.setGridSize(QtCore.QSize(230, 240))
        self.project_grid.setWordWrap(True)

        splitter.addWidget(self.project_grid)

        self.detail_panel = QtWidgets.QFrame()
        self.detail_panel.setMinimumWidth(260)
        self.detail_panel.setStyleSheet("background: #2b2f36; border: 1px solid #14171c;")

        detail_layout = QtWidgets.QVBoxLayout(self.detail_panel)
        title_row = QtWidgets.QHBoxLayout()
        detail_layout.addLayout(title_row)
        self.detail_title = QtWidgets.QLabel("Project Structure")
        self.detail_title.setStyleSheet("font-weight: bold;")
        title_row.addWidget(self.detail_title, 1)
        self.detail_close_btn = QtWidgets.QToolButton()
        self.detail_close_btn.setText("×")
        self.detail_close_btn.setAutoRaise(True)
        title_row.addWidget(self.detail_close_btn, 0)

        toolbar = QtWidgets.QHBoxLayout()
        detail_layout.addLayout(toolbar)
        self.detail_open_btn = QtWidgets.QToolButton()
        self.detail_open_btn.setToolTip("Open in Explorer")
        folder_icon = QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DirOpenIcon)
        self.detail_open_btn.setIcon(folder_icon)
        self.detail_open_btn.setAutoRaise(True)
        self.detail_open_btn.setStyleSheet(
            "QToolButton { padding: 4px; border-radius: 4px; }"
            "QToolButton:hover { background: rgba(255,255,255,30); }"
        )
        toolbar.addWidget(self.detail_open_btn)
        for icon_type, tip in (
            (QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView, "Details (coming soon)"),
            (QtWidgets.QStyle.StandardPixmap.SP_FileDialogInfoView, "Info (coming soon)"),
        ):
            btn = QtWidgets.QToolButton()
            btn.setIcon(QtWidgets.QApplication.style().standardIcon(icon_type))
            btn.setToolTip(tip)
            btn.setEnabled(False)
            btn.setAutoRaise(True)
            btn.setStyleSheet(
                "QToolButton { padding: 4px; border-radius: 4px; }"
            )
            toolbar.addWidget(btn)
        toolbar.addStretch(1)

        self.detail_tree = QtWidgets.QTreeWidget()
        self.detail_tree.setHeaderHidden(True)
        detail_layout.addWidget(self.detail_tree, 1)
        self.detail_panel.setVisible(False)
        splitter.addWidget(self.detail_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        footer = QtWidgets.QHBoxLayout()
        layout.addLayout(footer)

        self.open_btn = QtWidgets.QPushButton("Open Project Hip")
        footer.addWidget(self.open_btn)

        self.add_asset_btn = QtWidgets.QPushButton("Add to Asset Manager")
        footer.addWidget(self.add_asset_btn)

        self.remove_asset_btn = QtWidgets.QPushButton("Remove from Asset Manager")
        footer.addWidget(self.remove_asset_btn)

        self.status = QtWidgets.QLabel("")
        footer.addWidget(self.status, 1)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        return super().eventFilter(watched, event)
