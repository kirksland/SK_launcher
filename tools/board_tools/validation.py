from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from tools.board_tools.edit import EditToolSpec, ToolUiControlSpec, discover_edit_tools
from tools.board_tools.registry import discover_board_tools, get_board_tool_scene_runtime


KNOWN_MEDIA_KINDS = frozenset({"image", "video", "sequence"})


@dataclass(slots=True, frozen=True)
class BoardToolContractIssue:
    tool_id: str
    code: str
    message: str


def validate_board_tool_contracts(force: bool = False) -> list[BoardToolContractIssue]:
    specs = discover_edit_tools(force=force)
    capabilities = discover_board_tools(force=False)
    issues: list[BoardToolContractIssue] = []

    for tool_id, capability in sorted(capabilities.items()):
        if capability.has_tool and tool_id not in specs:
            issues.append(
                BoardToolContractIssue(
                    tool_id,
                    "missing_edit_spec",
                    f"Tool package '{tool_id}' has tool.py but did not register an EditToolSpec.",
                )
            )
        if capability.has_image and not capability.has_tool:
            issues.append(
                BoardToolContractIssue(
                    tool_id,
                    "image_without_tool_spec",
                    f"Tool package '{tool_id}' has image.py but no tool.py.",
                )
            )
        if capability.has_scene and get_board_tool_scene_runtime(tool_id) is None:
            issues.append(
                BoardToolContractIssue(
                    tool_id,
                    "invalid_scene_runtime",
                    f"Tool package '{tool_id}' has scene.py but no valid SCENE_RUNTIME.",
                )
            )

    for tool_id, spec in sorted(specs.items()):
        if tool_id not in capabilities:
            issues.append(
                BoardToolContractIssue(
                    tool_id,
                    "orphan_edit_spec",
                    f"EditToolSpec '{tool_id}' is registered without a discovered tool package.",
                )
            )
        issues.extend(validate_edit_tool_spec(spec))

    return issues


def format_board_tool_contract_issues(issues: Iterable[BoardToolContractIssue]) -> list[str]:
    return [
        f"[{issue.tool_id}] {issue.code}: {issue.message}"
        for issue in issues
    ]


def validate_edit_tool_spec(spec: EditToolSpec) -> list[BoardToolContractIssue]:
    tool_id = _normalized_tool_id(getattr(spec, "id", ""))
    issue_id = tool_id or "<missing>"
    issues: list[BoardToolContractIssue] = []

    if not tool_id:
        issues.append(BoardToolContractIssue(issue_id, "missing_id", "EditToolSpec.id must be non-empty."))
    elif tool_id != str(spec.id):
        issues.append(
            BoardToolContractIssue(
                issue_id,
                "unnormalized_id",
                f"EditToolSpec.id should be lowercase/trimmed: expected '{tool_id}', got '{spec.id}'.",
            )
        )

    if not str(getattr(spec, "label", "") or "").strip():
        issues.append(BoardToolContractIssue(issue_id, "missing_label", "EditToolSpec.label must be non-empty."))

    supports = _clean_tuple(getattr(spec, "supports", ()))
    if not supports:
        issues.append(BoardToolContractIssue(issue_id, "missing_supports", "EditToolSpec.supports must be non-empty."))
    issues.extend(_validate_media_kinds(issue_id, "supports", supports))

    default_for = _clean_tuple(getattr(spec, "default_for", ()))
    issues.extend(_validate_media_kinds(issue_id, "default_for", default_for))
    for media_kind in default_for:
        if media_kind not in supports:
            issues.append(
                BoardToolContractIssue(
                    issue_id,
                    "default_for_not_supported",
                    f"default_for kind '{media_kind}' is not declared in supports.",
                )
            )

    if getattr(spec, "stack_insert_at", None) is not None:
        try:
            if int(spec.stack_insert_at) < 0:
                issues.append(
                    BoardToolContractIssue(issue_id, "invalid_stack_insert_at", "stack_insert_at must be >= 0.")
                )
        except Exception:
            issues.append(
                BoardToolContractIssue(issue_id, "invalid_stack_insert_at", "stack_insert_at must be an int.")
            )

    try:
        raw_default_state = spec.default_state_factory()
    except Exception:
        raw_default_state = None
        issues.append(
            BoardToolContractIssue(issue_id, "invalid_default_state", "default_state_factory() must not raise.")
        )
    if raw_default_state is not None and not isinstance(raw_default_state, dict):
        issues.append(
            BoardToolContractIssue(issue_id, "invalid_default_state", "default_state() must return a dict.")
        )
    default_state = _safe_dict(raw_default_state)

    try:
        raw_normalized_state = spec.normalize_state_fn(default_state)
    except Exception:
        raw_normalized_state = None
        issues.append(
            BoardToolContractIssue(issue_id, "invalid_normalized_state", "normalize_state_fn() must not raise.")
        )
    if raw_normalized_state is not None and not isinstance(raw_normalized_state, dict):
        issues.append(
            BoardToolContractIssue(issue_id, "invalid_normalized_state", "normalize_state() must return a dict.")
        )
    normalized_state = _safe_dict(raw_normalized_state)
    if not normalized_state:
        issues.append(
            BoardToolContractIssue(issue_id, "invalid_normalized_state", "normalize_state(default_state) must return a dict.")
        )
    try:
        spec.is_effective_fn(normalized_state)
    except Exception:
        issues.append(
            BoardToolContractIssue(issue_id, "invalid_effective_fn", "is_effective() must not raise.")
        )

    ui_panel = str(getattr(spec, "ui_panel", "") or "").strip().lower()
    ui_settings_keys = _clean_tuple(getattr(spec, "ui_settings_keys", ()))
    controls = tuple(getattr(spec, "ui_controls", ()) or ())
    if (ui_settings_keys or controls) and not ui_panel:
        issues.append(
            BoardToolContractIssue(
                issue_id,
                "missing_ui_panel",
                "Tools with ui_settings_keys or ui_controls should declare ui_panel.",
            )
        )

    issues.extend(_validate_unique_values(issue_id, "ui_settings_keys", ui_settings_keys))
    control_keys: list[str] = []
    for control in controls:
        if not isinstance(control, ToolUiControlSpec):
            issues.append(
                BoardToolContractIssue(issue_id, "invalid_ui_control", "ui_controls entries must be ToolUiControlSpec.")
            )
            continue
        control_key = str(control.key or "").strip()
        control_keys.append(control_key)
        if not control_key:
            issues.append(
                BoardToolContractIssue(issue_id, "invalid_ui_control_key", "ToolUiControlSpec.key must be non-empty.")
            )
        if float(control.minimum) >= float(control.maximum):
            issues.append(
                BoardToolContractIssue(
                    issue_id,
                    "invalid_ui_control_range",
                    f"Control '{control.key}' minimum must be lower than maximum.",
                )
            )
        if float(control.display_scale) == 0.0:
            issues.append(
                BoardToolContractIssue(
                    issue_id,
                    "invalid_ui_control_display_scale",
                    f"Control '{control.key}' display_scale must be non-zero.",
                )
            )

    issues.extend(_validate_unique_values(issue_id, "ui_controls", control_keys))
    for key in ui_settings_keys:
        if normalized_state and key not in normalized_state:
            issues.append(
                BoardToolContractIssue(
                    issue_id,
                    "ui_key_missing_from_state",
                    f"ui_settings key '{key}' is not present in normalized default state.",
                )
            )
    for key in control_keys:
        if key and ui_settings_keys and key not in ui_settings_keys:
            issues.append(
                BoardToolContractIssue(
                    issue_id,
                    "control_key_missing_from_ui_settings",
                    f"ui control key '{key}' is not declared in ui_settings_keys.",
                )
            )

    return issues


def _normalized_tool_id(value: object) -> str:
    return str(value or "").strip().lower()


def _clean_tuple(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(str(value or "").strip().lower() for value in values if str(value or "").strip())


def _safe_dict(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _validate_media_kinds(tool_id: str, field_name: str, values: tuple[str, ...]) -> list[BoardToolContractIssue]:
    issues: list[BoardToolContractIssue] = []
    for value in values:
        if value not in KNOWN_MEDIA_KINDS:
            issues.append(
                BoardToolContractIssue(
                    tool_id,
                    "unknown_media_kind",
                    f"{field_name} contains unknown media kind '{value}'.",
                )
            )
    return issues


def _validate_unique_values(
    tool_id: str,
    field_name: str,
    values: Iterable[str],
) -> list[BoardToolContractIssue]:
    issues: list[BoardToolContractIssue] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            issues.append(
                BoardToolContractIssue(
                    tool_id,
                    "duplicate_value",
                    f"{field_name} contains duplicate value '{value}'.",
                )
            )
        seen.add(value)
    return issues
