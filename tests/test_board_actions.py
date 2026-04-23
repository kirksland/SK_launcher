import unittest

from core.board_actions import BoardAction, BoardMutationResult


class BoardActionTests(unittest.TestCase):
    def test_board_action_normalizes_kind_and_freezes_payload(self) -> None:
        payload = {"item": "a"}
        action = BoardAction(" Move_Items ", payload=payload, history_label=" Move ")
        payload["item"] = "b"

        self.assertEqual("move_items", action.kind)
        self.assertEqual("Move", action.history_label)
        self.assertEqual("a", action.payload["item"])
        with self.assertRaises(TypeError):
            action.payload["item"] = "c"  # type: ignore[index]

    def test_board_action_rejects_empty_kind(self) -> None:
        with self.assertRaises(ValueError):
            BoardAction("")

    def test_board_mutation_result_carries_action_flags(self) -> None:
        action = BoardAction("delete_items", affects_history=False, should_save=True)
        result = BoardMutationResult(
            action=action,
            state={"items": []},
            dirty=True,
            history_scheduled=False,
            saved=True,
        )

        self.assertEqual("delete_items", result.action.kind)
        self.assertTrue(result.dirty)
        self.assertFalse(result.history_scheduled)
        self.assertTrue(result.saved)


if __name__ == "__main__":
    unittest.main()
