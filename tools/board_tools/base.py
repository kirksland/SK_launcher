from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


class BoardToolSceneHost(Protocol):
    def focus_item(self) -> object | None: ...
    def graphics_scene(self) -> Any: ...
    def selected_tool_panel(self) -> str: ...
    def tool_panel_state(self, tool_id: str) -> dict[str, object]: ...
    def set_tool_panel_state(self, tool_id: str, state: dict[str, object]) -> None: ...
    def set_tool_stack_state(
        self,
        tool_id: str,
        state: dict[str, object],
        *,
        add_if_missing: bool = True,
    ) -> None: ...
    def update_scene_tool_settings(
        self,
        tool_id: str,
        settings: dict[str, object],
        *,
        schedule_preview: bool = True,
    ) -> None: ...
    def scene_tool_state(self, tool_id: str, factory: Callable[[], object]) -> object: ...
    def find_group_for_item(self, item: object) -> Any: ...
    def refresh_workspace(self, extra_rect: object | None = None) -> None: ...
    def commit_focus_override(self) -> None: ...
    def schedule_focus_preview(self) -> None: ...


@dataclass(slots=True, frozen=True)
class BoardToolSceneRuntime:
    refresh_handles: Callable[[BoardToolSceneHost], None]
    clear_handles: Callable[[BoardToolSceneHost, bool], None]
    panel_value_changed: Callable[[BoardToolSceneHost], None]
    mouse_press: Callable[[BoardToolSceneHost, object, object], bool]
    mouse_move: Callable[[BoardToolSceneHost, object, object], bool]
    mouse_release: Callable[[BoardToolSceneHost, object, object], bool]
    apply_to_focus_item: Callable[[BoardToolSceneHost], bool] | None = None
    reset_focus_item: Callable[[BoardToolSceneHost], bool] | None = None
