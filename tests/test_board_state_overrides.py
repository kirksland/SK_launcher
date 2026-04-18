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
            brightness=0.2,
            contrast=1.1,
            saturation=0.8,
            crop_left=0.1,
            crop_top=0.2,
            crop_right=0.9,
            crop_bottom=0.95,
            tool_stack=[{"id": "crop"}],
            exr_channel="beauty",
            exr_gamma=2.4,
            exr_srgb=False,
        )
        self.assertEqual(result["channel"], "beauty")
        self.assertEqual(result["gamma"], 2.4)
        self.assertFalse(result["srgb"])
        self.assertEqual(result["crop_left"], 0.1)

    def test_commit_image_override_removes_entry_when_not_effective(self) -> None:
        overrides = {"plate.exr": {"brightness": 0.2}}
        changed = commit_image_override(
            overrides,
            "plate.exr",
            current=overrides["plate.exr"],
            effective=False,
            brightness=0.0,
            contrast=1.0,
            saturation=1.0,
            crop_left=0.0,
            crop_top=0.0,
            crop_right=0.0,
            crop_bottom=0.0,
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
            crop_left=0.1,
            crop_top=0.2,
            crop_right=0.8,
            crop_bottom=0.9,
            tool_stack=[{"id": "crop"}],
        )
        self.assertTrue(changed)
        self.assertEqual(overrides["clip.mov"]["crop_right"], 0.8)

    def test_rename_override_key_moves_entry(self) -> None:
        overrides = {"old.png": {"brightness": 0.1}}
        self.assertTrue(rename_override_key(overrides, "old.png", "new.png"))
        self.assertEqual(overrides, {"new.png": {"brightness": 0.1}})

    def test_remove_override_rejects_missing_key(self) -> None:
        self.assertFalse(remove_override({}, "missing.png"))


if __name__ == "__main__":
    unittest.main()
