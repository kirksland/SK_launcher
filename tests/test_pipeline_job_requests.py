import unittest

from core.pipeline.entities.models import ExecutionTarget
from core.pipeline.jobs import build_runtime_process_request, default_local_execution_target
from core.pipeline.processes.planning import PreparedProcessRequest


class PipelineJobRequestTests(unittest.TestCase):
    def test_build_runtime_process_request_uses_local_default_target(self) -> None:
        prepared = PreparedProcessRequest(
            process_id="publish.asset.usd",
            process_label="Publish Asset USD",
            family="publish",
            entity_id="testpipeline:pipeline_asset:tree",
            entity_label="tree",
            entity_kind="pipeline_asset",
            description="Publish the asset as USD.",
            required_capabilities=("houdini", "usd"),
            outputs=("usd",),
            supports_remote=True,
            review_required=False,
        )

        runtime_request = build_runtime_process_request(prepared)

        self.assertIsNotNone(runtime_request)
        assert runtime_request is not None
        self.assertEqual("local", runtime_request.execution_target.id)
        self.assertEqual("local_workstation", runtime_request.execution_target.kind)
        self.assertFalse(runtime_request.is_runtime_ready())
        self.assertEqual(("houdini", "usd"), runtime_request.capability_gaps)

    def test_build_runtime_process_request_tracks_target_capability_gaps(self) -> None:
        prepared = PreparedProcessRequest(
            process_id="publish.asset.usd",
            process_label="Publish Asset USD",
            family="publish",
            entity_id="testpipeline:pipeline_asset:tree",
            entity_label="tree",
            entity_kind="pipeline_asset",
            description="Publish the asset as USD.",
            required_capabilities=("houdini", "usd"),
            outputs=("usd",),
            supports_remote=True,
            review_required=False,
        )
        target = ExecutionTarget(
            id="pipeline_host_a",
            kind="pipeline_host",
            label="Pipeline Host A",
            capabilities=("houdini", "usd"),
        )

        runtime_request = build_runtime_process_request(prepared, execution_target=target, parameters={"version": 12})

        self.assertIsNotNone(runtime_request)
        assert runtime_request is not None
        self.assertTrue(runtime_request.is_runtime_ready())
        self.assertEqual((), runtime_request.capability_gaps)
        self.assertEqual(12, runtime_request.parameters["version"])
        with self.assertRaises(TypeError):
            runtime_request.parameters["version"] = 13  # type: ignore[index]

    def test_default_local_execution_target_is_stable(self) -> None:
        target = default_local_execution_target()

        self.assertEqual("local", target.id)
        self.assertEqual("local_workstation", target.kind)
        self.assertEqual("Local Workstation", target.label)


if __name__ == "__main__":
    unittest.main()
