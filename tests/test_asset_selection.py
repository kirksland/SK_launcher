import unittest
from pathlib import Path
from uuid import uuid4

from core.asset_selection import (
    build_active_asset_selection,
    choose_best_context_for_selection,
    resolve_entity_record_for_path,
    resolve_entity_type_for_path,
)
from core.asset_layout import resolve_asset_layout
from core.asset_schema import normalize_asset_schema


class AssetSelectionTests(unittest.TestCase):
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

    def test_resolve_entity_type_for_path_uses_layout_when_available(self) -> None:
        root = self._make_case_dir("asset_selection_layout")
        shot_dir = root / "shots" / "sh010"
        shot_dir.mkdir(parents=True)
        layout = resolve_asset_layout(root, normalize_asset_schema({}))

        resolved = resolve_entity_type_for_path(
            shot_dir,
            layout=layout,
            schema=normalize_asset_schema({}),
            active_tab_index=1,
        )

        self.assertEqual("shot", resolved)

    def test_resolve_entity_type_for_path_falls_back_to_schema_then_tab(self) -> None:
        resolved = resolve_entity_type_for_path(
            Path("C:/show/custom/tree"),
            layout=None,
            schema=normalize_asset_schema({}),
            active_tab_index=0,
        )
        self.assertEqual("shot", resolved)

    def test_resolve_entity_record_for_path_matches_layout_entity(self) -> None:
        root = self._make_case_dir("asset_selection_record")
        asset_dir = root / "assets" / "tree"
        asset_dir.mkdir(parents=True)
        layout = resolve_asset_layout(root, normalize_asset_schema({}))

        record = resolve_entity_record_for_path(asset_dir, layout=layout)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual("tree", record.name)

    def test_build_active_asset_selection_exposes_summary_and_tab_label(self) -> None:
        root = self._make_case_dir("asset_selection_build")
        asset_dir = root / "assets" / "tree"
        asset_dir.mkdir(parents=True)
        layout = resolve_asset_layout(root, normalize_asset_schema({}))

        selection = build_active_asset_selection(
            asset_dir,
            layout=layout,
            schema=normalize_asset_schema({}),
            active_tab_index=1,
        )

        self.assertEqual("asset", selection.entity_type)
        self.assertEqual("Assets", selection.tab_label)
        self.assertEqual("tree [ASSET]", selection.selection_summary)

    def test_choose_best_context_for_selection_preserves_current_context_when_outputs_exist(self) -> None:
        root = self._make_case_dir("asset_selection_context")
        shot_dir = root / "shots" / "sh010"
        (shot_dir / "publish" / "lighting").mkdir(parents=True)
        (shot_dir / "publish" / "lighting" / "shot.usd").write_text("", encoding="utf-8")
        layout = resolve_asset_layout(root, normalize_asset_schema({}))
        selection = build_active_asset_selection(
            shot_dir,
            layout=layout,
            schema=normalize_asset_schema({}),
            active_tab_index=0,
        )

        chosen = choose_best_context_for_selection(
            selection,
            layout=layout,
            current="lighting",
            contexts=("layout", "lighting", "comp"),
        )

        self.assertEqual("lighting", chosen)


if __name__ == "__main__":
    unittest.main()
