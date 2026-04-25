from __future__ import annotations

import json
import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Mapping, Optional

from core.settings import normalize_runtime_cache_location


def local_runtime_storage_dir() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA", "").strip()
    if local_appdata:
        return Path(local_appdata) / "SkyforgeLauncher"
    return Path.home() / "AppData" / "Local" / "SkyforgeLauncher"


def runtime_cache_location(settings: Optional[Mapping[str, object]] = None) -> str:
    if settings is None:
        return "project"
    return normalize_runtime_cache_location(settings.get("runtime_cache_location"))


def project_storage_key(project_root: Path) -> str:
    try:
        resolved = project_root.resolve()
    except Exception:
        resolved = project_root
    return hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:16]


def local_project_runtime_dir(project_root: Optional[Path]) -> Optional[Path]:
    if project_root is None:
        return None
    return local_runtime_storage_dir() / "projects" / project_storage_key(project_root)


def project_cache_base_dir(
    project_root: Optional[Path],
    settings: Optional[Mapping[str, object]] = None,
) -> Optional[Path]:
    if project_root is None:
        return None
    if runtime_cache_location(settings) == "project":
        return project_root / ".skyforge_cache"
    local_root = local_project_runtime_dir(project_root)
    if local_root is None:
        return None
    _touch_local_project_runtime(local_root, project_root)
    return local_root / "cache"


def board_exr_thumb_dir(
    project_root: Optional[Path],
    settings: Optional[Mapping[str, object]] = None,
) -> Optional[Path]:
    base_dir = project_cache_base_dir(project_root, settings)
    return None if base_dir is None else base_dir / "exr_thumbs"


def asset_exr_thumb_dir(
    project_root: Optional[Path],
    settings: Optional[Mapping[str, object]] = None,
) -> Optional[Path]:
    base_dir = project_cache_base_dir(project_root, settings)
    return None if base_dir is None else base_dir / "asset_exr_thumbs"


def prune_local_runtime_cache(settings: Optional[Mapping[str, object]] = None) -> dict[str, int]:
    if runtime_cache_location(settings) != "local_appdata":
        return {"removed_projects": 0, "freed_bytes": 0}
    projects_root = local_runtime_storage_dir() / "projects"
    if not projects_root.exists():
        return {"removed_projects": 0, "freed_bytes": 0}

    max_days = _positive_int(settings.get("runtime_cache_max_days") if settings else None, 30)
    max_gb = _positive_float(settings.get("runtime_cache_max_gb") if settings else None, 5.0)
    max_bytes = int(max_gb * 1024 * 1024 * 1024)
    now = time.time()
    deadline = now - (max_days * 86400)

    entries: list[dict[str, object]] = []
    removed_projects = 0
    freed_bytes = 0

    for child in projects_root.iterdir():
        if not child.is_dir():
            continue
        metadata = _read_runtime_metadata(child)
        project_path = Path(str(metadata.get("project_root", "")).strip()) if metadata else None
        last_access = float(metadata.get("last_access", 0.0)) if metadata else 0.0
        if last_access <= 0:
            last_access = _safe_mtime(child)
        size_bytes = _dir_size(child)
        missing_project = project_path is None or not str(project_path) or not project_path.exists()
        stale = last_access < deadline
        if missing_project or stale:
            freed_bytes += _remove_tree(child)
            removed_projects += 1
            continue
        entries.append({"path": child, "last_access": last_access, "size": size_bytes})

    total_size = sum(int(item["size"]) for item in entries)
    if total_size > max_bytes:
        for item in sorted(entries, key=lambda item: float(item["last_access"])):
            if total_size <= max_bytes:
                break
            total_size -= int(item["size"])
            freed_bytes += _remove_tree(Path(item["path"]))
            removed_projects += 1

    return {"removed_projects": removed_projects, "freed_bytes": freed_bytes}


def _touch_local_project_runtime(local_root: Path, project_root: Path) -> None:
    try:
        local_root.mkdir(parents=True, exist_ok=True)
        metadata_path = local_root / "project.json"
        payload = {
            "project_root": str(project_root),
            "last_access": time.time(),
        }
        metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        return


def _read_runtime_metadata(local_root: Path) -> Optional[dict[str, object]]:
    path = local_root / "project.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _safe_mtime(path: Path) -> float:
    try:
        return float(path.stat().st_mtime)
    except Exception:
        return 0.0


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for child in path.rglob("*"):
            if child.is_file():
                try:
                    total += int(child.stat().st_size)
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def _remove_tree(path: Path) -> int:
    size = _dir_size(path)
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        return 0
    return size


def _positive_int(raw: object, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _positive_float(raw: object, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default
