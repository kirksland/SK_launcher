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
            parameters={"source": "C:/project/source/tree.obj"},
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
        artifacts = runtime.latest_artifacts()
        self.assertEqual(0, len(artifacts))

    def test_execute_registers_artifacts_with_source_provenance(self) -> None:
        runtime = LocalJobRuntime()
        request = RuntimeProcessRequest(
            process_id="publish.asset.usd",
            process_label="Publish Asset USD",
            family="publish",
            target_entity=EntityRef("testpipeline:library_asset:tree", "library_asset", label="tree"),
            execution_target=ExecutionTarget(
                id="pipeline_host_a",
                kind="pipeline_host",
                label="Pipeline Host A",
                capabilities=("houdini", "usd"),
            ),
            required_capabilities=("houdini", "usd"),
            parameters={
                "source": "C:/project/library/tree.obj",
                "output": "C:/project/assets/tree/publish/modeling/tree.usd",
                "context": "modeling",
            },
        )

        result = runtime.execute(
            request,
            executor=lambda _request: ExecutionResult(
                status=ExecutionStatus.SUCCEEDED,
                message="USD publish completed.",
                outputs=(
                    __import__("core.pipeline.execution", fromlist=["ProducedOutput"]).ProducedOutput(
                        kind="usd",
                        path="C:/project/assets/tree/publish/modeling/tree.usd",
                    ),
                ),
                payload={"execution_mode": "houdini_headless"},
            ),
        )

        self.assertIsNotNone(result)
        artifacts = runtime.latest_artifacts()
        self.assertEqual(1, len(artifacts))
        self.assertEqual("publish.asset.usd", artifacts[0].process_id)
        self.assertEqual("C:/project/library/tree.obj", artifacts[0].source_artifacts[0].path)


if __name__ == "__main__":
    unittest.main()
