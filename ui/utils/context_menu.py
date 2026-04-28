from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from core.commands import ResolvedAction
from ui.utils.styles import menu_dark_style


def exec_context_menu(
    parent: QtWidgets.QWidget,
    actions: list[ResolvedAction],
    global_pos,
) -> str:
    visible_actions = [action for action in actions if action.visible]
    if not visible_actions:
        return ""

    menu = QtWidgets.QMenu(parent)
    menu.setStyleSheet(menu_dark_style())
    action_by_qaction: dict[QtGui.QAction, ResolvedAction] = {}
    for resolved in visible_actions:
        if resolved.separator_before and menu.actions():
            menu.addSeparator()
        qaction = menu.addAction(resolved.label)
        qaction.setEnabled(resolved.enabled)
        if resolved.shortcut:
            qaction.setShortcut(QtGui.QKeySequence(resolved.shortcut))
            qaction.setShortcutVisibleInContextMenu(True)
        action_by_qaction[qaction] = resolved

    chosen = menu.exec(global_pos)
    if chosen is None:
        return ""
    resolved = action_by_qaction.get(chosen)
    return resolved.command_id if resolved is not None and resolved.enabled else ""
