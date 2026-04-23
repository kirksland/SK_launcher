import unittest

from tools.board_tools.base import BoardToolSceneRuntime
from tools.board_tools.edit import EditToolSpec, ToolUiControlSpec, discover_edit_tools, get_edit_tool
from tools.board_tools.image import apply_image_tool_stack
from tools.board_tools.registry import discover_board_tools, get_board_tool, get_board_tool_scene_runtime
from tools.board_tools.validation import (
    format_board_tool_contract_issues,
    validate_board_tool_contracts,
    validate_edit_tool_spec,
)


class BoardToolDiscoveryTests(unittest.TestCase):
    def test_board_tool_registry_exposes_capabilities(self) -> None:
        tools = discover_board_tools(force=True)
        self.assertIn("bcs", tools)
        self.assertIn("crop", tools)
        self.assertTrue(tools["bcs"].has_tool)
        self.assertTrue(tools["bcs"].has_image)
        self.assertFalse(tools["bcs"].has_scene)
        self.assertTrue(tools["crop"].has_scene)
        self.assertFalse(tools["crop"].has_image)
        self.assertEqual(get_board_tool("vibrance").tool_id, "vibrance")  # type: ignore[union-attr]

    def test_edit_tool_registry_discovers_board_tool_packages(self) -> None:
        specs = discover_edit_tools(force=True)
        self.assertIn("bcs", specs)
        self.assertIn("crop", specs)
        spec = get_edit_tool("vibrance")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.ui_panel, "vibrance")

    def test_edit_tool_specs_declare_default_media_kinds(self) -> None:
        discover_edit_tools(force=True)
        bcs = get_edit_tool("bcs")
        crop = get_edit_tool("crop")
        self.assertIsNotNone(bcs)
        self.assertIsNotNone(crop)
        assert bcs is not None
        assert crop is not None
        self.assertIn("image", bcs.default_for)
        self.assertIn("video", crop.default_for)

    def test_board_tool_scene_runtime_is_typed_and_exposed(self) -> None:
        runtime = get_board_tool_scene_runtime("crop")
        self.assertIsNotNone(runtime)
        self.assertIsInstance(runtime, BoardToolSceneRuntime)
        assert runtime is not None
        self.assertTrue(callable(runtime.mouse_press))
        self.assertTrue(callable(runtime.refresh_handles))
        self.assertTrue(callable(runtime.reset_focus_item))

    def test_image_tool_registry_discovers_board_tool_image_modules(self) -> None:
        rgb = [[[128, 128, 128]]]
        output = apply_image_tool_stack(
            rgb,
            [{"id": "vibrance", "enabled": True, "settings": {"amount": 0.5}}],
        )
        self.assertIsNotNone(output)

    def test_current_board_tools_pass_contract_validation(self) -> None:
        issues = validate_board_tool_contracts(force=True)
        self.assertEqual([], issues)

    def test_edit_tool_contract_validation_reports_actionable_issues(self) -> None:
        spec = EditToolSpec(
            id="Bad Tool",
            label="",
            supports=("image",),
            default_state_factory=lambda: {"amount": 0.0},
            normalize_state_fn=lambda _state: {"amount": 0.0},
            is_effective_fn=lambda _state: False,
            default_for=("video",),
            stack_insert_at=-1,
            ui_panel="bad",
            ui_settings_keys=("other", "other"),
            ui_controls=(
                ToolUiControlSpec("missing", "Missing", 1.0, 0.0),
                ToolUiControlSpec("missing", "Missing Again", 0.0, 1.0),
            ),
        )
        codes = {issue.code for issue in validate_edit_tool_spec(spec)}
        self.assertIn("unnormalized_id", codes)
        self.assertIn("missing_label", codes)
        self.assertIn("default_for_not_supported", codes)
        self.assertIn("invalid_stack_insert_at", codes)
        self.assertIn("duplicate_value", codes)
        self.assertIn("ui_key_missing_from_state", codes)
        self.assertIn("control_key_missing_from_ui_settings", codes)
        self.assertIn("invalid_ui_control_range", codes)
        lines = format_board_tool_contract_issues(validate_edit_tool_spec(spec))
        self.assertTrue(any("[bad tool]" in line.lower() for line in lines))
        self.assertTrue(any("default_for_not_supported" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
