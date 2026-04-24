import unittest
from pathlib import Path
import shutil
import uuid

from houdini_pipeline.processes.publish_asset_usd import (
    HDA_PARAM_CONTEXT,
    HDA_PARAM_OUTPUT,
    HDA_PARAM_SOURCE,
    HDA_TYPE_NAME,
    run,
)


class _FakeParm:
    def __init__(self, name: str, on_press=None) -> None:
        self.name = name
        self.value = None
        self.pressed = False
        self.on_press = on_press

    def set(self, value: str) -> None:
        self.value = value

    def pressButton(self) -> None:
        self.pressed = True
        if self.on_press is not None:
            self.on_press()


class _FakeNode:
    def __init__(self, node_type: str = "node", write_output_on_cook: bool = True) -> None:
        self.node_type = node_type
        self.write_output_on_cook = write_output_on_cook
        self.parms = {
            "source": _FakeParm("source"),
            "output": _FakeParm("output"),
            "context": _FakeParm("context"),
            "execute": _FakeParm("execute", on_press=self._write_output_if_needed),
        }
        self.cooked = False
        self.destroyed = False
        self.created = []

    def parm(self, name: str):
        return self.parms.get(name)

    def cook(self, force: bool = False) -> None:
        self.cooked = force
        self._write_output_if_needed()

    def _write_output_if_needed(self) -> None:
        if self.write_output_on_cook:
            output = self.parms["output"].value
            if output:
                output_path = Path(output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("usd", encoding="utf-8")

    def destroy(self) -> None:
        self.destroyed = True

    def createNode(self, node_type: str, node_name: str | None = None):
        child = _FakeNode(node_type=node_type, write_output_on_cook=self.write_output_on_cook)
        self.created.append((node_type, node_name, child))
        return child


class _FakeHou:
    def __init__(self, include_stage: bool = True, write_output_on_cook: bool = True) -> None:
        self.root = _FakeNode(node_type="root", write_output_on_cook=write_output_on_cook)
        self.stage = (
            _FakeNode(node_type="lopnet", write_output_on_cook=write_output_on_cook)
            if include_stage
            else None
        )

    def node(self, path: str):
        if path == "/":
            return self.root
        if path == "/stage":
            return self.stage
        return None


def _make_workspace_temp_dir() -> Path:
    base_dir = Path(__file__).resolve().parent / ".tmp"
    base_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = base_dir / f"publish_asset_usd_{uuid.uuid4().hex}"
    temp_dir.mkdir()
    return temp_dir


class PublishAssetUsdProcessTests(unittest.TestCase):
    def test_run_validates_inputs_and_returns_hda_contract(self) -> None:
        result = run(
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
        self.assertEqual(HDA_TYPE_NAME, result["payload"]["hda_type_name"])
        self.assertEqual(
            {
                "source": HDA_PARAM_SOURCE,
                "output": HDA_PARAM_OUTPUT,
                "context": HDA_PARAM_CONTEXT,
            },
            result["payload"]["parameter_mapping"],
        )

    def test_run_rejects_missing_required_inputs(self) -> None:
        with self.assertRaises(ValueError):
            run({"process_id": "publish.asset.usd", "parameters": {"source": "x", "output": "y"}})

    def test_run_executes_hda_when_hou_is_available(self) -> None:
        temp_dir = _make_workspace_temp_dir()
        try:
            source = temp_dir / "source.bgeo"
            source.write_text("geo", encoding="utf-8")
            output = temp_dir / "publish" / "tree.usd"
            fake_hou = _FakeHou()

            result = run(
                {
                    "process_id": "publish.asset.usd",
                    "parameters": {
                        "source": str(source),
                        "output": str(output),
                        "context": "lookdev",
                    },
                },
                hou_module=fake_hou,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual("succeeded", result["status"])
        self.assertEqual("houdini_headless", result["payload"]["execution_mode"])
        created_type, _, hda_node = fake_hou.stage.created[0]
        self.assertEqual(HDA_TYPE_NAME, created_type)
        self.assertEqual(str(source), hda_node.parm("source").value)
        self.assertEqual(str(output), hda_node.parm("output").value)
        self.assertEqual("lookdev", hda_node.parm("context").value)
        self.assertTrue(hda_node.parm("execute").pressed)
        self.assertTrue(hda_node.destroyed)

    def test_run_creates_stage_parent_when_missing(self) -> None:
        temp_dir = _make_workspace_temp_dir()
        try:
            source = temp_dir / "source.bgeo"
            source.write_text("geo", encoding="utf-8")
            output = temp_dir / "publish" / "tree.usd"
            fake_hou = _FakeHou(include_stage=False)

            result = run(
                {
                    "process_id": "publish.asset.usd",
                    "parameters": {
                        "source": str(source),
                        "output": str(output),
                        "context": "lookdev",
                    },
                },
                hou_module=fake_hou,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual("succeeded", result["status"])
        created_type, created_name, stage_node = fake_hou.root.created[0]
        self.assertEqual("lopnet", created_type)
        self.assertEqual("stage", created_name)
        hda_type, _, _ = stage_node.created[0]
        self.assertEqual(HDA_TYPE_NAME, hda_type)

    def test_run_rejects_missing_source_path_when_hou_is_available(self) -> None:
        temp_dir = _make_workspace_temp_dir()
        try:
            fake_hou = _FakeHou()
            with self.assertRaises(ValueError):
                run(
                    {
                        "process_id": "publish.asset.usd",
                        "parameters": {
                            "source": str(temp_dir / "missing.bgeo"),
                            "output": str(temp_dir / "publish" / "tree.usd"),
                            "context": "lookdev",
                        },
                    },
                    hou_module=fake_hou,
                )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_run_fails_when_hda_does_not_write_output_file(self) -> None:
        temp_dir = _make_workspace_temp_dir()
        try:
            source = temp_dir / "source.bgeo"
            source.write_text("geo", encoding="utf-8")
            output = temp_dir / "publish" / "tree.usd"
            fake_hou = _FakeHou(write_output_on_cook=False)

            result = run(
                {
                    "process_id": "publish.asset.usd",
                    "parameters": {
                        "source": str(source),
                        "output": str(output),
                        "context": "lookdev",
                    },
                },
                hou_module=fake_hou,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual("failed", result["status"])
        self.assertIn("no output file was produced", result["message"])


if __name__ == "__main__":
    unittest.main()
