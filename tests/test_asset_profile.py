import unittest
from pathlib import Path
from uuid import uuid4

from core.asset_detection import detect_project_layout
from core.asset_layout import resolve_asset_layout
from core.asset_profile import profile_entity_collection


class AssetProfileTests(unittest.TestCase):
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

    def test_profiles_pipeline_asset_collection_by_content(self) -> None:
        root = self._make_case_dir("profile_pipeline")
        asset = root / "whatever_name" / "tree"
        (asset / "publish" / "modeling").mkdir(parents=True)
        (asset / "publish" / "modeling" / "tree_geo_v001.usdnc").write_text("", encoding="utf-8")
        (asset / "preview").mkdir()
        (asset / "preview" / "tree.png").write_text("", encoding="utf-8")

        profile = profile_entity_collection(root / "whatever_name")

        self.assertEqual(profile.role, "pipeline_asset")
        self.assertGreater(profile.pipeline_score, profile.library_score)
        self.assertIn("published USD files", profile.evidence)

    def test_profiles_library_asset_collection_by_content(self) -> None:
        root = self._make_case_dir("profile_library")
        asset = root / "vendor_drop" / "chair"
        (asset / "Textures").mkdir(parents=True)
        (asset / "chair.obj").write_text("", encoding="utf-8")
        (asset / "Textures" / "chair_1001_BaseColor.exr").write_text("", encoding="utf-8")

        profile = profile_entity_collection(root / "vendor_drop")

        self.assertEqual(profile.role, "library_asset")
        self.assertGreater(profile.library_score, profile.pipeline_score)
        self.assertIn("direct source geometry files", profile.evidence)

    def test_detection_separates_pipeline_and_library_sources_with_arbitrary_names(self) -> None:
        root = self._make_case_dir("profile_detect")
        pipe = root / "production_items" / "lamp"
        lib = root / "incoming_models" / "lamp"
        (pipe / "publish" / "lookdev").mkdir(parents=True)
        (pipe / "publish" / "lookdev" / "lamp_mat_v001.usdnc").write_text("", encoding="utf-8")
        (lib / "Textures").mkdir(parents=True)
        (lib / "lamp.obj").write_text("", encoding="utf-8")
        (lib / "Textures" / "lamp_BaseColor.exr").write_text("", encoding="utf-8")

        detected = detect_project_layout(root)
        layout = resolve_asset_layout(root, detected.schema)

        self.assertEqual([entity.name for entity in layout.entities_by_role("pipeline_asset")], ["lamp"])
        self.assertEqual([entity.name for entity in layout.entities_by_role("library_asset")], ["lamp"])
        roles = {source["path"]: source["role"] for source in detected.schema["entity_sources"]}
        self.assertEqual(roles["production_items"], "pipeline_asset")
        self.assertEqual(roles["incoming_models"], "library_asset")


if __name__ == "__main__":
    unittest.main()
