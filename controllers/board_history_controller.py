from __future__ import annotations

import json

from PySide6 import QtCore


class BoardHistoryController:
    """Owns board undo/redo history snapshots."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.w = board_controller.w

    def undo(self) -> None:
        board = self.board
        if board._history_index <= 0:
            return
        board._history_index -= 1
        payload = board._set_board_state(json.loads(board._history[board._history_index]))
        self._apply_history_payload(payload)

    def redo(self) -> None:
        board = self.board
        if board._history_index >= len(board._history) - 1:
            return
        board._history_index += 1
        payload = board._set_board_state(json.loads(board._history[board._history_index]))
        self._apply_history_payload(payload)

    def schedule_snapshot(self) -> None:
        board = self.board
        if board._loading or board._saving:
            return
        if board._history_timer is not None:
            return
        board._history_timer = QtCore.QTimer(self.w)
        board._history_timer.setSingleShot(True)
        board._history_timer.timeout.connect(self.capture_snapshot)
        board._history_timer.start(250)

    def capture_snapshot(self) -> None:
        board = self.board
        board._history_timer = None
        payload = board._current_board_state()
        serialized = json.dumps(payload, sort_keys=True)
        if board._history and board._history[board._history_index] == serialized:
            return
        if board._history_index < len(board._history) - 1:
            board._history = board._history[: board._history_index + 1]
        board._history.append(serialized)
        board._history_index = len(board._history) - 1

    def reset(self, payload: dict) -> None:
        board = self.board
        payload = board._set_board_state(payload)
        serialized = json.dumps(payload, sort_keys=True)
        board._history = [serialized]
        board._history_index = 0

    def _apply_history_payload(self, payload: dict) -> None:
        board = self.board
        board._loading = True
        board._scene.blockSignals(True)
        board._scene.clear()
        board._apply_payload(payload)
        board._scene.blockSignals(False)
        board._loading = False
        board._refresh_scene_workspace()
        board._dirty = True
        board._update_view_quality()
        board.update_visible_items()
