from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

from tools.board_tools.edit import ToolUiControlSpec, list_edit_tools
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
        "edit_image_adjust_reset_btn",
    )

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._panel_widgets: dict[str, list[QtWidgets.QWidget]] = {}
        self._control_rows: dict[str, ToolControlRow] = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._build_exr_controls(layout)
        self._build_tool_stack_controls(layout)
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
        self.edit_image_tools_label = QtWidgets.QLabel("Tool Stack")
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

        self.edit_image_tool_empty = QtWidgets.QLabel("No tools in the stack yet.")
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

        self.edit_image_adjust_reset_btn = QtWidgets.QPushButton("Reset Adjustments")
        self.edit_image_adjust_reset_btn.setVisible(False)
        self.edit_tool_stack_layout.addWidget(self.edit_image_adjust_reset_btn, 0)

        self.edit_tool_stack_section.setVisible(False)

    def _build_tool_panels(self) -> None:
        self._panel_widgets.clear()
        self._control_rows.clear()
        for spec in list_edit_tools():
            panel = str(getattr(spec, "ui_panel", "") or "").strip().lower()
            if not panel:
                continue
            label = QtWidgets.QLabel(str(getattr(spec, "label", "") or panel))
            label.setStyleSheet(muted_text_style())
            label.setVisible(False)
            self.edit_tool_stack_layout.addWidget(label, 0)
            widgets: list[QtWidgets.QWidget] = [label]
            for control in getattr(spec, "ui_controls", ()):
                control_key = str(getattr(control, "key", "") or "").strip().lower()
                if not control_key:
                    continue
                row = self._create_control_row(control)
                row.widget.setVisible(False)
                self.edit_tool_stack_layout.addWidget(row.widget, 0)
                widgets.append(row.widget)
                self._control_rows[control_key] = row
            self._panel_widgets[panel] = widgets

    def panel_widgets(self) -> dict[str, list[QtWidgets.QWidget]]:
        return {panel: list(widgets) for panel, widgets in self._panel_widgets.items()}

    def set_tool_panel_visible(self, panel: str, visible: bool) -> None:
        for widget in self._panel_widgets.get(str(panel or "").strip().lower(), []):
            widget.setVisible(bool(visible))

    def set_active_tool_panel(self, panel: str) -> None:
        key = str(panel or "").strip().lower()
        for panel_id in self._panel_widgets:
            self.set_tool_panel_visible(panel_id, panel_id == key)

    def current_control_value(self, control_key: str) -> float | None:
        key = str(control_key or "").strip().lower()
        row = self._control_rows.get(key)
        if row is None:
            return None
        return row.current_value()

    def control_slider(self, control_key: str) -> QtWidgets.QSlider | None:
        row = self._control_rows.get(str(control_key or "").strip().lower())
        return row.slider if row is not None else None

    def set_control_value(self, control_key: str, value: object) -> None:
        key = str(control_key or "").strip().lower()
        row = self._control_rows.get(key)
        if row is None:
            return
        row.set_value(value)

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
