from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True, frozen=True)
class BoardToolSceneRuntime:
    refresh_handles: Callable[[object], None]
    clear_handles: Callable[[object, bool], None]
    panel_value_changed: Callable[[object], None]
    mouse_press: Callable[[object, object, object], bool]
    mouse_move: Callable[[object, object, object], bool]
    mouse_release: Callable[[object, object, object], bool]
    apply_to_focus_item: Callable[[object], bool] | None = None
    reset_focus_item: Callable[[object], bool] | None = None
