import unittest

from core.board_edit.tool_stack import (
    extract_bcs_settings,
    extract_crop_settings,
    move_tool,
    tool_stack_is_effective,
    upsert_tool_settings,
)


class BoardToolStackTests(unittest.TestCase):
    def test_extract_bcs_settings_reads_normalized_values(self) -> None:
        stack = [{"id": "bcs", "enabled": True, "settings": {"brightness": "0.25", "contrast": 1.5, "saturation": 0.8}}]
        self.assertEqual(extract_bcs_settings(stack), (0.25, 1.5, 0.8))

    def test_extract_crop_settings_sanitizes_invalid_values(self) -> None:
        stack = [{"id": "crop", "enabled": True, "settings": {"left": -1.0, "top": 0.2, "right": 0.9, "bottom": 0.95}}]
        crop = extract_crop_settings(stack)
        self.assertIsNotNone(crop)
        assert crop is not None
        self.assertEqual(crop[0], 0.0)
        self.assertEqual(crop[2], 0.9)
        self.assertLessEqual(crop[1] + crop[3], 0.95)

    def test_tool_stack_is_effective_ignores_default_entries(self) -> None:
        stack = [{"id": "bcs", "enabled": True, "settings": {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0}}]
        self.assertFalse(tool_stack_is_effective(stack))

    def test_tool_stack_is_effective_detects_non_default_entry(self) -> None:
        stack = [{"id": "vibrance", "enabled": True, "settings": {"amount": 0.3}}]
        self.assertTrue(tool_stack_is_effective(stack))

    def test_upsert_tool_settings_updates_existing_entry(self) -> None:
        stack = [{"id": "bcs", "enabled": True, "settings": {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0}}]
        updated, index = upsert_tool_settings(stack, "bcs", {"brightness": 0.4})
        self.assertEqual(index, 0)
        self.assertEqual(extract_bcs_settings(updated), (0.4, 1.0, 1.0))

    def test_move_tool_reorders_entries(self) -> None:
        stack = [
            {"id": "bcs", "enabled": True, "settings": {}},
            {"id": "crop", "enabled": True, "settings": {}},
        ]
        moved, index = move_tool(stack, 0, 1)
        self.assertEqual(index, 1)
        self.assertEqual([entry["id"] for entry in moved], ["crop", "bcs"])


if __name__ == "__main__":
    unittest.main()
