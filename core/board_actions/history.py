from __future__ import annotations

from dataclasses import dataclass

from .action import BoardAction


@dataclass(slots=True)
class BoardInteractionSession:
    kind: str = "scene_interaction"
    history_label: str | None = None
    depth: int = 0

    def begin(self, *, kind: str = "scene_interaction", history_label: str | None = None) -> None:
        if self.depth <= 0:
            self.kind = str(kind or "").strip().lower() or "scene_interaction"
            label = str(history_label or "").strip()
            self.history_label = label or None
        self.depth += 1

    def end_action(
        self,
        *,
        history: bool = True,
        update_groups: bool = True,
    ) -> BoardAction | None:
        if self.depth > 0:
            self.depth -= 1
        if self.depth > 0:
            return None
        action = BoardAction(
            self.kind,
            history_label=self.history_label,
            affects_history=history,
            update_groups=update_groups,
        )
        self.kind = "scene_interaction"
        self.history_label = None
        return action
