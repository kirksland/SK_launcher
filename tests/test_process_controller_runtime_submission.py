import unittest

from controllers.process_controller import ProcessController
from core.pipeline.asset_bridge import PipelineEntityInspection
from core.pipeline.entities.models import EntityRef, FreshnessState
from core.pipeline.jobs.models import JobState
from core.pipeline.processes.registry import available_processes_for_entity_kind


class _WindowStub:
    pass


class ProcessControllerRuntimeSubmissionTests(unittest.TestCase):
    def test_submit_runtime_request_records_job(self) -> None:
        controller = ProcessController(_WindowStub())
        inspection = PipelineEntityInspection(
            entity=EntityRef("testpipeline:pipeline_asset:tree", "pipeline_asset", project_id="testpipeline", label="tree"),
            freshness=FreshnessState.STALE,
            downstream=(),
            summary={FreshnessState.STALE: 1},
            available_processes=available_processes_for_entity_kind("pipeline_asset"),
        )

        result = controller.submit_runtime_request(inspection, "publish.asset.usd")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(JobState.BLOCKED, result.job.state)
        self.assertEqual(1, len(controller.runtime_jobs()))


if __name__ == "__main__":
    unittest.main()
