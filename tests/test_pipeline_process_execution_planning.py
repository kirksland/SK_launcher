import unittest
from pathlib import Path
from uuid import uuid4

from core.asset_layout import EntityRecord, resolve_asset_layout
from core.asset_schema import normalize_asset_schema
from core.pipeline.processes.execution_planning import (
    plan_asset_manager_process_execution,
    resolve_effective_pipeline_context,
)


class PipelineProcessExecutionPlanningTests(unittest.TestCase):
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

    def test_resolve_effective_pipeline_context_prefers_selected_value(self) -> None:
        resolved = resolve_effective_pipeline_context("animation", ("modeling", "lookdev"))
        self.assertEqual("animation", resolved)

    def test_resolve_effective_pipeline_context_falls_back_to_first_schema_context(self) -> None:
        resolved = resolve_effective_pipeline_context("All", ("lookdev", "modeling"))
        self.assertEqual("lookdev", resolved)

    def test_plan_publish_asset_usd_for_library_routes_to_managed_asset_output(self) -> None:
        root = self._make_case_dir("pipeline_exec_planning")
        library_asset = root / "library" / "assets" / "bar_double_lamp"
        library_asset.mkdir(parents=True)
        source_path = library_asset / "bar_double_lamp.obj"
        source_path.write_text("", encoding="utf-8")
        managed_asset = root / "assets" / "bar_double_lamp"
        managed_asset.mkdir(parents=True)

        schema = normalize_asset_schema(
            {
                "entity_roots": {
                    "asset": [
                        {"path": "assets", "role": "pipeline_asset"},
                        {"path": "library/assets", "role": "library_asset"},
                    ],
                    "shot": ["shots"],
                }
            }
        )
        layout = resolve_asset_layout(root, schema)
        record = EntityRecord(
            entity_type="asset",
            role="library_asset",
            name="bar_double_lamp",
            source_path=library_asset,
        )

        plan = plan_asset_manager_process_execution(
            "publish.asset.usd",
            entity_dir=library_asset,
            current_inventory_path=None,
            record=record,
            layout=layout,
            current_context="All",
            schema_contexts=("modeling", "lookdev"),
            ensure_dirs=False,
        )

        self.assertTrue(plan.is_ready)
        assert plan.parameters is not None
        self.assertEqual(source_path.as_posix(), plan.parameters["source"])
        self.assertEqual(
            (managed_asset / "publish" / "modeling" / "bar_double_lamp.usdnc").as_posix(),
            plan.parameters["output"],
        )
        self.assertEqual("modeling", plan.parameters["context"])

    def test_plan_publish_asset_usd_uses_selected_inventory_source_when_valid(self) -> None:
        root = self._make_case_dir("pipeline_exec_inventory_source")
        entity_dir = root / "assets" / "tree"
        entity_dir.mkdir(parents=True)
        fallback_source = entity_dir / "tree.obj"
        fallback_source.write_text("", encoding="utf-8")
        selected_source = entity_dir / "variants" / "tree_high.fbx"
        selected_source.parent.mkdir(parents=True)
        selected_source.write_text("", encoding="utf-8")

        plan = plan_asset_manager_process_execution(
            "publish.asset.usd",
            entity_dir=entity_dir,
            current_inventory_path=selected_source,
            record=None,
            layout=None,
            current_context="lookdev",
            schema_contexts=(),
            ensure_dirs=False,
        )

        self.assertTrue(plan.is_ready)
        assert plan.parameters is not None
        self.assertEqual(selected_source.as_posix(), plan.parameters["source"])

    def test_plan_publish_asset_usd_reports_missing_geometry(self) -> None:
        root = self._make_case_dir("pipeline_exec_missing_source")
        entity_dir = root / "assets" / "empty"
        entity_dir.mkdir(parents=True)

        plan = plan_asset_manager_process_execution(
            "publish.asset.usd",
            entity_dir=entity_dir,
            current_inventory_path=None,
            record=None,
            layout=None,
            current_context="modeling",
            schema_contexts=(),
            ensure_dirs=False,
        )

        self.assertFalse(plan.is_ready)
        self.assertEqual("No geometry source found for publish.asset.usd.", plan.status_message)
        self.assertIn("No supported geometry source", plan.run_summary)


if __name__ == "__main__":
    unittest.main()
