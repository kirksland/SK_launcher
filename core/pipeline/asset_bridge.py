from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from core.asset_layout import EntityRecord, ResolvedAssetLayout
from core.pipeline.entities.models import EntityRef, FreshnessState
from core.pipeline.graph import DependencyEdge, DependencyGraph, impacted_downstream_entities, summarize_freshness
from core.pipeline.processes.registry import available_processes_for_entity_kind

if TYPE_CHECKING:
    from core.pipeline.provenance.models import ProducedArtifactRecord


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
    available_processes: tuple[object, ...]


def build_entity_dependency_graph(
    layout: ResolvedAssetLayout | None,
    record: EntityRecord | None,
    *,
    context: str | None = None,
    produced_artifacts: tuple[ProducedArtifactRecord, ...] = (),
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
    edges.extend(_provenance_edges_for_entity(source, layout.project_root.name, produced_artifacts))
    return DependencyGraph(tuple(edges))


def _provenance_edges_for_entity(
    source: EntityRef,
    project_name: str,
    produced_artifacts: tuple[ProducedArtifactRecord, ...],
) -> tuple[DependencyEdge, ...]:
    if not produced_artifacts:
        return ()
    normalized_source_path = str(source.path or "").strip().replace("\\", "/").lower()
    edges: list[DependencyEdge] = []
    seen_paths: set[str] = set()
    for artifact in produced_artifacts:
        matched = False
        for source_artifact in artifact.source_artifacts:
            artifact_entity_id = _clean_token(source_artifact.entity_id)
            artifact_source_path = str(source_artifact.path or "").strip().replace("\\", "/").lower()
            if artifact_entity_id and artifact_entity_id == source.id:
                matched = True
                break
            if normalized_source_path and artifact_source_path and artifact_source_path.startswith(normalized_source_path):
                matched = True
                break
        if not matched:
            continue
        artifact_path = str(artifact.path or "").strip()
        dedupe_key = artifact_path.lower()
        if not artifact_path or dedupe_key in seen_paths:
            continue
        seen_paths.add(dedupe_key)
        downstream_kind = "publish" if artifact.kind == "usd" else "review_media"
        downstream = EntityRef(
            id=f"{source.id}:artifact:{_clean_token(artifact.id)}",
            kind=downstream_kind,
            project_id=project_name,
            label=artifact.label or Path(artifact.path).name,
            path=artifact.path,
        )
        edges.append(
            DependencyEdge(
                upstream=source,
                downstream=downstream,
                kind="publishes_from",
                freshness=FreshnessState.UP_TO_DATE,
            )
        )
    return tuple(edges)


def inspect_entity_pipeline(
    layout: ResolvedAssetLayout | None,
    record: EntityRecord | None,
    *,
    context: str | None = None,
    produced_artifacts: tuple[ProducedArtifactRecord, ...] = (),
) -> PipelineEntityInspection | None:
    if layout is None or record is None:
        return None
    source = entity_ref_for_record(layout.project_root, record)
    graph = build_entity_dependency_graph(
        layout,
        record,
        context=context,
        produced_artifacts=produced_artifacts,
    )
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
        available_processes=available_processes_for_entity_kind(source.kind),
    )
