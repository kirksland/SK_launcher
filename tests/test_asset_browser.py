import unittest
from pathlib import Path
from uuid import uuid4

from core.asset_browser import (
    entity_prefixes,
    existing_project_paths,
    filter_asset_entries,
    filter_entity_dirs,
    list_project_entities,
    resolved_filter_choice,
)


class AssetBrowserTests(unittest.TestCase):
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

    def test_filter_asset_entries_matches_query_on_path(self) -> None:
        entries = [
            {"local_path": "C:/show/ProjectA"},
            {"local_path": "C:/show/TestProject"},
        ]
        filtered = filter_asset_entries(entries, "test")
        self.assertEqual(filtered, [{"local_path": "C:/show/TestProject"}])

    def test_existing_project_paths_keeps_existing_directories(self) -> None:
        existing = self._make_case_dir("asset_project")
        paths = existing_project_paths(
            [
                {"local_path": str(existing)},
                {"local_path": str(existing / "missing")},
            ]
        )
        self.assertEqual(paths, [existing])

    def test_list_project_entities_reads_shots_and_assets(self) -> None:
        root = self._make_case_dir("asset_entities")
        (root / "shots" / "sh010").mkdir(parents=True)
        (root / "assets" / "tree_oak").mkdir(parents=True)
        shots, assets = list_project_entities(root)
        self.assertEqual([path.name for path in shots], ["sh010"])
        self.assertEqual([path.name for path in assets], ["tree_oak"])

    def test_entity_prefixes_extract_unique_prefixes(self) -> None:
        prefixes = entity_prefixes([Path("sh010_lighting"), Path("sh020_fx"), Path("tree_oak")])
        self.assertEqual(prefixes, ["sh010", "sh020", "tree"])

    def test_resolved_filter_choice_preserves_known_value(self) -> None:
        self.assertEqual(resolved_filter_choice("FX", ["All", "FX"]), "FX")
        self.assertEqual(resolved_filter_choice("Missing", ["All", "FX"]), "All")

    def test_filter_entity_dirs_applies_prefix_and_search(self) -> None:
        entity_dirs = [
            Path("sh010_lighting"),
            Path("sh020_fx"),
            Path("tree_oak"),
        ]
        filtered = filter_entity_dirs(entity_dirs, prefix_filter="sh020", search_text="fx")
        self.assertEqual(filtered, [Path("sh020_fx")])


if __name__ == "__main__":
    unittest.main()
