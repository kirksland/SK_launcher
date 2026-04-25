import unittest
import os
from pathlib import Path
from time import time
from uuid import uuid4

from core.asset_layout import EntityRecord, resolve_asset_layout
from core.asset_schema import normalize_asset_schema
from core.pipeline.asset_bridge import inspect_entity_pipeline
from core.pipeline.entities.models import FreshnessState
from core.pipeline.provenance import ProducedArtifactRecord, SourceArtifactRef


class PipelineAssetBridgeTests(unittest.TestCase):
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

    def test_inspect_entity_pipeline_marks_missing_dependency_when_publish_missing(self) -> None:
        root = self._make_case_dir("pipeline_asset_bridge_missing")
        entity = root / "assets" / "tree"
        entity.mkdir(parents=True)
        (entity / "tree_source.obj").write_text("", encoding="utf-8")
        layout = resolve_asset_layout(root, normalize_asset_schema({}))
        record = layout.entities("asset")[0]

        inspection = inspect_entity_pipeline(layout, record)

        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertEqual(FreshnessState.MISSING_DEPENDENCY, inspection.freshness)
        self.assertEqual(2, len(inspection.downstream))
        self.assertTrue(any(process.id == "publish.asset.usd" for process in inspection.available_processes))

    def test_inspect_entity_pipeline_marks_publish_stale_when_source_is_newer(self) -> None:
        root = self._make_case_dir("pipeline_asset_bridge_stale")
        entity = root / "assets" / "tree"
        publish = entity / "publish"
        preview = entity / "preview"
        publish.mkdir(parents=True)
        preview.mkdir(parents=True)
        usd = publish / "tree_v001.usd"
        jpg = preview / "tree.jpg"
        usd.write_text("", encoding="utf-8")
        jpg.write_text("", encoding="utf-8")
        source = entity / "tree_source.obj"
        source.write_text("", encoding="utf-8")
        future = time() + 5.0
        os.utime(source, (future, future))

        layout = resolve_asset_layout(root, normalize_asset_schema({}))
        record = layout.entities("asset")[0]
        inspection = inspect_entity_pipeline(layout, record)

        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertEqual(FreshnessState.STALE, inspection.freshness)
        self.assertEqual(2, inspection.summary[FreshnessState.STALE])
        self.assertTrue(any(process.id == "validate.asset.readiness" for process in inspection.available_processes))

    def test_inspect_entity_pipeline_includes_provenance_artifact_for_library_source(self) -> None:
        root = self._make_case_dir("pipeline_asset_bridge_provenance")
        entity = root / "library" / "assets" / "bar_double_lamp"
        entity.mkdir(parents=True)
        source = entity / "bar_double_lamp.obj"
        source.write_text("", encoding="utf-8")
        output = root / "assets" / "bar_double_lamp" / "publish" / "modeling" / "bar_double_lamp.usdnc"
        output.parent.mkdir(parents=True)
        output.write_text("", encoding="utf-8")

        schema = normalize_asset_schema(
            {
                "entity_sources": {
                    "library_asset": [{"path": "library/assets", "entity_type": "asset"}],
                    "pipeline_asset": [{"path": "assets", "entity_type": "asset"}],
                }
            }
        )
        layout = resolve_asset_layout(root, schema)
        record = EntityRecord(entity_type="asset", role="library_asset", name="bar_double_lamp", source_path=entity)
        source_entity_id = f"{root.name}:library_asset:bar_double_lamp"
        artifact = ProducedArtifactRecord(
            id="job_publish:artifact:1",
            path=output.as_posix(),
            kind="usd",
            process_id="publish.asset.usd",
            job_id="job_publish",
            target_entity_id=source_entity_id,
            execution_target_id="local",
            label="bar_double_lamp.usdnc",
            source_artifacts=(
                SourceArtifactRef(
                    path=source.as_posix(),
                    kind="file",
                    label=source.name,
                    entity_id=source_entity_id,
                ),
            ),
            execution_mode="houdini_headless",
        )

        inspection = inspect_entity_pipeline(layout, record, produced_artifacts=(artifact,))

        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertEqual(FreshnessState.UP_TO_DATE, inspection.freshness)
        self.assertTrue(any(item.entity.path == output.as_posix() for item in inspection.downstream))


if __name__ == "__main__":
    unittest.main()
