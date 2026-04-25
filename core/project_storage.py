from __future__ import annotations

import hashlib
import os
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
    return None if local_root is None else local_root / "cache"


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
