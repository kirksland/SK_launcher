from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


class ProjectsPage(QtWidgets.QWidget):
    def __init__(self, projects_dir: Path, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._resizing_detail = False
        self._detail_resize_start_pos = QtCore.QPoint()
        self._detail_resize_start_width = 0
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

        self.project_grid = QtWidgets.QListWidget()
        self.project_grid.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.project_grid.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.project_grid.setMovement(QtWidgets.QListView.Movement.Static)
        self.project_grid.setSpacing(16)
        self.project_grid.setIconSize(QtCore.QSize(200, 130))
        self.project_grid.setGridSize(QtCore.QSize(230, 240))
        self.project_grid.setWordWrap(True)

        self.project_grid_container = QtWidgets.QFrame()
        self.project_grid_container.setStyleSheet("QFrame { background: transparent; }")
        container_layout = QtWidgets.QGridLayout(self.project_grid_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.project_grid, 0, 0)
        content.addWidget(self.project_grid_container, 1)

        self.detail_panel = QtWidgets.QFrame()
        self.detail_panel.setMinimumWidth(260)
        self.detail_panel.setMaximumWidth(10000)
        self.detail_panel.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Expanding)
        self.detail_panel.setStyleSheet("background: #2b2f36; border: 1px solid #14171c;")
        self.detail_panel.setMouseTracking(True)
        self.detail_panel.installEventFilter(self)

        detail_shell = QtWidgets.QHBoxLayout(self.detail_panel)
        detail_shell.setContentsMargins(0, 0, 0, 0)
        detail_shell.setSpacing(0)

        self.detail_resize_handle = QtWidgets.QFrame()
        self.detail_resize_handle.setFixedWidth(6)
        self.detail_resize_handle.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        self.detail_resize_handle.setStyleSheet("background: transparent;")
        self.detail_resize_handle.setMouseTracking(True)
        self.detail_resize_handle.installEventFilter(self)
        detail_shell.addWidget(self.detail_resize_handle, 0)

        detail_body = QtWidgets.QFrame()
        detail_body.setStyleSheet("background: transparent;")
        detail_shell.addWidget(detail_body, 1)

        detail_layout = QtWidgets.QVBoxLayout(detail_body)
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
        container_layout.addWidget(self.detail_panel, 0, 0, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

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
        if watched in (self.detail_panel, getattr(self, "detail_resize_handle", None)):
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                mouse = event  # type: ignore[assignment]
                if mouse.button() == QtCore.Qt.MouseButton.LeftButton:
                    pos = mouse.position().toPoint()  # type: ignore[attr-defined]
                    if watched != self.detail_panel or pos.x() <= 6:
                        self._resizing_detail = True
                        self._detail_resize_start_pos = mouse.globalPosition().toPoint()  # type: ignore[attr-defined]
                        self._detail_resize_start_width = self.detail_panel.width()
                        if hasattr(self, "detail_resize_handle"):
                            self.detail_resize_handle.grabMouse()
                        return True
            if event.type() == QtCore.QEvent.Type.MouseMove:
                mouse = event  # type: ignore[assignment]
                if self._resizing_detail:
                    delta = mouse.globalPosition().toPoint().x() - self._detail_resize_start_pos.x()  # type: ignore[attr-defined]
                    new_width = self._detail_resize_start_width - delta
                    max_w = self.detail_panel.maximumWidth()
                    new_width = max(self.detail_panel.minimumWidth(), min(max_w, new_width))
                    self.detail_panel.setFixedWidth(new_width)
                    return True
            if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                if self._resizing_detail:
                    self._resizing_detail = False
                    if hasattr(self, "detail_resize_handle"):
                        self.detail_resize_handle.releaseMouse()
                    return True
        return super().eventFilter(watched, event)
