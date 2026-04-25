from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.asset_schema import entity_root_candidates
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


def list_project_entities(
    project_root: Path,
    schema: Mapping[str, Any] | None = None,
) -> tuple[list[Path], list[Path]]:
    shots = _list_entity_dirs(project_root, "shot", schema)
    assets = _list_entity_dirs(project_root, "asset", schema)
    return shots, assets


def _list_entity_dirs(
    project_root: Path,
    entity_type: str,
    schema: Mapping[str, Any] | None = None,
) -> list[Path]:
    root_names = entity_root_candidates(dict(schema or {}), entity_type) if schema else []
    if not root_names:
        root_names = ["shots"] if entity_type == "shot" else ["assets"]
    found: list[Path] = []
    seen: set[Path] = set()
    for root_name in root_names:
        root_path = project_root / root_name
        if not root_path.exists():
            continue
        try:
            children = sorted(
                [path for path in root_path.iterdir() if path.is_dir()],
                key=lambda path: path.name.lower(),
            )
        except OSError:
            continue
        for child in children:
            if child not in seen:
                seen.add(child)
                found.append(child)
    return found


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


def count_visible_entity_dirs(
    entity_dirs: Sequence[Path],
    *,
    prefix_filter: str,
    search_text: str,
) -> int:
    return len(
        filter_entity_dirs(
            entity_dirs,
            prefix_filter=prefix_filter,
            search_text=search_text,
        )
    )


def entity_empty_reason(
    *,
    total: int,
    search_text: str,
    prefix_filter: str,
    role_label: str,
) -> str:
    if total > 0 and search_text:
        return "Try clearing the search field or changing the current group filter."
    if total > 0 and prefix_filter and prefix_filter != "All":
        return "Try switching Group back to All."
    return f"The current layout did not classify any folder as a {role_label}."
