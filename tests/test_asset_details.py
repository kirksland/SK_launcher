import unittest
from pathlib import Path
from uuid import uuid4

from core.asset_details import (
    build_asset_meta_text,
    empty_versions_message,
    entity_type_for_path,
    normalize_list_context,
    pick_best_context,
    read_history_note,
)


class AssetDetailsTests(unittest.TestCase):
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

    def test_entity_type_for_path_detects_shot(self) -> None:
        self.assertEqual(entity_type_for_path(Path("C:/show/shots/sh010")), "shot")
        self.assertEqual(entity_type_for_path(Path("C:/show/assets/tree")), "asset")

    def test_normalize_list_context_maps_all_to_none(self) -> None:
        self.assertIsNone(normalize_list_context("All"))
        self.assertEqual(normalize_list_context("lighting"), "lighting")

    def test_build_asset_meta_text_formats_summary(self) -> None:
        text = build_asset_meta_text("Justin", "WIP", "lighting", "sh010")
        self.assertIn("Owner: Justin", text)
        self.assertIn("Entity: sh010", text)

    def test_pick_best_context_prefers_first_available_when_current_empty(self) -> None:
        chosen = pick_best_context(
            entity_type="shot",
            current="layout",
            contexts=["layout", "lighting", "comp"],
            has_content=lambda ctx: ctx == "lighting",
        )
        self.assertEqual(chosen, "lighting")

    def test_read_history_note_returns_default_when_missing(self) -> None:
        entity = self._make_case_dir("asset_history")
        self.assertEqual(read_history_note(entity), "No history yet")

    def test_empty_versions_message_depends_on_entity_type(self) -> None:
        self.assertIn("USD/Video", empty_versions_message("shot"))
        self.assertIn("USD", empty_versions_message("asset"))


if __name__ == "__main__":
    unittest.main()
