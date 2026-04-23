import unittest

from core.board_actions import BoardAction, BoardMutationHooks, BoardMutationResult, commit_board_action


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

    def test_commit_board_action_runs_common_pipeline(self) -> None:
        calls: list[str] = []

        hooks = BoardMutationHooks(
            sync_state=lambda: calls.append("sync") or {"items": [1]},
            refresh_workspace=lambda: calls.append("refresh"),
            mark_dirty=lambda: calls.append("dirty"),
            schedule_history=lambda: calls.append("history"),
            schedule_groups=lambda: calls.append("groups"),
            reveal_items=lambda items: calls.append(f"reveal:{len(items)}"),
            save=lambda: calls.append("save"),
        )

        result = commit_board_action(
            BoardAction("group_selection", should_save=True),
            hooks,
            reveal_items=["item"],
        )

        self.assertEqual(
            calls,
            ["groups", "sync", "refresh", "dirty", "history", "reveal:1", "save"],
        )
        self.assertEqual({"items": [1]}, dict(result.state))
        self.assertTrue(result.history_scheduled)
        self.assertTrue(result.saved)

    def test_commit_board_action_respects_side_effect_flags(self) -> None:
        calls: list[str] = []

        hooks = BoardMutationHooks(
            sync_state=lambda: calls.append("sync") or {},
            refresh_workspace=lambda: calls.append("refresh"),
            mark_dirty=lambda: calls.append("dirty"),
            schedule_history=lambda: calls.append("history"),
            schedule_groups=lambda: calls.append("groups"),
            reveal_items=lambda items: calls.append("reveal"),
            save=lambda: calls.append("save"),
        )

        result = commit_board_action(
            BoardAction("preview_only", affects_history=False, should_save=False, update_groups=False),
            hooks,
        )

        self.assertEqual(calls, ["sync", "refresh", "dirty"])
        self.assertFalse(result.history_scheduled)
        self.assertFalse(result.saved)


if __name__ == "__main__":
    unittest.main()
