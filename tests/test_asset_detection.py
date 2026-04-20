import unittest
from pathlib import Path
from uuid import uuid4

from core.asset_detection import detect_project_layout


class AssetDetectionTests(unittest.TestCase):
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

    def test_detect_project_layout_reads_standard_structure(self) -> None:
        root = self._make_case_dir("asset_detect_standard")
        shot = root / "shots" / "sh010"
        asset = root / "assets" / "tree_oak"
        (shot / "publish" / "lighting").mkdir(parents=True)
        (shot / "publish" / "lighting" / "sh010_lighting_v001.usd").write_text("", encoding="utf-8")
        (shot / "review").mkdir(parents=True)
        (shot / "review" / "sh010_lighting_v001.mp4").write_text("", encoding="utf-8")
        (shot / "preview").mkdir(parents=True)
        (shot / "preview" / "thumb.jpg").write_text("", encoding="utf-8")
        (asset / "publish").mkdir(parents=True)
        (asset / "publish" / "tree_oak_v001.usd").write_text("", encoding="utf-8")

        detected = detect_project_layout(root)

        self.assertEqual(detected.confidence, "high")
        self.assertEqual(detected.schema["entity_roots"]["shot"], ["shots"])
        self.assertEqual(detected.schema["entity_roots"]["asset"], ["assets"])
        self.assertEqual(detected.schema["representations"]["usd"]["folders"], ["publish"])
        self.assertIn("review", detected.schema["representations"]["review_video"]["folders"])
        self.assertIn("preview", detected.schema["representations"]["preview_image"]["folders"])
        self.assertEqual(detected.schema["contexts"], ["lighting"])

    def test_detect_project_layout_reads_alias_roots(self) -> None:
        root = self._make_case_dir("asset_detect_alias")
        shot = root / "seq" / "sq010_sh020"
        asset = root / "chars" / "hero"
        (shot / "publish" / "animation").mkdir(parents=True)
        (shot / "publish" / "animation" / "sq010_sh020_v003.usdc").write_text("", encoding="utf-8")
        (asset / "preview").mkdir(parents=True)
        (asset / "preview" / "hero.jpg").write_text("", encoding="utf-8")

        detected = detect_project_layout(root)

        self.assertEqual(detected.schema["entity_roots"]["shot"], ["seq"])
        self.assertEqual(detected.schema["entity_roots"]["asset"], ["chars"])
        self.assertEqual(detected.schema["contexts"], ["animation"])
        self.assertEqual(detected.confidence, "high")


if __name__ == "__main__":
    unittest.main()
