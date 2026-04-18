from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from core.fs import name_prefix


def filter_asset_entries(
    entries: Sequence[Mapping[str, object]],
    query: str,
) -> list[Mapping[str, object]]:
    normalized = query.strip().lower()
    if not normalized:
        return list(entries)
    return [
        entry
        for entry in entries
        if normalized in str(entry.get("local_path", "")).lower()
    ]


def existing_project_paths(entries: Iterable[Mapping[str, object]]) -> list[Path]:
    paths: list[Path] = []
    for entry in entries:
        path = Path(str(entry.get("local_path", "")))
        if path.exists() and path.is_dir():
            paths.append(path)
    return paths


def list_project_entities(project_root: Path) -> tuple[list[Path], list[Path]]:
    shots_root = project_root / "shots"
    assets_root = project_root / "assets"
    shots = sorted([path for path in shots_root.iterdir() if path.is_dir()]) if shots_root.exists() else []
    assets = sorted([path for path in assets_root.iterdir() if path.is_dir()]) if assets_root.exists() else []
    return shots, assets


def entity_prefixes(entity_dirs: Sequence[Path]) -> list[str]:
    return sorted({name_prefix(path.name) for path in entity_dirs})


def resolved_filter_choice(previous: str, options: Sequence[str], default: str = "All") -> str:
    return previous if previous in options else default


def filter_entity_dirs(
    entity_dirs: Sequence[Path],
    *,
    prefix_filter: str,
    search_text: str,
) -> list[Path]:
    normalized_search = search_text.strip().lower()
    filtered: list[Path] = []
    for entity_dir in entity_dirs:
        if prefix_filter != "All" and name_prefix(entity_dir.name) != prefix_filter:
            continue
        if normalized_search and normalized_search not in entity_dir.name.lower():
            continue
        filtered.append(entity_dir)
    return filtered
