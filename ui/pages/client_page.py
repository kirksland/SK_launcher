from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ui.utils.styles import muted_text_style, panel_style, title_style


class _SyncTreeDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, tree: QtWidgets.QTreeView, sync_roots: list[str]) -> None:
        super().__init__(tree)
        self._tree = tree
        self._sync_roots = [r.lower() for r in sync_roots]

    def set_sync_roots(self, roots: list[str]) -> None:
        self._sync_roots = [r.lower() for r in roots]
        self._tree.viewport().update()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        model = self._tree.model()
        if model is not None:
            path = model.filePath(index)  # type: ignore[attr-defined]
            root_index = self._tree.rootIndex()
            root_path = model.filePath(root_index) if root_index.isValid() else ""
            if root_path and path.startswith(root_path):
                rel = path[len(root_path):].lstrip("\\/").split("\\")[0].split("/")[0]
                if rel.lower() in self._sync_roots:
                    painter.save()
                    painter.fillRect(option.rect, QtGui.QColor(46, 68, 52, 140))
                    painter.restore()
        super().paint(painter, option, index)


class _ClientTree(QtWidgets.QTreeView):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setAnimated(True)


class ClientPage(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)

        header = QtWidgets.QHBoxLayout()
        layout.addLayout(header)

        title = QtWidgets.QLabel("Client Catalog")
        title.setStyleSheet(title_style())
        header.addWidget(title, 0)
        header.addStretch(1)

        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        header.addWidget(self.refresh_btn, 0)

        body = QtWidgets.QHBoxLayout()
        layout.addLayout(body, 1)

        self.client_list = QtWidgets.QListWidget()
        self.client_list.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.client_list.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.client_list.setMovement(QtWidgets.QListView.Movement.Static)
        self.client_list.setSpacing(16)
        self.client_list.setIconSize(QtCore.QSize(200, 130))
        self.client_list.setGridSize(QtCore.QSize(230, 240))
        self.client_list.setWordWrap(True)
        body.addWidget(self.client_list, 0)

        right_panel = QtWidgets.QFrame()
        right_panel.setStyleSheet(panel_style())
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)
        body.addWidget(right_panel, 1)

        header_row = QtWidgets.QHBoxLayout()
        sync_title = QtWidgets.QLabel("Client Sync")
        sync_title.setStyleSheet("font-weight: bold;")
        header_row.addWidget(sync_title, 0)
        header_row.addStretch(1)
        self.client_sync_status = QtWidgets.QLabel("Status: —")
        self.client_sync_status.setStyleSheet(muted_text_style())
        header_row.addWidget(self.client_sync_status, 0)
        right_layout.addLayout(header_row)

        info_panel = QtWidgets.QFrame()
        info_panel.setStyleSheet(panel_style())
        info_layout = QtWidgets.QVBoxLayout(info_panel)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(6)

        info_title = QtWidgets.QLabel("Project Info")
        info_title.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(info_title, 0)

        self.client_info = QtWidgets.QLabel("Project: —")
        self.client_info.setWordWrap(True)
        info_layout.addWidget(self.client_info, 0)

        self.client_sync_local_path = QtWidgets.QLabel("Local: —")
        self.client_sync_local_path.setStyleSheet(muted_text_style())
        self.client_sync_local_path.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addWidget(self.client_sync_local_path, 0)

        self.client_sync_server_path = QtWidgets.QLabel("Server: —")
        self.client_sync_server_path.setStyleSheet(muted_text_style())
        self.client_sync_server_path.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addWidget(self.client_sync_server_path, 0)

        self.client_tree = _ClientTree()
        self.client_tree.setMinimumHeight(180)
        info_layout.addWidget(self.client_tree, 1)

        right_layout.addWidget(info_panel, 0)

        actions_panel = QtWidgets.QFrame()
        actions_panel.setStyleSheet(panel_style())
        actions_layout = QtWidgets.QVBoxLayout(actions_panel)
        actions_layout.setContentsMargins(12, 10, 12, 10)
        actions_layout.setSpacing(8)

        actions_title = QtWidgets.QLabel("Actions")
        actions_title.setStyleSheet("font-weight: bold;")
        actions_layout.addWidget(actions_title, 0)

        actions_row = QtWidgets.QHBoxLayout()
        self.client_sync_preview_btn = QtWidgets.QPushButton("Preview")
        self.client_sync_preview_btn.setToolTip("Analyze differences without changing files.")
        self.client_sync_pull_btn = QtWidgets.QPushButton("Pull")
        self.client_sync_pull_btn.setToolTip("Copy newer server files to local (with backups).")
        self.client_sync_push_btn = QtWidgets.QPushButton("Push")
        self.client_sync_push_btn.setToolTip("Copy newer local files to server (with backups).")
        self.client_sync_btn = QtWidgets.QPushButton("Sync")
        self.client_sync_btn.setToolTip("Run pull + push in one operation (with backups).")
        actions_row.addWidget(self.client_sync_preview_btn)
        actions_row.addWidget(self.client_sync_pull_btn)
        actions_row.addWidget(self.client_sync_push_btn)
        actions_row.addWidget(self.client_sync_btn)
        actions_layout.addLayout(actions_row)

        secondary_row = QtWidgets.QHBoxLayout()
        self.client_sync_open_btn = QtWidgets.QPushButton("Open Local")
        self.client_sync_open_btn.setToolTip("Open the local project folder.")
        self.client_sync_baseline_btn = QtWidgets.QPushButton("Save Baseline")
        self.client_sync_baseline_btn.setToolTip("Save a baseline to detect real conflicts.")
        secondary_row.addWidget(self.client_sync_open_btn)
        secondary_row.addWidget(self.client_sync_baseline_btn)
        secondary_row.addStretch(1)
        actions_layout.addLayout(secondary_row)

        self.client_sync_note = QtWidgets.QLabel("Preview first, then Push/Pull/Sync.")
        self.client_sync_note.setStyleSheet(muted_text_style())
        actions_layout.addWidget(self.client_sync_note, 0)

        right_layout.addWidget(actions_panel, 0)

        changes_panel = QtWidgets.QFrame()
        changes_panel.setStyleSheet(panel_style())
        changes_layout = QtWidgets.QVBoxLayout(changes_panel)
        changes_layout.setContentsMargins(12, 10, 12, 10)
        changes_layout.setSpacing(8)

        changes_title = QtWidgets.QLabel("Changes")
        changes_title.setStyleSheet("font-weight: bold;")
        changes_layout.addWidget(changes_title, 0)

        changes_grid = QtWidgets.QGridLayout()
        changes_grid.setContentsMargins(0, 0, 0, 0)
        changes_grid.setHorizontalSpacing(10)
        changes_grid.setVerticalSpacing(8)

        push_header, self.client_push_dot = self._label_with_dot("To Push")
        pull_header, self.client_pull_dot = self._label_with_dot("To Pull")
        changes_grid.addWidget(push_header, 0, 0)
        changes_grid.addWidget(pull_header, 0, 1)

        self.client_sync_push_list = QtWidgets.QListWidget()
        self.client_sync_pull_list = QtWidgets.QListWidget()
        changes_grid.addWidget(self.client_sync_push_list, 1, 0)
        changes_grid.addWidget(self.client_sync_pull_list, 1, 1)

        conflicts_header, self.client_conflicts_dot = self._label_with_dot("Conflicts")
        self.client_sync_conflicts_list = QtWidgets.QListWidget()
        changes_grid.addWidget(conflicts_header, 2, 0, 1, 2)
        changes_grid.addWidget(self.client_sync_conflicts_list, 3, 0, 1, 2)

        changes_layout.addLayout(changes_grid, 1)

        conflict_actions = QtWidgets.QHBoxLayout()
        conflict_actions.addStretch(1)
        self.client_conflict_keep_local_btn = QtWidgets.QPushButton("Keep Local")
        self.client_conflict_keep_local_btn.setToolTip("Overwrite server files with local versions.")
        self.client_conflict_keep_server_btn = QtWidgets.QPushButton("Keep Server")
        self.client_conflict_keep_server_btn.setToolTip("Overwrite local files with server versions.")
        self.client_conflict_keep_both_btn = QtWidgets.QPushButton("Keep Both")
        self.client_conflict_keep_both_btn.setToolTip("Keep both versions by renaming the local file.")
        conflict_actions.addWidget(self.client_conflict_keep_local_btn)
        conflict_actions.addWidget(self.client_conflict_keep_server_btn)
        conflict_actions.addWidget(self.client_conflict_keep_both_btn)
        changes_layout.addLayout(conflict_actions)

        right_layout.addWidget(changes_panel, 1)

        footer_row = QtWidgets.QHBoxLayout()
        self.bind_btn = QtWidgets.QPushButton("Clone Selected")
        footer_row.addWidget(self.bind_btn, 0)
        footer_row.addStretch(1)
        right_layout.addLayout(footer_row)

        self.status = QtWidgets.QLabel("")
        layout.addWidget(self.status)

    def _label_with_dot(self, text: str) -> tuple[QtWidgets.QWidget, QtWidgets.QLabel]:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QtWidgets.QLabel(text)
        label.setStyleSheet("font-weight: bold;")
        dot = QtWidgets.QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet("background: #e03b3b; border-radius: 4px;")
        dot.setVisible(False)
        layout.addWidget(label, 0)
        layout.addWidget(dot, 0)
        layout.addStretch(1)
        return container, dot
