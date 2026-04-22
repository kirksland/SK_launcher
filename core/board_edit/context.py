from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from .session import EditSessionState
from .tool_stack import normalize_tool_entries


ToolStackFactory = Callable[[str | None], list[dict[str, object]]]


@dataclass(slots=True)
class BoardEditContext:
    """Small state facade shared by board edit controllers."""

    session: EditSessionState
    tool_defs: list[tuple[str, str]] = field(default_factory=list)

    @property
    def focus_kind(self) -> Optional[str]:
        return self.session.focus_kind

    @focus_kind.setter
    def focus_kind(self, value: Optional[str]) -> None:
        kind = str(value or "").strip().lower()
        self.session.focus_kind = kind or None

    @property
    def stack(self) -> list[dict[str, object]]:
        return self.session.tool_stack

    @stack.setter
    def stack(self, value: object) -> None:
        self.session.tool_stack = normalize_tool_entries(value)

    @property
    def selected_index(self) -> int:
        return int(self.session.selected_tool_index)

    @selected_index.setter
    def selected_index(self, value: object) -> None:
        try:
            self.session.selected_tool_index = int(value)
        except Exception:
            self.session.selected_tool_index = -1

    def reset_for_kind(self, media_kind: str | None) -> None:
        self.focus_kind = media_kind
        self.stack = []
        self.selected_index = -1

    def media_kind(self, default: str = "image") -> str:
        return str(self.focus_kind or default).strip().lower() or default

    def set_tool_defs(self, defs: Iterable[tuple[str, str]]) -> None:
        self.tool_defs = [(str(tool_id), str(label)) for tool_id, label in defs]

    def current_stack(self) -> list[dict[str, object]]:
        return normalize_tool_entries(self.stack)

    def ensure_stack(self, default_factory: ToolStackFactory) -> list[dict[str, object]]:
        tools = self.current_stack()
        if not tools:
            tools = normalize_tool_entries(default_factory(self.focus_kind))
        self.stack = tools
        if self.selected_index < 0 or self.selected_index >= len(self.stack):
            self.selected_index = 0 if self.stack else -1
        return self.current_stack()

    def selected_tool_entry(self) -> dict[str, object] | None:
        idx = self.selected_index
        stack = self.stack
        if idx < 0 or idx >= len(stack):
            return None
        entry = stack[idx]
        return entry if isinstance(entry, dict) else None

    def replace_stack(self, stack: object, selected_index: int | None = None) -> None:
        self.stack = stack
        if selected_index is not None:
            self.selected_index = selected_index
        elif self.selected_index >= len(self.stack):
            self.selected_index = len(self.stack) - 1
        if not self.stack:
            self.selected_index = -1
