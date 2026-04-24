import unittest
from pathlib import Path
from uuid import uuid4

from controllers.process_controller import ProcessController
from core.asset_layout import resolve_asset_layout
from core.asset_schema import normalize_asset_schema
from core.pipeline.entities.models import FreshnessState


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


if __name__ == "__main__":
    unittest.main()
