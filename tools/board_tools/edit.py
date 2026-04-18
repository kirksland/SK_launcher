from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from tools.board_tools.registry import discover_board_tools


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


_TOOL_REGISTRY: dict[str, EditToolSpec] = {}
_TOOLS_DISCOVERED = False


def register_edit_tool(spec: EditToolSpec) -> None:
    tool_id = str(getattr(spec, "id", "") or "").strip().lower()
    if not tool_id:
        return
    _TOOL_REGISTRY[tool_id] = spec


def discover_edit_tools(force: bool = False) -> dict[str, EditToolSpec]:
    global _TOOLS_DISCOVERED
    if _TOOLS_DISCOVERED and not force:
        return dict(_TOOL_REGISTRY)
    if force:
        _TOOL_REGISTRY.clear()
        _TOOLS_DISCOVERED = False
    discover_board_tools(force=force)
    _TOOLS_DISCOVERED = True
    return dict(_TOOL_REGISTRY)


def list_edit_tools() -> list[EditToolSpec]:
    discover_edit_tools()
    return sorted(
        _TOOL_REGISTRY.values(),
        key=lambda spec: (int(getattr(spec, "order", 100)), str(spec.label).lower(), str(spec.id)),
    )


def available_tools_for_kind(media_kind: str) -> list[EditToolSpec]:
    return [spec for spec in list_edit_tools() if spec.supports_kind(media_kind)]


def get_edit_tool(tool_id: str) -> EditToolSpec | None:
    discover_edit_tools()
    return _TOOL_REGISTRY.get(str(tool_id or "").strip().lower())
