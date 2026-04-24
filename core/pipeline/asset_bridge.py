from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.asset_layout import EntityRecord, ResolvedAssetLayout
from core.pipeline.entities.models import EntityRef, FreshnessState
from core.pipeline.graph import DependencyEdge, DependencyGraph, impacted_downstream_entities, summarize_freshness


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


def _entity_id(project_root: Path, record: EntityRecord) -> str:
    project = _clean_token(project_root.name)
    role = _clean_token(record.role or record.entity_type)
    name = _clean_token(record.name)
    return ":".join(part for part in (project, role, name) if part)


def _path_entity_id(source_entity_id: str, representation: str, index: int) -> str:
    return f"{source_entity_id}:{_clean_token(representation)}:{index}"


def _latest_tree_mtime(path: Path) -> float:
    latest = 0.0
    try:
        if path.is_file():
            return path.stat().st_mtime
        for child in path.rglob("*"):
            try:
                latest = max(latest, child.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        return latest
    return latest


def entity_ref_for_record(project_root: Path, record: EntityRecord) -> EntityRef:
    return EntityRef(
        id=_entity_id(project_root, record),
        kind=_clean_token(record.role or record.entity_type),
        project_id=project_root.name,
        label=record.name,
        path=str(record.source_path),
    )


@dataclass(frozen=True, slots=True)
class PipelineEntityInspection:
    entity: EntityRef
    freshness: str
    downstream: tuple[object, ...]
    summary: dict[str, int]


def build_entity_dependency_graph(
    layout: ResolvedAssetLayout | None,
    record: EntityRecord | None,
    *,
    context: str | None = None,
) -> DependencyGraph:
    if layout is None or record is None:
        return DependencyGraph()
    source = entity_ref_for_record(layout.project_root, record)
    source_mtime = _latest_tree_mtime(record.source_path)
    edges: list[DependencyEdge] = []

    expected_representations = ["usd", "preview_image"]
    if record.entity_type == "shot":
        expected_representations.append("review_video")

    for representation in expected_representations:
        paths = layout.representation_paths(record, representation, context=context)
        if not paths:
            if record.role != "library_asset":
                missing = EntityRef(
                    id=_path_entity_id(source.id, representation, 0),
                    kind="missing_output",
                    project_id=layout.project_root.name,
                    label=f"Missing {representation}",
                )
                edges.append(
                    DependencyEdge(
                        upstream=source,
                        downstream=missing,
                        kind="publishes_from",
                        freshness=FreshnessState.MISSING_DEPENDENCY,
                    )
                )
            continue
        for index, path in enumerate(paths[:6], start=1):
            try:
                path_mtime = path.stat().st_mtime
            except OSError:
                path_mtime = 0.0
            freshness = FreshnessState.UP_TO_DATE
            if path_mtime < source_mtime:
                freshness = FreshnessState.STALE
            downstream = EntityRef(
                id=_path_entity_id(source.id, representation, index),
                kind="publish" if representation == "usd" else "review_media",
                project_id=layout.project_root.name,
                label=path.name,
                path=str(path),
            )
            edges.append(
                DependencyEdge(
                    upstream=source,
                    downstream=downstream,
                    kind="publishes_from",
                    freshness=freshness,
                )
            )
    return DependencyGraph(tuple(edges))


def inspect_entity_pipeline(
    layout: ResolvedAssetLayout | None,
    record: EntityRecord | None,
    *,
    context: str | None = None,
) -> PipelineEntityInspection | None:
    if layout is None or record is None:
        return None
    source = entity_ref_for_record(layout.project_root, record)
    graph = build_entity_dependency_graph(layout, record, context=context)
    downstream = impacted_downstream_entities(graph, source.id)
    summary = summarize_freshness(downstream)
    freshness = FreshnessState.UP_TO_DATE
    for state in (
        FreshnessState.INVALID,
        FreshnessState.MISSING_DEPENDENCY,
        FreshnessState.STALE,
        FreshnessState.NEEDS_REVIEW,
        FreshnessState.UP_TO_DATE,
    ):
        if summary.get(state, 0):
            freshness = state
            break
    return PipelineEntityInspection(
        entity=source,
        freshness=freshness,
        downstream=downstream,
        summary=summary,
    )
