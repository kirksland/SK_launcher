import unittest

from core.board_state.overrides import (
    build_image_override,
    commit_image_override,
    commit_video_override,
    rename_override_key,
    remove_override,
)


class BoardStateOverridesTests(unittest.TestCase):
    def test_build_image_override_merges_existing_values(self) -> None:
        result = build_image_override(
            {"channel": "rgba"},
            tool_stack=[{"id": "crop"}],
            exr_channel="beauty",
            exr_gamma=2.4,
            exr_srgb=False,
        )
        self.assertEqual(result["channel"], "beauty")
        self.assertEqual(result["gamma"], 2.4)
        self.assertFalse(result["srgb"])
        self.assertEqual(result["tool_stack"], [{"id": "crop"}])
        self.assertNotIn("crop_left", result)
        self.assertNotIn("brightness", result)

    def test_commit_image_override_removes_entry_when_not_effective(self) -> None:
        overrides = {"plate.exr": {"brightness": 0.2}}
        changed = commit_image_override(
            overrides,
            "plate.exr",
            current=overrides["plate.exr"],
            effective=False,
            tool_stack=[],
        )
        self.assertTrue(changed)
        self.assertNotIn("plate.exr", overrides)

    def test_commit_video_override_updates_existing_entry(self) -> None:
        overrides = {}
        changed = commit_video_override(
            overrides,
            "clip.mov",
            current=None,
            effective=True,
            tool_stack=[{"id": "crop", "settings": {"right": 0.8}}],
        )
        self.assertTrue(changed)
        self.assertEqual(overrides["clip.mov"], {"tool_stack": [{"id": "crop", "settings": {"right": 0.8}}]})

    def test_rename_override_key_moves_entry(self) -> None:
        overrides = {"old.png": {"brightness": 0.1}}
        self.assertTrue(rename_override_key(overrides, "old.png", "new.png"))
        self.assertEqual(overrides, {"new.png": {"brightness": 0.1}})

    def test_remove_override_rejects_missing_key(self) -> None:
        self.assertFalse(remove_override({}, "missing.png"))


if __name__ == "__main__":
    unittest.main()
