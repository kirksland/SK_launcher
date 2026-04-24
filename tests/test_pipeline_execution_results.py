import unittest

from core.pipeline.execution import ExecutionResult, ExecutionStatus, ProducedOutput


class PipelineExecutionResultTests(unittest.TestCase):
    def test_produced_output_normalizes_values(self) -> None:
        output = ProducedOutput(" USD ", " C:/project/publish/tree.usd ", label=" Tree USD ")

        self.assertEqual("usd", output.kind)
        self.assertEqual("C:/project/publish/tree.usd", output.path)
        self.assertEqual("Tree USD", output.label)

    def test_execution_result_normalizes_and_freezes_payload(self) -> None:
        payload = {"version": 12}
        result = ExecutionResult(
            status=" skipped ",
            message=" Planned only ",
            payload=payload,
        )
        payload["version"] = 13

        self.assertEqual(ExecutionStatus.SKIPPED, result.status)
        self.assertEqual("Planned only", result.message)
        self.assertEqual(12, result.payload["version"])
        with self.assertRaises(TypeError):
            result.payload["version"] = 14  # type: ignore[index]

    def test_execution_result_rejects_invalid_status(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionResult(status="done")


if __name__ == "__main__":
    unittest.main()
