import os
import unittest
from pathlib import Path
from unittest import mock

from core.project_storage import (
    asset_exr_thumb_dir,
    board_exr_thumb_dir,
    local_project_runtime_dir,
    local_runtime_storage_dir,
    project_cache_base_dir,
    runtime_cache_location,
)


class ProjectStorageTests(unittest.TestCase):
    def test_runtime_cache_location_defaults_to_project_without_settings(self) -> None:
        self.assertEqual(runtime_cache_location(None), "project")

    def test_project_cache_base_dir_uses_project_folder_when_requested(self) -> None:
        root = Path("C:/projects/demo")

        result = project_cache_base_dir(root, {"runtime_cache_location": "project"})

        self.assertEqual(result, root / ".skyforge_cache")

    def test_project_cache_base_dir_uses_local_runtime_storage_when_requested(self) -> None:
        root = Path("C:/projects/demo")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\justi\AppData\Local"}, clear=False):
            result = project_cache_base_dir(root, {"runtime_cache_location": "local_appdata"})

        self.assertEqual(
            result,
            local_project_runtime_dir(root) / "cache",
        )

    def test_asset_and_board_thumb_dirs_are_namespaced_under_cache_base(self) -> None:
        root = Path("C:/projects/demo")

        asset_dir = asset_exr_thumb_dir(root, {"runtime_cache_location": "project"})
        board_dir = board_exr_thumb_dir(root, {"runtime_cache_location": "project"})

        self.assertEqual(asset_dir, root / ".skyforge_cache" / "asset_exr_thumbs")
        self.assertEqual(board_dir, root / ".skyforge_cache" / "exr_thumbs")

    def test_local_runtime_storage_dir_prefers_localappdata(self) -> None:
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\justi\AppData\Local"}, clear=False):
            result = local_runtime_storage_dir()

        self.assertEqual(result, Path(r"C:\Users\justi\AppData\Local") / "SkyforgeLauncher")


if __name__ == "__main__":
    unittest.main()
