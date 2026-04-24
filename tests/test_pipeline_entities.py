import unittest

from core.pipeline.entities.models import EntityRef, ExecutionTarget, FreshnessState, TargetCapability


class PipelineEntityTests(unittest.TestCase):
    def test_entity_ref_normalizes_tokens(self) -> None:
        entity = EntityRef(" CharacterA ", " Asset ", project_id=" TestPipeline ", task_id=" Model ")

        self.assertEqual("charactera", entity.id)
        self.assertEqual("asset", entity.kind)
        self.assertEqual("testpipeline", entity.project_id)
        self.assertEqual("model", entity.task_id)

    def test_entity_ref_rejects_empty_identity(self) -> None:
        with self.assertRaises(ValueError):
            EntityRef("", "asset")

        with self.assertRaises(ValueError):
            EntityRef("charactera", "")

    def test_execution_target_normalizes_and_supports_capabilities(self) -> None:
        target = ExecutionTarget(
            " Local ",
            " local_workstation ",
            "Main Workstation",
            capabilities=("houdini", " USD ", "houdini", "opencv"),
            environment_profile=" Houdini20 ",
            reachable_roots=("C:\\projects", " ", "D:\\cache"),
        )

        self.assertEqual("local", target.id)
        self.assertEqual("local_workstation", target.kind)
        self.assertEqual(("houdini", "usd", "opencv"), target.capabilities)
        self.assertTrue(target.supports(TargetCapability.HOUDINI))
        self.assertEqual("houdini20", target.environment_profile)
        self.assertEqual(("C:\\projects", "D:\\cache"), target.reachable_roots)

    def test_execution_target_rejects_invalid_kind(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionTarget("local", "desktop", "Desktop")

    def test_freshness_state_constants_cover_expected_values(self) -> None:
        self.assertIn(FreshnessState.UP_TO_DATE, FreshnessState.ALL)
        self.assertIn(FreshnessState.STALE, FreshnessState.ALL)
        self.assertIn(FreshnessState.NEEDS_REVIEW, FreshnessState.ALL)


if __name__ == "__main__":
    unittest.main()
