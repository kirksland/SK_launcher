import unittest

from core.pipeline.processes.registry import available_processes_for_entity_kind, list_process_definitions


class PipelineProcessRegistryTests(unittest.TestCase):
    def test_registry_lists_default_processes(self) -> None:
        processes = list_process_definitions()

        self.assertGreaterEqual(len(processes), 4)
        self.assertEqual("validate.asset.readiness", processes[0].id)

    def test_available_processes_filter_by_entity_kind(self) -> None:
        asset_processes = available_processes_for_entity_kind("pipeline_asset")
        shot_processes = available_processes_for_entity_kind("shot")

        self.assertTrue(any(process.id == "publish.asset.usd" for process in asset_processes))
        self.assertTrue(any(process.id == "refresh.shot.assembly" for process in shot_processes))
        self.assertFalse(any(process.id == "refresh.shot.assembly" for process in asset_processes))


if __name__ == "__main__":
    unittest.main()
