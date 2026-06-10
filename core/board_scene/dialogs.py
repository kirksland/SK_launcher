from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from video.player import VideoPreviewLabel


ImageLoader = Callable[[Path], QtGui.QPixmap]


class PopupOutsideCloseFilter(QtCore.QObject):
    def __init__(self, dialog: QtWidgets.QDialog, on_close) -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self._on_close = on_close
        self.block_outside_close = False

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if self._dialog is None or not self._dialog.isVisible():
            return False
        if self.block_outside_close:
            return False
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            try:
                mouse_event = event  # type: ignore[assignment]
                global_pos = mouse_event.globalPosition().toPoint()  # type: ignore[attr-defined]
            except Exception:
                return False
            if not self._dialog.geometry().contains(global_pos):
                self._on_close()
                self._dialog.close()
                return True
        return False


class _NoUnderlineHighlighter(QtGui.QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:  # type: ignore[override]
        if not text:
            return
        fmt = QtGui.QTextCharFormat()
        fmt.setUnderlineStyle(QtGui.QTextCharFormat.UnderlineStyle.NoUnderline)
        self.setFormat(0, len(text), fmt)


class NoteTextEditor(QtWidgets.QGraphicsView):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.TextAntialiasing
        )
        self.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QtGui.QColor("#1f2329"))
        self.setStyleSheet("border: 1px solid #14171c;")
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._text_item = QtWidgets.QGraphicsTextItem()
        self._text_item.setDefaultTextColor(QtGui.QColor("#e6e6e6"))
        self._text_item.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditorInteraction)
        self._scene.addItem(self._text_item)
        self._padding = 8
        self._highlighter = _NoUnderlineHighlighter(self._text_item.document())
        self._disable_spellcheck(self._text_item.document())

    def set_text(self, text: str) -> None:
        self._text_item.setPlainText(text)
        self._refresh_layout()

    def text(self) -> str:
        return self._text_item.toPlainText()

    def _refresh_layout(self) -> None:
        w = max(40.0, self.viewport().width() - self._padding * 2)
        self._text_item.setTextWidth(w)
        self._text_item.setPos(self._padding, self._padding)
        self._scene.setSceneRect(self.viewport().rect())

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh_layout()

    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:  # type: ignore[override]
        super().focusInEvent(event)
        self._scene.setFocusItem(self._text_item)

    @staticmethod
    def _disable_spellcheck(document: QtGui.QTextDocument) -> None:
        try:
            option = document.defaultTextOption()
            flag = getattr(QtGui.QTextOption.Flag, "NoTextCheck", None)
            if flag is not None:
                option.setFlags(option.flags() | flag)
                document.setDefaultTextOption(option)
        except Exception:
            pass


class SequencePlayerDialog(QtWidgets.QDialog):
    def __init__(self, dir_path: Path, image_exts: set[str], parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sequence: {dir_path.name}")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(860, 540)
        self._image_exts = {str(ext).lower() for ext in image_exts}
        self._dir_path = dir_path
        self._frames = self._collect_frames(dir_path)
        self._frame_index = 0
        self._playing = False
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._advance)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #9aa3ad;")
        layout.addWidget(self._status, 0)

        self._preview = VideoPreviewLabel()
        self._preview.setStyleSheet("color: #9aa3ad;")
        layout.addWidget(self._preview, 1)

        controls = QtWidgets.QHBoxLayout()
        layout.addLayout(controls, 0)

        self._play_btn = QtWidgets.QPushButton("Play")
        controls.addWidget(self._play_btn, 0)
        self._play_btn.clicked.connect(self._toggle_play)

        self._slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._slider.setRange(0, max(0, len(self._frames) - 1))
        self._slider.valueChanged.connect(self._on_slider)
        controls.addWidget(self._slider, 1)

        fps_label = QtWidgets.QLabel("FPS")
        controls.addWidget(fps_label, 0)
        self._fps_spin = QtWidgets.QSpinBox()
        self._fps_spin.setRange(1, 60)
        self._fps_spin.setValue(24)
        self._fps_spin.valueChanged.connect(self._on_fps_changed)
        controls.addWidget(self._fps_spin, 0)

        if not self._frames:
            self._status.setText("No frames found in directory.")
        else:
            self._status.setText(f"{len(self._frames)} frames")
            self._show_frame(0)

    def _collect_frames(self, dir_path: Path) -> list[Path]:
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        frames = [p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in self._image_exts]
        return sorted(frames, key=lambda p: p.name)

    def _on_slider(self, value: int) -> None:
        self._frame_index = value
        self._show_frame(value)

    def _toggle_play(self) -> None:
        if not self._frames:
            return
        if self._playing:
            self._timer.stop()
            self._playing = False
            self._play_btn.setText("Play")
        else:
            interval = int(1000 / max(1, self._fps_spin.value()))
            self._timer.start(max(interval, 1))
            self._playing = True
            self._play_btn.setText("Pause")

    def _on_fps_changed(self) -> None:
        if self._playing:
            interval = int(1000 / max(1, self._fps_spin.value()))
            self._timer.start(max(interval, 1))

    def _advance(self) -> None:
        if not self._frames:
            return
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self._slider.blockSignals(True)
        self._slider.setValue(self._frame_index)
        self._slider.blockSignals(False)
        self._show_frame(self._frame_index)

    def _show_frame(self, index: int) -> None:
        if not self._frames:
            return
        if index < 0 or index >= len(self._frames):
            return
        path = self._frames[index]
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull():
            return
        max_dim = 1920
        if pixmap.width() > max_dim or pixmap.height() > max_dim:
            pixmap = pixmap.scaled(
                max_dim,
                max_dim,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        self._preview.set_base_pixmap(pixmap)
        self._status.setText(f"{path.name} ({index + 1}/{len(self._frames)})")


class BoardSlideshowDialog(QtWidgets.QDialog):
    def __init__(
        self,
        image_paths: list[Path],
        image_loader: ImageLoader,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Board Slideshow")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._screen_fit_applied = False
        self._original_image_paths = list(image_paths)
        self._image_paths = list(image_paths)
        self._image_loader = image_loader
        self._index = 0
        self._playing = False
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._shortcuts: list[QtGui.QShortcut] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #9aa3ad;")
        layout.addWidget(self._status, 0)

        options = QtWidgets.QHBoxLayout()
        layout.addLayout(options, 0)

        order_label = QtWidgets.QLabel("Order")
        options.addWidget(order_label, 0)
        self._order_combo = QtWidgets.QComboBox()
        self._order_combo.addItem("Selection", "selection")
        self._order_combo.addItem("Name A-Z", "name_asc")
        self._order_combo.addItem("Name Z-A", "name_desc")
        self._order_combo.addItem("Created oldest", "created_asc")
        self._order_combo.addItem("Created newest", "created_desc")
        self._order_combo.addItem("Modified oldest", "modified_asc")
        self._order_combo.addItem("Modified newest", "modified_desc")
        self._order_combo.setCurrentIndex(3)
        self._order_combo.currentIndexChanged.connect(self._on_order_changed)
        options.addWidget(self._order_combo, 0)
        options.addStretch(1)

        self._preview = VideoPreviewLabel()
        self._preview.setMinimumSize(240, 160)
        self._preview.setStyleSheet("color: #9aa3ad;")
        layout.addWidget(self._preview, 1)

        controls = QtWidgets.QHBoxLayout()
        layout.addLayout(controls, 0)

        self._prev_btn = QtWidgets.QPushButton("Previous")
        self._prev_btn.clicked.connect(self.previous_image)
        controls.addWidget(self._prev_btn, 0)

        self._play_btn = QtWidgets.QPushButton("Play")
        self._play_btn.clicked.connect(self.toggle_play)
        controls.addWidget(self._play_btn, 0)

        self._next_btn = QtWidgets.QPushButton("Next")
        self._next_btn.clicked.connect(self.next_image)
        controls.addWidget(self._next_btn, 0)

        self._slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._slider.setRange(0, max(0, len(self._image_paths) - 1))
        self._slider.valueChanged.connect(self._on_slider)
        controls.addWidget(self._slider, 1)

        delay_label = QtWidgets.QLabel("Delay")
        controls.addWidget(delay_label, 0)
        self._delay_spin = QtWidgets.QDoubleSpinBox()
        self._delay_spin.setRange(0.2, 30.0)
        self._delay_spin.setSingleStep(0.25)
        self._delay_spin.setSuffix(" s")
        self._delay_spin.setValue(2.0)
        self._delay_spin.valueChanged.connect(self._on_delay_changed)
        controls.addWidget(self._delay_spin, 0)

        self._apply_order("created_asc")

        if self._image_paths:
            self._show_image(0)
        else:
            self._status.setText("No images selected.")
            self._set_controls_enabled(False)
        self._bind_keyboard_shortcuts()
        self._fit_to_screen()

    def _bind_keyboard_shortcuts(self) -> None:
        bindings = (
            (QtCore.Qt.Key.Key_Right, self.next_image),
            (QtCore.Qt.Key.Key_Down, self.next_image),
            (QtCore.Qt.Key.Key_Left, self.previous_image),
            (QtCore.Qt.Key.Key_Up, self.previous_image),
            (QtCore.Qt.Key.Key_Space, self.toggle_play),
            (QtCore.Qt.Key.Key_Escape, self.close),
        )
        for key, callback in bindings:
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self)
            shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _available_screen_geometry(self) -> QtCore.QRect:
        parent = self.parentWidget()
        screen = None
        if parent is not None:
            center = parent.frameGeometry().center()
            screen = QtGui.QGuiApplication.screenAt(center)
            if screen is None:
                screen = parent.screen()
        if screen is None:
            screen = QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos())
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else QtCore.QRect(0, 0, 1100, 720)

    def _fit_to_screen(self) -> None:
        available = self._available_screen_geometry()
        margin = 48
        max_width = max(360, available.width() - margin)
        max_height = max(280, available.height() - margin)
        width = min(1100, max_width)
        height = min(720, max_height)
        self.resize(width, height)
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._screen_fit_applied:
            return
        self._screen_fit_applied = True
        self._fit_to_screen()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (self._prev_btn, self._play_btn, self._next_btn, self._slider, self._delay_spin, self._order_combo):
            widget.setEnabled(bool(enabled))

    def _on_slider(self, value: int) -> None:
        self._index = int(value)
        self._show_image(self._index)

    @staticmethod
    def _path_created_time(path: Path) -> float:
        try:
            stat = path.stat()
            return float(getattr(stat, "st_birthtime", stat.st_ctime))
        except Exception:
            return 0.0

    @staticmethod
    def _path_modified_time(path: Path) -> float:
        try:
            return float(path.stat().st_mtime)
        except Exception:
            return 0.0

    def _apply_order(self, order_key: str) -> None:
        if order_key == "selection":
            ordered = list(self._original_image_paths)
        elif order_key == "name_asc":
            ordered = sorted(self._image_paths, key=lambda path: path.name.lower())
        elif order_key == "name_desc":
            ordered = sorted(self._image_paths, key=lambda path: path.name.lower(), reverse=True)
        elif order_key == "created_desc":
            ordered = sorted(
                self._image_paths,
                key=lambda path: (self._path_created_time(path), path.name.lower()),
                reverse=True,
            )
        elif order_key == "modified_asc":
            ordered = sorted(self._image_paths, key=lambda path: (self._path_modified_time(path), path.name.lower()))
        elif order_key == "modified_desc":
            ordered = sorted(
                self._image_paths,
                key=lambda path: (self._path_modified_time(path), path.name.lower()),
                reverse=True,
            )
        else:
            ordered = sorted(self._image_paths, key=lambda path: (self._path_created_time(path), path.name.lower()))
        self._image_paths = ordered

    def _on_order_changed(self) -> None:
        if not self._image_paths:
            return
        current_path = self._image_paths[self._index] if 0 <= self._index < len(self._image_paths) else None
        order_key = str(self._order_combo.currentData() or "created_asc")
        self._apply_order(order_key)
        if current_path in self._image_paths:
            self._index = self._image_paths.index(current_path)
        else:
            self._index = min(self._index, len(self._image_paths) - 1)
        self._slider.setRange(0, max(0, len(self._image_paths) - 1))
        self._set_index(self._index)

    def _on_delay_changed(self) -> None:
        if self._playing:
            self._timer.start(self._interval_ms())

    def _interval_ms(self) -> int:
        return max(1, int(round(float(self._delay_spin.value()) * 1000.0)))

    def toggle_play(self) -> None:
        if not self._image_paths:
            return
        if self._playing:
            self._timer.stop()
            self._playing = False
            self._play_btn.setText("Play")
            return
        self._timer.start(self._interval_ms())
        self._playing = True
        self._play_btn.setText("Pause")

    def previous_image(self) -> None:
        if not self._image_paths:
            return
        self._set_index((self._index - 1) % len(self._image_paths))

    def next_image(self) -> None:
        if not self._image_paths:
            return
        self._set_index((self._index + 1) % len(self._image_paths))

    def _advance(self) -> None:
        self.next_image()

    def _set_index(self, index: int) -> None:
        self._index = int(index)
        self._slider.blockSignals(True)
        self._slider.setValue(self._index)
        self._slider.blockSignals(False)
        self._show_image(self._index)

    def _show_image(self, index: int) -> None:
        if not self._image_paths:
            return
        if index < 0 or index >= len(self._image_paths):
            return
        path = self._image_paths[index]
        pixmap = self._image_loader(path)
        if pixmap.isNull():
            self._status.setText(f"Failed to load: {path.name} ({index + 1}/{len(self._image_paths)})")
            return
        self._preview.set_base_pixmap(pixmap)
        self._status.setText(f"{path.name} ({index + 1}/{len(self._image_paths)})")

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        if event.key() in (QtCore.Qt.Key.Key_Right, QtCore.Qt.Key.Key_Down):
            self.next_image()
            event.accept()
            return
        if event.key() in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Up):
            self.previous_image()
            event.accept()
            return
        if event.key() == QtCore.Qt.Key.Key_Space:
            self.toggle_play()
            event.accept()
            return
        super().keyPressEvent(event)
