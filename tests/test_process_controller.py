import unittest
from pathlib import Path
from uuid import uuid4

from controllers.process_controller import ProcessController
from core.asset_layout import EntityRecord, resolve_asset_layout
from core.asset_schema import normalize_asset_schema
from core.pipeline.entities.models import FreshnessState
from core.pipeline.execution import ExecutionResult, ExecutionStatus, ProducedOutput


class _WindowStub:
    pass


class ProcessControllerTests(unittest.TestCase):
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

    def test_process_controller_proxies_entity_inspection(self) -> None:
        root = self._make_case_dir("process_controller")
        entity = root / "assets" / "tree"
        entity.mkdir(parents=True)
        (entity / "tree_source.obj").write_text("", encoding="utf-8")
        layout = resolve_asset_layout(root, normalize_asset_schema({}))
        record = layout.entities("asset")[0]

        controller = ProcessController(_WindowStub())
        inspection = controller.inspect_entity(layout, record, context="All")

        self.assertIsNotNone(inspection)
        assert inspection is not None
        self.assertEqual(FreshnessState.MISSING_DEPENDENCY, inspection.freshness)
        self.assertTrue(any(process.id == "publish.asset.usd" for process in inspection.available_processes))

    def test_process_controller_inspection_includes_recorded_artifacts(self) -> None:
        root = self._make_case_dir("process_controller_provenance")
        entity = root / "library" / "assets" / "tree"
        entity.mkdir(parents=True)
        source = entity / "tree.obj"
        source.write_text("", encoding="utf-8")
        output = root / "assets" / "tree" / "publish" / "modeling" / "tree.usdnc"
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
        record = EntityRecord(entity_type="asset", role="library_asset", name="tree", source_path=entity)

        controller = ProcessController(_WindowStub())
        inspection = controller.inspect_entity(layout, record, context="modeling")
        assert inspection is not None
        request = controller.build_runtime_request(
            inspection,
            "publish.asset.usd",
            parameters={
                "source": source.as_posix(),
                "output": output.as_posix(),
                "context": "modeling",
            },
        )
        assert request is not None
        controller._runtime.execute(  # type: ignore[attr-defined]
            request,
            executor=lambda _request: ExecutionResult(
                status=ExecutionStatus.SUCCEEDED,
                message="ok",
                outputs=(ProducedOutput(kind="usd", path=output.as_posix(), label="tree.usdnc"),),
                payload={"execution_mode": "houdini_headless"},
            ),
        )

        updated = controller.inspect_entity(layout, record, context="modeling")

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertTrue(any(item.entity.path == output.as_posix() for item in updated.downstream))


if __name__ == "__main__":
    unittest.main()
