import unittest

from core.commands import (
    AppCommand,
    CommandContext,
    CommandRegistry,
    CommandResult,
    build_shortcut_bindings,
    create_default_command_registry,
    find_shortcut_conflicts,
)
from controllers.app_command_controller import AppCommandController
from controllers.board.command_dispatcher import BoardCommandDispatcher
from controllers.app_shortcuts_controller import should_block_shortcut_for_text_input
from core.commands.registry import validate_command
from core.commands.shortcuts import normalize_shortcut_sequence
from core.commands.scopes import scopes_overlap


def _command(
    command_id: str,
    scope: str,
    shortcuts: tuple[str, ...] = (),
    domain: str = "board",
) -> AppCommand:
    return AppCommand(
        id=command_id,
        label=command_id,
        domain=domain,
        scope=scope,
        default_shortcuts=shortcuts,
    )


class AppCommandTests(unittest.TestCase):
    def test_default_command_registry_declares_initial_board_commands(self) -> None:
        registry = create_default_command_registry()

        self.assertEqual("L", registry.require("board.layout.auto").default_shortcuts[0])
        self.assertEqual("F", registry.require("board.view.fit").default_shortcuts[0])
        self.assertEqual("Ctrl+G", registry.require("board.group.create").default_shortcuts[0])
        self.assertEqual("Ctrl+Shift+G", registry.require("board.group.ungroup").default_shortcuts[0])
        self.assertEqual("Escape", registry.require("board.focus.exit").default_shortcuts[0])

    def test_command_registry_registers_and_lists_by_domain(self) -> None:
        registry = CommandRegistry(
            [
                _command("board.layout.auto", "board", ("L",)),
                _command("projects.open", "projects", ("Enter",), domain="projects"),
            ]
        )

        self.assertEqual("board.layout.auto", registry.require("BOARD.LAYOUT.AUTO").id)
        self.assertEqual(["board.layout.auto"], [cmd.id for cmd in registry.list_by_domain("board")])
        self.assertEqual(["projects.open"], [cmd.id for cmd in registry.list_by_scope("projects")])

    def test_command_registry_rejects_duplicate_ids(self) -> None:
        registry = CommandRegistry([_command("board.layout.auto", "board")])

        with self.assertRaises(ValueError):
            registry.register(_command("BOARD.LAYOUT.AUTO", "board"))

    def test_command_validation_reports_unknown_scope(self) -> None:
        command = _command("board.unknown", "not_a_scope")
        codes = {issue.code for issue in validate_command(command)}

        self.assertIn("unknown_scope", codes)

    def test_shortcut_bindings_use_defaults_and_user_overrides(self) -> None:
        commands = [
            _command("board.layout.auto", "board", ("L",)),
            _command("board.view.fit", "board", ("F",)),
            _command("board.focus.exit", "board.focus", ("Escape",)),
        ]
        bindings = build_shortcut_bindings(
            commands,
            overrides={
                "board.layout.auto": ["Ctrl+L"],
                "board.focus.exit": [],
            },
        )

        by_command = {binding.command_id: binding for binding in bindings}
        self.assertEqual("Ctrl+L", by_command["board.layout.auto"].sequence)
        self.assertEqual("user", by_command["board.layout.auto"].source)
        self.assertEqual("F", by_command["board.view.fit"].sequence)
        self.assertNotIn("board.focus.exit", by_command)

    def test_shortcut_conflicts_detect_global_and_hierarchical_scope_overlap(self) -> None:
        commands = [
            _command("app.palette", "global", ("Ctrl+K",), domain="app"),
            _command("board.search", "board", ("Ctrl+K",)),
            _command("board.edit.local", "board.edit", ("L",)),
            _command("board.layout.auto", "board", ("L",)),
            _command("projects.filter", "projects", ("L",), domain="projects"),
        ]
        conflicts = find_shortcut_conflicts(build_shortcut_bindings(commands))
        conflict_ids = {conflict.command_ids for conflict in conflicts}

        self.assertIn(("app.palette", "board.search"), conflict_ids)
        self.assertIn(("board.edit.local", "board.layout.auto"), conflict_ids)
        self.assertNotIn(("board.layout.auto", "projects.filter"), conflict_ids)

    def test_text_input_filter_allows_board_focus_exit_escape(self) -> None:
        layout_binding = build_shortcut_bindings([
            _command("board.layout.auto", "board", ("L",)),
        ])[0]
        exit_binding = build_shortcut_bindings([
            _command("board.focus.exit", "board.focus", ("Escape",)),
        ])[0]

        self.assertTrue(should_block_shortcut_for_text_input(layout_binding, True))
        self.assertFalse(should_block_shortcut_for_text_input(exit_binding, True))

    def test_scope_overlap_and_sequence_normalization(self) -> None:
        self.assertTrue(scopes_overlap("global", "board"))
        self.assertTrue(scopes_overlap("board", "board.edit"))
        self.assertFalse(scopes_overlap("board", "projects"))
        self.assertEqual("ctrl+k", normalize_shortcut_sequence(" Ctrl + K "))

    def test_command_context_and_result_are_normalized(self) -> None:
        context = CommandContext(" Board.Edit ", page_id=" Board ", metadata={"a": 1})
        result = CommandResult(" Board.Layout.Auto ", handled=True, message=" Done ")

        self.assertEqual("board.edit", context.active_scope)
        self.assertEqual("board", context.page_id)
        self.assertEqual(1, context.metadata["a"])
        self.assertEqual("board.layout.auto", result.command_id)
        self.assertEqual("Done", result.message)
        with self.assertRaises(TypeError):
            context.metadata["a"] = 2  # type: ignore[index]

    def test_app_command_controller_routes_to_domain_dispatcher(self) -> None:
        board = _FakeBoardController()
        controller = AppCommandController()
        controller.register_dispatcher("board", BoardCommandDispatcher(board))

        self.assertTrue(controller.has_dispatcher("BOARD"))
        result = controller.execute("board.layout.auto", CommandContext("board"))

        self.assertTrue(result.handled)
        self.assertEqual(["layout"], board.calls)

    def test_board_command_dispatcher_executes_grid_toggle(self) -> None:
        board = _FakeBoardController()
        dispatcher = BoardCommandDispatcher(board)

        result = dispatcher.execute_command("board.view.toggle_grid")

        self.assertTrue(result.handled)
        self.assertFalse(board.w.board_page.grid_toggle.isChecked())

    def test_board_command_dispatcher_executes_group_commands(self) -> None:
        board = _FakeBoardController()
        dispatcher = BoardCommandDispatcher(board)

        group_result = dispatcher.execute_command("board.group.create")
        ungroup_result = dispatcher.execute_command("board.group.ungroup")

        self.assertTrue(group_result.handled)
        self.assertTrue(ungroup_result.handled)
        self.assertEqual(["group", "ungroup"], board.calls)

    def test_app_command_controller_reports_missing_dispatcher(self) -> None:
        controller = AppCommandController()

        result = controller.execute("board.layout.auto")

        self.assertFalse(result.handled)
        self.assertIn("No dispatcher", result.message)


class _FakeGridToggle:
    def __init__(self) -> None:
        self._checked = True

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, value: bool) -> None:
        self._checked = bool(value)


class _FakeBoardPage:
    def __init__(self) -> None:
        self.grid_toggle = _FakeGridToggle()


class _FakeWindow:
    def __init__(self) -> None:
        self.board_page = _FakeBoardPage()


class _FakeBoardController:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.w = _FakeWindow()

    def layout_selection_grid(self) -> None:
        self.calls.append("layout")

    def fit_view(self) -> None:
        self.calls.append("fit")

    def exit_focus_mode(self) -> None:
        self.calls.append("exit_focus")

    def add_group(self) -> None:
        self.calls.append("group")

    def ungroup_selected(self) -> None:
        self.calls.append("ungroup")


if __name__ == "__main__":
    unittest.main()
