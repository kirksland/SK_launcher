from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets


class BoardToolStackRow(QtWidgets.QWidget):
    removeRequested = QtCore.Signal()

    def __init__(self, label: str, muted: bool, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self._muted = bool(muted)
        self._selected = False
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 6, 4)
        layout.setSpacing(6)
        self.label = QtWidgets.QLabel(label)
        self.label.setStyleSheet("background: transparent;")
        layout.addWidget(self.label, 1)
        self.remove_btn = QtWidgets.QToolButton()
        self.remove_btn.setText("x")
        self.remove_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.remove_btn.setAutoRaise(True)
        self.remove_btn.setFixedSize(16, 16)
        self.remove_btn.clicked.connect(self.removeRequested)
        layout.addWidget(self.remove_btn, 0)
        self.setFixedHeight(32)
        self._apply_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._apply_style()

    def _apply_style(self) -> None:
        tone = "#87919d" if self._muted else "#d8dde5"
        if self._selected:
            bg = "rgba(255,255,255,10)"
            border = "rgba(242,193,78,72)"
        else:
            bg = "rgba(255,255,255,4)"
            border = "rgba(255,255,255,10)"
        self.setStyleSheet(
            "background: %s;"
            "border: 1px solid %s;"
            "border-radius: 7px;"
            % (bg, border)
        )
        self.label.setStyleSheet(f"color: {tone}; background: transparent; border: 0;")
        self.remove_btn.setStyleSheet(
            "QToolButton {"
            "background: transparent;"
            "border: 1px solid rgba(255,255,255,10);"
            "border-radius: 5px;"
            "padding: 0px;"
            "color: #8f99a4;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255,255,255,6);"
            "border: 1px solid rgba(255,120,120,52);"
            "color: #d8dde5;"
            "}"
        )
