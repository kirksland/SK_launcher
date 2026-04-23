from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class BoardTimeline(QtWidgets.QWidget):
    playheadChanged = QtCore.Signal(int)
    selectedClipChanged = QtCore.Signal(int)
    scrubStateChanged = QtCore.Signal(bool)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._total = 0
        self._clips: list[tuple[int, int]] = []
        self._playhead = 0
        self._dragging = False
        self._selected_clip = -1
        self._zoom = 1.0
        self._view_start = 0
        self._view_end = 0
        self._panning = False
        self._pan_last_x = 0.0
        self._ruler_height = 20
        self.setMinimumHeight(64)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setMouseTracking(True)

    def set_data(self, total_frames: int, clips: list[tuple[int, int]], playhead: int) -> None:
        self._total = max(0, int(total_frames))
        self._clips = list(clips)
        self._playhead = max(0, min(int(playhead), max(0, self._total - 1)))
        if self._selected_clip >= len(self._clips):
            self._selected_clip = -1
        if self._selected_clip < 0 and self._clips:
            self._selected_clip = 0
        self._recompute_view()
        self.update()

    def set_selected_clip(self, index: int) -> None:
        if not self._clips:
            self._selected_clip = -1
        else:
            self._selected_clip = max(0, min(int(index), len(self._clips) - 1))
        self.update()

    def set_playhead(self, frame: int) -> None:
        self._playhead = max(0, min(int(frame), max(0, self._total - 1)))
        self._recompute_view()
        self.update()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if self._total <= 0:
            return
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_last_x = event.position().x()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if not self._dragging:
                self._dragging = True
                self.scrubStateChanged.emit(True)
            hit = self._hit_test_clip(event.position().x())
            if hit is not None:
                if hit != self._selected_clip:
                    self._selected_clip = hit
                    self.selectedClipChanged.emit(hit)
                self._set_playhead_from_x(event.position().x())
                self.update()
            else:
                self._set_playhead_from_x(event.position().x())

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if self._panning:
            dx = event.position().x() - self._pan_last_x
            self._pan_last_x = event.position().x()
            self._pan_by_pixels(dx)
            return
        if self._dragging:
            self._set_playhead_from_x(event.position().x())

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._dragging:
                self._dragging = False
                self.scrubStateChanged.emit(False)
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._panning = False

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        if self._total <= 0:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            self._pan_by_pixels(40 if delta < 0 else -40)
        else:
            factor = 1.2 if delta > 0 else 0.85
            self._zoom = max(1.0, min(40.0, self._zoom * factor))
            self._recompute_view(center=self._x_to_frame(event.position().x()))
        self.update()

    def _set_playhead_from_x(self, x_pos: float) -> None:
        frame = self._x_to_frame(x_pos)
        if frame != self._playhead:
            self._playhead = frame
            self._recompute_view()
            self.update()
            self.playheadChanged.emit(frame)

    def _recompute_view(self, center: Optional[int] = None) -> None:
        if self._total <= 0:
            self._view_start = 0
            self._view_end = 0
            return
        visible = int(max(2, self._total / self._zoom))
        half = visible // 2
        center = self._playhead if center is None else center
        start = max(0, center - half)
        end = min(self._total - 1, start + visible - 1)
        start = max(0, end - visible + 1)
        self._view_start = start
        self._view_end = end

    def _pan_by_pixels(self, dx: float) -> None:
        if self._total <= 0:
            return
        visible = max(1, self._view_end - self._view_start + 1)
        frames_per_px = visible / max(1.0, float(self.width()))
        delta_frames = int(dx * frames_per_px)
        if delta_frames == 0:
            return
        start = self._view_start - delta_frames
        start = max(0, min(start, max(0, self._total - visible)))
        self._view_start = start
        self._view_end = min(self._total - 1, start + visible - 1)
        self.update()

    def _x_to_frame(self, x_pos: float) -> int:
        x = max(0.0, min(float(x_pos), float(self.width())))
        ratio = x / max(1.0, float(self.width()))
        frame = int(self._view_start + ratio * max(1, self._view_end - self._view_start))
        return max(0, min(frame, max(0, self._total - 1)))

    def _frame_to_x(self, frame: int) -> float:
        if self._view_end <= self._view_start:
            return 0.0
        ratio = (frame - self._view_start) / max(1, self._view_end - self._view_start)
        return ratio * max(1.0, float(self.width()))

    def _hit_test_clip(self, x_pos: float) -> Optional[int]:
        if self._total <= 0:
            return None
        frame = self._x_to_frame(x_pos)
        for idx, (start, end) in enumerate(self._clips):
            if start <= frame <= end:
                return idx
        return None

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QtGui.QColor("#1f2329"))
        ruler_rect = QtCore.QRectF(8, 4, self.width() - 16, self._ruler_height)
        track_rect = QtCore.QRectF(8, self._ruler_height + 8, self.width() - 16, self.height() - self._ruler_height - 16)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#20252c"))
        painter.drawRoundedRect(ruler_rect, 4, 4)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#2a3038"))
        painter.drawRoundedRect(track_rect, 6, 6)
        if self._total > 0:
            for start, end in self._clips:
                left = track_rect.left() + self._frame_to_x(start)
                right = track_rect.left() + self._frame_to_x(end)
                rect = QtCore.QRectF(left, track_rect.top(), max(2.0, right - left), track_rect.height())
                painter.setBrush(QtGui.QColor(90, 140, 220, 200))
                painter.drawRoundedRect(rect, 5, 5)
            if 0 <= self._selected_clip < len(self._clips):
                s, e = self._clips[self._selected_clip]
                left = track_rect.left() + self._frame_to_x(s)
                right = track_rect.left() + self._frame_to_x(e)
                rect = QtCore.QRectF(left, track_rect.top(), max(2.0, right - left), track_rect.height())
                painter.setPen(QtGui.QPen(QtGui.QColor("#f2c14e"), 2))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
            visible = max(1, self._view_end - self._view_start + 1)
            major = 24
            target_labels = max(4, int(track_rect.width() / 120))
            step_major = max(major, int((visible / max(1, target_labels) + major - 1) // major) * major)
            minor = max(1, step_major // 4)
            painter.setPen(QtGui.QPen(QtGui.QColor("#3a404a"), 1))
            start_tick = (self._view_start // minor) * minor
            for f in range(start_tick, self._view_end + 1, minor):
                x = track_rect.left() + self._frame_to_x(f)
                if f % step_major == 0:
                    painter.setPen(QtGui.QPen(QtGui.QColor("#6c737d"), 1))
                    painter.drawLine(QtCore.QPointF(x, ruler_rect.top()), QtCore.QPointF(x, ruler_rect.bottom()))
                    painter.setPen(QtGui.QPen(QtGui.QColor("#9aa3ad"), 1))
                    painter.drawText(QtCore.QPointF(x + 2, ruler_rect.bottom() - 4), str(f))
                else:
                    painter.setPen(QtGui.QPen(QtGui.QColor("#3a404a"), 1))
                    painter.drawLine(QtCore.QPointF(x, ruler_rect.bottom() - 6), QtCore.QPointF(x, ruler_rect.bottom()))
            ph_x = track_rect.left() + self._frame_to_x(self._playhead)
            painter.setPen(QtGui.QPen(QtGui.QColor("#f2c14e"), 2))
            painter.drawLine(QtCore.QPointF(ph_x, ruler_rect.top()), QtCore.QPointF(ph_x, track_rect.bottom() + 6))
        painter.setPen(QtGui.QColor("#9aa3ad"))
        painter.drawText(
            self.rect().adjusted(8, 0, -8, 0),
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop,
            "Timeline",
        )
