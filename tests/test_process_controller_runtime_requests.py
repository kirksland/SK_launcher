import unittest

from controllers.process_controller import ProcessController
from core.pipeline.asset_bridge import PipelineEntityInspection
from core.pipeline.entities.models import EntityRef, FreshnessState
from core.pipeline.processes.registry import available_processes_for_entity_kind


class _WindowStub:
    pass


class ProcessControllerRuntimeRequestTests(unittest.TestCase):
    def test_process_controller_builds_runtime_request(self) -> None:
        controller = ProcessController(_WindowStub())
        inspection = PipelineEntityInspection(
            entity=EntityRef("testpipeline:pipeline_asset:tree", "pipeline_asset", project_id="testpipeline", label="tree"),
            freshness=FreshnessState.STALE,
            downstream=(),
            summary={FreshnessState.STALE: 1},
            available_processes=available_processes_for_entity_kind("pipeline_asset"),
        )

        runtime_request = controller.build_runtime_request(inspection, "publish.asset.usd")

        self.assertIsNotNone(runtime_request)
        assert runtime_request is not None
        self.assertEqual("publish.asset.usd", runtime_request.process_id)
        self.assertEqual("tree", runtime_request.target_entity.label)
        self.assertEqual("local_workstation", runtime_request.execution_target.kind)


if __name__ == "__main__":
    unittest.main()
