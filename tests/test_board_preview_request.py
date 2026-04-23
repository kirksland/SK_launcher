import unittest
from pathlib import Path

from core.board_preview import PreviewRequest


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


if __name__ == "__main__":
    unittest.main()
