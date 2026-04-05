from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from ui.utils.thumbnails import add_cloud_badge, build_thumbnail_pixmap


def group_hip_variants(hips: List[Path]) -> Dict[str, List[Tuple[str, Path]]]:
    pattern = re.compile(r"^(?P<base>.+)_(?P<ver>\d+)$")
    grouped: Dict[str, List[Tuple[str, Path]]] = {}
    for hip in hips:
        stem = hip.stem
        match = pattern.match(stem)
        if match:
            base = match.group("base")
            ver = match.group("ver")
            label = ver
        else:
            base = stem
            label = "current"
        grouped.setdefault(base, []).append((label, hip))

    # Sort versions numerically when possible, fallback to mtime
    for base, entries in grouped.items():
        def sort_key(item: Tuple[str, Path]) -> Tuple[int, float]:
            label, path = item
            if label.isdigit():
                return (0, int(label))
            return (1, -path.stat().st_mtime)

        entries.sort(key=sort_key, reverse=True)
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))


class ProjectCard(QtWidgets.QWidget):
    selection_changed = QtCore.Signal(object)

    def __init__(
        self,
        project_path: Path,
        thumb_size: QtCore.QSize,
        hips: List[Path],
        show_cloud_badge: bool = False,
        selected_hip: Optional[Path] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project_path = project_path
        self._hips = hips
        self._variants = group_hip_variants(self._hips)
        self._current_base: Optional[str] = None
        self._thumb_size = thumb_size

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        thumb_container = QtWidgets.QWidget()
        thumb_container.setFixedSize(thumb_size)
        thumb_layout = QtWidgets.QGridLayout(thumb_container)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(0)

        thumbnail = QtWidgets.QLabel()
        thumbnail.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        pixmap = build_thumbnail_pixmap(project_path, thumb_size)
        if show_cloud_badge:
            pixmap = add_cloud_badge(pixmap)
        thumbnail.setPixmap(pixmap)
        thumb_layout.addWidget(thumbnail, 0, 0)

        self.title_button = QtWidgets.QToolButton()
        self.title_button.setText(project_path.name)
        self.title_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.title_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.title_button.setAutoRaise(True)
        title_font = QtGui.QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.title_button.setFont(title_font)
        self.title_button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.title_button.setStyleSheet(
            "QToolButton {"
            "background: #ffffff;"
            "color: #111;"
            "padding: 4px 6px;"
            "}"
        )
        thumb_layout.addWidget(
            self.title_button,
            0,
            0,
            QtCore.Qt.AlignmentFlag.AlignBottom,
        )

        layout.addWidget(thumb_container, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.version_combo = QtWidgets.QComboBox()
        self.version_combo.setFixedWidth(thumb_size.width())
        self.version_combo.setStyleSheet(
            "QComboBox {"
            "background: rgba(20, 20, 20, 180);"
            "color: #fff;"
            "padding: 2px 14px 2px 10px;"
            "border: 1px solid rgba(255,255,255,80);"
            "border-radius: 6px;"
            "}"
            "QComboBox QAbstractItemView::item {"
            "padding-right: 14px;"
            "}"
        )
        self.version_combo.view().setMinimumWidth(thumb_size.width())
        self.version_combo.view().setMaximumWidth(thumb_size.width())
        thumb_layout.addWidget(
            self.version_combo,
            0,
            0,
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight,
        )

        if not self._variants:
            self.title_button.setEnabled(False)
            self.version_combo.setVisible(False)
        else:
            self._build_variant_menu()
            if not self._apply_selected_hip(selected_hip):
                first_base = next(iter(self._variants.keys()))
                self._set_current_base(first_base)
            self.version_combo.currentTextChanged.connect(self._emit_selection_changed)

    def _emit_selection_changed(self) -> None:
        hip = self.selected_hip()
        if hip is not None:
            self.selection_changed.emit(self)

    def _build_variant_menu(self) -> None:
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(
            "QMenu {"
            "background: #ffffff;"
            "color: #111;"
            "border: 1px solid #d0d0d0;"
            "}"
            "QMenu::item:selected {"
            "background: #e6e6e6;"
            "}"
        )
        for base in self._variants.keys():
            action = menu.addAction(base)
            action.triggered.connect(lambda _checked=False, b=base: self._set_current_base(b))
        self.title_button.setMenu(menu)

    def _set_current_base(self, base: str, emit: bool = True) -> None:
        self._current_base = base
        self.version_combo.clear()
        entries = self._variants.get(base, [])
        for label, _path in entries:
            self.version_combo.addItem(label)
        self._update_combo_popup_width(entries)
        if emit:
            self._emit_selection_changed()

    def _update_combo_popup_width(self, entries: List[Tuple[str, Path]]) -> None:
        if not entries:
            self.version_combo.view().setMinimumWidth(self._thumb_size.width())
            return
        fm = self.version_combo.view().fontMetrics()
        max_text = max(fm.horizontalAdvance(label) for label, _path in entries)
        extra_padding = 15  # user-requested breathing room after the longest label
        popup_width = max(self.version_combo.width(), max_text + extra_padding)
        self.version_combo.view().setMinimumWidth(popup_width)
        self.version_combo.view().setMaximumWidth(popup_width)

    def _apply_selected_hip(self, selected_hip: Optional[Path]) -> bool:
        if selected_hip is None:
            return False
        for base, entries in self._variants.items():
            for label, path in entries:
                if path == selected_hip:
                    self._set_current_base(base, emit=False)
                    idx = self.version_combo.findText(label)
                    if idx >= 0:
                        self.version_combo.setCurrentIndex(idx)
                    self._emit_selection_changed()
                    return True
        return False

    def selected_hip(self) -> Optional[Path]:
        if not self._variants:
            return None
        base = self._current_base
        if base is None:
            return None
        entries = self._variants.get(base, [])
        if not entries:
            return None
        label = self.version_combo.currentText()
        for entry_label, path in entries:
            if entry_label == label:
                return path
        return entries[0][1]
