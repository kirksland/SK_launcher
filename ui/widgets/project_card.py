from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from core.fs import scene_file_label
from ui.utils.thumbnails import add_cloud_badge, build_thumbnail_pixmap
from ui.utils.styles import project_card_menu_style, project_card_title_style, project_card_version_combo_style


def group_scene_variants(scene_files: List[Path]) -> Dict[str, List[Tuple[str, Path]]]:
    pattern = re.compile(r"^(?P<base>.+)_(?P<ver>\d+)$")
    grouped: Dict[str, List[Tuple[str, Path]]] = {}
    for scene_file in scene_files:
        stem = scene_file.stem
        match = pattern.match(stem)
        if match:
            base = match.group("base")
            version_label = match.group("ver")
        else:
            base = stem
            version_label = "current"
        group_label = f"{base} [{scene_file_label(scene_file)}]"
        grouped.setdefault(group_label, []).append((version_label, scene_file))

    for group_label, entries in grouped.items():
        def sort_key(item: Tuple[str, Path]) -> Tuple[int, float]:
            version_label, path = item
            if version_label.isdigit():
                return (0, int(version_label))
            return (1, -path.stat().st_mtime)

        entries.sort(key=sort_key, reverse=True)
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))


class _SceneVersionCombo(QtWidgets.QComboBox):
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
        base_gutter = 26
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
        scene_files: List[Path],
        show_cloud_badge: bool = False,
        show_alert_badge: bool = False,
        selected_scene_file: Optional[Path] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project_path = project_path
        self._scene_files = scene_files
        self._variants = group_scene_variants(self._scene_files)
        self._current_group: Optional[str] = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 2)
        layout.setSpacing(2)

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

        self._alert_dot = QtWidgets.QFrame()
        self._alert_dot.setFixedSize(10, 10)
        self._alert_dot.setStyleSheet(
            "background: #e03b3b; border-radius: 5px; border: 1px solid #ffffff; margin: 4px;"
        )
        self._alert_dot.setVisible(show_alert_badge)
        thumb_layout.addWidget(
            self._alert_dot,
            0,
            0,
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
        )

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

        self.selected_scene_label = QtWidgets.QLabel("")
        self.selected_scene_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.selected_scene_label.setStyleSheet("color: #c6ccd6; font-size: 11px;")
        layout.addWidget(self.selected_scene_label, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.version_combo = _SceneVersionCombo()
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
            self.version_combo.setVisible(False)
            self._update_selected_scene_label()
        else:
            self._build_variant_menu()
            if not self._apply_selected_scene_file(selected_scene_file):
                first_group = next(iter(self._variants.keys()))
                self._set_current_group(first_group)
            self.version_combo.currentTextChanged.connect(self._emit_selection_changed)

    def set_alert_visible(self, visible: bool) -> None:
        self._alert_dot.setVisible(bool(visible))

    def _emit_selection_changed(self) -> None:
        self._update_selected_scene_label()
        scene_file = self.selected_scene_file()
        if scene_file is not None:
            self.selection_changed.emit(self)

    def _build_variant_menu(self) -> None:
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(project_card_menu_style())
        for group_label in self._variants.keys():
            action = menu.addAction(group_label)
            action.triggered.connect(lambda _checked=False, g=group_label: self._set_current_group(g))
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
        extra_padding = 30
        menu_width = max(self.title_button.width(), max_text + extra_padding)
        menu.setFixedWidth(menu_width)

    def _set_current_group(self, group_label: str, emit: bool = True) -> None:
        self._current_group = group_label
        self.version_combo.clear()
        entries = self._variants.get(group_label, [])
        for version_label, _path in entries:
            self.version_combo.addItem(version_label)
        self._update_selected_scene_label()
        if emit:
            self._emit_selection_changed()

    def _apply_selected_scene_file(self, selected_scene_file: Optional[Path]) -> bool:
        if selected_scene_file is None:
            return False
        for group_label, entries in self._variants.items():
            for version_label, path in entries:
                if path == selected_scene_file:
                    self._set_current_group(group_label, emit=False)
                    idx = self.version_combo.findText(version_label)
                    if idx >= 0:
                        self.version_combo.setCurrentIndex(idx)
                    self._emit_selection_changed()
                    return True
        return False

    def selected_scene_file(self) -> Optional[Path]:
        if not self._variants:
            return None
        group_label = self._current_group
        if group_label is None:
            return None
        entries = self._variants.get(group_label, [])
        if not entries:
            return None
        version_label = self.version_combo.currentText()
        for entry_version_label, path in entries:
            if entry_version_label == version_label:
                return path
        return entries[0][1]

    def selected_hip(self) -> Optional[Path]:
        scene_file = self.selected_scene_file()
        if scene_file is None or scene_file.suffix.lower() not in (".hip", ".hiplc", ".hipnc"):
            return None
        return scene_file

    def _update_selected_scene_label(self) -> None:
        scene_file = self.selected_scene_file()
        label = scene_file.stem if scene_file is not None else ""
        if self.selected_scene_label.text() != label:
            self.selected_scene_label.setText(label)
