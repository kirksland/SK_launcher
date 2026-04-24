import unittest

from core.pipeline.processes.definitions import ProcessDefinition, ProcessFamily


class PipelineProcessDefinitionTests(unittest.TestCase):
    def test_process_definition_normalizes_values(self) -> None:
        process = ProcessDefinition(
            " Publish_Asset_USD ",
            "Publish Asset USD",
            " publish ",
            entity_kinds=("asset", " Asset "),
            required_capabilities=("houdini", "usd", "houdini"),
            outputs=("usd_asset", "review_media", "usd_asset"),
        )

        self.assertEqual("publish_asset_usd", process.id)
        self.assertEqual("publish", process.family)
        self.assertEqual(("asset",), process.entity_kinds)
        self.assertEqual(("houdini", "usd"), process.required_capabilities)
        self.assertEqual(("usd_asset", "review_media"), process.outputs)
        self.assertTrue(process.supports_entity_kind("asset"))

    def test_process_definition_rejects_missing_entity_kinds(self) -> None:
        with self.assertRaises(ValueError):
            ProcessDefinition("publish_asset_usd", "Publish", ProcessFamily.PUBLISH, entity_kinds=())

    def test_process_definition_rejects_invalid_family(self) -> None:
        with self.assertRaises(ValueError):
            ProcessDefinition("publish_asset_usd", "Publish", "run", entity_kinds=("asset",))


if __name__ == "__main__":
    unittest.main()
