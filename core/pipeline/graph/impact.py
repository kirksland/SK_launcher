from __future__ import annotations

from dataclasses import dataclass

from core.pipeline.entities.models import EntityRef, FreshnessState

from .models import DependencyEdge
from .resolver import DependencyGraph


def _freshness_rank(value: object) -> int:
    key = str(value or "").strip().lower()
    order = {
        FreshnessState.INVALID: 4,
        FreshnessState.MISSING_DEPENDENCY: 3,
        FreshnessState.STALE: 2,
        FreshnessState.NEEDS_REVIEW: 1,
        FreshnessState.UP_TO_DATE: 0,
    }
    return order.get(key, 0)


@dataclass(frozen=True, slots=True)
class ImpactRecord:
    entity: EntityRef
    freshness: str
    via: tuple[DependencyEdge, ...]


def impacted_downstream_entities(graph: DependencyGraph, entity_id: object) -> tuple[ImpactRecord, ...]:
    closure = graph.downstream_closure(entity_id)
    if not closure:
        return ()
    records: dict[str, ImpactRecord] = {}
    for edge in closure:
        existing = records.get(edge.downstream.id)
        path = (edge,)
        if existing is None:
            records[edge.downstream.id] = ImpactRecord(
                entity=edge.downstream,
                freshness=edge.freshness,
                via=path,
            )
            continue
        if _freshness_rank(edge.freshness) > _freshness_rank(existing.freshness):
            records[edge.downstream.id] = ImpactRecord(
                entity=edge.downstream,
                freshness=edge.freshness,
                via=existing.via + path,
            )
    return tuple(sorted(records.values(), key=lambda item: (item.entity.kind, item.entity.id)))


def summarize_freshness(records: tuple[ImpactRecord, ...]) -> dict[str, int]:
    summary = {state: 0 for state in FreshnessState.ALL}
    for record in records:
        summary[record.freshness] = summary.get(record.freshness, 0) + 1
    return summary
