import unittest
from pathlib import Path
from uuid import uuid4

from core.board_media_cache import BoardMediaCache


class BoardMediaCacheTests(unittest.TestCase):
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

    def test_pixmap_cache_returns_only_matching_mtime(self) -> None:
        cache = BoardMediaCache()
        path = Path("example.png")
        pixmap = object()

        cache.store_pixmap(cache.pixmaps, path, 128, 10.0, pixmap)

        self.assertIs(cache.cached_pixmap(cache.pixmaps, path, 128, 10.0), pixmap)
        self.assertIsNone(cache.cached_pixmap(cache.pixmaps, path, 128, 11.0))

    def test_project_thumb_cache_dir_is_project_scoped_and_resettable(self) -> None:
        root = self._make_case_dir("board_media_cache")
        cache = BoardMediaCache()

        first = cache.project_thumb_cache_dir(root)
        second = cache.project_thumb_cache_dir(root)
        cache.visible_images.add(42)
        cache.reset_project_scoped()

        self.assertEqual(first, root / ".skyforge_cache" / "exr_thumbs")
        self.assertEqual(second, first)
        self.assertTrue(first.exists() if first is not None else False)
        self.assertIsNone(cache.thumb_cache_dir)
        self.assertFalse(cache.visible_images)

    def test_exr_cache_path_changes_with_dimension(self) -> None:
        root = self._make_case_dir("board_media_exr_key")
        image = root / "plate.exr"
        image.write_text("fake", encoding="utf-8")
        cache = BoardMediaCache()

        small = cache.exr_cache_path(root, image, 128)
        large = cache.exr_cache_path(root, image, 256)

        self.assertIsNotNone(small)
        self.assertIsNotNone(large)
        self.assertNotEqual(small, large)


if __name__ == "__main__":
    unittest.main()
