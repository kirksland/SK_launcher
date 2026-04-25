import os
import unittest
from pathlib import Path
from unittest import mock
import json
import time

from core.project_storage import (
    asset_exr_thumb_dir,
    board_exr_thumb_dir,
    local_project_runtime_dir,
    local_runtime_storage_dir,
    project_cache_base_dir,
    prune_local_runtime_cache,
    runtime_cache_location,
)


class ProjectStorageTests(unittest.TestCase):
    def _make_case_dir(self, name: str) -> Path:
        path = Path("tests") / ".tmp" / name
        if path.exists():
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()
        path.mkdir(parents=True, exist_ok=False)
        self.addCleanup(self._cleanup_dir, path)
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

    def test_prune_local_runtime_cache_removes_missing_projects(self) -> None:
        root = self._make_case_dir("project_storage_prune_missing")
        local_appdata = root / "AppData"
        projects_root = local_appdata / "SkyforgeLauncher" / "projects"
        runtime_dir = projects_root / "deadbeef"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "cache" / "thumb.png").parent.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "cache" / "thumb.png").write_text("fake", encoding="utf-8")
        (runtime_dir / "project.json").write_text(
            json.dumps({"project_root": str(root / "missing_project"), "last_access": 9999999999}),
            encoding="utf-8",
        )

        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata)}, clear=False):
            result = prune_local_runtime_cache({"runtime_cache_location": "local_appdata"})

        self.assertEqual(result["removed_projects"], 1)
        self.assertFalse(runtime_dir.exists())

    def test_prune_local_runtime_cache_trims_oldest_when_oversized(self) -> None:
        root = self._make_case_dir("project_storage_prune_size")
        local_appdata = root / "AppData"
        projects_root = local_appdata / "SkyforgeLauncher" / "projects"
        source_a = root / "projectA"
        source_b = root / "projectB"
        source_a.mkdir(parents=True, exist_ok=True)
        source_b.mkdir(parents=True, exist_ok=True)

        old_dir = projects_root / "old"
        new_dir = projects_root / "new"
        now = time.time()
        for runtime_dir, source, access_value in ((old_dir, source_a, now - 10.0), (new_dir, source_b, now - 5.0)):
            (runtime_dir / "cache").mkdir(parents=True, exist_ok=True)
            (runtime_dir / "cache" / "thumb.bin").write_bytes(b"x" * 1024 * 1024)
            (runtime_dir / "project.json").write_text(
                json.dumps({"project_root": str(source), "last_access": access_value}),
                encoding="utf-8",
            )

        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata)}, clear=False):
            result = prune_local_runtime_cache(
                {
                    "runtime_cache_location": "local_appdata",
                    "runtime_cache_max_gb": 1,
                    "runtime_cache_max_days": 365,
                }
            )

        self.assertEqual(result["removed_projects"], 0)
        self.assertTrue(old_dir.exists())
        self.assertTrue(new_dir.exists())

        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata)}, clear=False):
            result = prune_local_runtime_cache(
                {
                    "runtime_cache_location": "local_appdata",
                    "runtime_cache_max_gb": 0.001,
                    "runtime_cache_max_days": 365,
                }
            )

        self.assertEqual(result["removed_projects"], 1)
        self.assertFalse(old_dir.exists())
        self.assertTrue(new_dir.exists())


if __name__ == "__main__":
    unittest.main()
