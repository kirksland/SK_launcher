import unittest

from core.asset_schema import (
    default_asset_schema,
    entity_root_candidates,
    normalize_asset_schema,
    representation_extensions,
    representation_folders,
)


class AssetSchemaTests(unittest.TestCase):
    def test_default_schema_exposes_entity_roots_and_representations(self) -> None:
        schema = default_asset_schema()
        self.assertEqual(schema["schema_version"], 1)
        self.assertEqual(entity_root_candidates(schema, "shot"), ["shots"])
        self.assertEqual(entity_root_candidates(schema, "asset"), ["assets"])
        self.assertEqual(representation_folders(schema, "usd"), ["publish", "root"])
        self.assertIn(".usd", representation_extensions(schema, "usd"))
        self.assertEqual(schema["usd_search"], ["publish", "root"])

    def test_legacy_usd_search_is_upgraded_to_representation_folders(self) -> None:
        schema = normalize_asset_schema({"usd_search": ["Publish", "cache/usd"]})
        self.assertEqual(representation_folders(schema, "usd"), ["publish", "cache/usd"])
        self.assertEqual(schema["usd_search"], ["publish", "cache/usd"])

    def test_partial_schema_overrides_default_values(self) -> None:
        schema = normalize_asset_schema(
            {
                "preset_id": "studio_a",
                "contexts": ["Animation", "Lighting", "Lighting"],
                "entity_roots": {
                    "shot": ["seq", "shots"],
                    "asset": ["chars", "props"],
                },
                "representations": {
                    "review_video": {
                        "folders": ["playblast", "review"],
                        "extensions": ["mov", ".mp4"],
                    }
                },
            }
        )
        self.assertEqual(schema["preset_id"], "studio_a")
        self.assertEqual(schema["contexts"], ["animation", "lighting"])
        self.assertEqual(entity_root_candidates(schema, "shot"), ["seq", "shots"])
        self.assertEqual(entity_root_candidates(schema, "asset"), ["chars", "props"])
        self.assertEqual(representation_folders(schema, "review_video"), ["playblast", "review"])
        self.assertEqual(representation_extensions(schema, "review_video"), [".mov", ".mp4"])


if __name__ == "__main__":
    unittest.main()
