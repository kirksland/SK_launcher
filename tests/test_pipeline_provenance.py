import unittest

from core.pipeline.entities.models import EntityRef, ExecutionTarget
from core.pipeline.execution import ExecutionResult, ExecutionStatus, ProducedOutput
from core.pipeline.jobs.models import JobRecord
from core.pipeline.jobs.requests import RuntimeProcessRequest
from core.pipeline.provenance import ProducedArtifactRecord, SourceArtifactRef, build_artifact_records


class PipelineProvenanceTests(unittest.TestCase):
    def test_source_artifact_ref_normalizes_values(self) -> None:
        ref = SourceArtifactRef(" C:/project/source/tree.obj ", kind=" File ", label=" Tree ")

        self.assertEqual("C:/project/source/tree.obj", ref.path)
        self.assertEqual("file", ref.kind)
        self.assertEqual("Tree", ref.label)

    def test_produced_artifact_record_rejects_missing_identity(self) -> None:
        with self.assertRaises(ValueError):
            ProducedArtifactRecord(
                id="",
                path="C:/project/publish/tree.usd",
                kind="usd",
                process_id="publish.asset.usd",
                job_id="job_1",
                target_entity_id="test:asset:tree",
                execution_target_id="local",
            )

    def test_build_artifact_records_uses_request_and_execution(self) -> None:
        request = RuntimeProcessRequest(
            process_id="publish.asset.usd",
            process_label="Publish Asset USD",
            family="publish",
            target_entity=EntityRef("testpipeline:library_asset:tree", "library_asset", label="tree"),
            execution_target=ExecutionTarget("local", "local_workstation", label="Local"),
            parameters={
                "source": "C:/project/library/tree.obj",
                "output": "C:/project/assets/tree/publish/modeling/tree.usd",
                "context": "modeling",
            },
        )
        job = JobRecord(
            id="job_123",
            process_id="publish.asset.usd",
            target_entity=request.target_entity,
            execution_target_id="local",
            state="succeeded",
            parameters=request.parameters,
        )
        execution = ExecutionResult(
            status=ExecutionStatus.SUCCEEDED,
            outputs=(ProducedOutput(kind="usd", path="C:/project/assets/tree/publish/modeling/tree.usd"),),
            payload={"execution_mode": "houdini_headless"},
        )

        records = build_artifact_records(request=request, job=job, execution=execution)

        self.assertEqual(1, len(records))
        artifact = records[0]
        self.assertEqual("publish.asset.usd", artifact.process_id)
        self.assertEqual("local", artifact.execution_target_id)
        self.assertEqual("houdini_headless", artifact.execution_mode)
        self.assertEqual(1, len(artifact.source_artifacts))
        self.assertEqual("C:/project/library/tree.obj", artifact.source_artifacts[0].path)


if __name__ == "__main__":
    unittest.main()
