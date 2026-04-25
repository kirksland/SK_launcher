import unittest

from controllers.process_controller import ProcessController
from core.pipeline.asset_bridge import PipelineEntityInspection
from core.pipeline.entities.models import EntityRef, FreshnessState
from core.pipeline.processes.registry import available_processes_for_entity_kind


class _WindowStub:
    pass


class ProcessControllerPlanningTests(unittest.TestCase):
    def test_process_controller_prepares_requests(self) -> None:
        controller = ProcessController(_WindowStub())
        inspection = PipelineEntityInspection(
            entity=EntityRef("testpipeline:pipeline_asset:tree", "pipeline_asset", project_id="testpipeline", label="tree"),
            freshness=FreshnessState.STALE,
            downstream=(),
            summary={FreshnessState.STALE: 1},
            available_processes=available_processes_for_entity_kind("pipeline_asset"),
        )

        prepared = controller.prepare_request(inspection, "publish.asset.usd")

        self.assertIsNotNone(prepared)
        assert prepared is not None
        self.assertEqual("publish.asset.usd", prepared.process_id)


if __name__ == "__main__":
    unittest.main()
