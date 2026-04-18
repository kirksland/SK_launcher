from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

DEFAULT_SYNC_EXCLUDE_DIRS = frozenset(
    {".git", ".skyforge_board_assets", ".skyforge_sync", "__pycache__"}
)
DEFAULT_SYNC_INCLUDE_EXTS = frozenset(
    {
        ".usd",
        ".usda",
        ".usdc",
        ".usdnc",
        ".abc",
        ".fbx",
        ".obj",
        ".png",
        ".jpg",
        ".jpeg",
        ".exr",
        ".tif",
        ".tiff",
        ".mov",
        ".mp4",
        ".txt",
        ".json",
    }
)
DEFAULT_SYNC_PREFERRED_ROOTS = ("assets", "shots")


def safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def resolve_local_project_path(
    client_path: Path,
    asset_manager_projects: Sequence[Mapping[str, object]],
    projects_dir: Path,
) -> Optional[Path]:
    client_id = client_path.name
    for entry in asset_manager_projects:
        if entry.get("client_id") == client_id and entry.get("local_path"):
            return Path(str(entry.get("local_path")))
    candidate = projects_dir / client_id
    return candidate if candidate.exists() else None


def available_sync_roots(
    client_path: Path,
    local_path: Path,
    *,
    exclude_dirs: Optional[Iterable[str]] = None,
) -> list[str]:
    exclude = {name.lower() for name in (exclude_dirs or DEFAULT_SYNC_EXCLUDE_DIRS)}
    server_dirs = _list_child_dirs(client_path, exclude)
    local_dirs = _list_child_dirs(local_path, exclude)
    return sorted(server_dirs & local_dirs, key=lambda value: value.lower())


def sync_roots_for_project(
    client_id: str,
    available: Sequence[str],
    store: Mapping[str, object],
    *,
    preferred_roots: Sequence[str] = DEFAULT_SYNC_PREFERRED_ROOTS,
) -> tuple[list[str], bool]:
    roots = store.get(client_id)
    if not isinstance(roots, list):
        preferred = [root for root in preferred_roots if root in available]
        resolved = preferred if preferred else list(available)
        return resolved, True

    cleaned = [str(root) for root in roots if isinstance(root, str)]
    if available:
        cleaned = [root for root in cleaned if root in available]
    return cleaned, False


def latest_mtime(root: Path, max_entries: int = 12000, time_budget: float = 0.20) -> float:
    latest = 0.0
    start = time.time()
    count = 0
    stack = [root]
    while stack:
        if count >= max_entries or (time.time() - start) > time_budget:
            break
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    count += 1
                    if count >= max_entries or (time.time() - start) > time_budget:
                        break
                    try:
                        stat = entry.stat()
                    except OSError:
                        continue
                    if stat.st_mtime > latest:
                        latest = stat.st_mtime
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
        except OSError:
            continue
    return latest


def compare_subdir(local_root: Path, client_root: Path, subdir: str) -> str:
    local_path = local_root / subdir
    client_path = client_root / subdir
    if not local_path.exists() and not client_path.exists():
        return "missing"
    if not local_path.exists():
        return "missing local"
    if not client_path.exists():
        return "missing server"
    local_latest = latest_mtime(local_path, max_entries=12000, time_budget=0.20)
    client_latest = latest_mtime(client_path, max_entries=12000, time_budget=0.20)
    if local_latest > client_latest:
        return "local newer"
    if client_latest > local_latest:
        return "server newer"
    return "same"


def collect_changes(
    local_root: Path,
    client_root: Path,
    *,
    max_items: int = 40,
    time_budget: float = 0.30,
) -> list[str]:
    start = time.time()
    local_map = _scan_relative_mtimes(local_root, start=start, time_budget=time_budget)
    client_map = _scan_relative_mtimes(client_root, start=start, time_budget=time_budget)
    results: list[str] = []
    keys = set(local_map.keys()) | set(client_map.keys())
    for rel in sorted(keys):
        if (time.time() - start) > time_budget:
            break
        if rel not in client_map:
            results.append(f"+ {rel}")
        elif rel not in local_map:
            results.append(f"- {rel}")
        else:
            local_mtime = local_map[rel]
            client_mtime = client_map[rel]
            if local_mtime > client_mtime + 0.5:
                results.append(f"↑ {rel}")
            elif client_mtime > local_mtime + 0.5:
                results.append(f"↓ {rel}")
        if len(results) >= max_items:
            break
    return results


def _list_child_dirs(root: Path, exclude: set[str]) -> set[str]:
    names: set[str] = set()
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if not entry.is_dir():
                    continue
                name = entry.name
                if name.lower() not in exclude:
                    names.add(name)
    except OSError:
        return set()
    return names


def _scan_relative_mtimes(
    root: Path,
    *,
    start: float,
    time_budget: float,
    max_entries: int = 5000,
) -> dict[str, float]:
    data: dict[str, float] = {}
    stack = [root]
    while stack and len(data) < max_entries:
        if (time.time() - start) > time_budget:
            break
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if (time.time() - start) > time_budget:
                        break
                    try:
                        rel = str(Path(entry.path).relative_to(root))
                        stat = entry.stat()
                    except (OSError, ValueError):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    else:
                        data[rel] = stat.st_mtime
                    if len(data) >= max_entries:
                        break
        except OSError:
            continue
    return data
