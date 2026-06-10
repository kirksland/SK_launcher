import json
import unittest
from pathlib import Path
from uuid import uuid4

from core.comfy_metadata import format_workflow_json, load_comfy_video_metadata


class ComfyMetadataTests(unittest.TestCase):
    def _make_video(self, payload: dict[str, object]) -> Path:
        root = Path("tests") / ".tmp" / f"comfy_metadata_{uuid4().hex}"
        root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(self._cleanup_dir, root)
        path = root / "sample.mp4"
        comment = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16 + comment)
        return path

    @staticmethod
    def _cleanup_dir(path: Path) -> None:
        if not path.exists():
            return
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()

    def test_loads_comfy_prompt_and_workflow_from_mp4_comment(self) -> None:
        prompt = {
            "1": {
                "inputs": {"text": "A city at sunset"},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Positive Prompt"},
            },
            "2": {
                "inputs": {"text": "blurry"},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Negative Prompt"},
            },
            "3": {
                "inputs": {
                    "seed": 42,
                    "steps": 8,
                    "cfg": 1.5,
                    "sampler_name": "euler",
                    "scheduler": "beta",
                },
                "class_type": "KSampler",
            },
            "4": {
                "inputs": {"unet_name": "wan.gguf"},
                "class_type": "UnetLoader",
            },
        }
        workflow = {"id": "workflow-id", "nodes": []}
        path = self._make_video({"prompt": json.dumps(prompt), "workflow": workflow})

        metadata = load_comfy_video_metadata(path)

        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(metadata.positive_prompt, "A city at sunset")
        self.assertEqual(metadata.negative_prompt, "blurry")
        self.assertEqual(metadata.seed, 42)
        self.assertEqual(metadata.steps, 8)
        self.assertEqual(metadata.model, "wan.gguf")
        self.assertIn('"workflow-id"', format_workflow_json(metadata))

    def test_returns_none_for_video_without_comfy_metadata(self) -> None:
        path = self._make_video({"unrelated": True})
        self.assertIsNone(load_comfy_video_metadata(path))


if __name__ == "__main__":
    unittest.main()
