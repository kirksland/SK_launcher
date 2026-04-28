from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from PySide6 import QtCore, QtGui, QtWidgets

from core.commands import CommandContext, ShortcutBinding, build_shortcut_bindings, find_shortcut_conflicts
from core.commands.shortcuts import normalize_shortcut_sequence
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
)


@dataclass(frozen=True, slots=True)
class ShortcutContextSnapshot:
    page_id: str
    active_scope: str
    focus_kind: str = ""
    text_input_has_focus: bool = False


@dataclass(frozen=True, slots=True)
class ShortcutInstallPlan:
    bindings: tuple[ShortcutBinding, ...]
    blocked_sequences: frozenset[str]
    signature: tuple[tuple[str, str, str, str], ...]


def should_block_shortcut_for_text_input(binding: ShortcutBinding, text_input_has_focus: bool) -> bool:
    if not text_input_has_focus:
        return False
    if binding.scope == GLOBAL_SCOPE:
        return False
    return binding.command_id != "board.focus.exit"


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
        self.installed_bindings: tuple[ShortcutBinding, ...] = ()
        self.conflicts = []
        self._install_signature: tuple[tuple[str, str, str, str], ...] = ()
        self._installed = False
        self.install_count = 0
        self.last_activation_status = ""

    def install(self, *, force: bool = False) -> None:
        plan = self._build_install_plan()
        if self._installed and not force and plan.signature == self._install_signature:
            self.last_activation_status = "install_skipped_unchanged"
            return
        self.clear()
        self._install_signature = plan.signature
        self.installed_bindings = tuple(
            binding for binding in plan.bindings if binding.normalized_sequence not in plan.blocked_sequences
        )
        for binding in self.installed_bindings:
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(binding.sequence), self.window)
            shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(lambda checked=False, binding=binding: self._activate(binding))
            self.shortcuts.append(shortcut)
        self._installed = True
        self.install_count += 1
        self.last_activation_status = f"installed:{len(self.shortcuts)}"

    def reload_settings(self, settings: Mapping[str, object] | None) -> None:
        self.settings = settings or {}
        self.install(force=True)

    def clear(self) -> None:
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts = []
        self.installed_bindings = ()
        self._installed = False

    def _build_install_plan(self) -> ShortcutInstallPlan:
        commands = [
            command
            for command in self.command_controller.registry.list()
            if self.command_controller.has_dispatcher(command.domain)
        ]
        bindings = tuple(build_shortcut_bindings(commands, self._shortcut_overrides()))
        self.conflicts = find_shortcut_conflicts(list(bindings))
        blocked_sequences = frozenset(conflict.sequence for conflict in self.conflicts)
        signature = tuple(
            sorted(
                (
                    binding.command_id,
                    binding.normalized_sequence,
                    binding.scope,
                    binding.source,
                )
                for binding in bindings
            )
        )
        return ShortcutInstallPlan(bindings, blocked_sequences, signature)

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

    def active_context_snapshot(self) -> ShortcutContextSnapshot:
        return ShortcutContextSnapshot(
            page_id=self.active_page_id(),
            active_scope=self.active_scope(),
            focus_kind=self._active_focus_kind(),
            text_input_has_focus=self._text_input_has_focus(),
        )

    def activate_sequence(self, sequence: object) -> bool:
        normalized = normalize_shortcut_sequence(_canonical_shortcut_text(sequence))
        if not normalized:
            return False
        snapshot = self.active_context_snapshot()
        for binding in self.installed_bindings:
            if binding.normalized_sequence != normalized:
                continue
            if not scopes_overlap(snapshot.active_scope, binding.scope):
                continue
            self._activate_with_snapshot(binding, snapshot)
            return self.last_activation_status.startswith("handled")
        return False

    def handle_key_event(self, event: QtGui.QKeyEvent) -> bool:
        if event.type() != QtCore.QEvent.Type.KeyPress:
            return False
        if event.isAutoRepeat():
            return False
        sequence = _sequence_from_key_event(event)
        if not sequence:
            return False
        return self.activate_sequence(sequence)

    def _activate(self, binding: ShortcutBinding) -> None:
        snapshot = self.active_context_snapshot()
        self._activate_with_snapshot(binding, snapshot)

    def _activate_with_snapshot(self, binding: ShortcutBinding, snapshot: ShortcutContextSnapshot) -> None:
        if not scopes_overlap(snapshot.active_scope, binding.scope):
            self.last_activation_status = (
                f"blocked_scope:{binding.command_id}:{binding.scope}!={snapshot.active_scope}"
            )
            return
        if should_block_shortcut_for_text_input(binding, snapshot.text_input_has_focus):
            self.last_activation_status = f"blocked_text_input:{binding.command_id}"
            return
        context = CommandContext(
            active_scope=snapshot.active_scope,
            page_id=snapshot.page_id,
            focus_kind=snapshot.focus_kind,
        )
        result = self.command_controller.execute(binding.command_id, context=context)
        self.last_activation_status = "handled" if result.handled else f"unhandled:{binding.command_id}"
        if not result.handled and result.message:
            self._show_status(result.message)

    def _shortcut_overrides(self) -> Mapping[str, object]:
        shortcuts = self.settings.get("shortcuts") if isinstance(self.settings, Mapping) else None
        return shortcuts if isinstance(shortcuts, Mapping) else {}

    def _text_input_has_focus(self) -> bool:
        focus_widget = QtWidgets.QApplication.focusWidget()
        if isinstance(focus_widget, QtWidgets.QComboBox):
            return focus_widget.isEditable()
        if isinstance(focus_widget, QtWidgets.QAbstractSpinBox):
            return False
        if isinstance(focus_widget, QtWidgets.QLineEdit):
            parent = focus_widget.parent()
            while parent is not None:
                if isinstance(parent, QtWidgets.QAbstractSpinBox):
                    return False
                if isinstance(parent, QtWidgets.QComboBox):
                    return parent.isEditable()
                parent = parent.parent()
        return isinstance(focus_widget, TEXT_INPUT_TYPES)

    def _active_focus_kind(self) -> str:
        board = getattr(self.window, "board_controller", None)
        return str(getattr(board, "_edit_focus_kind", "") or "").strip().lower()

    def _show_status(self, message: str) -> None:
        status_bar = getattr(self.window, "statusBar", None)
        if callable(status_bar):
            status_bar().showMessage(message, 2500)


def _sequence_from_key_event(event: QtGui.QKeyEvent) -> str:
    key = int(event.key())
    if key in (
        int(QtCore.Qt.Key.Key_Control),
        int(QtCore.Qt.Key.Key_Shift),
        int(QtCore.Qt.Key.Key_Alt),
        int(QtCore.Qt.Key.Key_Meta),
        int(QtCore.Qt.Key.Key_unknown),
    ):
        return ""
    modifiers = event.modifiers() & (
        QtCore.Qt.KeyboardModifier.ControlModifier
        | QtCore.Qt.KeyboardModifier.ShiftModifier
        | QtCore.Qt.KeyboardModifier.AltModifier
        | QtCore.Qt.KeyboardModifier.MetaModifier
    )
    try:
        return _canonical_shortcut_text(QtGui.QKeySequence(event.keyCombination()))
    except AttributeError:
        return _canonical_shortcut_text(QtGui.QKeySequence(modifiers | QtCore.Qt.Key(key)))


def _canonical_shortcut_text(sequence: object) -> str:
    if isinstance(sequence, QtGui.QKeySequence):
        text = sequence.toString(QtGui.QKeySequence.SequenceFormat.PortableText)
    else:
        text = str(sequence or "")
    if text.lower() == "esc":
        return "Escape"
    return text
