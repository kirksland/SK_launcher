import unittest
from pathlib import Path

from core.project_catalog import (
    filter_and_sort_projects,
    prune_project_cache,
    prune_project_selection,
)


class ProjectCatalogTests(unittest.TestCase):
    def test_filter_and_sort_projects_filters_by_query(self) -> None:
        projects = [Path("Alpha"), Path("Beta"), Path("Gamma")]
        filtered = filter_and_sort_projects(
            projects,
            query="be",
            sort_mode="Name (A-Z)",
            latest_mtime=lambda _path: 0.0,
        )
        self.assertEqual(filtered, [Path("Beta")])

    def test_filter_and_sort_projects_uses_latest_mtime_for_date_sort(self) -> None:
        projects = [Path("A"), Path("B"), Path("C")]
        mtimes = {Path("A"): 1.0, Path("B"): 5.0, Path("C"): 3.0}
        ordered = filter_and_sort_projects(
            projects,
            query="",
            sort_mode="Date (Newest)",
            latest_mtime=lambda path: mtimes[path],
        )
        self.assertEqual(ordered, [Path("B"), Path("C"), Path("A")])

    def test_prune_project_cache_removes_missing_projects(self) -> None:
        keep = [Path("A")]
        cache = {
            Path("A"): (1.0, [], 0.0),
            Path("B"): (1.0, [], 0.0),
        }
        prune_project_cache(keep, cache)
        self.assertEqual(set(cache.keys()), {Path("A")})

    def test_prune_project_selection_removes_missing_projects(self) -> None:
        selection = {
            Path("A"): Path("A.hip"),
            Path("B"): Path("B.hip"),
        }
        prune_project_selection([Path("B")], selection)
        self.assertEqual(selection, {Path("B"): Path("B.hip")})


if __name__ == "__main__":
    unittest.main()
