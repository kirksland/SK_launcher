from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from video.player import VideoPreviewLabel


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
