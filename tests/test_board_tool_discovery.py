import unittest

from tools.board_tools.base import BoardToolSceneRuntime
from tools.board_tools.edit import discover_edit_tools, get_edit_tool
from tools.board_tools.image import apply_image_tool_stack
from tools.board_tools.registry import discover_board_tools, get_board_tool, get_board_tool_scene_runtime


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

    def test_board_tool_scene_runtime_is_typed_and_exposed(self) -> None:
        runtime = get_board_tool_scene_runtime("crop")
        self.assertIsNotNone(runtime)
        self.assertIsInstance(runtime, BoardToolSceneRuntime)
        assert runtime is not None
        self.assertTrue(callable(runtime.mouse_press))
        self.assertTrue(callable(runtime.refresh_handles))

    def test_image_tool_registry_discovers_board_tool_image_modules(self) -> None:
        rgb = [[[128, 128, 128]]]
        output = apply_image_tool_stack(
            rgb,
            [{"id": "vibrance", "enabled": True, "settings": {"amount": 0.5}}],
        )
        self.assertIsNotNone(output)


if __name__ == "__main__":
    unittest.main()
