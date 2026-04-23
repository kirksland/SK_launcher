import unittest

from PySide6 import QtCore

from core.board_apply_runtime import BoardApplyRuntime
from core.board_state import ApplyPayloadState


class BoardApplyRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])

    def test_start_marks_generation_and_progress(self) -> None:
        state = ApplyPayloadState()
        state.queue.extend([{"id": 1}, {"id": 2}, {"id": 3}])
        runtime = BoardApplyRuntime(self._app, state, lambda: None)

        runtime.start(total=3)
        state.queue.popleft()

        self.assertTrue(runtime.is_current())
        self.assertEqual(runtime.total, 3)
        self.assertEqual(runtime.done_count(), 1)

    def test_cancel_invalidates_previous_generation_and_clears_state(self) -> None:
        state = ApplyPayloadState()
        state.queue.extend([{"id": 1}])
        runtime = BoardApplyRuntime(self._app, state, lambda: None)
        runtime.start(total=1)
        previous_generation = state.generation

        runtime.cancel()

        self.assertNotEqual(runtime.generation, previous_generation)
        self.assertFalse(state.has_pending())
        self.assertFalse(runtime.is_current())


if __name__ == "__main__":
    unittest.main()
