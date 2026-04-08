from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional video backend
    cv2 = None  # type: ignore

QtMultimedia = None  # type: ignore[assignment]
QtMultimediaWidgets = None  # type: ignore[assignment]


class VideoPreviewLabel(QtWidgets.QLabel):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._base_pixmap: Optional[QtGui.QPixmap] = None
        self._zoom = 1.0
        self._pan = QtCore.QPointF(0.0, 0.0)
        self._dragging = False
        self._drag_last = QtCore.QPointF()

    def set_base_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._base_pixmap = pixmap
        self._zoom = 1.0
        self._pan = QtCore.QPointF(0.0, 0.0)
        self._update_view()

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        if self._base_pixmap is None:
            return
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            factor = 1.05 if event.angleDelta().y() > 0 else 0.95
        else:
            factor = 1.15 if event.angleDelta().y() > 0 else 0.87
        new_zoom = max(0.2, min(6.0, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-6:
            return
        self._zoom = new_zoom
        self._update_view()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._zoom = 1.0
            self._pan = QtCore.QPointF(0.0, 0.0)
            self._update_view()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._base_pixmap is not None:
            self._dragging = True
            self._drag_last = QtCore.QPointF(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if self._dragging and self._base_pixmap is not None:
            pos = QtCore.QPointF(event.position())
            delta = pos - self._drag_last
            self._drag_last = pos
            self._pan += delta
            self._update_view()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        self._update_view()
        super().resizeEvent(event)

    def _update_view(self) -> None:
        if self._base_pixmap is None or self.width() <= 0 or self.height() <= 0:
            return
        scaled = self._base_pixmap.scaled(
            self.size() * self._zoom,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QtGui.QPixmap(self.size())
        canvas.fill(QtGui.QColor("#1b1f26"))
        painter = QtGui.QPainter(canvas)
        x = (self.width() - scaled.width()) / 2 + self._pan.x()
        y = (self.height() - scaled.height()) / 2 + self._pan.y()
        painter.drawPixmap(int(x), int(y), scaled)
        painter.end()
        self.setPixmap(canvas)


class VideoController:
    def __init__(
        self,
        backend_pref: str,
        status_label: QtWidgets.QLabel,
        preview_label: QtWidgets.QLabel,
        preview_widget: QtWidgets.QLabel,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        self._backend_pref = backend_pref
        self._status_label = status_label
        self._preview_label = preview_label
        self._preview_widget = preview_widget
        self._parent = parent

        self._video_backend = "none"
        self._video_widget: Optional[QtWidgets.QWidget] = None
        self._image_widget: Optional[VideoPreviewLabel] = None
        self._container: Optional[QtWidgets.QWidget] = None
        self._stack: Optional[QtWidgets.QStackedLayout] = None
        self._player = None
        self._cv_cap = None
        self._cv_timer = QtCore.QTimer(parent)
        self._cv_frame_count = 0
        self._cv_fps = 24.0
        self._cv_playing = False

        self._play_button: Optional[QtWidgets.QPushButton] = None
        self._slider: Optional[QtWidgets.QSlider] = None

    @property
    def widget(self) -> QtWidgets.QWidget:
        if self._container is None:
            self._container = self._build_widget()
        return self._container

    def bind_controls(self, play_button: QtWidgets.QPushButton, slider: QtWidgets.QSlider) -> None:
        self._play_button = play_button
        self._slider = slider
        play_button.clicked.connect(self.toggle_play)
        slider.sliderMoved.connect(self.seek)

    def play_path(self, path: Path) -> None:
        self._show_video_widget()
        if self._video_backend == "qt" and self._player:
            try:
                url = QtCore.QUrl.fromLocalFile(str(path))
                self._player.setSource(url)  # type: ignore[attr-defined]
                self._player.play()
                if self._play_button:
                    self._play_button.setText("Pause")
            except Exception:
                pass
        elif self._video_backend == "opencv":
            self._play_video_opencv(path)

    def preview_first_frame(self, path: Path) -> None:
        if cv2 is None:
            return
        try:
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                cap.release()
                return
            ok, frame = cap.read()
            cap.release()
            if not ok or frame is None:
                return
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
            pixmap = QtGui.QPixmap.fromImage(image)
            if not pixmap.isNull():
                self.show_image(pixmap)
        except Exception:
            return

    def show_image(self, pixmap: QtGui.QPixmap) -> None:
        if self._image_widget is None:
            return
        self._image_widget.set_base_pixmap(pixmap)
        self._show_image_widget()

    def toggle_play(self) -> None:
        if self._video_backend == "qt" and self._player:
            try:
                state = self._player.playbackState()
                if state == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
                    self._player.pause()
                    if self._play_button:
                        self._play_button.setText("Play")
                else:
                    self._player.play()
                    if self._play_button:
                        self._play_button.setText("Pause")
            except Exception:
                pass
            return

        if self._video_backend == "opencv":
            if self._cv_cap is None:
                return
            if self._cv_playing:
                self._cv_timer.stop()
                self._cv_playing = False
                if self._play_button:
                    self._play_button.setText("Play")
            else:
                interval = int(1000 / max(self._cv_fps, 1.0))
                self._cv_timer.start(max(interval, 1))
                self._cv_playing = True
                if self._play_button:
                    self._play_button.setText("Pause")

    def seek(self, value: int) -> None:
        if self._video_backend == "qt" and self._player:
            self._player.setPosition(value)
            return
        if self._video_backend == "opencv" and self._cv_cap is not None:
            self._cv_cap.set(1, value)  # CAP_PROP_POS_FRAMES
            ok, frame = self._cv_cap.read()
            if ok:
                self._show_cv_frame(frame)

    def seek_frame(self, frame_index: int) -> None:
        if self._video_backend == "qt" and self._player:
            ms = int(max(0, frame_index) * 1000 / max(self._cv_fps, 1.0))
            self._player.setPosition(ms)
            return
        if self._video_backend == "opencv":
            self.seek(int(frame_index))

    def _build_widget(self) -> QtWidgets.QWidget:
        global QtMultimedia, QtMultimediaWidgets

        video_min_size = QtCore.QSize(420, 200)
        use_qt_backend = False

        pref = (self._backend_pref or "auto").strip().lower()
        if pref == "auto" and cv2 is not None:
            pref = "opencv"

        if pref not in ("opencv", "none"):
            if QtMultimedia is None or QtMultimediaWidgets is None:
                try:
                    from PySide6 import QtMultimedia as _QtMultimedia, QtMultimediaWidgets as _QtMultimediaWidgets
                except Exception:
                    _QtMultimedia = None
                    _QtMultimediaWidgets = None
                QtMultimedia = _QtMultimedia  # type: ignore[assignment]
                QtMultimediaWidgets = _QtMultimediaWidgets  # type: ignore[assignment]

        if pref not in ("opencv", "none") and QtMultimedia and QtMultimediaWidgets:
            try:
                candidate_player = QtMultimedia.QMediaPlayer()
                if candidate_player.isAvailable():
                    widget = QtMultimediaWidgets.QVideoWidget()
                    widget.setMinimumSize(video_min_size)
                    widget.setSizePolicy(
                        QtWidgets.QSizePolicy.Policy.Expanding,
                        QtWidgets.QSizePolicy.Policy.Expanding,
                    )
                    candidate_player.setVideoOutput(widget)
                    candidate_player.positionChanged.connect(self._on_position)
                    candidate_player.durationChanged.connect(self._on_duration)
                    self._player = candidate_player
                    self._video_backend = "qt"
                    use_qt_backend = True
                    self._video_widget = widget
            except Exception:
                self._player = None
        if self._video_widget is None:
            widget = VideoPreviewLabel()
            widget.setStyleSheet("color: #9aa3ad;")
            widget.setMinimumSize(video_min_size)
            widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
            if pref == "none":
                widget.setText("Video preview disabled")
            else:
                if cv2 is None:
                    widget.setText("OpenCV not available for video preview")
                else:
                    widget.setText("Select a video to preview")

            if pref != "none" and cv2 is not None:
                self._video_backend = "opencv"
                self._cv_timer.timeout.connect(self._cv_video_tick)
            self._video_widget = widget

        self._image_widget = VideoPreviewLabel()
        self._image_widget.setStyleSheet("color: #9aa3ad;")
        self._image_widget.setMinimumSize(video_min_size)
        self._image_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        container = QtWidgets.QWidget()
        self._stack = QtWidgets.QStackedLayout(container)
        self._stack.addWidget(self._image_widget)
        self._stack.addWidget(self._video_widget)
        self._show_image_widget()
        return container

    def _on_position(self, position: int) -> None:
        if self._slider:
            self._slider.setValue(position)

    def _on_duration(self, duration: int) -> None:
        if self._slider:
            self._slider.setRange(0, duration)

    def _play_video_opencv(self, path: Path) -> None:
        if cv2 is None:
            self._status_label.setText("OpenCV not available for video playback.")
            return
        if self._cv_cap is not None:
            self._cv_cap.release()
        self._cv_cap = cv2.VideoCapture(str(path))
        if not self._cv_cap.isOpened():
            self._status_label.setText("Failed to open video.")
            return
        self._cv_fps = self._cv_cap.get(5) or 24.0  # CAP_PROP_FPS
        self._cv_frame_count = int(self._cv_cap.get(7) or 0)  # CAP_PROP_FRAME_COUNT
        if self._slider:
            self._slider.setRange(0, max(self._cv_frame_count - 1, 0))
        ok, frame = self._cv_cap.read()
        if ok:
            self._show_cv_frame(frame)
        self._cv_timer.stop()
        self._cv_playing = False
        if self._play_button:
            self._play_button.setText("Play")
        self._status_label.setText(f"Video: {path.name}")

    def _cv_video_tick(self) -> None:
        if self._cv_cap is None:
            return
        ok, frame = self._cv_cap.read()
        if not ok:
            self._cv_timer.stop()
            self._cv_playing = False
            if self._play_button:
                self._play_button.setText("Play")
            return
        self._show_cv_frame(frame)

    def _show_cv_frame(self, frame) -> None:
        if cv2 is None:
            return
        if frame is None:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(image)
        if isinstance(self._video_widget, VideoPreviewLabel):
            self._video_widget.set_base_pixmap(pixmap)
        elif isinstance(self._video_widget, QtWidgets.QLabel):
            self._video_widget.setPixmap(
                pixmap.scaled(
                    self._video_widget.size(),
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )

    def _show_image_widget(self) -> None:
        if self._stack is not None and self._image_widget is not None:
            self._stack.setCurrentWidget(self._image_widget)

    def _show_video_widget(self) -> None:
        if self._stack is not None and self._video_widget is not None:
            self._stack.setCurrentWidget(self._video_widget)
