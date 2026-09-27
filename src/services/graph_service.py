"""Graph Analytics Service for Fraud Network Detection.

Maintains a fraud network using NetworkX. Detects if a user or card
is connected to known fraudsters (2 hops or less), indicating potential mule accounts.

Thread-Safe: Uses threading.Lock() to prevent race conditions on concurrent access.
Memory-Safe: Implements pruning to prevent unbounded growth.
Persistence: Graph is persisted to Redis so it survives service restarts.
"""

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import networkx as nx

from src.core.redis import get_redis

logger = logging.getLogger(__name__)

_REDIS_NODES_KEY = "graph:nodes"
_REDIS_EDGES_KEY = "graph:edges"
_REDIS_FRAUDSTERS_KEY = "graph:fraudsters"


class FraudGraphService:
    """Detects fraud networks using graph analysis.
    
    Maintains a directed graph where:
    - Nodes: user IDs and card IDs
    - Edges: transactions between users/cards
    - Attributes: fraud labels on nodes, timestamps for pruning
    
    Thread-Safe: All operations protected by threading.Lock() to handle concurrent requests.
    Memory-Safe: Automatic pruning keeps graph bounded (default: 30-day retention).
    Persistence: Graph is persisted to Redis so it survives service restarts.
    """

    def __init__(self, retention_days: int = 30, redis_client: Any | None = None):
        """Initialize the fraud graph.
        
        Args:
            retention_days: Days to retain transaction nodes (default: 30)
            redis_client: Optional async Redis client for persistence
        """
        self.graph = nx.DiGraph()
        self.known_fraudsters: set[str] = set()
        self.lock = threading.Lock()  # Thread-safety lock (sync, for to_thread)
        self.retention_days = retention_days
        self.last_pruned = datetime.now(tz=timezone.utc)
        self._redis = redis_client
        self._restored = False
        # A22: persist() used to serialise the entire graph and ship the whole
        # node/edge set to Redis on every scored transaction, while holding the
        # lock for the traversal. That is O(V+E) per request on the hot path and
        # it grew for the lifetime of the deployment. These accumulate the delta
        # instead, so a single transaction writes three nodes and two edges.
        self._pending_nodes: dict[str, str] = {}
        self._pending_edges: set[str] = set()
        self._pending_fraudsters: set[str] = set()
        # A21: nodes removed by a prune, waiting to be deleted from Redis.
        self._pending_removed_nodes: set[str] = set()
        self._pending_removed_edges: set[str] = set()
        # A21: the prune trigger used to be `number_of_nodes() % 1000 == 0`.
        # The node count steps by ~3 per transaction, so it can jump straight
        # over a multiple of 1000 and never prune at all. A monotonic counter
        # cannot skip its own threshold.
        self._adds_since_prune = 0
        self.prune_threshold = 1000
        logger.info(
            "FraudGraphService initialized (retention: %d days, persistence: %s)",
            retention_days,
            "redis" if redis_client else "shared-pool",
        )

    def _resolve_redis(self, redis_client: Any | None = None) -> Any | None:
        """Resolve the Redis client: explicit arg, injected client, or shared pool.

        Returns None when no client can be resolved, so callers can treat
        persistence as a best-effort side effect instead of failing.
        """
        if redis_client is not None:
            return redis_client
        if self._redis is not None:
            return self._redis
        return get_redis()

    @staticmethod
    def _as_str(value: Any) -> str:
        """Normalize bytes/str from Redis to str."""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    def _snapshot(self) -> tuple[dict[str, str], list[str], list[str]]:
        """Serialize the whole graph. Kept for tests and full resyncs.

        `persist` no longer uses this: writing the entire graph on every scored
        transaction was O(V+E) per request (A22). It is retained because a
        deliberate full resync is still occasionally the right thing to do.
        """
        with self.lock:
            nodes = {
                str(node_id): json.dumps(
                    {
                        "node_type": data.get("node_type", "user"),
                        "is_fraud": bool(data.get("is_fraud", False)),
                        "timestamp": (
                            data["timestamp"].isoformat()
                            if data.get("timestamp") is not None
                            else None
                        ),
                    }
                )
                for node_id, data in self.graph.nodes(data=True)
            }
            edges = [f"{sender}:{receiver}" for sender, receiver in self.graph.edges()]
            fraudsters = list(self.known_fraudsters)
        return nodes, edges, fraudsters

    @staticmethod
    def _serialize_node(data: dict[str, Any]) -> str:
        return json.dumps(
            {
                "node_type": data.get("node_type", "user"),
                "is_fraud": bool(data.get("is_fraud", False)),
                "timestamp": (
                    data["timestamp"].isoformat()
                    if data.get("timestamp") is not None
                    else None
                ),
            }
        )

    def _collect_delta(self) -> tuple[dict[str, str], list[str], list[str], list[str], list[str]]:
        """Swap out the pending delta. Returns the writes and the deletions.

        Synchronous and lock-free with respect to the caller: it is called from
        async code after the worker thread has finished, and the swap is atomic
        so a concurrent mutation lands in the next batch instead of being lost.
        """
        nodes, self._pending_nodes = self._pending_nodes, {}
        edges, self._pending_edges = self._pending_edges, set()
        fraudsters, self._pending_fraudsters = self._pending_fraudsters, set()
        removed_nodes, self._pending_removed_nodes = self._pending_removed_nodes, set()
        removed_edges, self._pending_removed_edges = self._pending_removed_edges, set()
        return (
            nodes,
            list(edges),
            list(fraudsters),
            list(removed_nodes),
            list(removed_edges),
        )

    async def restore(self, redis_client: Any | None = None) -> bool:
        """Restore the graph from Redis so it survives restarts.

        Returns True when a restore pass completed (including the empty-graph
        case), False when Redis was unavailable or unreadable. Never raises:
        an unavailable Redis degrades to memory-only operation.
        """
        if self._restored:
            return True
        redis = self._resolve_redis(redis_client)
        if redis is None:
            return False

        try:
            nodes_data = await redis.hgetall(_REDIS_NODES_KEY) or {}
            edges_data = await redis.smembers(_REDIS_EDGES_KEY) or set()
            fraudsters_data = await redis.smembers(_REDIS_FRAUDSTERS_KEY) or set()
        except Exception as exc:
            logger.warning("Failed to read graph from Redis: %s", exc)
            return False

        now = datetime.now(tz=timezone.utc)
        with self.lock:
            for node_key, node_json in nodes_data.items():
                try:
                    payload = json.loads(self._as_str(node_json))
                except (TypeError, ValueError) as exc:
                    logger.warning("Skipping malformed graph node: %s", exc)
                    continue
                raw_ts = payload.get("timestamp")
                try:
                    timestamp = (
                        datetime.fromisoformat(raw_ts) if raw_ts else now
                    )
                except (TypeError, ValueError):
                    timestamp = now
                self.graph.add_node(
                    self._as_str(node_key),
                    node_type=payload.get("node_type", "user"),
                    is_fraud=bool(payload.get("is_fraud", False)),
                    timestamp=timestamp,
                )

            for edge in edges_data:
                parts = self._as_str(edge).split(":", 1)
                if len(parts) == 2:
                    self.graph.add_edge(parts[0], parts[1])
                else:
                    logger.warning("Skipping malformed graph edge: %s", edge)

            self.known_fraudsters.update(
                self._as_str(item) for item in fraudsters_data
            )
            self._restored = True

        logger.info(
            "Restored graph from Redis: %d nodes, %d edges, %d fraudsters",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
            len(self.known_fraudsters),
        )
        return True

    async def persist(self, redis_client: Any | None = None) -> bool:
        """Flush the pending graph delta to Redis (best-effort).

        Returns True when the delta was written, False when Redis was
        unavailable. Never raises: graph detection must keep working when
        Redis is down.

        A22: this used to call ``_snapshot()`` and write every node and every
        edge on each scored transaction — O(V+E) serialisation while holding the
        graph lock, plus a full hash rewrite, on the hot path of
        ``POST /transactions``. Now it writes only what changed since the last
        flush, so one transaction costs three node writes and two edge writes
        regardless of how large the graph has grown.

        A21: it also issues the deletions a prune computed. ``persist`` previously
        only ever did ``hset``/``sadd``, which are upserts, so a pruned node was
        simply absent from the new mapping and therefore *retained* in Redis;
        ``restore`` then resurrected the full pruned history on every restart and
        the edge set grew without limit.

        A failed flush puts the delta back, so a Redis blip defers the write
        instead of discarding it.
        """
        redis = self._resolve_redis(redis_client)
        if redis is None:
            return False

        nodes, edges, fraudsters, removed_nodes, removed_edges = self._collect_delta()
        if not (nodes or edges or fraudsters or removed_nodes or removed_edges):
            return True

        try:
            if nodes:
                await redis.hset(_REDIS_NODES_KEY, mapping=nodes)
            if edges:
                await redis.sadd(_REDIS_EDGES_KEY, *edges)
            if fraudsters:
                await redis.sadd(_REDIS_FRAUDSTERS_KEY, *fraudsters)
            if removed_nodes:
                await redis.hdel(_REDIS_NODES_KEY, *removed_nodes)
            if removed_edges:
                await redis.srem(_REDIS_EDGES_KEY, *removed_edges)
        except Exception as exc:
            logger.warning("Failed to persist graph to Redis: %s", exc)
            # Re-queue so the next flush retries instead of losing the delta.
            self._pending_nodes.update(nodes)
            self._pending_edges.update(edges)
            self._pending_fraudsters.update(fraudsters)
            self._pending_removed_nodes.update(removed_nodes)
            self._pending_removed_edges.update(removed_edges)
            return False
        return True

    async def ensure_restored(self, redis_client: Any | None = None) -> bool:
        """Restore the graph once, before the first detection query."""
        return await self.restore(redis_client)


    def add_transaction(
        self,
        sender_id: str,
        receiver_id: str,
        card_id: str,
        is_fraud: bool = False,
    ) -> None:
        """Add a transaction to the fraud network (thread-safe).
        
        Creates edges between sender/receiver and marks the card.
        If is_fraud=True, marks both sender and card as fraudsters.
        
        Args:
            sender_id: User ID of sender
            receiver_id: User ID of receiver
            card_id: Card identifier (last 4 digits or full card hash)
            is_fraud: Whether this transaction was flagged as fraud
        """
        with self.lock:  # Thread-safety: serialize all graph modifications
            try:
                # Add nodes if they don't exist, with timestamp for pruning
                now = datetime.now(tz=timezone.utc)
                self.graph.add_node(sender_id, node_type="user", is_fraud=False, timestamp=now)
                self.graph.add_node(receiver_id, node_type="user", is_fraud=False, timestamp=now)
                self.graph.add_node(card_id, node_type="card", is_fraud=False, timestamp=now)

                # Add edges (transactions)
                self.graph.add_edge(sender_id, receiver_id)
                self.graph.add_edge(sender_id, card_id)

                # If fraud, mark nodes
                if is_fraud:
                    self.graph.nodes[sender_id]["is_fraud"] = True
                    self.graph.nodes[card_id]["is_fraud"] = True
                    self.known_fraudsters.add(sender_id)
                    self.known_fraudsters.add(card_id)
                    self._pending_fraudsters.update({sender_id, card_id})
                    logger.warning(
                        "Marked as fraudster: sender=%s, card=%s (known_fraudsters=%d)",
                        sender_id,
                        card_id,
                        len(self.known_fraudsters),
                    )

                # A22: record the delta instead of re-serialising the whole graph
                # on every persist.
                for node_id in (sender_id, receiver_id, card_id):
                    if node_id in self.graph:
                        self._pending_nodes[node_id] = self._serialize_node(
                            self.graph.nodes[node_id]
                        )
                self._pending_edges.add(f"{sender_id}:{receiver_id}")
                self._pending_edges.add(f"{sender_id}:{card_id}")

                # A21: prune on a monotonic counter. `number_of_nodes() % 1000`
                # stepped by ~3 per transaction and could jump over a multiple
                # of 1000, in which case the graph never pruned at all.
                self._adds_since_prune += 1
                if self._adds_since_prune >= self.prune_threshold:
                    self._prune_old_nodes()
                    self._adds_since_prune = 0

            except Exception as exc:
                logger.error("Failed to add transaction to graph: %s", exc)

    async def add_transaction_persisted(
        self,
        sender_id: str,
        receiver_id: str,
        card_id: str,
        is_fraud: bool = False,
        redis_client: Any | None = None,
    ) -> bool:
        """Add a transaction and persist the graph (async entry point).

        The mutation runs in a worker thread (it is CPU/lock bound, never
        awaited), then the snapshot is written to Redis. Persistence failure
        never propagates: detection keeps working from memory.

        Returns:
            True when the graph was persisted, False otherwise.
        """
        await asyncio.to_thread(
            self.add_transaction, sender_id, receiver_id, card_id, is_fraud
        )
        return await self.persist(redis_client)

    def get_graph_features(self, user_id: str) -> dict:
        """Get graph-based features for a user (thread-safe).
        
        Args:
            user_id: User ID to analyze
            
        Returns:
            Dict with keys:
            - is_near_fraud: 1 if user is ≤2 hops from fraudster, 0 otherwise
            - degree_centrality: User's connection count (0-1 normalized)
            - shortest_path_to_fraud: Hops to nearest fraudster (999 if unreachable)
            - connected_fraudsters: Count of connected fraudsters
        """
        with self.lock:  # Thread-safety: serialize graph reads
            if not self.graph.nodes():
                # Empty graph
                return {
                    "is_near_fraud": 0,
                    "degree_centrality": 0.0,
                    "shortest_path_to_fraud": 999,
                    "connected_fraudsters": 0,
                }

            if user_id not in self.graph:
                # User not in graph yet
                return {
                    "is_near_fraud": 0,
                    "degree_centrality": 0.0,
                    "shortest_path_to_fraud": 999,
                    "connected_fraudsters": 0,
                }

            try:
                # A22: `nx.degree_centrality(self.graph)` walks the entire graph
                # on every scored transaction, to read a single node's degree.
                # NetworkX defines degree centrality as degree / (V - 1), so
                # computing it directly is O(1) here and returns the same value.
                total_nodes = self.graph.number_of_nodes()
                degree_centrality = (
                    self.graph.degree(user_id) / (total_nodes - 1)
                    if total_nodes > 1
                    else 0.0
                )

                # Find shortest path to any fraudster using BFS with cutoff=2.
                # single_source_shortest_path_length returns all reachable nodes
                # within cutoff hops in one BFS pass — O(V+E at depth≤2).
                shortest_path = 999
                connected_fraudsters = 0

                # Fast path: BFS from user_id with depth limit
                reachable = nx.single_source_shortest_path_length(
                    self.graph, user_id, cutoff=2
                )

                for fraudster_id in self.known_fraudsters:
                    if fraudster_id == user_id:
                        # User IS a fraudster
                        shortest_path = 0
                        connected_fraudsters += 1
                        continue

                    if fraudster_id in reachable:
                        path_length = reachable[fraudster_id]
                        if path_length < shortest_path:
                            shortest_path = path_length
                        connected_fraudsters += 1

                # Determine if near fraud (≤2 hops)
                is_near_fraud = 1 if shortest_path <= 2 else 0

                return {
                    "is_near_fraud": is_near_fraud,
                    "degree_centrality": float(degree_centrality),
                    "shortest_path_to_fraud": shortest_path,
                    "connected_fraudsters": connected_fraudsters,
                }

            except Exception as exc:
                logger.error("Failed to compute graph features for %s: %s", user_id, exc)
                return {
                    "is_near_fraud": 0,
                    "degree_centrality": 0.0,
                    "shortest_path_to_fraud": 999,
                    "connected_fraudsters": 0,
                }

    def get_stats(self) -> dict:
        """Get overall graph statistics (thread-safe)."""
        with self.lock:
            return {
                "node_count": self.graph.number_of_nodes(),
                "edge_count": self.graph.number_of_edges(),
                "known_fraudsters": len(self.known_fraudsters),
                "graph_density": nx.density(self.graph),
            }

    def _prune_old_nodes(self) -> list[str]:
        """Remove nodes older than retention_days (memory management).

        Called on a monotonic counter (every `prune_threshold` adds) to prevent
        unbounded growth. Removes transaction nodes but preserves fraudster
        nodes.

        A21: returns the removed ids and queues them for deletion from Redis.
        Previously the removed set was computed in memory and dropped on the
        floor: `persist` only ever did `hset`/`sadd`, so the pruned nodes stayed
        in the Redis hash and `restore` resurrected them on every restart.
        """
        try:
            cutoff_time = datetime.now(tz=timezone.utc) - timedelta(days=self.retention_days)
            nodes_to_remove = []
            removed_edges: set[str] = set()
            
            for node in self.graph.nodes():
                node_timestamp = self.graph.nodes[node].get("timestamp")
                if node_timestamp and node_timestamp < cutoff_time:
                    # Don't remove fraudsters (keep for detection)
                    if node not in self.known_fraudsters:
                        nodes_to_remove.append(node)
            
            if nodes_to_remove:
                # Collect the incident edges before removal: after
                # remove_nodes_from they are gone from the graph and cannot be
                # derived any more, and the Redis edge set would keep them
                # forever.
                for node in nodes_to_remove:
                    for sender, receiver in list(self.graph.in_edges(node)) + list(
                        self.graph.out_edges(node)
                    ):
                        removed_edges.add(f"{sender}:{receiver}")

                self.graph.remove_nodes_from(nodes_to_remove)
                self._pending_removed_nodes.update(nodes_to_remove)
                self._pending_removed_edges.update(removed_edges)
                # A removed node's pending write must not resurrect it.
                for node in nodes_to_remove:
                    self._pending_nodes.pop(node, None)
                    self._pending_edges.discard(f"{node}")
                self.last_pruned = datetime.now(tz=timezone.utc)
                logger.info(
                    "Pruned %d old nodes and %d edges (retention: %d days). "
                    "Graph size: %d nodes, %d edges",
                    len(nodes_to_remove),
                    len(removed_edges),
                    self.retention_days,
                    self.graph.number_of_nodes(),
                    self.graph.number_of_edges(),
                )
                return nodes_to_remove
            return []
        except Exception as exc:
            logger.error("Failed to prune old nodes: %s", exc)
            return []
