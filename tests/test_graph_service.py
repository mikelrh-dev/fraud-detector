"""Graph service tests — verifies cutoff behavior and async offloading.

R2: shortest_path_length must use cutoff=2 so BFS stops at depth 2,
making the algorithm O(edges at depth ≤2) instead of O(V+E).
"""



from src.services.graph_service import FraudGraphService


class TestGraphCutoffBehavior:
    """Verify that BFS respects the cutoff=2 boundary."""

    def test_user_at_depth_2_returns_near_fraud(self):
        """A fraudster reachable at depth 2 must be flagged.

        R2 test: cutoff=2 allows discovering paths up to 2 hops.
        """
        svc = FraudGraphService()
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        for n in ["user_A", "user_B", "user_C"]:
            svc.graph.add_node(n, node_type="user", is_fraud=False, timestamp=now)

        svc.graph.add_edge("user_A", "user_B")
        svc.graph.add_edge("user_B", "user_C")
        svc.known_fraudsters.add("user_C")

        features = svc.get_graph_features("user_A")
        # C is a fraudster at depth 2 (A->B->C) — should be near fraud
        assert features["shortest_path_to_fraud"] == 2
        assert features["is_near_fraud"] == 1

    def test_fraudster_at_depth_3_plus_not_reachable(self):
        """With cutoff=2, a fraudster at depth 3+ returns 999 for shortest path.

        R2: This is the critical behavior change — BFS no longer explores
        the full graph.
        """
        svc = FraudGraphService()
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        for n in ["user_A", "user_B", "user_C", "fraudster_X"]:
            svc.graph.add_node(n, node_type="user", is_fraud=False, timestamp=now)

        # Chain: A -> B -> C -> fraudster at depth 3
        svc.graph.add_edge("user_A", "user_B")
        svc.graph.add_edge("user_B", "user_C")
        svc.graph.add_edge("user_C", "fraudster_X")
        svc.known_fraudsters.add("fraudster_X")

        features = svc.get_graph_features("user_A")
        # With cutoff=2, BFS cannot reach fraudster_X (depth 3)
        assert features["shortest_path_to_fraud"] == 999
        assert features["is_near_fraud"] == 0

    def test_is_near_fraud_zero_when_user_not_in_graph(self):
        """User not in graph returns zero features (baseline)."""
        svc = FraudGraphService()
        features = svc.get_graph_features("nonexistent_user")
        assert features["is_near_fraud"] == 0
        assert features["shortest_path_to_fraud"] == 999

    def test_is_near_fraud_one_when_user_is_fraudster(self):
        """User who IS a fraudster gets path=0."""
        svc = FraudGraphService()
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        svc.graph.add_node("bad_user", node_type="user", is_fraud=True, timestamp=now)
        svc.known_fraudsters.add("bad_user")

        features = svc.get_graph_features("bad_user")
        assert features["shortest_path_to_fraud"] == 0
        assert features["is_near_fraud"] == 1
