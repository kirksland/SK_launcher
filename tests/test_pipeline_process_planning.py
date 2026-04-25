import unittest

from core.pipeline.asset_bridge import PipelineEntityInspection
from core.pipeline.entities.models import EntityRef, FreshnessState
from core.pipeline.processes.planning import prepare_process_request
from core.pipeline.processes.registry import available_processes_for_entity_kind


class PipelineProcessPlanningTests(unittest.TestCase):
    def test_prepare_process_request_builds_read_only_request(self) -> None:
        inspection = PipelineEntityInspection(
            entity=EntityRef("testpipeline:pipeline_asset:tree", "pipeline_asset", project_id="testpipeline", label="tree"),
            freshness=FreshnessState.STALE,
            downstream=(),
            summary={FreshnessState.STALE: 1},
            available_processes=available_processes_for_entity_kind("pipeline_asset"),
        )

        prepared = prepare_process_request(inspection, "publish.asset.usd")

        self.assertIsNotNone(prepared)
        assert prepared is not None
        self.assertEqual("publish.asset.usd", prepared.process_id)
        self.assertEqual("tree", prepared.entity_label)
        self.assertIn("houdini", prepared.required_capabilities)
        self.assertTrue(prepared.supports_remote)

    def test_prepare_process_request_rejects_unknown_process(self) -> None:
        inspection = PipelineEntityInspection(
            entity=EntityRef("testpipeline:shot:shot010", "shot", project_id="testpipeline", label="shot010"),
            freshness=FreshnessState.UP_TO_DATE,
            downstream=(),
            summary={FreshnessState.UP_TO_DATE: 1},
            available_processes=available_processes_for_entity_kind("shot"),
        )

        self.assertIsNone(prepare_process_request(inspection, "missing.process"))


if __name__ == "__main__":
    unittest.main()
