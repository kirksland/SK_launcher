import unittest
from pathlib import Path
from uuid import uuid4

from core.asset_layout import resolve_asset_layout
from core.asset_schema import normalize_asset_schema


class AssetLayoutTests(unittest.TestCase):
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

    def test_resolved_layout_handles_local_publish_structure(self) -> None:
        root = self._make_case_dir("asset_layout_local")
        entity = root / "assets" / "tree_oak"
        (entity / "publish").mkdir(parents=True)
        (entity / "publish" / "tree_oak_v001.usd").write_text("", encoding="utf-8")
        (entity / "preview").mkdir(parents=True)
        (entity / "preview" / "thumb.jpg").write_text("", encoding="utf-8")

        layout = resolve_asset_layout(root, normalize_asset_schema({}))
        assets = layout.entities("asset")

        self.assertEqual([item.name for item in assets], ["tree_oak"])
        self.assertTrue(layout.representation_paths(assets[0], "usd"))
        self.assertTrue(layout.representation_paths(assets[0], "preview_image"))

    def test_resolved_layout_handles_mirrored_project_usd(self) -> None:
        root = self._make_case_dir("asset_layout_mirror")
        entity = root / "Library" / "Assets" / "bar_lamp"
        entity.mkdir(parents=True)
        (entity / "Textures").mkdir(parents=True)
        (entity / "Textures" / "lamp.jpg").write_text("", encoding="utf-8")
        mirror = root / "usd" / "assets" / "bar_lamp"
        mirror.mkdir(parents=True)
        (mirror / "payload.usdnc").write_text("", encoding="utf-8")
        (mirror / "bar_lamp.usd").write_text("", encoding="utf-8")

        schema = normalize_asset_schema(
            {
                "entity_roots": {"asset": ["Library/Assets"], "shot": ["shots"]},
                "representations": {
                    "usd": {"folders": ["usd/assets"], "extensions": [".usd", ".usdnc"]},
                    "preview_image": {"folders": ["Textures"], "extensions": [".jpg"]},
                },
            }
        )
        layout = resolve_asset_layout(root, schema)
        assets = layout.entities("asset")

        self.assertEqual([item.name for item in assets], ["bar_lamp"])
        usd_paths = layout.representation_paths(assets[0], "usd")
        self.assertEqual(sorted(path.name for path in usd_paths), ["bar_lamp.usd", "payload.usdnc"])
        preview_paths = layout.representation_paths(assets[0], "preview_image")
        self.assertEqual([path.name for path in preview_paths], ["lamp.jpg"])


if __name__ == "__main__":
    unittest.main()
