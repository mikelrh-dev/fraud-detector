"""The near-fraud graph signal: what it can and cannot see.

Measured with `python -m scripts.measure_near_fraud_impact` on a
production-shaped topology (200 users, 2k transactions, `card_id` =
`payload.card_last4`, so a 4-digit namespace).

Findings, recorded so the behaviour is not re-derived from scratch:

* The graph is a ``DiGraph`` and ``add_transaction`` only creates
  ``sender -> receiver`` and ``sender -> card``. ``get_graph_features`` follows
  **outgoing** edges only, so a node's reachable set never includes another
  user who transacted with the same merchant.
* Consequently the only way a non-fraudster gets flagged is by holding a card
  that some fraudster also used. The signal therefore measures *card reuse*,
  not network proximity to a fraudster.
* It is extremely sensitive to card cardinality. With a realistic 4-digit
  ``card_last4`` space it fires for **0%** of nodes. With a small reused card
  pool it fires for ~17%. There is no regime where it usefully means
  "connected to a fraudster within two hops".
* Making the edges bidirectional would flag **~91%** of nodes — worse than
  useless, and enough to auto-block legitimate users if it fed the ensemble.

These tests pin the structural facts deterministically, with no simulation, so
a future topology change shows up as a failure rather than as a silent
behaviour shift.
"""

import random

import networkx as nx
import pytest

from src.services.graph_service import FraudGraphService


def _service() -> FraudGraphService:
    return FraudGraphService()


class TestTopologyLimits:
    """Structural facts about the directed graph."""

    def test_graph_is_directed(self):
        assert _service().graph.is_directed(), (
            "the signal's usefulness depends on this being directed; a change "
            "here invalidates the measurements in this module's docstring"
        )

    def test_merchant_nodes_have_no_outgoing_edges(self):
        """A receiver can never reach anything, because it only receives."""
        service = _service()
        service.add_transaction("user_a", "merchant_x", "1234")

        assert service.graph.out_degree("merchant_x") == 0
        assert service.graph.out_degree("user_a") == 2

    def test_shared_merchant_does_not_connect_two_users(self):
        """The core limitation: a shared merchant creates no path between users.

        Two users paying the same merchant produce merchant_x -> user_a and
        merchant_x -> user_b — never user_a -> ... -> user_b. BFS from user_a
        reaches the merchant and then stops.
        """
        service = _service()
        service.add_transaction("user_a", "merchant_shared", "1111")
        service.add_transaction("user_b", "merchant_shared", "2222")
        service.add_transaction("user_b", "fraudster", "3333", is_fraud=True)

        reachable = nx.single_source_shortest_path_length(
            service.graph, "user_a", cutoff=2
        )
        assert "user_b" not in reachable
        assert "fraudster" not in reachable

        features = service.get_graph_features("user_a")
        assert features["connected_fraudsters"] == 0
        assert features["is_near_fraud"] == 0

    def test_merchant_node_is_never_flagged_as_near_fraud(self):
        """Merchants are pure receivers, so they can never be flagged."""
        service = _service()
        service.add_transaction("user_a", "merchant_x", "1234", is_fraud=True)

        # The fraudster's own card and the sender are flagged as themselves,
        # but the merchant — a receiver — cannot reach anything.
        assert service.get_graph_features("merchant_x")["is_near_fraud"] == 0


class TestSignalIsDrivenByCardReuse:
    """The only path to a positive result runs through a shared card."""

    def test_no_signal_without_card_reuse(self):
        service = _service()
        service.add_transaction("user_a", "merchant_x", "1111")
        service.add_transaction("user_b", "fraudster", "2222", is_fraud=True)

        assert service.get_graph_features("user_a")["is_near_fraud"] == 0

    def test_signal_appears_only_via_a_shared_card(self):
        """Same graph, one difference: user_a reuses the fraudster's card."""
        service = _service()
        service.add_transaction("user_b", "merchant_y", "2222", is_fraud=True)
        service.add_transaction("user_a", "merchant_x", "2222")

        features = service.get_graph_features("user_a")
        assert features["is_near_fraud"] == 1
        assert features["connected_fraudsters"] == 1
        assert features["shortest_path_to_fraud"] == 1


class TestBidirectionalCounterfactual:
    """What adding reverse edges would do — the reason not to."""

    @staticmethod
    def _flagged(graph, fraudsters) -> int:
        undirected = graph.to_undirected()
        return sum(
            1
            for node in undirected.nodes()
            if node not in fraudsters
            and any(
                f in nx.single_source_shortest_path_length(undirected, node, cutoff=2)
                for f in fraudsters
            )
        )

    def test_reverse_edges_widen_the_signal_substantially(self):
        """Compared on the same graph, so the topology cannot skew the result.

        Measured on a production-shaped graph the gap is 17% -> 91%. The exact
        ratio is topology-dependent; what does not vary is that making edges
        traversable both ways flags far more nodes, and a signal that fires on
        most of the population carries no information.
        """
        service = _service()
        rng = random.Random(7)
        merchants = [f"merchant_{i}" for i in range(40)]
        for _ in range(2000):
            u = rng.randrange(200)
            recv = (
                rng.choice(merchants)
                if rng.random() < 0.5
                else f"merchant_{rng.randrange(400)}"
            )
            service.add_transaction(
                f"user_{u}", recv, f"{rng.randrange(10000):04d}",
                is_fraud=rng.random() < 0.02,
            )

        fraudsters = service.known_fraudsters
        assert fraudsters, "fixture must produce known fraudsters"

        directed = self._flagged(service.graph.to_undirected(as_view=False), fraudsters)
        # Directed traversal, counted the same way for a fair comparison.
        directed_only = sum(
            1
            for node in service.graph.nodes()
            if node not in fraudsters
            and any(
                f in nx.single_source_shortest_path_length(
                    service.graph, node, cutoff=2
                )
                for f in fraudsters
            )
        )

        assert directed > directed_only, (
            f"bidirectional ({directed}) must flag at least as many nodes as "
            f"directed ({directed_only})"
        )
        assert directed >= directed_only * 3, (
            f"expected the gap to be large, got {directed_only} -> {directed}"
        )
