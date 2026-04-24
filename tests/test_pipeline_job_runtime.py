import unittest

from core.pipeline.entities.models import EntityRef, ExecutionTarget
from core.pipeline.execution import ExecutionResult, ExecutionStatus
from core.pipeline.jobs import LocalJobRuntime
from core.pipeline.jobs.models import JobState
from core.pipeline.jobs.requests import RuntimeProcessRequest


class PipelineJobRuntimeTests(unittest.TestCase):
    def test_submit_records_queued_job_when_request_is_runtime_ready(self) -> None:
        runtime = LocalJobRuntime()
        request = RuntimeProcessRequest(
            process_id="publish.asset.usd",
            process_label="Publish Asset USD",
            family="publish",
            target_entity=EntityRef("testpipeline:pipeline_asset:tree", "pipeline_asset", label="tree"),
            execution_target=ExecutionTarget(
                id="pipeline_host_a",
                kind="pipeline_host",
                label="Pipeline Host A",
                capabilities=("houdini", "usd"),
            ),
            required_capabilities=("houdini", "usd"),
            outputs=("usd",),
        )

        result = runtime.submit(request)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.accepted)
        self.assertEqual(JobState.QUEUED, result.job.state)
        self.assertEqual("publish.asset.usd", result.job.process_id)
        self.assertEqual(1, len(runtime.jobs()))

    def test_submit_records_blocked_job_when_capabilities_are_missing(self) -> None:
        runtime = LocalJobRuntime()
        request = RuntimeProcessRequest(
            process_id="publish.asset.usd",
            process_label="Publish Asset USD",
            family="publish",
            target_entity=EntityRef("testpipeline:pipeline_asset:tree", "pipeline_asset", label="tree"),
            execution_target=ExecutionTarget(
                id="local",
                kind="local_workstation",
                label="Local Workstation",
            ),
            required_capabilities=("houdini", "usd"),
            outputs=("usd",),
            capability_gaps=("houdini", "usd"),
        )

        result = runtime.submit(request)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.accepted)
        self.assertEqual(JobState.BLOCKED, result.job.state)
        self.assertIn("Blocked", result.job.message)

    def test_runtime_filters_jobs_by_process_and_entity(self) -> None:
        runtime = LocalJobRuntime()
        request = RuntimeProcessRequest(
            process_id="publish.asset.usd",
            process_label="Publish Asset USD",
            family="publish",
            target_entity=EntityRef("testpipeline:pipeline_asset:tree", "pipeline_asset", label="tree"),
            execution_target=ExecutionTarget(
                id="pipeline_host_a",
                kind="pipeline_host",
                label="Pipeline Host A",
                capabilities=("houdini", "usd"),
            ),
            required_capabilities=("houdini", "usd"),
        )
        runtime.submit(request)

        self.assertEqual(1, len(runtime.jobs_for_process("publish.asset.usd")))
        self.assertEqual(1, len(runtime.jobs_for_entity("testpipeline:pipeline_asset:tree")))

    def test_execute_updates_job_state_and_stores_result(self) -> None:
        runtime = LocalJobRuntime()
        request = RuntimeProcessRequest(
            process_id="publish.asset.usd",
            process_label="Publish Asset USD",
            family="publish",
            target_entity=EntityRef("testpipeline:pipeline_asset:tree", "pipeline_asset", label="tree"),
            execution_target=ExecutionTarget(
                id="pipeline_host_a",
                kind="pipeline_host",
                label="Pipeline Host A",
                capabilities=("houdini", "usd"),
            ),
            required_capabilities=("houdini", "usd"),
        )

        result = runtime.execute(
            request,
            executor=lambda _request: ExecutionResult(
                status=ExecutionStatus.SUCCEEDED,
                message="USD publish completed.",
            ),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(JobState.SUCCEEDED, result.job.state)
        self.assertEqual(ExecutionStatus.SUCCEEDED, result.execution.status)
        self.assertEqual(ExecutionStatus.SUCCEEDED, runtime.latest_result().status)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
