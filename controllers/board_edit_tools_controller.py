from __future__ import annotations

from typing import Optional

from core.board_edit.panels import panel_state_map_for_tools, normalize_panel_state
from core.board_edit.session import EditVisualState, coerce_color_adjustments, default_tool_stack_for_kind, tool_stack_from_override
from core.board_edit.tool_stack import (
    append_tool,
    make_tool_entry,
    move_tool,
    normalize_tool_entries,
    remove_tool_at,
    tool_stack_is_effective,
    upsert_tool_settings,
)
from core.board_scene.items import BoardImageItem, BoardVideoItem
from tools.board_tools.edit import available_tools_for_kind, discover_edit_tools, get_edit_tool, list_edit_tools
from tools.board_tools.image import normalize_tool_stack
from tools.board_tools.registry import get_board_tool


class BoardEditToolsController:
    """Owns edit tool discovery, stack mutation, and tool panel sync."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.edit = board_controller.edit_context
        self.w = board_controller.w

    def refresh_registry(self) -> dict[str, object]:
        self.board._edit_tool_specs = discover_edit_tools(force=True)
        self.sync_defs_for_kind(self.edit.media_kind())
        return dict(self.board._edit_tool_specs)

    def available_tools(self, media_kind: str) -> list[dict[str, object]]:
        return [
            {
                "id": spec.id,
                "label": spec.label,
                "supports": tuple(spec.supports),
                "tags": tuple(spec.tags),
            }
            for spec in available_tools_for_kind(media_kind)
        ]

    def default_tool_state(self, tool_id: str) -> dict[str, object]:
        spec = get_edit_tool(tool_id)
        if spec is None:
            return {}
        return {
            "id": spec.id,
            "enabled": True,
            "settings": dict(spec.default_state()),
        }

    def normalize_tool_state(self, entry: object) -> dict[str, object]:
        entries = normalize_tool_entries([entry])
        return entries[0] if entries else {}

    def sync_defs_for_kind(self, media_kind: str) -> None:
        tools = available_tools_for_kind(media_kind)
        self.edit.set_tool_defs((spec.id, spec.label) for spec in tools)

    def connect_panel_signals(self) -> None:
        for spec in list_edit_tools():
            tool_id = str(getattr(spec, "id", "") or "").strip().lower()
            if not tool_id:
                continue
            tool_caps = get_board_tool(tool_id)
            has_scene = bool(getattr(tool_caps, "has_scene", False))
            for control in getattr(spec, "ui_controls", ()):
                slider = self.w.board_page.image_tool_control_slider(getattr(control, "key", ""))
                if slider is None:
                    continue
                if has_scene:
                    slider.valueChanged.connect(
                        lambda *_args, current_tool_id=tool_id: self.board._on_edit_scene_tool_panel_changed(current_tool_id)
                    )
                else:
                    slider.valueChanged.connect(
                        lambda *_args, current_tool_id=tool_id: self.board._on_edit_image_tool_panel_changed(
                            current_tool_id,
                            insert_at=getattr(get_edit_tool(current_tool_id), "stack_insert_at", None),
                        )
                    )
                slider.sliderPressed.connect(self.board._on_edit_preview_slider_pressed)
                slider.sliderReleased.connect(self.board._on_edit_preview_slider_released)

    def default_stack(self) -> list[dict[str, object]]:
        self.sync_defs_for_kind(self.edit.media_kind())
        return default_tool_stack_for_kind(self.edit.focus_kind)

    def ensure_stack(self) -> None:
        self.sync_defs_for_kind(self.edit.media_kind())
        self.edit.ensure_stack(lambda media_kind: default_tool_stack_for_kind(media_kind))

    def tool_label_for_id(self, tool_id: str) -> str:
        key = str(tool_id or "").strip().lower()
        for tid, label in self.edit.tool_defs:
            if tid == key:
                return label
        spec = get_edit_tool(key)
        if spec is not None:
            return spec.label
        return key or "Tool"

    def tool_entry_from_id(self, tool_id: str) -> dict[str, object]:
        entry = make_tool_entry(tool_id)
        if entry:
            return entry
        return {}

    def selected_tool_entry(self) -> Optional[dict[str, object]]:
        return self.edit.selected_tool_entry()

    def tool_panel_for_id(self, tool_id: str) -> str:
        spec = get_edit_tool(tool_id)
        if spec is None:
            return ""
        return str(getattr(spec, "ui_panel", "") or "").strip().lower()

    def selected_tool_panel(self) -> str:
        selected = self.selected_tool_entry()
        selected_id = str(selected.get("id", "")).strip().lower() if isinstance(selected, dict) else ""
        return self.tool_panel_for_id(selected_id)

    def panel_state_for_id(self, tool_id: str) -> dict[str, object]:
        spec = get_edit_tool(tool_id)
        if spec is None:
            return {}
        panel = str(getattr(spec, "ui_panel", "") or "").strip().lower()
        if not panel:
            return {}
        raw_state = self.w.board_page.current_image_tool_panel_state(panel)
        return normalize_panel_state(tool_id, raw_state)

    def sync_values_from_stack(self) -> None:
        visual = self.visual_state()
        self.w.board_page.set_image_adjust_labels(
            visual.brightness,
            visual.contrast,
            visual.saturation,
        )

    def visual_state(self) -> EditVisualState:
        return EditVisualState.from_tool_stack(self.current_stack())

    def sync_stack_ui(self) -> None:
        self.ensure_stack()
        self.sync_values_from_stack()
        self.w.board_page.set_image_tool_add_options(
            [(label, tool_id) for tool_id, label in self.edit.tool_defs]
        )
        rows = []
        for entry in self.edit.stack:
            tool_id = str(entry.get("id", "tool")).strip().lower()
            enabled = bool(entry.get("enabled", True))
            rows.append((self.tool_label_for_id(tool_id), enabled))
        self.w.board_page.set_image_tool_stack_items(rows, self.edit.selected_index)
        for panel, state in panel_state_map_for_tools(
            (tool_id for tool_id, _label in self.edit.tool_defs),
            self.edit.stack,
        ).items():
            self.w.board_page.set_image_tool_panel_state(panel, state)
        self.w.board_page.set_active_image_tool_panel(self.selected_tool_panel())
        self.board._refresh_focus_scene_handles()

    def current_stack(self) -> list[dict[str, object]]:
        self.ensure_stack()
        return normalize_tool_stack(self.edit.stack)

    def stack_from_override(self, override: object) -> list[dict[str, object]]:
        return tool_stack_from_override(override, self.edit.focus_kind)

    def coerce_color_adjustments(self, override: object) -> tuple[float, float, float]:
        return coerce_color_adjustments(override)

    def stack_is_effective(
        self,
        stack: object,
        brightness: float,
        contrast: float,
        saturation: float,
    ) -> bool:
        if not normalize_tool_stack(stack):
            return not (
                abs(float(brightness)) < 1e-6
                and abs(float(contrast) - 1.0) < 1e-6
                and abs(float(saturation) - 1.0) < 1e-6
            )
        return tool_stack_is_effective(stack)

    def reset_settings(self) -> None:
        self.ensure_stack()
        media_kind = self.edit.media_kind()
        for spec in available_tools_for_kind(media_kind):
            tool_id = str(spec.id).strip().lower()
            state = dict(spec.default_state())
            panel = str(getattr(spec, "ui_panel", "") or "").strip().lower()
            if panel:
                self.w.board_page.set_image_tool_panel_state(panel, state)
            default_for = tuple(
                str(value).strip().lower()
                for value in getattr(spec, "default_for", ())
                if str(value).strip()
            )
            self.set_tool_state(
                tool_id,
                state,
                add_if_missing=media_kind in default_for,
                insert_at=getattr(spec, "stack_insert_at", None),
            )
        self.sync_values_from_stack()
        self.board._apply_scene_tool_to_focus_item()
        if isinstance(self.board._focus_item, BoardVideoItem):
            self.board._commit_current_focus_video_override()
            self.board._schedule_video_focus_preview(self.board._edit_video_playhead, immediate=True)
            return
        selected_tool = self.selected_tool_entry()
        selected_id = str(selected_tool.get("id", "")).strip().lower() if isinstance(selected_tool, dict) else ""
        if selected_id:
            tool_caps = get_board_tool(selected_id)
            if tool_caps is not None and tool_caps.has_scene:
                self.board._on_edit_scene_tool_panel_changed(selected_id)
                return
            self.board._on_edit_image_tool_panel_changed(
                selected_id,
                insert_at=getattr(get_edit_tool(selected_id), "stack_insert_at", None),
            )

    def set_tool_state(
        self,
        tool_id: str,
        settings: dict[str, object],
        *,
        add_if_missing: bool = True,
        insert_at: int | None = None,
    ) -> None:
        self.ensure_stack()
        entries, idx = upsert_tool_settings(
            self.edit.stack,
            tool_id,
            settings,
            add_if_missing=add_if_missing,
            insert_at=insert_at,
        )
        self.edit.stack = entries
        if idx >= 0:
            self.edit.selected_index = idx

    def sync_panel_to_stack(self, tool_id: str, *, add_if_missing: bool = True, insert_at: int | None = None) -> None:
        settings = self.panel_state_for_id(tool_id)
        self.set_tool_state(
            tool_id,
            settings,
            add_if_missing=add_if_missing,
            insert_at=insert_at,
        )

    def on_stack_selection_changed(self, row: int) -> None:
        self.edit.selected_index = int(row)
        self.sync_stack_ui()

    def on_stack_add_clicked(self, tool_id: object = None) -> None:
        if self.board._edit_image_path is None:
            return
        if tool_id is None:
            tool_id = self.w.board_page.current_image_tool_add_id()
        tool_id = str(tool_id or "").strip().lower()
        if not tool_id:
            return
        self.ensure_stack()
        entries, idx = append_tool(self.edit.stack, tool_id)
        self.edit.stack = entries
        if idx >= 0:
            self.edit.selected_index = idx
        self.sync_stack_ui()
        self.board._schedule_edit_preview_update(channel=str(self.board._edit_exr_channel or ""))

    def on_stack_remove_index(self, idx: int) -> None:
        if self.board._edit_image_path is None:
            return
        self.remove_stack_index(int(idx))

    def remove_stack_index(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.edit.stack):
            return
        entries, next_idx = remove_tool_at(self.edit.stack, idx)
        self.edit.stack = entries
        if not self.edit.stack:
            self.edit.stack = self.default_stack()
            self.edit.selected_index = 0 if self.edit.stack else -1
        else:
            self.edit.selected_index = next_idx
        self.sync_stack_ui()
        if isinstance(self.board._focus_item, BoardVideoItem):
            self.board._commit_current_focus_video_override()
            self.board._apply_scene_tool_to_focus_item()
            self.board._schedule_video_focus_preview(self.board._edit_video_playhead, immediate=True)
        else:
            self.board._schedule_edit_preview_update(channel=str(self.board._edit_exr_channel or ""))

    def on_stack_up_clicked(self) -> None:
        idx = self.w.board_page.current_image_tool_stack_index()
        if idx <= 0 or idx >= len(self.edit.stack):
            return
        entries, next_idx = move_tool(self.edit.stack, idx, -1)
        self.edit.stack = entries
        self.edit.selected_index = next_idx
        self.sync_stack_ui()
        self.board._schedule_edit_preview_update(channel=str(self.board._edit_exr_channel or ""))

    def on_stack_down_clicked(self) -> None:
        idx = self.w.board_page.current_image_tool_stack_index()
        if idx < 0 or idx >= len(self.edit.stack) - 1:
            return
        entries, next_idx = move_tool(self.edit.stack, idx, 1)
        self.edit.stack = entries
        self.edit.selected_index = next_idx
        self.sync_stack_ui()
        self.board._schedule_edit_preview_update(channel=str(self.board._edit_exr_channel or ""))

    def schedule_focus_image_preview(self) -> None:
        if self.board._edit_image_path is None or not isinstance(self.board._focus_item, BoardImageItem):
            return
        if self.board._edit_exr_path is not None:
            channel = self.w.board_page.current_exr_channel_value()
            if channel:
                self.board._edit_exr_channel = str(channel)
                self.board._schedule_edit_preview_update(channel=str(channel))
            return
        self.board._schedule_edit_preview_update()

    def on_image_tool_panel_changed(
        self,
        tool_id: str,
        *,
        insert_at: int | None = None,
    ) -> None:
        panel_state = self.panel_state_for_id(tool_id)
        self.sync_panel_to_stack(tool_id, insert_at=insert_at)
        visual = self.visual_state()
        self.w.board_page.set_image_adjust_labels(
            visual.brightness,
            visual.contrast,
            visual.saturation,
        )
        self.board._commit_current_focus_image_override()
        self.schedule_focus_image_preview()
