import unittest

from core.board_edit.context import BoardEditContext
from core.board_edit.session import EditSessionState


class BoardEditContextTests(unittest.TestCase):
    def test_reset_for_kind_normalizes_kind_and_clears_session_stack(self) -> None:
        session = EditSessionState(
            focus_kind="image",
            tool_stack=[{"id": "bcs", "enabled": True, "settings": {}}],
            selected_tool_index=0,
        )
        context = BoardEditContext(session)

        context.reset_for_kind(" Video ")

        self.assertEqual(session.focus_kind, "video")
        self.assertEqual(session.tool_stack, [])
        self.assertEqual(session.selected_tool_index, -1)

    def test_ensure_stack_installs_default_stack_and_valid_selection(self) -> None:
        context = BoardEditContext(EditSessionState(focus_kind="image"))

        stack = context.ensure_stack(
            lambda _kind: [{"id": "bcs", "enabled": True, "settings": {"brightness": 0.25}}]
        )

        self.assertEqual(stack[0]["id"], "bcs")
        self.assertEqual(context.selected_index, 0)

    def test_selected_tool_entry_rejects_invalid_index(self) -> None:
        context = BoardEditContext(
            EditSessionState(
                focus_kind="image",
                tool_stack=[{"id": "bcs", "enabled": True, "settings": {}}],
                selected_tool_index=3,
            )
        )

        self.assertIsNone(context.selected_tool_entry())


if __name__ == "__main__":
    unittest.main()
