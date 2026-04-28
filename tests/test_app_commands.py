import unittest
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from core.commands import (
    AppCommand,
    ActionContext,
    ActionResolver,
    ActionRule,
    CommandContext,
    CommandRegistry,
    CommandResult,
    build_shortcut_bindings,
    create_default_command_registry,
    find_shortcut_conflicts,
)
from controllers.app_command_controller import AppCommandController
from controllers.asset_command_dispatcher import AssetCommandDispatcher
from controllers.board.command_dispatcher import BoardCommandDispatcher
from controllers.app_shortcuts_controller import AppShortcutsController, should_block_shortcut_for_text_input
from controllers.projects_command_dispatcher import ProjectsCommandDispatcher
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

        self.assertEqual("I", registry.require("board.layout.auto").default_shortcuts[0])
        self.assertEqual("F", registry.require("board.view.fit").default_shortcuts[0])
        self.assertEqual("G", registry.require("board.group.toggle").default_shortcuts[0])
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

        toggle_result = dispatcher.execute_command("board.group.toggle")
        group_result = dispatcher.execute_command("board.group.create")
        ungroup_result = dispatcher.execute_command("board.group.ungroup")

        self.assertTrue(toggle_result.handled)
        self.assertTrue(group_result.handled)
        self.assertTrue(ungroup_result.handled)
        self.assertEqual(["toggle_group", "group", "ungroup"], board.calls)

    def test_board_command_dispatcher_executes_context_actions(self) -> None:
        board = _FakeBoardController()
        dispatcher = BoardCommandDispatcher(board)

        note_result = dispatcher.execute_command(
            "board.add.note",
            CommandContext("board", metadata={"scene_pos": "scene-pos"}),
        )
        convert_result = dispatcher.execute_command(
            "board.media.convert_video_to_sequence",
            CommandContext("board", metadata={"item": "video-item"}),
        )
        remove_result = dispatcher.execute_command("board.group.remove_selected")

        self.assertTrue(note_result.handled)
        self.assertTrue(convert_result.handled)
        self.assertTrue(remove_result.handled)
        self.assertEqual(
            ["note:scene-pos", "convert_video:video-item", "remove_from_group"],
            board.calls,
        )

    def test_action_resolver_lists_context_actions_with_shortcuts(self) -> None:
        registry = CommandRegistry(
            [
                _command("board.layout.auto", "board", ("I",)),
                _command("board.group.create", "board", ("Ctrl+G",)),
                _command("board.group.ungroup", "board", ("Ctrl+Shift+G",)),
                _command("projects.open", "projects", ("Enter",), domain="projects"),
            ]
        )
        bindings = build_shortcut_bindings(registry.list())
        resolver = ActionResolver(
            registry,
            bindings,
            [
                ActionRule("board.layout.auto", targets=("board.viewport",)),
                ActionRule("board.group.create", targets=("board.viewport",), when="can_group"),
                ActionRule("board.group.ungroup", targets=("board.viewport",), when="has_group"),
                ActionRule("projects.open", targets=("board.viewport",)),
            ],
        )

        actions = resolver.resolve(
            ActionContext(
                "board",
                target="board.viewport",
                metadata={"can_group": True, "has_group": False},
            )
        )

        by_id = {action.command_id: action for action in actions}
        self.assertEqual(["board.group.create", "board.layout.auto"], sorted(by_id))
        self.assertEqual("Ctrl+G", by_id["board.group.create"].shortcut)
        self.assertEqual("I", by_id["board.layout.auto"].shortcut)

    def test_action_resolver_supports_contextual_rule_labels(self) -> None:
        registry = CommandRegistry([_command("board.item.open", "board")])
        resolver = ActionResolver(
            registry,
            [],
            [
                ActionRule("board.item.open", targets=("board.groups_tree",), when="kind=image", label="Edit Image"),
                ActionRule("board.item.open", targets=("board.groups_tree",), when="kind=video", label="Open Video"),
            ],
        )

        actions = resolver.resolve(ActionContext("board", target="board.groups_tree", metadata={"kind": "video"}))

        self.assertEqual(["Open Video"], [action.label for action in actions])

    def test_board_command_dispatcher_executes_group_tree_actions(self) -> None:
        board = _FakeBoardController()
        dispatcher = BoardCommandDispatcher(board)

        add_result = dispatcher.execute_command(
            "board.group.add_selected_to_group",
            CommandContext("board", metadata={"group_key": 42}),
        )
        open_result = dispatcher.execute_command(
            "board.item.open",
            CommandContext("board", metadata={"kind": "video", "item": "video-item"}),
        )
        rename_result = dispatcher.execute_command(
            "board.item.rename",
            CommandContext("board", metadata={"tree_item": "tree-item", "info": ("image", 1)}),
        )

        self.assertTrue(add_result.handled)
        self.assertTrue(open_result.handled)
        self.assertTrue(rename_result.handled)
        self.assertEqual(
            ["add_to_group:42", "open_media:video-item", "rename:tree-item:('image', 1)"],
            board.calls,
        )

    def test_projects_command_dispatcher_sends_selection_to_board(self) -> None:
        projects = _FakeProjectsController()
        dispatcher = ProjectsCommandDispatcher(projects)

        result = dispatcher.execute_command(
            "projects.send_to_board",
            CommandContext("projects", metadata={"paths": ("C:/project/a.png", "C:/project/b.mov")}),
        )

        self.assertTrue(result.handled)
        self.assertEqual(["C:\\project\\a.png", "C:\\project\\b.mov"], [str(path) for path in projects.w.board_controller.paths])

    def test_asset_command_dispatcher_copies_normalized_path(self) -> None:
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        _ = app
        asset = _FakeAssetController()
        dispatcher = AssetCommandDispatcher(asset)

        result = dispatcher.execute_command(
            "asset.copy_path",
            CommandContext("asset_manager", metadata={"path": "C:\\project\\asset\\tree.usd"}),
        )

        self.assertTrue(result.handled)
        self.assertEqual("C:/project/asset/tree.usd", QtWidgets.QApplication.clipboard().text())
        self.assertEqual(["Copied: C:/project/asset/tree.usd"], asset.statuses)

    def test_app_command_controller_reports_missing_dispatcher(self) -> None:
        controller = AppCommandController()

        result = controller.execute("board.layout.auto")

        self.assertFalse(result.handled)
        self.assertIn("No dispatcher", result.message)

    def test_shortcut_controller_install_is_idempotent_until_settings_reload(self) -> None:
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        _ = app
        window = QtWidgets.QMainWindow()
        pages = QtWidgets.QStackedWidget(window)
        for _idx in range(6):
            pages.addWidget(QtWidgets.QWidget())
        pages.setCurrentIndex(2)
        window.pages = pages  # type: ignore[attr-defined]
        window.board_controller = _FakeBoardController()  # type: ignore[attr-defined]

        command_controller = AppCommandController()
        command_controller.register_dispatcher("board", BoardCommandDispatcher(window.board_controller))  # type: ignore[attr-defined]
        shortcuts = AppShortcutsController(window, command_controller, {})

        shortcuts.install()
        first_count = len(shortcuts.shortcuts)
        first_install_count = shortcuts.install_count
        first_shortcuts = tuple(shortcuts.shortcuts)

        shortcuts.install()

        self.assertEqual(6, first_count)
        self.assertEqual(first_install_count, shortcuts.install_count)
        self.assertEqual(first_shortcuts, tuple(shortcuts.shortcuts))

        shortcuts.reload_settings({"shortcuts": {"board.view.fit": ["Ctrl+F"]}})

        self.assertEqual(first_install_count + 1, shortcuts.install_count)
        self.assertEqual(6, len(shortcuts.shortcuts))
        self.assertTrue(any(shortcut.key().toString() == "Ctrl+F" for shortcut in shortcuts.shortcuts))
        shortcuts.clear()

    def test_shortcut_controller_key_event_fallback_routes_active_board_shortcut(self) -> None:
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        _ = app
        window = QtWidgets.QMainWindow()
        pages = QtWidgets.QStackedWidget(window)
        for _idx in range(6):
            pages.addWidget(QtWidgets.QWidget())
        pages.setCurrentIndex(2)
        window.pages = pages  # type: ignore[attr-defined]
        window.board_controller = _FakeBoardController()  # type: ignore[attr-defined]

        command_controller = AppCommandController()
        command_controller.register_dispatcher("board", BoardCommandDispatcher(window.board_controller))  # type: ignore[attr-defined]
        shortcuts = AppShortcutsController(window, command_controller, {})
        shortcuts.install()

        event = QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            QtCore.Qt.Key.Key_F,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )

        self.assertTrue(shortcuts.handle_key_event(event))
        self.assertEqual(["fit"], window.board_controller.calls)  # type: ignore[attr-defined]

        event = QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            QtCore.Qt.Key.Key_G,
            QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier,
        )

        self.assertTrue(shortcuts.handle_key_event(event))
        self.assertEqual(["fit", "ungroup"], window.board_controller.calls)  # type: ignore[attr-defined]
        shortcuts.clear()

    def test_shortcut_controller_only_blocks_editable_combo_focus(self) -> None:
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        window = QtWidgets.QMainWindow()
        combo = QtWidgets.QComboBox(window)
        combo.addItem("Current")
        window.setCentralWidget(combo)
        window.show()
        combo.setFocus()
        app.processEvents()

        shortcuts = AppShortcutsController(window, AppCommandController(), {})

        self.assertFalse(shortcuts._text_input_has_focus())

        combo.setEditable(True)
        line_edit = combo.lineEdit()
        self.assertIsNotNone(line_edit)
        line_edit.setFocus()
        app.processEvents()

        self.assertTrue(shortcuts._text_input_has_focus())
        window.close()


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

    def toggle_group_selection(self) -> None:
        self.calls.append("toggle_group")

    def ungroup_selected(self) -> None:
        self.calls.append("ungroup")

    def remove_selected_from_groups(self) -> None:
        self.calls.append("remove_from_group")

    def add_note_at(self, scene_pos) -> None:
        self.calls.append(f"note:{scene_pos}")

    def convert_video_to_sequence(self, item) -> None:
        self.calls.append(f"convert_video:{item}")

    def add_selected_to_group(self, group_key: int) -> None:
        self.calls.append(f"add_to_group:{group_key}")

    def open_image_item(self, item) -> None:
        self.calls.append(f"open_image:{item}")

    def open_media_item(self, item) -> None:
        self.calls.append(f"open_media:{item}")

    def edit_note(self, item) -> None:
        self.calls.append(f"edit_note:{item}")

    def begin_group_tree_rename(self, item, info) -> None:
        self.calls.append(f"rename:{item}:{info}")


class _FakeProjectBoardController:
    def __init__(self) -> None:
        self.paths = []

    def add_paths_from_selection(self, paths) -> None:
        self.paths.extend(paths)


class _FakeProjectsWindow:
    def __init__(self) -> None:
        self.board_controller = _FakeProjectBoardController()


class _FakeProjectsController:
    def __init__(self) -> None:
        self.w = _FakeProjectsWindow()


class _FakeAssetWindow:
    @staticmethod
    def _to_houdini_path(text: str) -> str:
        return text.replace("\\", "/")


class _FakeAssetController:
    def __init__(self) -> None:
        self.w = _FakeAssetWindow()
        self.statuses = []

    def set_asset_status(self, text: str) -> None:
        self.statuses.append(text)


if __name__ == "__main__":
    unittest.main()
