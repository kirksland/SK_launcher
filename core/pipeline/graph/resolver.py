from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .models import DependencyEdge


@dataclass(frozen=True, slots=True)
class GraphNeighborhood:
    incoming: tuple[DependencyEdge, ...]
    outgoing: tuple[DependencyEdge, ...]


class DependencyGraph:
    def __init__(self, edges: tuple[DependencyEdge, ...] = ()) -> None:
        self._edges = tuple(edges)

    @property
    def edges(self) -> tuple[DependencyEdge, ...]:
        return self._edges

    def incoming_for(self, entity_id: object) -> tuple[DependencyEdge, ...]:
        key = str(entity_id or "").strip().lower()
        if not key:
            return ()
        return tuple(edge for edge in self._edges if edge.downstream.id == key)

    def outgoing_for(self, entity_id: object) -> tuple[DependencyEdge, ...]:
        key = str(entity_id or "").strip().lower()
        if not key:
            return ()
        return tuple(edge for edge in self._edges if edge.upstream.id == key)

    def neighborhood_for(self, entity_id: object) -> GraphNeighborhood:
        return GraphNeighborhood(
            incoming=self.incoming_for(entity_id),
            outgoing=self.outgoing_for(entity_id),
        )

    def downstream_closure(self, entity_id: object) -> tuple[DependencyEdge, ...]:
        start = str(entity_id or "").strip().lower()
        if not start:
            return ()
        queue: deque[str] = deque([start])
        visited_entities: set[str] = {start}
        seen_edges: set[tuple[str, str, str]] = set()
        ordered: list[DependencyEdge] = []
        while queue:
            current = queue.popleft()
            for edge in self.outgoing_for(current):
                edge_key = (edge.upstream.id, edge.downstream.id, edge.kind)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    ordered.append(edge)
                downstream_id = edge.downstream.id
                if downstream_id in visited_entities:
                    continue
                visited_entities.add(downstream_id)
                queue.append(downstream_id)
        return tuple(ordered)

