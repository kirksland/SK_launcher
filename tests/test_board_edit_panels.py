import unittest

from core.board_edit.panels import (
    default_panel_state,
    normalize_panel_state,
    panel_state_for_tool,
    panel_state_map_for_tools,
    tool_spec_for_panel,
)


class BoardEditPanelsTests(unittest.TestCase):
    def test_default_panel_state_uses_tool_spec_defaults(self) -> None:
        self.assertEqual(
            default_panel_state("bcs"),
            {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0},
        )

    def test_normalize_panel_state_uses_spec_rules(self) -> None:
        state = normalize_panel_state(
            "crop",
            {"left": -1.0, "top": 0.2, "right": 0.9, "bottom": 0.95},
        )
        self.assertEqual(state["left"], 0.0)
        self.assertEqual(state["right"], 0.9)
        self.assertLessEqual(state["top"] + state["bottom"], 0.950001)

    def test_panel_state_for_tool_reads_stack_settings(self) -> None:
        stack = [{"id": "vibrance", "enabled": True, "settings": {"amount": 0.35}}]
        self.assertEqual(panel_state_for_tool("vibrance", stack), {"amount": 0.35})

    def test_panel_state_map_for_tools_maps_panels_from_specs(self) -> None:
        stack = [
            {"id": "bcs", "enabled": True, "settings": {"brightness": 0.25, "contrast": 1.2, "saturation": 0.8}},
            {"id": "crop", "enabled": True, "settings": {"left": 0.1, "top": 0.0, "right": 0.2, "bottom": 0.0}},
        ]
        state_map = panel_state_map_for_tools(("bcs", "crop"), stack)
        self.assertEqual(
            state_map,
            {
                "bcs": {"brightness": 0.25, "contrast": 1.2, "saturation": 0.8},
                "crop": {"left": 0.1, "top": 0.0, "right": 0.2, "bottom": 0.0},
            },
        )

    def test_tool_spec_for_panel_exposes_ui_controls(self) -> None:
        spec = tool_spec_for_panel("bcs")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.ui_controls[0].key, "brightness")
        self.assertEqual(spec.ui_controls[0].label, "Brightness")


if __name__ == "__main__":
    unittest.main()
