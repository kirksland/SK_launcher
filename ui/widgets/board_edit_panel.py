from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

from tools.board_tools.edit import ToolUiControlSpec, get_edit_tool, list_edit_tools
from ui.utils.styles import muted_text_style
from ui.widgets.board_timeline import BoardTimeline
from video.player import VideoPreviewLabel


class BoardEditPanel(QtWidgets.QFrame):
    """Floating edit panel chrome used by the board page."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(320)
        self.setMaximumWidth(380)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.setStyleSheet(
            "QFrame {"
            "background: rgba(23, 26, 31, 238);"
            "border: 1px solid rgba(255,255,255,20);"
            "border-radius: 12px;"
            "}"
            "QLabel { background: transparent; }"
            "QPushButton, QToolButton, QComboBox {"
            "background: rgba(255,255,255,5);"
            "border: 1px solid rgba(255,255,255,12);"
            "border-radius: 6px;"
            "padding: 5px 9px;"
            "}"
            "QPushButton:hover, QToolButton:hover, QComboBox:hover {"
            "background: rgba(255,255,255,9);"
            "}"
            "QAbstractSpinBox {"
            "background: rgba(16, 19, 24, 220);"
            "border: 1px solid rgba(255,255,255,12);"
            "border-radius: 6px;"
            "padding: 4px 8px;"
            "selection-background-color: rgba(242,193,78,36);"
            "}"
            "QListWidget {"
            "background: rgba(255,255,255,3);"
            "border: 1px solid rgba(255,255,255,10);"
            "border-radius: 8px;"
            "padding: 6px;"
            "outline: none;"
            "}"
            "QListWidget::item {"
            "background: rgba(255,255,255,4);"
            "border: 1px solid rgba(255,255,255,10);"
            "border-radius: 7px;"
            "padding: 8px 10px;"
            "margin: 2px 0;"
            "}"
            "QListWidget::item:selected {"
            "background: rgba(255,255,255,8);"
            "border: 1px solid rgba(242,193,78,70);"
            "}"
            "QSlider::groove:horizontal {"
            "height: 4px;"
            "background: rgba(255,255,255,12);"
            "border-radius: 2px;"
            "}"
            "QSlider::handle:horizontal {"
            "background: #c7ccd3;"
            "border: 1px solid rgba(12,15,20,110);"
            "width: 12px;"
            "margin: -5px 0;"
            "border-radius: 6px;"
            "}"
        )

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 14)
        shadow.setColor(QtGui.QColor(0, 0, 0, 150))
        self.setGraphicsEffect(shadow)

        self.content_layout = QtWidgets.QVBoxLayout(self)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self.content_layout.setSpacing(8)


@dataclass(slots=True)
class ToolControlRow:
    spec: ToolUiControlSpec
    widget: QtWidgets.QWidget
    title: QtWidgets.QLabel
    slider: QtWidgets.QSlider
    spinbox: QtWidgets.QDoubleSpinBox

    @property
    def key(self) -> str:
        return str(self.spec.key or "").strip().lower()

    @property
    def scale(self) -> float:
        scale = float(getattr(self.spec, "display_scale", 1.0) or 1.0)
        if abs(scale - 1.0) > 1e-6:
            return scale
        decimals = int(getattr(self.spec, "display_decimals", 2))
        return float(10 ** max(0, decimals))

    @property
    def has_display_suffix(self) -> bool:
        return bool(str(getattr(self.spec, "display_suffix", "") or ""))

    def current_value(self) -> float:
        return float(self.slider.value()) / self.scale

    def set_value(self, value: object) -> None:
        try:
            numeric = float(value)
        except Exception:
            numeric = float(getattr(self.spec, "minimum", 0.0))
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(numeric * self.scale)))
        self.slider.blockSignals(False)
        display_value = numeric * self.scale if self.has_display_suffix else numeric
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(float(display_value))
        self.spinbox.blockSignals(False)

    def bind_spinbox(self) -> None:
        def on_slider_changed(value: int) -> None:
            numeric = float(value) / self.scale
            display_value = numeric * self.scale if self.has_display_suffix else numeric
            self.spinbox.blockSignals(True)
            self.spinbox.setValue(float(display_value))
            self.spinbox.blockSignals(False)

        def on_spinbox_changed(value: float) -> None:
            numeric = float(value) / self.scale if self.has_display_suffix else float(value)
            self.slider.blockSignals(True)
            self.slider.setValue(int(round(numeric * self.scale)))
            self.slider.blockSignals(False)

        self.slider.valueChanged.connect(on_slider_changed)
        self.spinbox.valueChanged.connect(on_spinbox_changed)


class BoardEditControlsPanel(QtWidgets.QWidget):
    """Tool stack and edit controls used by the floating edit panel."""

    toolRemoveRequested = QtCore.Signal(str)
    toolResetRequested = QtCore.Signal(str)
    toolMoveRequested = QtCore.Signal(str, int)
    toolSettingsChanged = QtCore.Signal(str)
    toolSelected = QtCore.Signal(str)

    EXPORTED_ATTRS = (
        "edit_exr_channel_row",
        "edit_exr_channel_label",
        "edit_exr_channel_combo",
        "edit_exr_gamma_row",
        "edit_exr_srgb_check",
        "edit_exr_gamma_label",
        "edit_exr_gamma_slider",
        "edit_exr_gamma_input",
        "edit_tool_stack_section",
        "edit_tool_stack_layout",
        "edit_image_tools_header",
        "edit_image_tools_label",
        "edit_image_tool_add_btn",
        "edit_image_tool_empty",
        "edit_image_tool_list",
        "edit_image_tool_add_row",
        "edit_image_tool_add_combo",
        "edit_image_tool_order_row",
        "edit_image_tool_up_btn",
        "edit_image_tool_down_btn",
        "edit_tool_settings_section",
        "edit_tool_settings_title",
        "edit_tool_settings_reset_btn",
        "edit_tool_settings_remove_btn",
        "edit_tool_settings_content",
        "edit_tool_settings_layout",
        "edit_tool_settings_scroll",
        "edit_image_adjust_reset_btn",
    )

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self._panel_widgets: dict[str, list[QtWidgets.QWidget]] = {}
        self._panel_cards: dict[str, QtWidgets.QFrame] = {}
        self._panel_titles: dict[str, QtWidgets.QLabel] = {}
        self._control_rows: dict[str, list[ToolControlRow]] = {}
        self._instance_cards: dict[str, QtWidgets.QFrame] = {}
        self._instance_rows: dict[str, dict[str, ToolControlRow]] = {}
        self._instance_tool_ids: dict[str, str] = {}
        self._instance_order: list[str] = []
        self._selected_instance_id = ""
        self._drag_start_pos: QtCore.QPoint | None = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._build_exr_controls(layout)
        self._build_tool_stack_controls(layout)
        self._build_tool_settings_controls(layout)
        self._build_tool_panels()

    def exported_attribute_names(self) -> tuple[str, ...]:
        return self.EXPORTED_ATTRS

    def _build_exr_controls(self, layout: QtWidgets.QVBoxLayout) -> None:
        self.edit_exr_channel_row = QtWidgets.QHBoxLayout()
        self.edit_exr_channel_label = QtWidgets.QLabel("Channel")
        self.edit_exr_channel_label.setStyleSheet(muted_text_style())
        self.edit_exr_channel_combo = QtWidgets.QComboBox()
        self.edit_exr_channel_combo.setMinimumWidth(120)
        self.edit_exr_channel_row.addWidget(self.edit_exr_channel_label, 0)
        self.edit_exr_channel_row.addWidget(self.edit_exr_channel_combo, 1)
        self.edit_exr_channel_row.setEnabled(False)
        self.edit_exr_channel_label.setVisible(False)
        self.edit_exr_channel_combo.setVisible(False)
        layout.addLayout(self.edit_exr_channel_row)

        self.edit_exr_gamma_row = QtWidgets.QHBoxLayout()
        self.edit_exr_srgb_check = QtWidgets.QCheckBox("sRGB")
        self.edit_exr_srgb_check.setChecked(True)
        self.edit_exr_gamma_label = QtWidgets.QLabel("Gamma: 2.2")
        self.edit_exr_gamma_label.setStyleSheet(muted_text_style())
        self.edit_exr_gamma_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_exr_gamma_slider.setRange(10, 30)
        self.edit_exr_gamma_slider.setValue(22)
        self.edit_exr_gamma_input = self._create_spinbox(1.0, 3.0, 1, 0.1, 62)
        self.edit_exr_gamma_input.setValue(2.2)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_srgb_check, 0)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_gamma_label, 0)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_gamma_slider, 1)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_gamma_input, 0)
        self.edit_exr_srgb_check.setVisible(False)
        self.edit_exr_gamma_label.setVisible(False)
        self.edit_exr_gamma_slider.setVisible(False)
        self.edit_exr_gamma_input.setVisible(False)
        layout.addLayout(self.edit_exr_gamma_row)

    def _build_tool_stack_controls(self, layout: QtWidgets.QVBoxLayout) -> None:
        self.edit_tool_stack_section = QtWidgets.QFrame()
        self.edit_tool_stack_section.setStyleSheet(
            "QFrame {"
            "background: rgba(255,255,255,2);"
            "border: 1px solid rgba(255,255,255,8);"
            "border-radius: 8px;"
            "}"
        )
        self.edit_tool_stack_layout = QtWidgets.QVBoxLayout(self.edit_tool_stack_section)
        self.edit_tool_stack_layout.setContentsMargins(10, 10, 10, 10)
        self.edit_tool_stack_layout.setSpacing(8)
        layout.addWidget(self.edit_tool_stack_section, 0)

        self.edit_image_tools_header = QtWidgets.QHBoxLayout()
        self.edit_tool_stack_layout.addLayout(self.edit_image_tools_header)
        self.edit_image_tools_label = QtWidgets.QLabel("Tools")
        self.edit_image_tools_label.setStyleSheet("color: #8d97a2; font-size: 11px; font-weight: 600;")
        self.edit_image_tools_header.addWidget(self.edit_image_tools_label, 0)
        self.edit_image_tools_header.addStretch(1)

        self.edit_image_tool_add_btn = QtWidgets.QToolButton()
        self.edit_image_tool_add_btn.setText("Add")
        self.edit_image_tool_add_btn.setAutoRaise(True)
        self.edit_image_tool_add_btn.setStyleSheet(
            "QToolButton {"
            "background: rgba(255,255,255,4);"
            "border: 1px solid rgba(255,255,255,10);"
            "border-radius: 6px;"
            "padding: 4px 8px;"
            "color: #c8ced6;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255,255,255,8);"
            "}"
        )
        self.edit_image_tools_header.addWidget(self.edit_image_tool_add_btn, 0)

        self.edit_image_tool_empty = QtWidgets.QLabel("")
        self.edit_image_tool_empty.setStyleSheet("color: #6f7a86; font-size: 12px; padding: 2px 2px 6px 2px;")
        self.edit_image_tool_empty.setVisible(False)
        self.edit_tool_stack_layout.addWidget(self.edit_image_tool_empty, 0)

        self.edit_image_tool_list = QtWidgets.QListWidget()
        self.edit_image_tool_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.edit_image_tool_list.setMaximumHeight(152)
        self.edit_image_tool_list.setUniformItemSizes(True)
        self.edit_image_tool_list.setSpacing(6)
        self.edit_image_tool_list.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.edit_image_tool_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit_image_tool_list.setStyleSheet(
            "QListWidget {"
            "background: transparent;"
            "border: none;"
            "padding: 0px;"
            "outline: none;"
            "}"
            "QListWidget::item {"
            "background: transparent;"
            "border: none;"
            "padding: 0px;"
            "margin: 0px;"
            "}"
        )
        self.edit_image_tool_list.setVisible(False)
        self.edit_tool_stack_layout.addWidget(self.edit_image_tool_list, 0)

        self.edit_image_tool_add_row = QtWidgets.QHBoxLayout()
        self.edit_image_tool_add_combo = QtWidgets.QComboBox()
        self.edit_image_tool_add_combo.setMinimumWidth(120)
        self.edit_image_tool_add_row.addWidget(self.edit_image_tool_add_combo, 1)
        self.edit_image_tool_add_combo.setVisible(False)

        self.edit_image_tool_order_row = QtWidgets.QHBoxLayout()
        self.edit_image_tool_up_btn = QtWidgets.QPushButton("Up")
        self.edit_image_tool_down_btn = QtWidgets.QPushButton("Down")
        self.edit_image_tool_up_btn.setFixedWidth(46)
        self.edit_image_tool_down_btn.setFixedWidth(56)
        self.edit_image_tool_up_btn.setStyleSheet("QPushButton { color: #aeb6bf; font-size: 11px; }")
        self.edit_image_tool_down_btn.setStyleSheet("QPushButton { color: #aeb6bf; font-size: 11px; }")
        self.edit_image_tool_order_row.addWidget(self.edit_image_tool_up_btn, 0)
        self.edit_image_tool_order_row.addWidget(self.edit_image_tool_down_btn, 0)
        self.edit_image_tool_order_row.addStretch(1)
        self.edit_image_tools_header.addWidget(self.edit_image_tool_up_btn, 0)
        self.edit_image_tools_header.addWidget(self.edit_image_tool_down_btn, 0)
        self.edit_image_tool_up_btn.setVisible(False)
        self.edit_image_tool_down_btn.setVisible(False)
        self.edit_image_tool_add_btn.setVisible(False)

        self.edit_tool_stack_section.setVisible(False)

    def _build_tool_settings_controls(self, layout: QtWidgets.QVBoxLayout) -> None:
        self.edit_tool_settings_section = QtWidgets.QFrame()
        self.edit_tool_settings_section.setStyleSheet(
            "QFrame {"
            "background: rgba(255,255,255,2);"
            "border: 1px solid rgba(255,255,255,8);"
            "border-radius: 8px;"
            "}"
        )
        self.edit_tool_settings_section.setMinimumHeight(96)
        self.edit_tool_settings_section.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        settings_layout = QtWidgets.QVBoxLayout(self.edit_tool_settings_section)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(0)
        layout.addWidget(self.edit_tool_settings_section, 1)

        self.edit_image_adjust_reset_btn = QtWidgets.QPushButton("Reset", self)
        self.edit_image_adjust_reset_btn.setVisible(False)
        self.edit_tool_settings_title = QtWidgets.QLabel("Tool Settings")
        self.edit_tool_settings_reset_btn = self.edit_image_adjust_reset_btn
        self.edit_tool_settings_remove_btn = QtWidgets.QToolButton(self)
        self.edit_tool_settings_remove_btn.setText("x")
        self.edit_tool_settings_remove_btn.setVisible(False)

        self.edit_tool_settings_scroll = QtWidgets.QScrollArea()
        self.edit_tool_settings_scroll.setWidgetResizable(True)
        self.edit_tool_settings_scroll.setMinimumHeight(84)
        self.edit_tool_settings_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.edit_tool_settings_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit_tool_settings_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.edit_tool_settings_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical {"
            "background: rgba(255,255,255,4);"
            "width: 8px;"
            "border-radius: 4px;"
            "}"
            "QScrollBar::handle:vertical {"
            "background: rgba(255,255,255,22);"
            "border-radius: 4px;"
            "min-height: 24px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        settings_layout.addWidget(self.edit_tool_settings_scroll, 1)

        self.edit_tool_settings_content = QtWidgets.QWidget()
        self.edit_tool_settings_content.setAcceptDrops(True)
        self.edit_tool_settings_content.installEventFilter(self)
        self.edit_tool_settings_layout = QtWidgets.QVBoxLayout(self.edit_tool_settings_content)
        self.edit_tool_settings_layout.setContentsMargins(10, 10, 10, 10)
        self.edit_tool_settings_layout.setSpacing(8)
        self.edit_tool_settings_layout.addStretch(1)
        self.edit_tool_settings_scroll.setWidget(self.edit_tool_settings_content)

        self.edit_tool_settings_section.setVisible(False)

    def _build_tool_panels(self) -> None:
        self._panel_widgets.clear()
        self._panel_cards.clear()
        self._panel_titles.clear()
        self._control_rows.clear()
        for spec in list_edit_tools():
            panel = str(getattr(spec, "ui_panel", "") or "").strip().lower()
            if not panel:
                continue
            card = QtWidgets.QFrame()
            card.setStyleSheet(
                "QFrame {"
                "background: rgba(255,255,255,3);"
                "border: 1px solid rgba(255,255,255,10);"
                "border-radius: 8px;"
                "}"
            )
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(10, 10, 10, 10)
            card_layout.setSpacing(8)

            header = QtWidgets.QHBoxLayout()
            card_layout.addLayout(header)
            label = QtWidgets.QLabel(str(getattr(spec, "label", "") or panel))
            label.setStyleSheet("color: #d8dde5; font-size: 12px; font-weight: 600;")
            header.addWidget(label, 1)

            reset_btn = QtWidgets.QPushButton("Reset")
            reset_btn.setFixedWidth(52)
            reset_btn.setStyleSheet("QPushButton { color: #aeb6bf; font-size: 11px; }")
            reset_btn.clicked.connect(lambda _checked=False, current_panel=panel: self.toolResetRequested.emit(current_panel))
            header.addWidget(reset_btn, 0)

            remove_btn = QtWidgets.QToolButton()
            remove_btn.setText("x")
            remove_btn.setAutoRaise(True)
            remove_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            remove_btn.setFixedSize(22, 22)
            remove_btn.setStyleSheet(
                "QToolButton {"
                "background: rgba(255,255,255,4);"
                "border: 1px solid rgba(255,255,255,12);"
                "border-radius: 6px;"
                "padding: 0px;"
                "color: #aeb6bf;"
                "}"
                "QToolButton:hover {"
                "background: rgba(255,120,120,22);"
                "border: 1px solid rgba(255,120,120,54);"
                "color: #e1e5eb;"
                "}"
            )
            remove_btn.clicked.connect(lambda _checked=False, current_panel=panel: self.toolRemoveRequested.emit(current_panel))
            header.addWidget(remove_btn, 0)

            card.setVisible(False)
            self.edit_tool_settings_layout.insertWidget(self.edit_tool_settings_layout.count() - 1, card, 0)
            widgets: list[QtWidgets.QWidget] = [card]
            for control in getattr(spec, "ui_controls", ()):
                control_key = str(getattr(control, "key", "") or "").strip().lower()
                if not control_key:
                    continue
                row = self._create_control_row(control)
                card_layout.addWidget(row.widget, 0)
                widgets.append(row.widget)
                self._control_rows.setdefault(control_key, []).append(row)
            self._panel_widgets[panel] = widgets
            self._panel_cards[panel] = card
            self._panel_titles[panel] = label

    def set_tool_instances(self, instances: list[dict[str, object]]) -> None:
        selected_id = self._selected_instance_id
        self._clear_instance_cards()
        self._instance_order = []
        for entry in instances:
            instance_id = str(entry.get("instance_id", "") or "").strip()
            tool_id = str(entry.get("id", "") or "").strip().lower()
            if not instance_id or not tool_id:
                continue
            spec = get_edit_tool(tool_id)
            if spec is None:
                continue
            settings = entry.get("settings", {})
            card = self._create_instance_card(instance_id, spec, settings if isinstance(settings, dict) else {})
            self._instance_cards[instance_id] = card
            self._instance_tool_ids[instance_id] = tool_id
            self._instance_order.append(instance_id)
            self.edit_tool_settings_layout.insertWidget(self.edit_tool_settings_layout.count() - 1, card, 0)
        self.edit_tool_settings_section.setVisible(bool(self._instance_cards))
        if selected_id not in self._instance_cards:
            selected_id = self._instance_order[0] if self._instance_order else ""
        self.set_selected_tool_instance(selected_id)

    def _clear_instance_cards(self) -> None:
        for card in self._instance_cards.values():
            self.edit_tool_settings_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._instance_cards.clear()
        self._instance_rows.clear()
        self._instance_tool_ids.clear()

    def _create_instance_card(self, instance_id: str, spec: object, settings: dict[str, object]) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setProperty("tool_instance_id", instance_id)
        card.setProperty("selected", False)
        card.setAcceptDrops(True)
        card.installEventFilter(self)
        card.setStyleSheet(
            "QFrame {"
            "background: rgba(255,255,255,3);"
            "border: 1px solid rgba(255,255,255,10);"
            "border-radius: 8px;"
            "}"
            "QFrame[dragTarget='true'] {"
            "border: 1px solid rgba(242,193,78,82);"
            "background: rgba(242,193,78,8);"
            "}"
            "QFrame[selected='true'] {"
            "border: 1px solid rgba(242,193,78,70);"
            "background: rgba(242,193,78,6);"
            "}"
        )
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        card_layout.addLayout(header)

        handle = QtWidgets.QToolButton()
        handle.setText("::")
        handle.setAutoRaise(True)
        handle.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        handle.setFixedSize(22, 22)
        handle.setProperty("tool_instance_id", instance_id)
        handle.setProperty("drag_handle", True)
        handle.installEventFilter(self)
        handle.setStyleSheet("QToolButton { color: #818b96; padding: 0px; }")
        header.addWidget(handle, 0)

        label = QtWidgets.QLabel(str(getattr(spec, "label", "") or getattr(spec, "id", "") or "Tool"))
        self._attach_instance_selector(label, instance_id)
        label.setStyleSheet("color: #d8dde5; font-size: 12px; font-weight: 600;")
        header.addWidget(label, 1)

        reset_btn = QtWidgets.QPushButton("Reset")
        reset_btn.setFixedWidth(52)
        reset_btn.setStyleSheet("QPushButton { color: #aeb6bf; font-size: 11px; }")
        reset_btn.clicked.connect(lambda _checked=False, current_id=instance_id: self.toolResetRequested.emit(current_id))
        header.addWidget(reset_btn, 0)

        remove_btn = QtWidgets.QToolButton()
        remove_btn.setText("x")
        remove_btn.setAutoRaise(True)
        remove_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        remove_btn.setFixedSize(22, 22)
        remove_btn.setStyleSheet(
            "QToolButton {"
            "background: rgba(255,255,255,4);"
            "border: 1px solid rgba(255,255,255,12);"
            "border-radius: 6px;"
            "padding: 0px;"
            "color: #aeb6bf;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255,120,120,22);"
            "border: 1px solid rgba(255,120,120,54);"
            "color: #e1e5eb;"
            "}"
        )
        remove_btn.clicked.connect(lambda _checked=False, current_id=instance_id: self.toolRemoveRequested.emit(current_id))
        header.addWidget(remove_btn, 0)

        rows: dict[str, ToolControlRow] = {}
        for control in getattr(spec, "ui_controls", ()):
            control_key = str(getattr(control, "key", "") or "").strip().lower()
            if not control_key:
                continue
            row = self._create_control_row(control)
            self._attach_instance_selector(row.widget, instance_id)
            self._attach_instance_selector(row.title, instance_id)
            self._attach_instance_selector(row.slider, instance_id)
            self._attach_instance_selector(row.spinbox, instance_id)
            row.set_value(settings.get(control_key, getattr(control, "minimum", 0.0)))
            row.slider.valueChanged.connect(lambda *_args, current_id=instance_id: self.toolSettingsChanged.emit(current_id))
            row.spinbox.valueChanged.connect(lambda *_args, current_id=instance_id: self.toolSettingsChanged.emit(current_id))
            card_layout.addWidget(row.widget, 0)
            rows[control_key] = row
        self._instance_rows[instance_id] = rows
        return card

    def _attach_instance_selector(self, widget: QtWidgets.QWidget, instance_id: str) -> None:
        widget.setProperty("tool_instance_id", instance_id)
        widget.installEventFilter(self)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and obj.property("tool_instance_id"):
            instance_id = str(obj.property("tool_instance_id") or "")
            if instance_id:
                self.set_selected_tool_instance(instance_id)
                self.toolSelected.emit(instance_id)
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and bool(obj.property("drag_handle")):
            mouse_event = event
            if isinstance(mouse_event, QtGui.QMouseEvent) and mouse_event.button() == QtCore.Qt.MouseButton.LeftButton:
                self._drag_start_pos = mouse_event.pos()
                return False
        if event.type() == QtCore.QEvent.Type.MouseMove and bool(obj.property("drag_handle")):
            mouse_event = event
            if isinstance(mouse_event, QtGui.QMouseEvent) and self._drag_start_pos is not None:
                if (mouse_event.pos() - self._drag_start_pos).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                    instance_id = str(obj.property("tool_instance_id") or "")
                    if instance_id:
                        drag = QtGui.QDrag(obj)
                        mime = QtCore.QMimeData()
                        mime.setData("application/x-sk-tool-instance", instance_id.encode("utf-8"))
                        drag.setMimeData(mime)
                        drag.exec(QtCore.Qt.DropAction.MoveAction)
                        self._drag_start_pos = None
                        return True
        if event.type() in (QtCore.QEvent.Type.DragEnter, QtCore.QEvent.Type.DragMove):
            drag_event = event
            if isinstance(drag_event, (QtGui.QDragEnterEvent, QtGui.QDragMoveEvent)) and drag_event.mimeData().hasFormat("application/x-sk-tool-instance"):
                self._set_drag_target(obj, True)
                drag_event.acceptProposedAction()
                return True
        if event.type() == QtCore.QEvent.Type.DragLeave:
            self._set_drag_target(obj, False)
            return False
        if event.type() == QtCore.QEvent.Type.Drop:
            drop_event = event
            if isinstance(drop_event, QtGui.QDropEvent) and drop_event.mimeData().hasFormat("application/x-sk-tool-instance"):
                source_id = bytes(drop_event.mimeData().data("application/x-sk-tool-instance")).decode("utf-8")
                target_id = str(obj.property("tool_instance_id") or "")
                self._set_drag_target(obj, False)
                if not target_id and obj is self.edit_tool_settings_content:
                    self.toolMoveRequested.emit(source_id, max(0, len(self._instance_order) - 1))
                    drop_event.acceptProposedAction()
                    return True
                if source_id and target_id and source_id != target_id and target_id in self._instance_order:
                    self.toolMoveRequested.emit(source_id, self._instance_order.index(target_id))
                    drop_event.acceptProposedAction()
                    return True
        return super().eventFilter(obj, event)

    def _set_drag_target(self, obj: QtCore.QObject, active: bool) -> None:
        if isinstance(obj, QtWidgets.QWidget) and obj.property("tool_instance_id"):
            obj.setProperty("dragTarget", bool(active))
            self._refresh_widget_style(obj)

    def _refresh_widget_style(self, widget: QtWidgets.QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def set_selected_tool_instance(self, instance_id: str) -> None:
        selected_id = str(instance_id or "").strip()
        self._selected_instance_id = selected_id
        for current_id, card in self._instance_cards.items():
            card.setProperty("selected", current_id == selected_id)
            self._refresh_widget_style(card)

    def panel_widgets(self) -> dict[str, list[QtWidgets.QWidget]]:
        return {}

    def set_tool_panel_visible(self, panel: str, visible: bool) -> None:
        card = self._panel_cards.get(str(panel or "").strip().lower())
        if card is not None:
            card.setVisible(bool(visible))

    def set_active_tool_panel(self, panel: str) -> None:
        key = str(panel or "").strip().lower()
        for panel_id in self._panel_widgets:
            self.set_tool_panel_visible(panel_id, panel_id == key)
        self.edit_tool_settings_section.setVisible(key in self._panel_widgets)

    def set_visible_tool_panels(self, panels: list[str]) -> None:
        ordered_panels = []
        for panel in panels:
            key = str(panel or "").strip().lower()
            if key and key in self._panel_cards and key not in ordered_panels:
                ordered_panels.append(key)
        visible_panels = set(ordered_panels)
        for panel_id in self._panel_widgets:
            self.set_tool_panel_visible(panel_id, panel_id in visible_panels)
        insert_at = 0
        for panel_id in ordered_panels:
            card = self._panel_cards.get(panel_id)
            if card is None:
                continue
            self.edit_tool_settings_layout.removeWidget(card)
            self.edit_tool_settings_layout.insertWidget(insert_at, card, 0)
            insert_at += 1
        self.edit_tool_settings_section.setVisible(bool(visible_panels))

    def set_active_tool_title(self, title: str) -> None:
        clean = str(title or "").strip()
        self.edit_tool_settings_title.setText(clean or "Tool Settings")

    def current_control_value(self, control_key: str, panel: str = "") -> float | None:
        row = self._control_row(control_key, panel)
        if row is None:
            return None
        return row.current_value()

    def control_slider(self, control_key: str, panel: str = "") -> QtWidgets.QSlider | None:
        row = self._control_row(control_key, panel)
        return row.slider if row is not None else None

    def set_control_value(self, control_key: str, value: object, panel: str = "") -> None:
        row = self._control_row(control_key, panel)
        if row is None:
            return
        row.set_value(value)

    def current_instance_state(self, instance_id: str) -> dict[str, float]:
        rows = self._instance_rows.get(str(instance_id or "").strip(), {})
        return {key: row.current_value() for key, row in rows.items()}

    def set_instance_state(self, instance_id: str, state: dict[str, object]) -> None:
        rows = self._instance_rows.get(str(instance_id or "").strip(), {})
        values = dict(state) if isinstance(state, dict) else {}
        for key, row in rows.items():
            row.set_value(values.get(key, getattr(row.spec, "minimum", 0.0)))

    def _control_row(self, control_key: str, panel: str = "") -> ToolControlRow | None:
        key = str(control_key or "").strip().lower()
        rows = self._control_rows.get(key, [])
        if not rows:
            return None
        panel_key = str(panel or "").strip().lower()
        if panel_key:
            panel_rows = set(self._panel_widgets.get(panel_key, []))
            for row in rows:
                if row.widget in panel_rows:
                    return row
            return None
        if len(rows) == 1:
            return rows[0]
        for row in rows:
            if row.widget.isVisible():
                return row
        return rows[0]

    def _create_control_row(self, control: ToolUiControlSpec) -> ToolControlRow:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title = QtWidgets.QLabel(str(getattr(control, "label", "") or getattr(control, "key", "")))
        title.setStyleSheet(muted_text_style())
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        scale = self._control_scale(control)
        slider.setRange(
            int(round(float(control.minimum) * scale)),
            int(round(float(control.maximum) * scale)),
        )
        spinbox = QtWidgets.QDoubleSpinBox()
        spinbox.setDecimals(int(getattr(control, "display_decimals", 2)))
        if str(getattr(control, "display_suffix", "") or ""):
            spinbox.setSuffix(str(control.display_suffix))
            spinbox.setRange(float(control.minimum) * scale, float(control.maximum) * scale)
            spinbox.setSingleStep(max(1.0, 1.0 / max(1.0, scale)))
            spinbox.setFixedWidth(74)
        else:
            spinbox.setRange(float(control.minimum), float(control.maximum))
            spinbox.setSingleStep(max(0.01, 1.0 / max(1.0, scale)))
            spinbox.setFixedWidth(70)
        spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        spinbox.setKeyboardTracking(False)
        spinbox.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        layout.addWidget(title, 0)
        layout.addWidget(slider, 1)
        layout.addWidget(spinbox, 0)
        row = ToolControlRow(control, widget, title, slider, spinbox)
        row.bind_spinbox()
        row.set_value(float(getattr(control, "minimum", 0.0)))
        return row

    def _control_scale(self, control: ToolUiControlSpec) -> float:
        scale = float(getattr(control, "display_scale", 1.0) or 1.0)
        if abs(scale - 1.0) > 1e-6:
            return scale
        decimals = int(getattr(control, "display_decimals", 2))
        return float(10 ** max(0, decimals))

    def _create_spinbox(
        self,
        minimum: float,
        maximum: float,
        decimals: int,
        step: float,
        width: int,
        *,
        suffix: str = "",
    ) -> QtWidgets.QDoubleSpinBox:
        spinbox = QtWidgets.QDoubleSpinBox()
        spinbox.setRange(minimum, maximum)
        spinbox.setDecimals(decimals)
        spinbox.setSingleStep(step)
        if suffix:
            spinbox.setSuffix(suffix)
        spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        spinbox.setKeyboardTracking(False)
        spinbox.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        spinbox.setFixedWidth(width)
        return spinbox


class BoardEditPreviewStack(QtWidgets.QWidget):
    """Preview stack for image, video and sequence edit modes."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.setMinimumHeight(140)
        layout.addWidget(self.stack, 1)

        self.image_preview = VideoPreviewLabel()
        self.image_preview.setStyleSheet("color: #9aa3ad;")
        self.stack.addWidget(self.image_preview)

        self.video_panel = QtWidgets.QWidget()
        video_layout = QtWidgets.QVBoxLayout(self.video_panel)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(6)
        self.video_status = QtWidgets.QLabel("")
        self.video_status.setStyleSheet(muted_text_style())
        video_layout.addWidget(self.video_status, 0)
        self.video_host = QtWidgets.QWidget()
        self.video_host.setStyleSheet("color: #9aa3ad;")
        self.video_host_layout = QtWidgets.QVBoxLayout(self.video_host)
        self.video_host_layout.setContentsMargins(0, 0, 0, 0)
        self.video_host_layout.setSpacing(0)
        video_layout.addWidget(self.video_host, 1)
        self.stack.addWidget(self.video_panel)

        self.sequence_panel = QtWidgets.QWidget()
        sequence_layout = QtWidgets.QVBoxLayout(self.sequence_panel)
        sequence_layout.setContentsMargins(0, 0, 0, 0)
        sequence_layout.setSpacing(6)
        self.sequence_label = QtWidgets.QLabel("")
        self.sequence_label.setStyleSheet(muted_text_style())
        sequence_layout.addWidget(self.sequence_label, 0)
        self.sequence_preview = VideoPreviewLabel()
        self.sequence_preview.setStyleSheet("color: #9aa3ad;")
        sequence_layout.addWidget(self.sequence_preview, 1)
        self.sequence_timeline = BoardTimeline()
        sequence_layout.addWidget(self.sequence_timeline, 0)
        self.sequence_timeline.setVisible(False)

        self.sequence_frame_label = QtWidgets.QLabel("Frame: 0")
        self.sequence_frame_label.setStyleSheet(muted_text_style())
        sequence_layout.addWidget(self.sequence_frame_label, 0)
        self.sequence_frame_label.setVisible(False)
        self.stack.addWidget(self.sequence_panel)
