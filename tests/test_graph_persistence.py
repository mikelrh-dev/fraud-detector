"""Graph persistence tests — the graph must survive a service restart.

These tests exercise the real Redis command surface (hset/hgetall/sadd/smembers)
against an in-memory fake, so an async/sync mismatch or a missing await fails
here instead of silently degrading to memory-only operation in production.
"""

import pytest

from src.services.graph_service import FraudGraphService


class FakeRedis:
    """Minimal async Redis stand-in that actually stores what it is given."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, set[str]] = {}

    async def hset(self, key, field=None, value=None, mapping=None):
        bucket = self.hashes.setdefault(key, {})
        if mapping:
            bucket.update(mapping)
        if field is not None:
            bucket[field] = value
        return 1

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def sadd(self, key, *values):
        self.sets.setdefault(key, set()).update(values)
        return 1

    async def smembers(self, key):
        return set(self.sets.get(key, set()))


class BrokenRedis:
    """Redis client that always fails — persistence must degrade, not raise."""

    async def hset(self, *args, **kwargs):
        raise RuntimeError("redis down")

    async def hgetall(self, *args, **kwargs):
        raise RuntimeError("redis down")

    async def sadd(self, *args, **kwargs):
        raise RuntimeError("redis down")

    async def smembers(self, *args, **kwargs):
        raise RuntimeError("redis down")


class TestGraphPersistence:
    """Persist/restore round-trip across independent service instances."""

    @pytest.mark.asyncio
    async def test_persist_writes_nodes_edges_and_fraudsters(self):
        """persist() must actually write to Redis, not silently no-op."""
        redis = FakeRedis()
        service = FraudGraphService(redis_client=redis)
        service.add_transaction("u1", "merchant_a", "card1", is_fraud=True)

        assert await service.persist() is True

        # The writes must be observable on the Redis side.
        assert set(redis.hashes["graph:nodes"]) == {"u1", "merchant_a", "card1"}
        assert "u1:merchant_a" in redis.sets["graph:edges"]
        assert "u1:card1" in redis.sets["graph:edges"]
        assert redis.sets["graph:fraudsters"] == {"u1", "card1"}

    @pytest.mark.asyncio
    async def test_graph_survives_service_restart(self):
        """A fresh service must rebuild the graph purely from Redis."""
        redis = FakeRedis()
        before = FraudGraphService(redis_client=redis)
        before.add_transaction("u1", "merchant_a", "card1", is_fraud=True)
        assert await before.persist() is True

        after = FraudGraphService(redis_client=redis)
        assert await after.restore() is True

        assert set(after.graph.nodes) == {"u1", "merchant_a", "card1"}
        assert after.known_fraudsters == {"u1", "card1"}
        assert after.graph.has_edge("u1", "merchant_a")
        # Fraud labels must be restored, not just topology.
        assert after.graph.nodes["u1"]["is_fraud"] is True
        assert after.graph.nodes["merchant_a"]["is_fraud"] is False
        # Timestamps must survive so pruning still has a cutoff to work with.
        assert after.graph.nodes["u1"]["timestamp"] is not None

    @pytest.mark.asyncio
    async def test_restored_graph_still_detects_near_fraud(self):
        """Detection must work off the restored graph, not only fresh memory.

        Topology note: the graph is directed and ``add_transaction`` only adds
        ``sender -> receiver`` / ``sender -> card`` edges, so BFS follows
        outgoing edges only. The queried user must therefore pay a known
        fraudster for the 2-hop signal to be reachable.
        """
        redis = FakeRedis()
        before = FraudGraphService(redis_client=redis)
        # Flags the sender and the card as fraudsters.
        before.add_transaction("fraudster", "merchant_a", "card_bad", is_fraud=True)
        # A legitimate-looking user pays that same fraudster.
        before.add_transaction("user_x", "fraudster", "card_x")
        await before.persist()

        after = FraudGraphService(redis_client=redis)
        await after.restore()

        assert after.known_fraudsters == {"fraudster", "card_bad"}

        features = after.get_graph_features("user_x")
        assert features["is_near_fraud"] == 1
        # Reachable fraudsters: the "fraudster" merchant at 1 hop and the
        # "card_bad" card reached through it at 2 hops.
        assert features["connected_fraudsters"] == 2
        assert features["shortest_path_to_fraud"] == 1

        # An unrelated node stays clean after restore.
        assert after.get_graph_features("merchant_a")["is_near_fraud"] == 0

    @pytest.mark.asyncio
    async def test_restore_is_idempotent(self):
        """Repeated restore() calls must not duplicate or fail."""
        redis = FakeRedis()
        service = FraudGraphService(redis_client=redis)
        service.add_transaction("u1", "merchant_a", "card1", is_fraud=True)
        await service.persist()

        assert await service.restore() is True
        assert await service.restore() is True
        assert service.graph.number_of_edges() == 2

    @pytest.mark.asyncio
    async def test_add_transaction_persisted_end_to_end(self):
        """The async entry point mutates the graph and persists in one call."""
        redis = FakeRedis()
        service = FraudGraphService(redis_client=redis)

        assert await service.add_transaction_persisted(
            "u2", "merchant_b", "card2", is_fraud=False, redis_client=redis
        ) is True

        assert "u2" in service.graph
        assert "graph:nodes" in redis.hashes


class TestGraphPersistenceDegradation:
    """Redis failures must never break fraud detection."""

    @pytest.mark.asyncio
    async def test_persist_returns_false_when_redis_fails(self):
        service = FraudGraphService(redis_client=BrokenRedis())
        service.add_transaction("u1", "merchant_a", "card1", is_fraud=True)
        assert await service.persist() is False

    @pytest.mark.asyncio
    async def test_restore_returns_false_when_redis_fails(self):
        service = FraudGraphService(redis_client=BrokenRedis())
        assert await service.restore() is False
        # Detection still works from an empty in-memory graph.
        assert service.get_graph_features("nobody")["is_near_fraud"] == 0

    @pytest.mark.asyncio
    async def test_add_transaction_persisted_survives_redis_failure(self):
        """A dead Redis must not fail the request or lose the in-memory edge."""
        service = FraudGraphService(redis_client=BrokenRedis())
        persisted = await service.add_transaction_persisted(
            "u1", "merchant_a", "card1", is_fraud=True, redis_client=BrokenRedis()
        )
        assert persisted is False
        assert service.graph.has_edge("u1", "merchant_a")
        assert "u1" in service.known_fraudsters
