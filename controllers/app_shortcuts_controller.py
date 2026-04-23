from __future__ import annotations

from typing import Mapping

from PySide6 import QtCore, QtGui, QtWidgets

from core.commands import CommandContext, ShortcutBinding, build_shortcut_bindings, find_shortcut_conflicts
from core.commands.scopes import GLOBAL_SCOPE, scopes_overlap
from controllers.app_command_controller import AppCommandController


PAGE_SCOPES = {
    0: "projects",
    1: "asset_manager",
    2: "board",
    3: "client",
    4: "settings",
    5: "dev",
}

TEXT_INPUT_TYPES = (
    QtWidgets.QLineEdit,
    QtWidgets.QTextEdit,
    QtWidgets.QPlainTextEdit,
    QtWidgets.QAbstractSpinBox,
    QtWidgets.QComboBox,
)


class AppShortcutsController:
    """Installs global Qt shortcuts and routes them through app commands."""

    def __init__(
        self,
        window: QtWidgets.QMainWindow,
        command_controller: AppCommandController,
        settings: Mapping[str, object] | None = None,
    ) -> None:
        self.window = window
        self.command_controller = command_controller
        self.settings = settings or {}
        self.shortcuts: list[QtGui.QShortcut] = []
        self.conflicts = []

    def install(self) -> None:
        self.clear()
        commands = [
            command
            for command in self.command_controller.registry.list()
            if self.command_controller.has_dispatcher(command.domain)
        ]
        bindings = build_shortcut_bindings(
            commands,
            self._shortcut_overrides(),
        )
        self.conflicts = find_shortcut_conflicts(bindings)
        blocked_sequences = {conflict.sequence for conflict in self.conflicts}
        for binding in bindings:
            if binding.normalized_sequence in blocked_sequences:
                continue
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(binding.sequence), self.window)
            shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(lambda checked=False, binding=binding: self._activate(binding))
            self.shortcuts.append(shortcut)

    def reload_settings(self, settings: Mapping[str, object] | None) -> None:
        self.settings = settings or {}
        self.install()

    def clear(self) -> None:
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts = []

    def active_page_id(self) -> str:
        pages = getattr(self.window, "pages", None)
        if pages is None or not callable(getattr(pages, "currentIndex", None)):
            return GLOBAL_SCOPE
        return PAGE_SCOPES.get(int(pages.currentIndex()), GLOBAL_SCOPE)

    def active_scope(self) -> str:
        page_id = self.active_page_id()
        if page_id != "board":
            return page_id
        board = getattr(self.window, "board_controller", None)
        focus_kind = str(getattr(board, "_edit_focus_kind", "") or "").strip().lower()
        return "board.focus" if focus_kind else "board"

    def _activate(self, binding: ShortcutBinding) -> None:
        active_scope = self.active_scope()
        if not scopes_overlap(active_scope, binding.scope):
            return
        if binding.scope != GLOBAL_SCOPE and self._text_input_has_focus():
            return
        context = CommandContext(
            active_scope=active_scope,
            page_id=self.active_page_id(),
            focus_kind=self._active_focus_kind(),
        )
        result = self.command_controller.execute(binding.command_id, context=context)
        if not result.handled and result.message:
            self._show_status(result.message)

    def _shortcut_overrides(self) -> Mapping[str, object]:
        shortcuts = self.settings.get("shortcuts") if isinstance(self.settings, Mapping) else None
        return shortcuts if isinstance(shortcuts, Mapping) else {}

    def _text_input_has_focus(self) -> bool:
        focus_widget = QtWidgets.QApplication.focusWidget()
        return isinstance(focus_widget, TEXT_INPUT_TYPES)

    def _active_focus_kind(self) -> str:
        board = getattr(self.window, "board_controller", None)
        return str(getattr(board, "_edit_focus_kind", "") or "").strip().lower()

    def _show_status(self, message: str) -> None:
        status_bar = getattr(self.window, "statusBar", None)
        if callable(status_bar):
            status_bar().showMessage(message, 2500)
