import unittest
from pathlib import Path
from uuid import uuid4

from controllers.board.media_import_controller import BoardMediaImportController


class BoardMediaImportTests(unittest.TestCase):
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

    def test_unique_asset_path_keeps_existing_asset_when_source_matches(self) -> None:
        assets_dir = self._make_case_dir("board_media_import_same_source")
        existing = assets_dir / "view.png"
        existing.write_text("same", encoding="utf-8")

        path = BoardMediaImportController._unique_asset_path(assets_dir, "view.png", existing)

        self.assertEqual(path, existing)

    def test_unique_asset_path_suffixes_colliding_filenames(self) -> None:
        assets_dir = self._make_case_dir("board_media_import_collision")
        (assets_dir / "view.png").write_text("first", encoding="utf-8")
        (assets_dir / "view_001.png").write_text("second", encoding="utf-8")
        source = self._make_case_dir("board_media_import_source") / "view.png"
        source.write_text("third", encoding="utf-8")

        path = BoardMediaImportController._unique_asset_path(assets_dir, "view.png", source)

        self.assertEqual(path, assets_dir / "view_002.png")


if __name__ == "__main__":
    unittest.main()
