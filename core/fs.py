from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

from core.dcc import detect_dcc_for_path, supported_scene_extensions

HIP_EXTS = (".hip", ".hiplc", ".hipnc")
SCENE_EXTS = supported_scene_extensions()


def find_projects(projects_dir: Path) -> List[Path]:
    if not projects_dir.exists():
        return []
    return sorted([p for p in projects_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower())


def list_scene_files_with_mtime(project_dir: Path) -> Tuple[List[Path], float]:
    scene_files_with_mtime: List[Tuple[Path, float]] = []
    latest = 0.0
    try:
        entries = list(project_dir.iterdir())
    except Exception:
        return [], 0.0
    for path in entries:
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCENE_EXTS:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        scene_files_with_mtime.append((path, mtime))
        if mtime > latest:
            latest = mtime
    scene_files_with_mtime.sort(key=lambda item: item[1], reverse=True)
    return [p for p, _ in scene_files_with_mtime], latest


def find_scene_files(project_dir: Path) -> List[Path]:
    scene_files, _latest = list_scene_files_with_mtime(project_dir)
    return scene_files


def list_hips_with_mtime(project_dir: Path) -> Tuple[List[Path], float]:
    scene_files, latest = list_scene_files_with_mtime(project_dir)
    hips = [path for path in scene_files if path.suffix.lower() in HIP_EXTS]
    return hips, latest


def find_hips(project_dir: Path) -> List[Path]:
    return [path for path in find_scene_files(project_dir) if path.suffix.lower() in HIP_EXTS]


def open_with_file_association(path: Path) -> None:
    os.startfile(str(path))  # type: ignore[attr-defined]


def open_hip(path: Path) -> None:
    open_with_file_association(path)


def scene_file_label(path: Path) -> str:
    descriptor = detect_dcc_for_path(path)
    if descriptor is None:
        return path.suffix.lower().lstrip(".") or "file"
    return descriptor.label


USD_EXTS = (".usd", ".usda", ".usdc", ".usdnc")


def list_usd_versions(
    entity_dir: Path,
    context: Optional[str] = None,
    search_locations: Optional[List[str]] = None,
) -> List[Path]:
    locations = [loc.lower() for loc in (search_locations or ["publish"])]
    usd_files: List[Path] = []
    seen: set[Path] = set()

    for loc in locations:
        if loc == "publish":
            publish_dir = entity_dir / "publish"
            if not publish_dir.exists():
                continue
            if context:
                context_dir = publish_dir / context
                if not context_dir.exists():
                    continue
                candidates = [p for p in context_dir.rglob("*") if p.is_file() and p.suffix.lower() in USD_EXTS]
            else:
                candidates = [p for p in publish_dir.rglob("*") if p.is_file() and p.suffix.lower() in USD_EXTS]
        elif loc == "root":
            candidates = [
                p for p in entity_dir.iterdir()
                if p.is_file() and p.suffix.lower() in USD_EXTS
            ]
        else:
            continue

        for path in candidates:
            if path not in seen:
                seen.add(path)
                usd_files.append(path)

    return sorted(usd_files, key=lambda p: p.name)


def list_review_videos(entity_dir: Path, context: Optional[str] = None) -> List[Path]:
    publish_dir = entity_dir / "publish"
    if not publish_dir.exists():
        return []
    if context:
        context_dir = publish_dir / context
        if not context_dir.exists():
            return []
        files = list(context_dir.rglob("*"))
    else:
        files = list(publish_dir.rglob("*"))
    videos = [p for p in files if p.is_file() and p.suffix.lower() in (".mp4", ".mov")]
    return sorted(videos, key=lambda p: p.name)


def group_versions(usd_files: List[Path], video_files: List[Path]) -> List[Tuple[str, Optional[Path], Optional[Path]]]:
    def key_for(p: Path) -> str:
        return p.stem

    usd_map = {key_for(p): p for p in usd_files}
    vid_map = {key_for(p): p for p in video_files}
    keys = sorted(set(usd_map.keys()) | set(vid_map.keys()))
    grouped: List[Tuple[str, Optional[Path], Optional[Path]]] = []
    for k in keys:
        grouped.append((k, usd_map.get(k), vid_map.get(k)))
    return grouped


def name_prefix(name: str) -> str:
    return name.split("_", 1)[0].lower()


def latest_preview_image(entity_dir: Path) -> Optional[Path]:
    preview_dir = entity_dir / "preview"
    if not preview_dir.exists():
        return None
    candidates = [p for p in preview_dir.iterdir() if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg")]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def list_preview_images(entity_dir: Path) -> List[Path]:
    preview_dir = entity_dir / "preview"
    if not preview_dir.exists():
        return []
    candidates = [p for p in preview_dir.iterdir() if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg")]
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
