"""A21 and A22: the fraud graph grew without bound and cost O(V+E) per request.

A21 — `persist()` only ever did `hset`/`sadd`, which are upserts, so a node
removed by a prune was simply absent from the new mapping and therefore
*retained* in Redis. `restore()` then resurrected the full pruned history on
every restart, and the edge set grew without limit.

The prune trigger made it worse: `number_of_nodes() % 1000 == 0`. The node
count steps by ~3 per transaction, so it could jump straight over a multiple of
1000 and never prune at all.

A22 — `persist()` serialised the whole graph and shipped every node and edge on
each scored transaction, holding the graph lock for the traversal.
`get_graph_features` called `nx.degree_centrality(self.graph)`, a full O(V+E)
pass, to read one node's degree.
"""

from unittest.mock import AsyncMock, MagicMock

import networkx as nx
import pytest

from src.services.graph_service import (
    _REDIS_FRAUDSTERS_KEY,
    _REDIS_NODES_KEY,
    FraudGraphService,
)

pytestmark = pytest.mark.asyncio


def fake_redis() -> MagicMock:
    redis = MagicMock()
    redis.hset = AsyncMock()
    redis.sadd = AsyncMock()
    redis.hdel = AsyncMock()
    redis.srem = AsyncMock()
    return redis


class TestPruneActuallyFires:
    """A21: the old modulo trigger could step over its own threshold."""

    async def test_prunes_without_depending_on_node_count_alignment(self) -> None:
        service = FraudGraphService(redis_client=fake_redis())
        service.prune_threshold = 10

        for i in range(10):
            service.add_transaction(f"u{i}", f"r{i}", f"c{i}")

        # 10 adds of 3 nodes each = 30 nodes, none of which is a multiple of the
        # old 1000 threshold, and `_prune_old_nodes` was reached on the counter.
        assert service._adds_since_prune == 0, "the counter should have reset"

    async def test_counter_does_not_depend_on_nodes_added(self) -> None:
        """The trigger must be additions, not a modulus of the live node count."""
        service = FraudGraphService(redis_client=fake_redis())
        service.prune_threshold = 5

        fired = 0
        original = service._prune_old_nodes

        def counting_prune() -> list[str]:
            nonlocal fired
            fired += 1
            return original()

        service._prune_old_nodes = counting_prune  # type: ignore[method-assign]

        for i in range(20):
            service.add_transaction(f"u{i}", f"r{i}", f"c{i}")

        assert fired == 4, f"expected one prune per 5 adds, got {fired}"

    async def test_old_modulo_trigger_would_have_missed(self) -> None:
        """Documents why the old condition was wrong, not just unusual."""
        counts = [3 * i for i in range(1, 400)]
        assert 1000 not in counts, "node counts step by 3 and skip 1000"
        assert any(c % 1000 == 0 for c in counts) is False


class TestPruneIsDurable:
    """A21: a pruned node must actually leave Redis."""

    async def test_hdel_and_srem_are_issued(self) -> None:
        from datetime import datetime, timedelta, timezone

        redis = fake_redis()
        service = FraudGraphService(retention_days=1, redis_client=redis)

        # Nodes old enough to be pruned.
        old = datetime.now(tz=timezone.utc) - timedelta(days=10)
        service.graph.add_node("old_u", node_type="user", is_fraud=False, timestamp=old)
        service.graph.add_node("old_r", node_type="user", is_fraud=False, timestamp=old)
        service.graph.add_edge("old_u", "old_r")
        service._pending_nodes["old_u"] = service._serialize_node(
            service.graph.nodes["old_u"]
        )
        service._pending_edges.add("old_u:old_r")

        removed = service._prune_old_nodes()
        assert "old_u" in removed

        await service.persist(redis)

        redis.hdel.assert_awaited()
        assert _REDIS_NODES_KEY in redis.hdel.await_args[0]
        assert "old_u" in redis.hdel.await_args[0]
        redis.srem.assert_awaited()
        assert "old_u:old_r" in redis.srem.await_args[0]

    async def test_fraudsters_are_never_pruned(self) -> None:
        from datetime import datetime, timedelta, timezone

        redis = fake_redis()
        service = FraudGraphService(retention_days=1, redis_client=redis)

        old = datetime.now(tz=timezone.utc) - timedelta(days=10)
        service.graph.add_node("fraudster", node_type="user", is_fraud=True, timestamp=old)
        service.known_fraudsters.add("fraudster")

        removed = service._prune_old_nodes()
        assert "fraudster" not in removed

    async def test_pruned_node_is_not_resurrected_by_a_pending_write(self) -> None:
        from datetime import datetime, timedelta, timezone

        redis = fake_redis()
        service = FraudGraphService(retention_days=1, redis_client=redis)

        old = datetime.now(tz=timezone.utc) - timedelta(days=10)
        service.graph.add_node("old_u", node_type="user", is_fraud=False, timestamp=old)
        service._pending_nodes["old_u"] = "stale"

        service._prune_old_nodes()

        assert "old_u" not in service._pending_nodes, (
            "a queued write would re-add the node the prune just removed"
        )

    async def test_removals_survive_a_failed_flush(self) -> None:
        """A Redis blip must defer the deletion, not drop it."""
        redis = fake_redis()
        redis.hdel.side_effect = RuntimeError("redis down")
        service = FraudGraphService(redis_client=redis)

        service._pending_removed_nodes.add("gone")
        assert await service.persist(redis) is False
        assert "gone" in service._pending_removed_nodes

    async def test_persist_writes_nothing_when_there_is_no_delta(self) -> None:
        redis = fake_redis()
        service = FraudGraphService(redis_client=redis)

        assert await service.persist(redis) is True
        redis.hset.assert_not_awaited()
        redis.sadd.assert_not_awaited()


class TestPersistIsDelta:
    """A22: one transaction must not rewrite the whole graph."""

    async def test_single_transaction_writes_only_its_own_nodes(self) -> None:
        redis = fake_redis()
        service = FraudGraphService(redis_client=redis)

        # Build a large graph first.
        for i in range(200):
            service.add_transaction(f"u{i}", f"r{i}", f"c{i}")
        assert service.graph.number_of_nodes() > 500

        # Clear the accumulated delta, then add exactly one more.
        await service.persist(redis)
        redis.hset.reset_mock()

        service.add_transaction("new_sender", "new_receiver", "new_card")
        await service.persist(redis)

        redis.hset.assert_awaited_once()
        mapping = redis.hset.await_args.kwargs["mapping"]
        assert set(mapping) == {"new_sender", "new_receiver", "new_card"}, (
            "persist must write the delta, not the whole graph"
        )

    async def test_edges_written_are_only_the_new_ones(self) -> None:
        redis = fake_redis()
        service = FraudGraphService(redis_client=redis)

        for i in range(50):
            service.add_transaction(f"u{i}", f"r{i}", f"c{i}")
        await service.persist(redis)
        redis.sadd.reset_mock()

        service.add_transaction("s", "r", "c")
        await service.persist(redis)

        written = set(redis.sadd.await_args[0][1:])
        assert written == {"s:r", "s:c"}

    async def test_delta_is_cleared_after_a_successful_flush(self) -> None:
        redis = fake_redis()
        service = FraudGraphService(redis_client=redis)
        service.add_transaction("a", "b", "c")

        await service.persist(redis)
        redis.sadd.reset_mock()

        await service.persist(redis)
        redis.sadd.assert_not_awaited()

    async def test_fraudsters_are_queued(self) -> None:
        redis = fake_redis()
        service = FraudGraphService(redis_client=redis)
        service.add_transaction("f", "r", "c", is_fraud=True)

        await service.persist(redis)

        # sadd is called once for edges and once for fraudsters, so find the
        # call that targets the fraudsters key rather than assuming an order.
        fraudster_writes = [
            call
            for call in redis.sadd.await_args_list
            if _REDIS_FRAUDSTERS_KEY in call[0]
        ]
        assert fraudster_writes, "the fraudsters set was never written"
        assert set(fraudster_writes[0][0][1:]) == {"f", "c"}


class TestDegreeCentralityIsLocal:
    """A22: reading one node's degree must not walk the whole graph."""

    def test_matches_networkx_definition(self) -> None:
        service = FraudGraphService(redis_client=fake_redis())
        for i in range(30):
            service.add_transaction(f"u{i}", f"r{i}", f"c{i}")

        expected = nx.degree_centrality(service.graph)["u0"]
        got = service.get_graph_features("u0")["degree_centrality"]

        assert got == pytest.approx(expected), (
            "the O(1) shortcut must return the same value networkx computes"
        )

    def test_single_node_graph(self) -> None:
        service = FraudGraphService(redis_client=fake_redis())
        service.graph.add_node("only")

        assert service.get_graph_features("only")["degree_centrality"] == 0.0

    def test_does_not_call_networkx_degree_centrality(self) -> None:
        """The whole point: no full-graph pass on the hot path."""
        service = FraudGraphService(redis_client=fake_redis())
        service.add_transaction("a", "b", "c")

        original = nx.degree_centrality
        called = False

        def spy(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal called
            called = True
            return original(*args, **kwargs)

        nx.degree_centrality = spy  # type: ignore[assignment]
        try:
            service.get_graph_features("a")
        finally:
            nx.degree_centrality = original  # type: ignore[assignment]

        assert called is False
