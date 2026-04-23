from __future__ import annotations

from typing import Optional
import re
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from core.board_edit.panels import default_panel_state, tool_spec_for_panel

from ui.widgets.board_edit_panel import BoardEditControlsPanel, BoardEditPanel, BoardEditPreviewStack
from ui.widgets.board_groups_tree import BoardGroupsTree as _GroupsTree
from ui.widgets.board_timeline import BoardTimeline as _TimelineWidget
from ui.widgets.board_tool_stack_row import BoardToolStackRow as _ToolStackRow
from ui.widgets.board_view import BoardView


from ui.utils.styles import (
    PALETTE,
    border_only_style,
    muted_text_style,
    subtle_panel_frame_style,
    title_style,
    tree_panel_style,
)


class BoardPage(QtWidgets.QWidget):
    imageToolAddRequested = QtCore.Signal(str)
    imageToolRemoveRequested = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = None
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        layout.addLayout(header)

        title = QtWidgets.QLabel("Board")
        title.setStyleSheet(title_style())
        header.addWidget(title, 0)

        self.project_label = QtWidgets.QLabel("No project selected")
        self.project_label.setStyleSheet(muted_text_style())
        header.addWidget(self.project_label, 1)

        self.grid_toggle = QtWidgets.QToolButton()
        self.grid_toggle.setText("Grid")
        self.grid_toggle.setCheckable(True)
        self.grid_toggle.setChecked(True)
        self.grid_toggle.setAutoRaise(True)
        self.grid_toggle.setIcon(QtWidgets.QApplication.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView
        ))
        header.addWidget(self.grid_toggle, 0)

        self.groups_toggle = QtWidgets.QToolButton()
        self.groups_toggle.setText("Groups")
        self.groups_toggle.setCheckable(True)
        self.groups_toggle.setChecked(True)
        self.groups_toggle.setAutoRaise(True)
        header.addWidget(self.groups_toggle, 0)

        self.add_image_btn = QtWidgets.QPushButton("Add Image")
        header.addWidget(self.add_image_btn, 0)
        self.add_video_btn = QtWidgets.QPushButton("Add Video")
        header.addWidget(self.add_video_btn, 0)
        self.auto_layout_btn = QtWidgets.QPushButton("Auto Layout")
        header.addWidget(self.auto_layout_btn, 0)
        self.auto_layout_btn.setToolTip("Auto layout (Pinterest / masonry)")
        self.fit_btn = QtWidgets.QPushButton("Fit")
        header.addWidget(self.fit_btn, 0)
        self.save_btn = QtWidgets.QPushButton("Save")
        header.addWidget(self.save_btn, 0)
        self.load_btn = QtWidgets.QPushButton("Reload")
        header.addWidget(self.load_btn, 0)

        self.scene = QtWidgets.QGraphicsScene(self)
        self.scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)
        self.view = BoardView(self.scene, self)
        self.view.setStyleSheet(border_only_style())

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        self.groups_panel = QtWidgets.QFrame()
        self.groups_panel.setFixedWidth(220)
        self.groups_panel.setStyleSheet(subtle_panel_frame_style(bg_key="app_bg"))
        groups_layout = QtWidgets.QVBoxLayout(self.groups_panel)
        groups_layout.setContentsMargins(8, 8, 8, 8)
        groups_layout.setSpacing(6)
        groups_title = QtWidgets.QLabel("Groups")
        groups_title.setStyleSheet(f"color: {PALETTE['light_text']}; font-weight: bold;")
        groups_layout.addWidget(groups_title, 0)
        self.groups_tree = _GroupsTree()
        self.groups_tree.setHeaderHidden(True)
        self.groups_tree.setStyleSheet(tree_panel_style(bg_key="app_bg"))
        self.groups_tree.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.groups_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.groups_tree.customContextMenuRequested.connect(self._on_groups_tree_menu)
        groups_layout.addWidget(self.groups_tree, 1)

        splitter.addWidget(self.groups_panel)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(1, 1)

        self.loading_overlay = QtWidgets.QFrame(self.view)
        self.loading_overlay.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.loading_overlay.setStyleSheet(
            "QFrame {"
            "background: rgba(23, 26, 31, 220);"
            "border: 1px solid rgba(242, 193, 78, 70);"
            "border-radius: 14px;"
            "}"
            "QLabel { background: transparent; border: 0; }"
        )
        loading_layout = QtWidgets.QVBoxLayout(self.loading_overlay)
        loading_layout.setContentsMargins(18, 14, 18, 14)
        loading_layout.setSpacing(6)
        self.loading_title = QtWidgets.QLabel("Loading board")
        self.loading_title.setStyleSheet("color: #f2c14e; font-weight: 700; font-size: 14px;")
        loading_layout.addWidget(self.loading_title, 0)
        self.loading_detail = QtWidgets.QLabel("Preparing workspace...")
        self.loading_detail.setStyleSheet(muted_text_style())
        self.loading_detail.setWordWrap(True)
        loading_layout.addWidget(self.loading_detail, 0)
        self.loading_overlay.setFixedWidth(300)
        self.loading_overlay.hide()

        # Edit overlay (floating over the board view)
        self.edit_panel = BoardEditPanel(self)
        edit_layout = self.edit_panel.content_layout

        edit_header = QtWidgets.QHBoxLayout()
        edit_layout.addLayout(edit_header)
        self.edit_title = QtWidgets.QLabel("Edit Mode")
        self.edit_title.setStyleSheet(f"color: {PALETTE['light_text']}; font-weight: 600; font-size: 15px;")
        edit_header.addWidget(self.edit_title, 1)
        self.edit_close_btn = QtWidgets.QToolButton()
        self.edit_close_btn.setText("×")
        self.edit_close_btn.setAutoRaise(True)
        self.edit_close_btn.setStyleSheet(
            "QToolButton {"
            "padding: 2px 8px;"
            "border-radius: 6px;"
            "background: rgba(255,255,255,4);"
            "border: 1px solid rgba(255,255,255,10);"
            "color: #aeb6bf;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255,255,255,8);"
            "color: #d8dde5;"
            "}"
        )
        edit_header.addWidget(self.edit_close_btn, 0)

        self.edit_info = QtWidgets.QLabel("")
        self.edit_info.setStyleSheet(muted_text_style())
        self.edit_info.setWordWrap(True)
        edit_layout.addWidget(self.edit_info, 0)

        self.edit_tool_hint = QtWidgets.QLabel("")
        self.edit_tool_hint.setStyleSheet("color: #c2a25a; font-size: 11px;")
        self.edit_tool_hint.setVisible(False)
        edit_layout.addWidget(self.edit_tool_hint, 0)

        self.edit_controls = BoardEditControlsPanel()
        edit_layout.addWidget(self.edit_controls, 0)
        for attr_name in self.edit_controls.exported_attribute_names():
            setattr(self, attr_name, getattr(self.edit_controls, attr_name))
        self.edit_image_tool_list.currentRowChanged.connect(self._refresh_tool_stack_row_selection)

        self.set_image_adjust_controls_visible(False)

        # Preview stack (image / video / sequence)
        self.edit_preview = BoardEditPreviewStack()
        edit_layout.addWidget(self.edit_preview, 1)
        self.edit_preview_stack = self.edit_preview.stack
        self.edit_image_preview = self.edit_preview.image_preview
        self.edit_video_panel = self.edit_preview.video_panel
        self.edit_video_status = self.edit_preview.video_status
        self.edit_video_host = self.edit_preview.video_host
        self.edit_video_host_layout = self.edit_preview.video_host_layout
        self.edit_sequence_panel = self.edit_preview.sequence_panel
        self.edit_sequence_label = self.edit_preview.sequence_label
        self.edit_sequence_preview = self.edit_preview.sequence_preview
        self.edit_sequence_timeline = self.edit_preview.sequence_timeline
        self.edit_sequence_frame_label = self.edit_preview.sequence_frame_label

        self.edit_list = QtWidgets.QListWidget()
        self.edit_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.edit_list.setVisible(False)
        edit_layout.addWidget(self.edit_list, 0)

        self.edit_footer = QtWidgets.QLabel("")
        self.edit_footer.setStyleSheet(muted_text_style())
        self.edit_footer.setWordWrap(True)
        edit_layout.addWidget(self.edit_footer, 0)

        self.edit_panel.setVisible(False)
        self.edit_panel.raise_()

        self.focus_exit_btn = QtWidgets.QToolButton(self)
        self.focus_exit_btn.setText("Exit Focus")
        self.focus_exit_btn.setVisible(False)
        self.focus_exit_btn.setAutoRaise(True)
        self.focus_exit_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.focus_exit_btn.setStyleSheet(
            "QToolButton {"
            "background: rgba(24, 28, 34, 228);"
            "border: 1px solid rgba(255,255,255,26);"
            "border-radius: 12px;"
            "padding: 8px 12px;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255,255,255,14);"
            "}"
        )
        exit_shadow = QtWidgets.QGraphicsDropShadowEffect(self.focus_exit_btn)
        exit_shadow.setBlurRadius(26)
        exit_shadow.setOffset(0, 8)
        exit_shadow.setColor(QtGui.QColor(0, 0, 0, 120))
        self.focus_exit_btn.setGraphicsEffect(exit_shadow)
        self.focus_exit_btn.clicked.connect(self._on_exit_focus)

        self.grid_toggle.toggled.connect(self.view.set_show_grid)
        self.groups_toggle.toggled.connect(self.groups_panel.setVisible)
        self.edit_close_btn.clicked.connect(lambda: self.set_edit_panel_visible(False))
        self.edit_image_tool_add_btn.clicked.connect(
            lambda: self.show_tool_add_menu(
                self.edit_image_tool_add_btn.mapToGlobal(
                    QtCore.QPoint(0, self.edit_image_tool_add_btn.height())
                )
            )
        )

        self._bind_slider_to_input(self.edit_exr_gamma_slider, self.edit_exr_gamma_input, 10.0)
        self._bind_slider_to_input(self.edit_image_adjust_brightness_slider, self.edit_image_adjust_brightness_value, 100.0)
        self._bind_slider_to_input(self.edit_image_adjust_contrast_slider, self.edit_image_adjust_contrast_value, 100.0)
        self._bind_slider_to_input(self.edit_image_adjust_saturation_slider, self.edit_image_adjust_saturation_value, 100.0)
        self._bind_slider_to_input(self.edit_image_vibrance_slider, self.edit_image_vibrance_value, 100.0)
        self._bind_slider_to_input(self.edit_crop_left_slider, self.edit_crop_left_value, 1.0)
        self._bind_slider_to_input(self.edit_crop_right_slider, self.edit_crop_right_value, 1.0)
        self._bind_slider_to_input(self.edit_crop_top_slider, self.edit_crop_top_value, 1.0)
        self._bind_slider_to_input(self.edit_crop_bottom_slider, self.edit_crop_bottom_value, 1.0)

        self._undo_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Undo, self)
        self._undo_shortcut.activated.connect(self._on_undo)
        self._redo_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Redo, self)
        self._redo_shortcut.activated.connect(self._on_redo)
        self._exit_focus_shortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self._exit_focus_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self._exit_focus_shortcut.activated.connect(self._on_exit_focus)
        self._tool_add_shortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Tab), self.view)
        self._tool_add_shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._tool_add_shortcut.activated.connect(lambda: self.show_tool_add_menu(QtGui.QCursor.pos()))

        footer = QtWidgets.QHBoxLayout()
        layout.addLayout(footer)
        self.hint_label = QtWidgets.QLabel(
            "Tip: Right-click for add/group, drag items, wheel to zoom, Ctrl+drag to scale, middle mouse to pan, Del to remove."
        )
        self.hint_label.setStyleSheet(muted_text_style())
        footer.addWidget(self.hint_label, 1)

        # Bottom timeline bar (for focus mode video editing)
        self.edit_timeline_bar = QtWidgets.QFrame()
        self.edit_timeline_bar.setStyleSheet(subtle_panel_frame_style(bg_key="app_bg"))
        self.edit_timeline_bar.setVisible(False)
        timeline_layout = QtWidgets.QVBoxLayout(self.edit_timeline_bar)
        timeline_layout.setContentsMargins(10, 6, 10, 6)
        timeline_layout.setSpacing(6)
        timeline_title = QtWidgets.QLabel("Timeline")
        timeline_title.setStyleSheet(muted_text_style())
        timeline_layout.addWidget(timeline_title, 0)
        self.edit_timeline = _TimelineWidget()
        timeline_layout.addWidget(self.edit_timeline, 0)
        timeline_actions = QtWidgets.QHBoxLayout()
        self.edit_timeline_play_btn = QtWidgets.QPushButton("Play")
        self.edit_timeline_frame_label = QtWidgets.QLabel("Frame: 0")
        self.edit_timeline_frame_label.setStyleSheet(muted_text_style())
        self.edit_timeline_split_btn = QtWidgets.QPushButton("Split")
        self.edit_timeline_export_btn = QtWidgets.QPushButton("Export Segment")
        timeline_actions.addWidget(self.edit_timeline_play_btn, 0)
        timeline_actions.addWidget(self.edit_timeline_frame_label, 0)
        timeline_actions.addWidget(self.edit_timeline_split_btn, 0)
        timeline_actions.addWidget(self.edit_timeline_export_btn, 0)
        timeline_actions.addStretch(1)
        timeline_layout.addLayout(timeline_actions, 0)
        layout.insertWidget(layout.count() - 1, self.edit_timeline_bar, 0)
        self._position_edit_overlay()

    def set_edit_panel_visible(self, visible: bool) -> None:
        self.edit_panel.setVisible(bool(visible))
        self.focus_exit_btn.setVisible(bool(visible))
        if visible:
            self._position_edit_overlay()
            self.edit_panel.raise_()
            self.focus_exit_btn.raise_()

    def _position_edit_overlay(self) -> None:
        if self.edit_panel is None:
            return
        viewport = self.view.viewport()
        top_left = viewport.mapTo(self, QtCore.QPoint(0, 0))
        anchor = QtCore.QRect(top_left, viewport.size())
        inset = 14
        panel_w = min(self.edit_panel.maximumWidth(), max(self.edit_panel.minimumWidth(), 344))
        panel_w = min(panel_w, max(260, anchor.width() - (inset * 2)))
        available_h = max(220, anchor.height() - (inset * 2))
        panel_h = min(available_h, 620)
        x = anchor.right() - panel_w - inset
        y = anchor.top() + inset
        self.edit_panel.setGeometry(x, y, panel_w, panel_h)
        self.focus_exit_btn.adjustSize()
        btn_x = anchor.left() + inset
        btn_y = anchor.top() + inset
        self.focus_exit_btn.move(btn_x, btn_y)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._position_edit_overlay()
        self._position_loading_overlay()

    def set_loading_overlay(self, visible: bool, detail: str = "Preparing workspace...") -> None:
        self.loading_detail.setText(detail)
        self.loading_overlay.setVisible(bool(visible))
        self._position_loading_overlay()
        if visible:
            self.loading_overlay.raise_()

    def _position_loading_overlay(self) -> None:
        if not hasattr(self, "loading_overlay"):
            return
        width = self.loading_overlay.width()
        height = max(84, self.loading_overlay.sizeHint().height())
        self.loading_overlay.resize(width, height)
        x = max(18, (self.view.width() - width) // 2)
        self.loading_overlay.move(x, 18)

    def show_tool_add_menu(self, global_pos: QtCore.QPoint) -> bool:
        if not self.edit_panel.isVisible():
            return False
        if not self.edit_tool_stack_section.isVisible():
            return False
        if self.edit_image_tool_add_combo.count() <= 0:
            return False
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(
            "QMenu {"
            "background: rgba(24, 28, 34, 245);"
            "color: #d8dde5;"
            "border: 1px solid rgba(255,255,255,26);"
            "padding: 8px;"
            "border-radius: 12px;"
            "}"
            "QMenu::item {"
            "padding: 8px 28px 8px 12px;"
            "border-radius: 8px;"
            "margin: 2px 0;"
            "}"
            "QMenu::item:selected {"
            "background: rgba(242,193,78,38);"
            "}"
        )
        for idx in range(self.edit_image_tool_add_combo.count()):
            label = self.edit_image_tool_add_combo.itemText(idx)
            tool_id = self.edit_image_tool_add_combo.itemData(idx)
            action = menu.addAction(f"Add {label}")
            action.setData(tool_id)
        chosen = menu.exec(global_pos)
        if chosen is not None:
            tool_id = chosen.data()
            idx = self.edit_image_tool_add_combo.findData(tool_id)
            if idx >= 0:
                self.edit_image_tool_add_combo.setCurrentIndex(idx)
                self.imageToolAddRequested.emit(str(tool_id))
        return True

    def set_edit_preview_visible(self, visible: bool) -> None:
        self.edit_preview_stack.setVisible(bool(visible))

    def set_timeline_bar_visible(self, visible: bool) -> None:
        self.edit_timeline_bar.setVisible(bool(visible))

    def set_edit_panel_content(
        self,
        title: str,
        info_lines: list[str],
        list_items: Optional[list[str]] = None,
        footer: str = "",
    ) -> None:
        self.edit_title.setText(title)
        self.edit_info.setText("\n".join([line for line in info_lines if line]))
        self.edit_info.setVisible(bool(self.edit_info.text().strip()))
        self.edit_list.clear()
        if list_items:
            self.edit_list.addItems(list_items)
            self.edit_list.setVisible(True)
        else:
            self.edit_list.setVisible(False)
        self.edit_footer.setText(footer)
        self.edit_footer.setVisible(bool(str(footer).strip()))
        self.set_edit_panel_visible(True)

    def set_exr_channels(self, channels: list[object]) -> None:
        self.edit_exr_channel_combo.blockSignals(True)
        self.edit_exr_channel_combo.clear()
        for entry in channels:
            if isinstance(entry, tuple) and len(entry) == 2:
                label, value = entry
                self.edit_exr_channel_combo.addItem(str(label), value)
            else:
                self.edit_exr_channel_combo.addItem(str(entry), str(entry))
        self.edit_exr_channel_combo.blockSignals(False)
        self.edit_exr_channel_row.setEnabled(bool(channels))
        self.edit_exr_channel_label.setVisible(True)
        self.edit_exr_channel_combo.setVisible(True)

    def current_exr_channel_value(self) -> str:
        data = self.edit_exr_channel_combo.currentData()
        if isinstance(data, str):
            return data
        return self.edit_exr_channel_combo.currentText()

    def set_exr_channel_row_visible(self, visible: bool) -> None:
        self.edit_exr_channel_label.setVisible(bool(visible))
        self.edit_exr_channel_combo.setVisible(bool(visible))
        self.edit_exr_channel_row.setEnabled(bool(visible))

        self.edit_exr_srgb_check.setVisible(bool(visible))
        self.edit_exr_gamma_label.setVisible(bool(visible))
        self.edit_exr_gamma_slider.setVisible(bool(visible))
        self.edit_exr_gamma_input.setVisible(bool(visible))

    def current_exr_gamma(self) -> float:
        return float(self.edit_exr_gamma_slider.value()) / 10.0

    def current_exr_srgb_enabled(self) -> bool:
        return bool(self.edit_exr_srgb_check.isChecked())

    def set_exr_gamma_label(self, gamma: float) -> None:
        self.edit_exr_gamma_label.setText(f"Gamma: {gamma:.1f}")
        self._set_spinbox_value(self.edit_exr_gamma_input, gamma)

    def _set_spinbox_value(self, spinbox: QtWidgets.QDoubleSpinBox, value: float) -> None:
        spinbox.blockSignals(True)
        spinbox.setValue(float(value))
        spinbox.blockSignals(False)

    def _set_slider_value(self, slider: QtWidgets.QSlider, value: float) -> None:
        target = int(round(float(value)))
        if slider.value() != target:
            slider.setValue(target)

    def _bind_slider_to_input(
        self,
        slider: QtWidgets.QSlider,
        spinbox: QtWidgets.QDoubleSpinBox,
        scale: float,
    ) -> None:
        factor = float(scale) if abs(float(scale)) > 1e-9 else 1.0
        slider.valueChanged.connect(
            lambda raw_value, current_spinbox=spinbox, current_factor=factor: self._set_spinbox_value(
                current_spinbox,
                float(raw_value) / current_factor,
            )
        )
        spinbox.valueChanged.connect(
            lambda raw_value, current_slider=slider, current_factor=factor: self._set_slider_value(
                current_slider,
                float(raw_value) * current_factor,
            )
        )

    def set_image_adjust_controls_visible(self, visible: bool) -> None:
        controls = [
            self.edit_tool_stack_section,
            self.edit_image_tools_label,
            self.edit_image_tool_empty,
            self.edit_image_tool_list,
            self.edit_image_tool_add_btn,
            self.edit_image_tool_up_btn,
            self.edit_image_tool_down_btn,
            self.edit_image_adjust_label,
            self.edit_image_adjust_brightness_title,
            self.edit_image_adjust_brightness_slider,
            self.edit_image_adjust_brightness_value,
            self.edit_image_adjust_contrast_title,
            self.edit_image_adjust_contrast_slider,
            self.edit_image_adjust_contrast_value,
            self.edit_image_adjust_saturation_title,
            self.edit_image_adjust_saturation_slider,
            self.edit_image_adjust_saturation_value,
            self.edit_image_vibrance_title,
            self.edit_image_vibrance_slider,
            self.edit_image_vibrance_value,
            self.edit_crop_label,
            self.edit_crop_left_title,
            self.edit_crop_left_slider,
            self.edit_crop_left_value,
            self.edit_crop_right_title,
            self.edit_crop_right_slider,
            self.edit_crop_right_value,
            self.edit_crop_top_title,
            self.edit_crop_top_slider,
            self.edit_crop_top_value,
            self.edit_crop_bottom_title,
            self.edit_crop_bottom_slider,
            self.edit_crop_bottom_value,
            self.edit_image_adjust_reset_btn,
        ]
        for widget in controls:
            widget.setVisible(bool(visible))
        self.edit_image_tool_add_combo.setVisible(False)
        if visible:
            self.set_active_image_tool_panel("")

    def _image_tool_panel_widgets(self) -> dict[str, list[QtWidgets.QWidget]]:
        return self.edit_controls.panel_widgets()

    def set_image_tool_panel_visible(self, panel: str, visible: bool) -> None:
        self.edit_controls.set_tool_panel_visible(panel, visible)

    def set_active_image_tool_panel(self, panel: str) -> None:
        self.edit_controls.set_active_tool_panel(panel)

    def current_image_brightness(self) -> float:
        return float(self.edit_image_adjust_brightness_slider.value()) / 100.0

    def current_image_contrast(self) -> float:
        return float(self.edit_image_adjust_contrast_slider.value()) / 100.0

    def current_image_saturation(self) -> float:
        return float(self.edit_image_adjust_saturation_slider.value()) / 100.0

    def set_image_adjust_labels(self, brightness: float, contrast: float, saturation: float) -> None:
        self._set_spinbox_value(self.edit_image_adjust_brightness_value, brightness)
        self._set_spinbox_value(self.edit_image_adjust_contrast_value, contrast)
        self._set_spinbox_value(self.edit_image_adjust_saturation_value, saturation)

    def set_image_vibrance_value(self, amount: float) -> None:
        self.edit_image_vibrance_slider.blockSignals(True)
        self.edit_image_vibrance_slider.setValue(int(round(float(amount) * 100.0)))
        self.edit_image_vibrance_slider.blockSignals(False)
        self._set_spinbox_value(self.edit_image_vibrance_value, float(amount))

    def current_image_vibrance(self) -> float:
        return float(self.edit_image_vibrance_slider.value()) / 100.0

    def set_image_vibrance_visible(self, visible: bool) -> None:
        self.set_image_tool_panel_visible("vibrance", visible)

    def set_image_crop_visible(self, visible: bool) -> None:
        self.set_image_tool_panel_visible("crop", visible)

    def set_image_crop_values(self, left: float, top: float, right: float, bottom: float) -> None:
        self.edit_crop_left_slider.blockSignals(True)
        self.edit_crop_top_slider.blockSignals(True)
        self.edit_crop_right_slider.blockSignals(True)
        self.edit_crop_bottom_slider.blockSignals(True)
        self.edit_crop_left_slider.setValue(int(round(float(left) * 100.0)))
        self.edit_crop_top_slider.setValue(int(round(float(top) * 100.0)))
        self.edit_crop_right_slider.setValue(int(round(float(right) * 100.0)))
        self.edit_crop_bottom_slider.setValue(int(round(float(bottom) * 100.0)))
        self.edit_crop_left_slider.blockSignals(False)
        self.edit_crop_top_slider.blockSignals(False)
        self.edit_crop_right_slider.blockSignals(False)
        self.edit_crop_bottom_slider.blockSignals(False)
        self._set_spinbox_value(self.edit_crop_left_value, int(round(float(left) * 100.0)))
        self._set_spinbox_value(self.edit_crop_top_value, int(round(float(top) * 100.0)))
        self._set_spinbox_value(self.edit_crop_right_value, int(round(float(right) * 100.0)))
        self._set_spinbox_value(self.edit_crop_bottom_value, int(round(float(bottom) * 100.0)))

    def current_image_crop_settings(self) -> tuple[float, float, float, float]:
        return (
            float(self.edit_crop_left_slider.value()) / 100.0,
            float(self.edit_crop_top_slider.value()) / 100.0,
            float(self.edit_crop_right_slider.value()) / 100.0,
            float(self.edit_crop_bottom_slider.value()) / 100.0,
        )

    def set_image_bcs_controls_visible(self, visible: bool) -> None:
        self.set_image_tool_panel_visible("bcs", visible)

    def set_image_tool_add_options(self, options: list[tuple[str, str]]) -> None:
        self.edit_image_tool_add_combo.blockSignals(True)
        self.edit_image_tool_add_combo.clear()
        for label, tool_id in options:
            self.edit_image_tool_add_combo.addItem(str(label), str(tool_id))
        self.edit_image_tool_add_combo.blockSignals(False)

    def current_image_tool_add_id(self) -> str:
        data = self.edit_image_tool_add_combo.currentData()
        return str(data) if data is not None else ""

    def set_image_tool_stack_items(self, items: list[tuple[str, bool]], selected_index: int = -1) -> None:
        self.edit_image_tool_list.blockSignals(True)
        self.edit_image_tool_list.clear()
        for idx, (label, enabled) in enumerate(items):
            item = QtWidgets.QListWidgetItem()
            item.setSizeHint(QtCore.QSize(0, 32))
            self.edit_image_tool_list.addItem(item)
            row = _ToolStackRow(label, muted=not enabled)
            row.removeRequested.connect(lambda _checked=False, row_idx=idx: self.imageToolRemoveRequested.emit(row_idx))
            self.edit_image_tool_list.setItemWidget(item, row)
        has_items = bool(items)
        self.edit_image_tool_list.setVisible(has_items)
        self.edit_image_tool_empty.setVisible(not has_items and self.edit_image_tools_label.isVisible())
        if items and selected_index >= 0 and selected_index < len(items):
            self.edit_image_tool_list.setCurrentRow(int(selected_index))
        elif items:
            self.edit_image_tool_list.setCurrentRow(0)
        row_h = 38
        visible_rows = max(1, min(3, len(items)))
        frame = 6
        self.edit_image_tool_list.setMaximumHeight(frame + (row_h * visible_rows))
        can_reorder = len(items) > 1
        self.edit_image_tool_up_btn.setVisible(can_reorder)
        self.edit_image_tool_down_btn.setVisible(can_reorder)
        self.edit_image_tool_list.blockSignals(False)
        self._refresh_tool_stack_row_selection(self.edit_image_tool_list.currentRow())

    def current_image_tool_stack_index(self) -> int:
        return int(self.edit_image_tool_list.currentRow())

    def _refresh_tool_stack_row_selection(self, current_row: int) -> None:
        for idx in range(self.edit_image_tool_list.count()):
            item = self.edit_image_tool_list.item(idx)
            row = self.edit_image_tool_list.itemWidget(item)
            if isinstance(row, _ToolStackRow):
                row.set_selected(idx == int(current_row))

    def set_image_adjust_values(self, brightness: float, contrast: float, saturation: float) -> None:
        self.edit_image_adjust_brightness_slider.blockSignals(True)
        self.edit_image_adjust_contrast_slider.blockSignals(True)
        self.edit_image_adjust_saturation_slider.blockSignals(True)
        self.edit_image_adjust_brightness_slider.setValue(int(round(float(brightness) * 100.0)))
        self.edit_image_adjust_contrast_slider.setValue(int(round(float(contrast) * 100.0)))
        self.edit_image_adjust_saturation_slider.setValue(int(round(float(saturation) * 100.0)))
        self.edit_image_adjust_brightness_slider.blockSignals(False)
        self.edit_image_adjust_contrast_slider.blockSignals(False)
        self.edit_image_adjust_saturation_slider.blockSignals(False)
        self.set_image_adjust_labels(brightness, contrast, saturation)

    def current_image_tool_panel_state(self, panel: str) -> dict[str, float]:
        key = str(panel or "").strip().lower()
        spec = tool_spec_for_panel(key)
        if spec is None:
            return {}
        values: dict[str, float] = {}
        for control in getattr(spec, "ui_controls", ()):
            control_key = str(getattr(control, "key", "") or "").strip()
            if not control_key:
                continue
            current = self._current_image_tool_control_value(control_key)
            if current is not None:
                values[control_key] = current
        return values

    def set_image_tool_panel_state(self, panel: str, state: dict[str, object]) -> None:
        key = str(panel or "").strip().lower()
        values = dict(state) if isinstance(state, dict) else {}
        spec = tool_spec_for_panel(key)
        if spec is None:
            return
        merged = default_panel_state(str(getattr(spec, "id", "") or key))
        merged.update(values)
        for control in getattr(spec, "ui_controls", ()):
            control_key = str(getattr(control, "key", "") or "").strip()
            if not control_key:
                continue
            self._set_image_tool_control_value(control_key, merged.get(control_key, getattr(control, "minimum", 0.0)))

    def _current_image_tool_control_value(self, control_key: str) -> float | None:
        return self.edit_controls.current_control_value(control_key)

    def image_tool_control_slider(self, control_key: str) -> QtWidgets.QSlider | None:
        return self.edit_controls.control_slider(control_key)

    def _set_image_tool_control_value(self, control_key: str, value: object) -> None:
        self.edit_controls.set_control_value(control_key, value)

    def show_edit_preview_image(self, pixmap: QtGui.QPixmap, label: str = "") -> None:
        self.edit_preview_stack.setCurrentWidget(self.edit_image_preview)
        if label:
            self.edit_footer.setText(label)
        self.edit_image_preview.set_base_pixmap(pixmap)

    def show_edit_preview_video(self) -> None:
        self.edit_preview_stack.setCurrentWidget(self.edit_video_panel)

    def show_edit_preview_sequence(self, pixmap: QtGui.QPixmap, label: str = "") -> None:
        self.edit_preview_stack.setCurrentWidget(self.edit_sequence_panel)
        if label:
            self.edit_sequence_label.setText(label)
        self.edit_sequence_preview.set_base_pixmap(pixmap)

    def handle_external_drop(self, event: QtGui.QDropEvent) -> None:
        controller = self._controller
        if controller is None:
            print("[BOARD] No board_controller on parent")
            return
        pos = None
        if hasattr(event, "position"):
            try:
                pos = event.position().toPoint()  # type: ignore[attr-defined]
            except Exception:
                pos = None
        if pos is None:
            try:
                pos = event.pos()  # type: ignore[attr-defined]
            except Exception:
                pos = None
        scene_pos = self.view.mapToScene(pos) if pos is not None else None
        print(f"[BOARD] Drop received. URLs: {len(event.mimeData().urls())} pos={pos} scene={scene_pos}")
        handled = False
        for url in event.mimeData().urls():
            local_path = Path(url.toLocalFile())
            print(f"[BOARD] URL -> {local_path}")
            if local_path.is_file():
                item = None
                if hasattr(controller, "_is_video_file") and controller._is_video_file(local_path):
                    if hasattr(controller, "add_video_from_path"):
                        item = controller.add_video_from_path(local_path, scene_pos=scene_pos)
                elif hasattr(controller, "_is_image_file") and controller._is_image_file(local_path):
                    item = controller.add_image_from_path(local_path, scene_pos=scene_pos)
                elif hasattr(controller, "_is_pic_file") and controller._is_pic_file(local_path):
                    if hasattr(controller, "convert_picnc_interactive"):
                        controller.convert_picnc_interactive(local_path)
                if item is not None:
                    controller.try_add_item_to_group(item, scene_pos)
                    handled = True
            else:
                if local_path.exists() and local_path.is_dir():
                    if hasattr(controller, "add_sequence_from_dir"):
                        item = controller.add_sequence_from_dir(local_path, scene_pos=scene_pos)
                        if item is not None:
                            controller.try_add_item_to_group(item, scene_pos)
                            handled = True
                    else:
                        print(f"[BOARD] Drop is a directory, ignored: {local_path}")
                    continue
                if url.isValid() and url.scheme().lower().startswith("http"):
                    controller.add_image_from_url(str(url.toString()), scene_pos=scene_pos)
                    handled = True
                else:
                    print(f"[BOARD] Missing path: {local_path}")
        if not handled and event.mimeData().hasImage():
            controller.add_image_from_image_data(event.mimeData().imageData(), scene_pos=scene_pos)
            handled = True
        if not handled and event.mimeData().hasHtml():
            html = event.mimeData().html()
            match = re.search(r'src=["\'](https?://[^"\']+)["\']', html)
            if match:
                controller.add_image_from_url(match.group(1), scene_pos=scene_pos)
                handled = True
        if not handled and event.mimeData().hasText():
            text = event.mimeData().text().strip()
            if text.lower().startswith("http"):
                controller.add_image_from_url(text, scene_pos=scene_pos)

    def set_controller(self, controller) -> None:
        self._controller = controller

    def _on_groups_tree_menu(self, pos: QtCore.QPoint) -> None:
        if self._controller is not None and hasattr(self._controller, "show_groups_tree_context_menu"):
            handled = self._controller.show_groups_tree_context_menu(pos)
            if handled:
                return
        item = self.groups_tree.itemAt(pos)
        if item is None:
            return
        info = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        menu = QtWidgets.QMenu(self.groups_tree)
        add_to_group = None
        remove_from_group = None
        ungroup = None
        if isinstance(info, tuple) and info:
            kind = info[0]
            if kind == "group":
                add_to_group = menu.addAction("Add Selected To Group")
                ungroup = menu.addAction("Ungroup")
            elif kind in ("image", "note"):
                remove_from_group = menu.addAction("Remove From Group")
        action = menu.exec(self.groups_tree.mapToGlobal(pos))
        controller = self._controller
        if controller is None:
            return
        if action == add_to_group and hasattr(controller, "add_selected_to_group"):
            controller.add_selected_to_group(info[1])
        elif action == remove_from_group and hasattr(controller, "remove_selected_from_groups"):
            controller.remove_selected_from_groups()
        elif action == ungroup and hasattr(controller, "ungroup_selected"):
            controller.ungroup_selected()

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            print("[BOARD] dragEnter")
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            print("[BOARD] dragMove")
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            print("[BOARD] dropEvent")
            self.handle_external_drop(event)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _on_undo(self) -> None:
        if self._controller is not None and hasattr(self._controller, "undo"):
            self._controller.undo()

    def _on_redo(self) -> None:
        if self._controller is not None and hasattr(self._controller, "redo"):
            self._controller.redo()

    def _on_exit_focus(self) -> None:
        if self._controller is not None and hasattr(self._controller, "exit_focus_mode"):
            self._controller.exit_focus_mode()

