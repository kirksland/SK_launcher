import unittest
from pathlib import Path
from uuid import uuid4

from PySide6 import QtCore

from ui.utils.thumbnails import (
    _preferred_exr_channel,
    asset_exr_cache_path,
    asset_exr_thumb_cache_dir,
    is_exr_path,
)


class ThumbnailTests(unittest.TestCase):
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

    def test_preferred_exr_channel_prefers_root_rgb(self) -> None:
        self.assertEqual(_preferred_exr_channel(["R", "G", "B", "A"]), "RGBA")

    def test_preferred_exr_channel_prefers_named_rgb_group(self) -> None:
        self.assertEqual(
            _preferred_exr_channel(["shadow.R", "shadow.G", "shadow.B", "albedo.R"]),
            "shadow.RGB",
        )

    def test_preferred_exr_channel_falls_back_to_first_channel(self) -> None:
        self.assertEqual(_preferred_exr_channel(["depth", "mask"]), "depth")

    def test_is_exr_path_is_case_insensitive(self) -> None:
        self.assertTrue(is_exr_path(Path("beauty.EXR")))
        self.assertFalse(is_exr_path(Path("beauty.png")))

    def test_asset_exr_thumb_cache_dir_is_project_scoped(self) -> None:
        root = self._make_case_dir("asset_exr_cache")

        cache_dir = asset_exr_thumb_cache_dir(root)

        self.assertEqual(cache_dir, root / ".skyforge_cache" / "asset_exr_thumbs")
        self.assertTrue(cache_dir.exists() if cache_dir is not None else False)

    def test_asset_exr_cache_path_changes_with_render_size(self) -> None:
        root = self._make_case_dir("asset_exr_key")
        image = root / "plate.exr"
        image.write_text("fake", encoding="utf-8")

        small = asset_exr_cache_path(root, image, QtCore.QSize(48, 30))
        large = asset_exr_cache_path(root, image, QtCore.QSize(420, 200))

        self.assertIsNotNone(small)
        self.assertIsNotNone(large)
        self.assertNotEqual(small, large)


if __name__ == "__main__":
    unittest.main()
