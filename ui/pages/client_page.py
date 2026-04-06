from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ui.utils.styles import panel_style, title_style


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
        self.client_list.setMinimumWidth(260)
        body.addWidget(self.client_list, 0)

        right_panel = QtWidgets.QFrame()
        right_panel.setStyleSheet(panel_style())
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        body.addWidget(right_panel, 1)

        self.client_preview = QtWidgets.QLabel("Select a project")
        self.client_preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.client_preview.setFixedHeight(200)
        right_layout.addWidget(self.client_preview, 0)

        self.client_info = QtWidgets.QLabel("")
        self.client_info.setWordWrap(True)
        right_layout.addWidget(self.client_info, 0)

        right_layout.addStretch(1)

        self.bind_btn = QtWidgets.QPushButton("Clone Selected")
        right_layout.addWidget(self.bind_btn, 0)

        self.status = QtWidgets.QLabel("")
        layout.addWidget(self.status)
