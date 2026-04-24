import unittest

from core.pipeline.entities.models import EntityRef, ExecutionTarget
from core.pipeline.execution import (
    ExecutionStatus,
    build_houdini_execution_plan,
    build_houdini_request_payload,
    execute_houdini_request,
)
from core.pipeline.jobs.requests import RuntimeProcessRequest


class PipelineHoudiniBackendTests(unittest.TestCase):
    def test_build_houdini_request_payload_uses_runtime_request_fields(self) -> None:
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
            parameters={"context": "lookdev"},
        )

        payload = build_houdini_request_payload(request)

        self.assertEqual("publish.asset.usd", payload["process_id"])
        self.assertEqual("tree", payload["entity"]["label"])
        self.assertEqual("pipeline_host_a", payload["execution_target"]["id"])
        self.assertEqual("lookdev", payload["parameters"]["context"])

    def test_build_houdini_execution_plan_is_headless(self) -> None:
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
        )

        plan = build_houdini_execution_plan(request)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertTrue(plan.headless)
        self.assertEqual("hython", plan.executable)
        self.assertIn("houdini_pipeline/process_runner.py", plan.command_preview)

    def test_execute_houdini_request_blocks_when_capabilities_are_missing(self) -> None:
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
            capability_gaps=("houdini", "usd"),
        )

        result = execute_houdini_request(request)

        self.assertEqual(ExecutionStatus.BLOCKED, result.status)
        self.assertIn("capability_gaps", result.payload)

    def test_execute_houdini_request_returns_skipped_stub_when_ready(self) -> None:
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

        result = execute_houdini_request(request)

        self.assertEqual(ExecutionStatus.SKIPPED, result.status)
        self.assertIn("command_preview", result.payload)
        self.assertIn("request_payload", result.payload)


if __name__ == "__main__":
    unittest.main()
