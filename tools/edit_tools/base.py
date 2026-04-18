from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


ToolStateFactory = Callable[[], dict[str, Any]]
ToolNormalizeFn = Callable[[object], dict[str, Any]]
ToolEffectiveFn = Callable[[object], bool]


@dataclass(slots=True, frozen=True)
class ToolUiControlSpec:
    key: str
    label: str
    minimum: float
    maximum: float
    display_scale: float = 1.0
    display_suffix: str = ""
    display_decimals: int = 2
    display_signed: bool = False


@dataclass(slots=True)
class EditToolSpec:
    id: str
    label: str
    supports: tuple[str, ...]
    default_state_factory: ToolStateFactory
    normalize_state_fn: ToolNormalizeFn
    is_effective_fn: ToolEffectiveFn
    order: int = 100
    tags: tuple[str, ...] = field(default_factory=tuple)
    stack_insert_at: int | None = None
    ui_panel: str = ""
    ui_settings_keys: tuple[str, ...] = field(default_factory=tuple)
    ui_controls: tuple[ToolUiControlSpec, ...] = field(default_factory=tuple)

    def default_state(self) -> dict[str, Any]:
        state = self.default_state_factory()
        return state if isinstance(state, dict) else {}

    def normalize_state(self, state: object) -> dict[str, Any]:
        normalized = self.normalize_state_fn(state)
        return normalized if isinstance(normalized, dict) else self.default_state()

    def is_effective(self, state: object) -> bool:
        try:
            return bool(self.is_effective_fn(state))
        except Exception:
            return False

    def supports_kind(self, media_kind: str) -> bool:
        return str(media_kind or "").strip().lower() in self.supports
