from __future__ import annotations

from typing import Callable

from PySide6 import QtCore

from core.board_state import ApplyPayloadState


class BoardApplyRuntime:
    def __init__(
        self,
        parent: QtCore.QObject,
        apply_state: ApplyPayloadState,
        tick_callback: Callable[[], None],
    ) -> None:
        self.apply_state = apply_state
        self.generation = 0
        self.total = 0
        self._timer = QtCore.QTimer(parent)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(tick_callback)

    def cancel(self) -> None:
        self.generation += 1
        self.total = 0
        if self._timer.isActive():
            self._timer.stop()
        self.apply_state.reset()

    def start(self, total: int) -> None:
        self.total = max(0, int(total))
        if self._timer.isActive():
            self._timer.stop()
        self.apply_state.generation = self.generation
        self._timer.start(0)

    def schedule_next(self, delay_ms: int = 10) -> None:
        self._timer.start(max(0, int(delay_ms)))

    def is_current(self) -> bool:
        return self.apply_state.generation == self.generation

    def in_progress(self) -> bool:
        return self._timer.isActive() or self.apply_state.has_pending()

    def done_count(self) -> int:
        if self.total <= 0:
            return 0
        return max(0, self.total - len(self.apply_state.queue))
