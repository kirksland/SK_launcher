import unittest

from core.board_state.payload import (
    clone_payload,
    parse_image_display_overrides,
    payload_item_count,
    sync_board_state_overrides,
)
from core.board_state.migrations import BOARD_SCHEMA_VERSION, migrate_board_payload


def _tool_stack_from_override(value: object) -> list[dict[str, object]]:
    data = value if isinstance(value, dict) else {}
    stack = data.get("tool_stack", [])
    return list(stack) if isinstance(stack, list) else []


class BoardStatePayloadTests(unittest.TestCase):
    def test_clone_payload_normalizes_invalid_shape(self) -> None:
        payload = clone_payload({"items": "bad", "image_display_overrides": []})
        self.assertEqual(
            payload,
            {"items": [], "image_display_overrides": {}, "schema_version": BOARD_SCHEMA_VERSION},
        )

    def test_migrate_board_payload_upgrades_legacy_override_key(self) -> None:
        payload = migrate_board_payload(
            {
                "items": [{"type": "image"}, "bad"],
                "image_exr_display_overrides": {"plate.exr": {"channel": "rgba"}},
            }
        )

        self.assertEqual(payload["schema_version"], BOARD_SCHEMA_VERSION)
        self.assertEqual(payload["items"], [{"type": "image"}])
        self.assertEqual(payload["image_display_overrides"], {"plate.exr": {"channel": "rgba"}})
        self.assertNotIn("image_exr_display_overrides", payload)

    def test_payload_item_count_counts_only_dict_entries(self) -> None:
        payload = {"items": [{"type": "image"}, "bad", {"type": "note"}]}
        self.assertEqual(payload_item_count(payload), 2)

    def test_sync_board_state_overrides_keeps_only_referenced_media(self) -> None:
        board_state = {
            "items": [
                {"type": "image", "file": "a.exr"},
                {"type": "video", "file": "b.mov"},
                {"type": "note", "id": "n1"},
            ]
        }
        overrides = {
            "a.exr": {"channel": "beauty"},
            "b.mov": {"crop_left": 0.1},
            "c.png": {"brightness": 0.2},
        }
        synced = sync_board_state_overrides(board_state, overrides)
        self.assertEqual(synced["schema_version"], BOARD_SCHEMA_VERSION)
        self.assertEqual(set(synced["image_display_overrides"].keys()), {"a.exr", "b.mov"})

    def test_parse_image_display_overrides_supports_legacy_key(self) -> None:
        payload = {
            "image_exr_display_overrides": {
                "plate.exr": {
                    "channel": "rgba",
                    "gamma": "0.05",
                    "srgb": 0,
                    "brightness": "0.1",
                    "contrast": "1.2",
                    "saturation": "0.9",
                    "tool_stack": [{"id": "crop", "settings": {"left": 0.1}}],
                }
            }
        }
        parsed = parse_image_display_overrides(
            payload,
            tool_stack_from_override=_tool_stack_from_override,
        )
        self.assertEqual(parsed["plate.exr"]["channel"], "rgba")
        self.assertEqual(parsed["plate.exr"]["gamma"], 0.1)
        self.assertFalse(parsed["plate.exr"]["srgb"])
        self.assertEqual(parsed["plate.exr"]["tool_stack"], [{"id": "crop", "settings": {"left": 0.1}}])
        self.assertNotIn("brightness", parsed["plate.exr"])


if __name__ == "__main__":
    unittest.main()
