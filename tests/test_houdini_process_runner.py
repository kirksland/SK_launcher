import json
import unittest

from houdini_pipeline.process_runner import dispatch_process, main


class HoudiniProcessRunnerTests(unittest.TestCase):
    def test_dispatch_process_routes_publish_asset_usd(self) -> None:
        result = dispatch_process(
            {
                "process_id": "publish.asset.usd",
                "parameters": {
                    "source": "C:/project/source/default.bgeo",
                    "output": "C:/project/publish/tree.usd",
                    "context": "lookdev",
                },
            }
        )

        self.assertEqual("skipped", result["status"])
        self.assertEqual("justi::sf_publish_asset_usd::1.0", result["payload"]["hda_type_name"])
        self.assertEqual("lookdev", result["payload"]["validated_inputs"]["context"])

    def test_main_writes_json_result(self) -> None:
        request_json = json.dumps(
            {
                "process_id": "publish.asset.usd",
                "parameters": {
                    "source": "C:/project/source/default.bgeo",
                    "output": "C:/project/publish/tree.usd",
                    "context": "lookdev",
                },
            }
        )

        exit_code = main(["--request-json", request_json])

        self.assertEqual(1, exit_code)

    def test_dispatch_process_reports_missing_parameters(self) -> None:
        with self.assertRaises(ValueError):
            dispatch_process({"process_id": "publish.asset.usd", "parameters": {"source": "only"}})


if __name__ == "__main__":
    unittest.main()
