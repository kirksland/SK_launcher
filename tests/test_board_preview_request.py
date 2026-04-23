import unittest
from pathlib import Path

from core.board_preview import PreviewRequest, PreviewRuntimeState


class PreviewRequestTests(unittest.TestCase):
    def test_preview_request_key_is_stable_for_equivalent_settings(self) -> None:
        first = PreviewRequest(
            kind=" Image_Adjust ",
            media_kind=" Image ",
            source_path="C:/show/plate.png",
            mtime_ns=12,
            settings={"tool_stack": [{"id": "crop", "settings": {"left": 0.1}}]},
        )
        second = PreviewRequest(
            kind="image_adjust",
            media_kind="image",
            source_path="C:/show/plate.png",
            mtime_ns=12,
            settings={"tool_stack": [{"settings": {"left": 0.1}, "id": "crop"}]},
        )

        self.assertEqual(first.key, second.key)
        self.assertTrue(first.matches_key(second.key))

    def test_preview_request_key_changes_when_settings_change(self) -> None:
        first = PreviewRequest("exr_channel", "image", "plate.exr", {"channel": "RGB"}, 1)
        second = PreviewRequest("exr_channel", "image", "plate.exr", {"channel": "depth"}, 1)

        self.assertNotEqual(first.key, second.key)

    def test_preview_request_from_path_includes_file_mtime_when_available(self) -> None:
        path = Path("tests") / ".tmp" / "preview_request_source.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("preview", encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        request = PreviewRequest.from_path(
            kind="image_adjust",
            media_kind="image",
            source_path=path,
            settings={"max_dim": 512},
        )

        self.assertGreater(request.mtime_ns, 0)
        self.assertEqual(str(path), request.source_path)

    def test_preview_runtime_queues_latest_request_while_busy(self) -> None:
        runtime = PreviewRuntimeState()
        first = PreviewRequest("image_adjust", "image", "a.png", {"v": 1}, 1)
        second = PreviewRequest("image_adjust", "image", "a.png", {"v": 2}, 1)
        third = PreviewRequest("image_adjust", "image", "a.png", {"v": 3}, 1)

        self.assertTrue(runtime.start_or_queue(first))
        self.assertFalse(runtime.start_or_queue(second))
        self.assertFalse(runtime.start_or_queue(third))

        self.assertTrue(runtime.is_current(first.key))
        self.assertIs(runtime.finish(), third)
        self.assertFalse(runtime.busy)

    def test_preview_runtime_cancel_clears_active_and_pending_requests(self) -> None:
        runtime = PreviewRuntimeState()
        first = PreviewRequest("image_adjust", "image", "a.png", {"v": 1}, 1)
        second = PreviewRequest("image_adjust", "image", "a.png", {"v": 2}, 1)

        runtime.start_or_queue(first)
        runtime.start_or_queue(second)
        runtime.cancel()

        self.assertFalse(runtime.busy)
        self.assertIsNone(runtime.active_key)
        self.assertIsNone(runtime.pending_request)
        self.assertFalse(runtime.is_current(first.key))


if __name__ == "__main__":
    unittest.main()
