from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from ui.utils.thumbnails import add_cloud_badge, build_thumbnail_pixmap
from ui.utils.styles import project_card_menu_style, project_card_title_style, project_card_version_combo_style


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


class _HipVersionCombo(QtWidgets.QComboBox):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._popup_padding = 15

    def set_popup_padding(self, padding: int) -> None:
        self._popup_padding = max(0, int(padding))

    def showPopup(self) -> None:  # type: ignore[override]
        super().showPopup()
        labels = [self.itemText(i) for i in range(self.count())]
        if not labels:
            return
        view = self.view()
        fm = view.fontMetrics()
        max_text = max(fm.horizontalAdvance(label) for label in labels)
        base_gutter = 26  # left padding + frame
        popup_width = max(self.width(), max_text + base_gutter + self._popup_padding)
        QtCore.QTimer.singleShot(0, lambda w=popup_width: self._apply_popup_width(w))

    def _apply_popup_width(self, width: int) -> None:
        view = self.view()
        popup = view.window()
        popup.setFixedWidth(width)
        view.setFixedWidth(width)


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
        self.title_button.setStyleSheet(project_card_title_style())
        thumb_layout.addWidget(
            self.title_button,
            0,
            0,
            QtCore.Qt.AlignmentFlag.AlignBottom,
        )

        layout.addWidget(thumb_container, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.version_combo = _HipVersionCombo()
        self.version_combo.setFixedWidth(86)
        self.version_combo.setStyleSheet(project_card_version_combo_style())
        self.version_combo.view().setMinimumWidth(86)
        self.version_combo.set_popup_padding(15)
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
        menu.setStyleSheet(project_card_menu_style())
        for base in self._variants.keys():
            action = menu.addAction(base)
            action.triggered.connect(lambda _checked=False, b=base: self._set_current_base(b))
        self.title_button.setMenu(menu)
        self._variant_menu = menu
        menu.aboutToShow.connect(self._update_variant_menu_width)

    def _update_variant_menu_width(self) -> None:
        menu = getattr(self, "_variant_menu", None)
        if menu is None:
            return
        labels = [a.text() for a in menu.actions()]
        if not labels:
            return
        fm = menu.fontMetrics()
        max_text = max(fm.horizontalAdvance(label) for label in labels)
        extra_padding = 30  # right breathing room after longest label
        menu_width = max(self.title_button.width(), max_text + extra_padding)
        menu.setFixedWidth(menu_width)

    def _set_current_base(self, base: str, emit: bool = True) -> None:
        self._current_base = base
        self.version_combo.clear()
        entries = self._variants.get(base, [])
        for label, _path in entries:
            self.version_combo.addItem(label)
        if emit:
            self._emit_selection_changed()

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
