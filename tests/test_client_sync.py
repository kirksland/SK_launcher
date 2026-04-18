import unittest
import os
from pathlib import Path
from uuid import uuid4

from core.client_sync import (
    available_sync_roots,
    collect_changes,
    compare_subdir,
    resolve_local_project_path,
    safe_mtime,
    sync_roots_for_project,
)


class ClientSyncTests(unittest.TestCase):
    def _make_case_dir(self, name: str) -> Path:
        path = Path("tests") / ".tmp" / f"{name}_{uuid4().hex}"
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

    def test_resolve_local_project_path_prefers_asset_manager_mapping(self) -> None:
        client_path = Path("C:/server/ProjectA")
        projects = [{"client_id": "ProjectA", "local_path": "D:/local/CustomA"}]
        resolved = resolve_local_project_path(client_path, projects, Path("D:/fallback"))
        self.assertEqual(resolved, Path("D:/local/CustomA"))

    def test_sync_roots_for_project_uses_preferred_defaults(self) -> None:
        roots, changed = sync_roots_for_project(
            "ProjectA",
            ["shots", "assets", "geo"],
            {},
        )
        self.assertTrue(changed)
        self.assertEqual(roots, ["assets", "shots"])

    def test_sync_roots_for_project_filters_unavailable_entries(self) -> None:
        roots, changed = sync_roots_for_project(
            "ProjectA",
            ["assets"],
            {"ProjectA": ["assets", "shots", 12]},
        )
        self.assertFalse(changed)
        self.assertEqual(roots, ["assets"])

    def test_available_sync_roots_returns_shared_directories(self) -> None:
        client = self._make_case_dir("client_roots")
        local = self._make_case_dir("local_roots")
        for root in ("assets", "shots", ".git"):
            (client / root).mkdir()
        for root in ("assets", "cache", "__pycache__"):
            (local / root).mkdir()
        self.assertEqual(available_sync_roots(client, local), ["assets"])

    def test_compare_subdir_detects_missing_local(self) -> None:
        client = self._make_case_dir("client_compare")
        local = self._make_case_dir("local_compare")
        (client / "assets").mkdir()
        self.assertEqual(compare_subdir(local, client, "assets"), "missing local")

    def test_collect_changes_reports_direction_markers(self) -> None:
        client = self._make_case_dir("client_changes")
        local = self._make_case_dir("local_changes")
        (local / "only_local.txt").write_text("a", encoding="utf-8")
        (client / "only_server.txt").write_text("b", encoding="utf-8")
        shared_local = local / "shared.txt"
        shared_server = client / "shared.txt"
        shared_server.write_text("old", encoding="utf-8")
        shared_local.write_text("new", encoding="utf-8")
        os.utime(shared_server, (1, 1))
        os.utime(shared_local, (5, 5))
        results = collect_changes(local, client, max_items=10, time_budget=1.0)
        self.assertIn("+ only_local.txt", results)
        self.assertIn("- only_server.txt", results)
        self.assertTrue(any(line.startswith("↑ shared.txt") for line in results))

    def test_safe_mtime_returns_zero_for_missing_path(self) -> None:
        self.assertEqual(safe_mtime(Path("Z:/does/not/exist")), 0.0)


if __name__ == "__main__":
    unittest.main()
