import unittest
from pathlib import Path
from uuid import uuid4

from core.board_io import board_path, load_board_payload, save_board_payload
from core.board_state.migrations import BOARD_SCHEMA_VERSION


class BoardIoTests(unittest.TestCase):
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

    def test_board_path_uses_project_board_file(self) -> None:
        root = self._make_case_dir("board_io_path")
        self.assertEqual(board_path(root), root / ".skyforge_board.json")

    def test_save_and_load_board_payload_round_trips_dict(self) -> None:
        root = self._make_case_dir("board_io_round_trip")
        payload = {"items": [{"type": "note", "text": "hello"}], "image_display_overrides": {}}

        saved_path = save_board_payload(root, payload)
        loaded = load_board_payload(root)

        self.assertEqual(saved_path, root / ".skyforge_board.json")
        self.assertEqual(
            loaded,
            {
                "items": [{"type": "note", "text": "hello"}],
                "image_display_overrides": {},
                "schema_version": BOARD_SCHEMA_VERSION,
            },
        )

    def test_load_board_payload_returns_none_for_missing_or_invalid_payload(self) -> None:
        root = self._make_case_dir("board_io_invalid")
        self.assertIsNone(load_board_payload(root))
        board_path(root).write_text("[]", encoding="utf-8")
        self.assertIsNone(load_board_payload(root))
        board_path(root).write_text("{bad json", encoding="utf-8")
        self.assertIsNone(load_board_payload(root))

if __name__ == "__main__":
    unittest.main()
