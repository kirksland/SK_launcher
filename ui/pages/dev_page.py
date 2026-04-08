from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ui.utils.styles import panel_style, title_style, muted_text_style


class DevPage(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QtWidgets.QLabel("Dev Lab")
        title.setStyleSheet(title_style())
        layout.addWidget(title, 0)

        hint = QtWidgets.QLabel("Experimental tools for Houdini integration.")
        hint.setStyleSheet(muted_text_style())
        layout.addWidget(hint, 0)

        panel = QtWidgets.QFrame()
        panel.setStyleSheet(panel_style())
        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(8)

        self.silent_check = QtWidgets.QCheckBox("Silent (no UI)")
        self.silent_check.setChecked(True)
        panel_layout.addWidget(self.silent_check, 0)

        self.add_box_btn = QtWidgets.QPushButton("Add Box (Dev)")
        panel_layout.addWidget(self.add_box_btn, 0)

        conv_row = QtWidgets.QHBoxLayout()
        self.picnc_input = QtWidgets.QLineEdit()
        self.picnc_input.setPlaceholderText("Path to .picnc")
        conv_row.addWidget(self.picnc_input, 1)
        self.picnc_browse_btn = QtWidgets.QPushButton("Browse")
        conv_row.addWidget(self.picnc_browse_btn, 0)
        panel_layout.addLayout(conv_row)

        out_row = QtWidgets.QHBoxLayout()
        self.picnc_out_combo = QtWidgets.QComboBox()
        self.picnc_out_combo.addItems(["jpg", "exr"])
        out_row.addWidget(self.picnc_out_combo, 0)
        self.picnc_out_dir = QtWidgets.QLineEdit()
        self.picnc_out_dir.setPlaceholderText("Output folder (optional)")
        out_row.addWidget(self.picnc_out_dir, 1)
        self.picnc_out_browse_btn = QtWidgets.QPushButton("Output...")
        out_row.addWidget(self.picnc_out_browse_btn, 0)
        self.picnc_convert_btn = QtWidgets.QPushButton("Convert PICNC")
        out_row.addWidget(self.picnc_convert_btn, 0)
        out_row.addStretch(1)
        panel_layout.addLayout(out_row)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet(muted_text_style())
        self.status.setWordWrap(True)
        panel_layout.addWidget(self.status, 0)

        panel_layout.addStretch(1)
        layout.addWidget(panel, 1)
