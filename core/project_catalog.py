from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from core.fs import list_scene_files_with_mtime

ProjectSceneCache = dict[Path, tuple[float, list[Path], float]]


def filter_and_sort_projects(
    projects: list[Path],
    *,
    query: str,
    sort_mode: str,
    latest_mtime: Callable[[Path], float],
) -> list[Path]:
    normalized = query.strip().lower()
    if normalized:
        projects = [project for project in projects if normalized in project.name.lower()]
    if sort_mode.startswith("Date"):
        return sorted(projects, key=latest_mtime, reverse=True)
    return sorted(projects, key=lambda project: project.name.lower())


def prune_project_cache(projects: list[Path], cache: ProjectSceneCache) -> None:
    keep = set(projects)
    for key in list(cache.keys()):
        if key not in keep:
            cache.pop(key, None)


def prune_project_selection(projects: list[Path], selection: dict[Path, Path]) -> None:
    keep = set(projects)
    for key in list(selection.keys()):
        if key not in keep:
            selection.pop(key, None)


def scan_project_scene_files(
    project_path: Path,
    *,
    scan_token: float,
    cache: ProjectSceneCache,
) -> tuple[list[Path], float]:
    cached = cache.get(project_path)
    if cached and cached[0] == scan_token:
        return cached[1], cached[2]
    scene_files, latest = list_scene_files_with_mtime(project_path)
    cache[project_path] = (scan_token, scene_files, latest)
    return scene_files, latest


def scan_project_hips(
    project_path: Path,
    *,
    scan_token: float,
    cache: ProjectSceneCache,
) -> tuple[list[Path], float]:
    return scan_project_scene_files(project_path, scan_token=scan_token, cache=cache)


def selected_project_path(current_item: object) -> Optional[Path]:
    if current_item is None or not hasattr(current_item, "data"):
        return None
    path_text = current_item.data(0x0100)
    if not path_text:
        return None
    return Path(str(path_text))
