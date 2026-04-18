from __future__ import annotations

from PySide6 import QtCore


def play_button_label(playing: bool) -> str:
    return "Pause" if bool(playing) else "Play"


def clamp_playhead(frame: int, total_frames: int) -> int:
    total = max(0, int(total_frames))
    if total <= 0:
        return 0
    return max(0, min(int(frame), total - 1))


def loop_next_playhead(frame: int, total_frames: int) -> int:
    total = max(0, int(total_frames))
    if total <= 0:
        return 0
    return (int(frame) + 1) % total


def frame_label_text(frame: int) -> str:
    return f"Frame: {max(0, int(frame))}"


class TimerPlaybackRuntime(QtCore.QObject):
    tick = QtCore.Signal()
    stateChanged = QtCore.Signal(bool)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.tick.emit)
        self._fps = 24.0
        self._playing = False

    def is_playing(self) -> bool:
        return bool(self._playing)

    def set_fps(self, fps: float) -> None:
        try:
            self._fps = max(1.0, float(fps))
        except Exception:
            self._fps = 24.0
        if self._playing:
            self._timer.start(max(1, int(round(1000.0 / self._fps))))

    def stop(self) -> None:
        if not self._playing:
            return
        self._timer.stop()
        self._playing = False
        self.stateChanged.emit(False)

    def start(self) -> None:
        if self._playing:
            return
        self._timer.start(max(1, int(round(1000.0 / self._fps))))
        self._playing = True
        self.stateChanged.emit(True)

    def toggle(self) -> bool:
        if self._playing:
            self.stop()
        else:
            self.start()
        return self._playing


class SequencePlaybackRuntime(TimerPlaybackRuntime):
    pass


class VideoPlaybackRuntime(TimerPlaybackRuntime):
    pass
