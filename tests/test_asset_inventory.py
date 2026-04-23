import unittest
from pathlib import Path
from uuid import uuid4

from core.asset_inventory import build_entity_inventory, collect_library_source_files
from core.asset_layout import EntityRecord, resolve_asset_layout
from core.asset_schema import normalize_asset_schema


class AssetInventoryTests(unittest.TestCase):
    def _make_case_dir(self, name: str) -> Path:
        path = Path("tests") / ".tmp" / f"{name}_{uuid4().hex}"
        path.mkdir(parents=True, exist_ok=False)
        self.addCleanup(self._cleanup_dir, path)
        return path

    @staticmethod
    def _cleanup_dir(path: Path) -> None:
        if not path.exists():
            return
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()

    def test_library_inventory_lists_geometry_before_textures_with_thumbnail(self) -> None:
        root = self._make_case_dir("asset_inventory_library")
        entity = root / "dropbox" / "robot_raw"
        (entity / "Textures").mkdir(parents=True)
        (entity / "robot_raw.fbx").write_text("", encoding="utf-8")
        texture = entity / "Textures" / "robot_raw_BaseColor.exr"
        texture.write_text("", encoding="utf-8")

        files = collect_library_source_files(entity)

        self.assertEqual([item.relative_label for item in files], ["robot_raw.fbx", "Textures/robot_raw_BaseColor.exr"])
        self.assertEqual(files[0].kind, "source")
        self.assertEqual(files[1].kind, "image")
        self.assertEqual(files[1].thumbnail_path, texture)

    def test_build_inventory_uses_source_mode_for_library_entities(self) -> None:
        root = self._make_case_dir("asset_inventory_library_mode")
        entity = root / "vendor" / "chair_raw"
        entity.mkdir(parents=True)
        (entity / "chair_raw.obj").write_text("", encoding="utf-8")
        record = EntityRecord("asset", "library_asset", "chair_raw", entity)

        inventory = build_entity_inventory(
            entity_dir=entity,
            entity_type="asset",
            record=record,
            layout=None,
            context=None,
            context_label="All",
        )

        self.assertEqual(inventory.mode, "source_files")
        self.assertFalse(inventory.bundles)
        self.assertEqual([item.label for item in inventory.files], ["chair_raw.obj"])

    def test_build_inventory_uses_bundle_mode_for_pipeline_assets(self) -> None:
        root = self._make_case_dir("asset_inventory_pipeline")
        entity = root / "assets" / "tree"
        (entity / "publish").mkdir(parents=True)
        (entity / "publish" / "tree_v001.usd").write_text("", encoding="utf-8")
        (entity / "preview").mkdir(parents=True)
        (entity / "preview" / "tree.jpg").write_text("", encoding="utf-8")
        layout = resolve_asset_layout(root, normalize_asset_schema({}))
        record = layout.entities("asset")[0]

        inventory = build_entity_inventory(
            entity_dir=entity,
            entity_type="asset",
            record=record,
            layout=layout,
            context=None,
            context_label="All",
        )

        self.assertEqual(inventory.mode, "published_bundles")
        self.assertTrue(inventory.bundles)
        self.assertFalse(inventory.files)


if __name__ == "__main__":
    unittest.main()
