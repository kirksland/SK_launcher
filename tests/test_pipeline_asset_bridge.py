import unittest
import os
from pathlib import Path
from time import time
from uuid import uuid4

from core.asset_layout import EntityRecord, resolve_asset_layout
from core.asset_schema import normalize_asset_schema
from core.pipeline.asset_bridge import inspect_entity_pipeline
from core.pipeline.entities.models import FreshnessState


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


if __name__ == "__main__":
    unittest.main()
