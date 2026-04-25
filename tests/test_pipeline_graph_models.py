import unittest

from core.pipeline.entities.models import EntityRef, FreshnessState
from core.pipeline.graph.models import DependencyEdge
from core.pipeline.jobs.models import JobRecord, JobState


class PipelineGraphModelTests(unittest.TestCase):
    def test_dependency_edge_normalizes_kind_and_freshness(self) -> None:
        upstream = EntityRef("charactera_model", "asset")
        downstream = EntityRef("charactera_rig", "publish")

        edge = DependencyEdge(
            upstream=upstream,
            downstream=downstream,
            kind=" builds_from ",
            freshness=" stale ",
        )

        self.assertEqual("builds_from", edge.kind)
        self.assertEqual(FreshnessState.STALE, edge.freshness)

    def test_dependency_edge_rejects_self_reference(self) -> None:
        entity = EntityRef("charactera_model", "asset")

        with self.assertRaises(ValueError):
            DependencyEdge(entity, entity, "consumes")

    def test_job_record_normalizes_and_freezes_parameters(self) -> None:
        payload = {"version": 12}
        job = JobRecord(
            " Publish01 ",
            " Publish_Asset_USD ",
            target_entity=EntityRef("charactera", "asset"),
            execution_target_id=" Local ",
            state=" running ",
            parameters=payload,
            message=" Working ",
        )
        payload["version"] = 13

        self.assertEqual("publish01", job.id)
        self.assertEqual("publish_asset_usd", job.process_id)
        self.assertEqual("local", job.execution_target_id)
        self.assertEqual(JobState.RUNNING, job.state)
        self.assertEqual(12, job.parameters["version"])
        self.assertEqual("Working", job.message)
        with self.assertRaises(TypeError):
            job.parameters["version"] = 14  # type: ignore[index]

    def test_job_record_rejects_invalid_state(self) -> None:
        with self.assertRaises(ValueError):
            JobRecord(
                "publish01",
                "publish_asset_usd",
                target_entity=EntityRef("charactera", "asset"),
                execution_target_id="local",
                state="done",
            )


if __name__ == "__main__":
    unittest.main()
