from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from .action import BoardAction, BoardMutationResult


@dataclass(frozen=True, slots=True)
class BoardMutationHooks:
    """Callbacks used by the board mutation pipeline."""

    sync_state: Callable[[], Mapping[str, object]]
    refresh_workspace: Callable[[], None]
    mark_dirty: Callable[[], None]
    schedule_history: Callable[[], None]
    schedule_groups: Callable[[], None]
    reveal_items: Callable[[list[object]], None]
    save: Callable[[], None]


def commit_board_action(
    action: BoardAction,
    hooks: BoardMutationHooks,
    *,
    reveal_items: Iterable[object] | None = None,
) -> BoardMutationResult:
    if action.update_groups:
        hooks.schedule_groups()
    state = hooks.sync_state()
    hooks.refresh_workspace()
    hooks.mark_dirty()
    history_scheduled = False
    if action.affects_history:
        hooks.schedule_history()
        history_scheduled = True
    items_to_reveal = list(reveal_items or [])
    if items_to_reveal:
        hooks.reveal_items(items_to_reveal)
    saved = False
    if action.should_save:
        hooks.save()
        saved = True
    return BoardMutationResult(
        action=action,
        state=state,
        dirty=True,
        history_scheduled=history_scheduled,
        saved=saved,
    )
