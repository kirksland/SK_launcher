import unittest

from core.pipeline.entities.models import EntityRef, FreshnessState
from core.pipeline.graph import DependencyEdge, DependencyGraph, impacted_downstream_entities, summarize_freshness


class PipelineGraphResolverTests(unittest.TestCase):
    def _make_graph(self) -> DependencyGraph:
        asset = EntityRef("charactera_model", "asset")
        rig = EntityRef("charactera_rig", "publish")
        anim = EntityRef("charactera_anim", "task")
        groom = EntityRef("charactera_groom", "task")
        shot = EntityRef("shot010_layout", "shot")
        return DependencyGraph(
            (
                DependencyEdge(asset, rig, "builds_from", freshness=FreshnessState.STALE),
                DependencyEdge(rig, anim, "consumes", freshness=FreshnessState.NEEDS_REVIEW),
                DependencyEdge(asset, groom, "consumes", freshness=FreshnessState.UP_TO_DATE),
                DependencyEdge(anim, shot, "references", freshness=FreshnessState.STALE),
            )
        )

    def test_graph_resolves_incoming_and_outgoing_edges(self) -> None:
        graph = self._make_graph()

        self.assertEqual(2, len(graph.outgoing_for("charactera_model")))
        self.assertEqual(1, len(graph.incoming_for("charactera_anim")))

    def test_graph_downstream_closure_walks_transitively(self) -> None:
        graph = self._make_graph()

        closure = graph.downstream_closure("charactera_model")

        self.assertEqual(4, len(closure))
        self.assertEqual("charactera_rig", closure[0].downstream.id)
        self.assertEqual("shot010_layout", closure[-1].downstream.id)

    def test_impacted_downstream_entities_summarizes_unique_targets(self) -> None:
        graph = self._make_graph()

        impacted = impacted_downstream_entities(graph, "charactera_model")

        self.assertEqual(
            ["charactera_rig", "shot010_layout", "charactera_anim", "charactera_groom"],
            [record.entity.id for record in impacted],
        )
        self.assertEqual(FreshnessState.STALE, impacted[0].freshness)

    def test_summarize_freshness_counts_records(self) -> None:
        graph = self._make_graph()

        summary = summarize_freshness(impacted_downstream_entities(graph, "charactera_model"))

        self.assertEqual(2, summary[FreshnessState.STALE])
        self.assertEqual(1, summary[FreshnessState.NEEDS_REVIEW])
        self.assertEqual(1, summary[FreshnessState.UP_TO_DATE])


if __name__ == "__main__":
    unittest.main()
