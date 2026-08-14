# Graph Service Concurrency Patterns — Architecture Guide

This document outlines current concurrency model and recommended patterns for future optimization when graph volume becomes a bottleneck.

---

## CURRENT STATE (FASE 4 + OCULTOS FIXES)

- **Single asyncio.Lock()** protecting all graph operations
- Simple but potentially blocks on pruning (every 1000 txns)
- **Suitable for current volume:** ~1000 txn/hour = 1 pruning/hour
- **Cost of pruning:** ~500ms, happens infrequently (acceptable)

---

## FUTURE OPTIMIZATION ROADMAP

### V1 → V2: Background Pruning Task
**When:** If P99 latency spikes appear every 1000 transactions  
**Effort:** 30 minutes (LOW)  
**Benefit:** Removes pruning latency from hot path

```python
# BEFORE (V1)
async def add_transaction(self, ...):
    async with self.lock:
        self.graph.add_node(...)
        if self.graph.number_of_nodes() % 1000 == 0:
            await self._prune_old_nodes()  # 500ms blocking!

# AFTER (V2)
async def add_transaction(self, ...):
    async with self.lock:
        self.graph.add_node(...)  # No pruning in hot path

async def _background_pruning_loop(self):
    while True:
        await asyncio.sleep(43200)  # 12 hours
        async with self.lock:
            await self._prune_old_nodes()  # 500ms, but not blocking requests
```

---

### V2 → V3: Read-Write Lock
**When:** If reads and writes contend (50K+ txn/hour)  
**Effort:** 2-3 hours (MEDIUM)  
**Benefit:** Multiple concurrent readers, single writer

```python
# BEFORE (V2)
class FraudGraphService:
    def __init__(self):
        self.lock = asyncio.Lock()  # Single mutex

# AFTER (V3)
class FraudGraphService:
    def __init__(self):
        self.write_lock = asyncio.Lock()            # Exclusive write
        self.read_semaphore = asyncio.Semaphore(100) # Up to 100 readers

    async def add_transaction(self, ...):
        async with self.write_lock:  # Only one writer
            self.graph.add_node(...)

    async def get_graph_features(self, user_id):
        async with self.read_semaphore:  # Multiple readers (no blocking)
            nx.degree_centrality(self.graph)
```

**Benefit:** Readers don't block each other; writes still exclusive

---

### V3 → V4: Dual-Graph Snapshots
**When:** If V3 still bottlenecks at 100K+ txn/hour  
**Effort:** 1-2 days (HIGH)  
**Complexity:** Requires atomic swap logic  
**Benefit:** Zero contention; readers use frozen snapshot

```python
# BEFORE (V3)
# Readers and writers contend on same graph

# AFTER (V4)
class FraudGraphService:
    def __init__(self):
        self.graph_current = nx.DiGraph()  # Active (frozen for reads)
        self.graph_next = nx.DiGraph()      # Being built (for writes)
        self.lock_swap = asyncio.Lock()

    async def add_transaction(self, ...):
        # Writers always use graph_next (NO LOCK)
        self.graph_next.add_node(...)
        
        # Atomic swap every 12 hours
        if time_to_swap():
            async with self.lock_swap:
                self.graph_current = self.graph_next
                self.graph_next = nx.DiGraph()

    async def get_graph_features(self, user_id):
        # Readers always use graph_current (FROZEN, NO LOCK)
        return nx.degree_centrality(self.graph_current)
```

**Benefit:** ZERO blocking between reads/writes. Trade-off: 2x memory

---

### V4 → External DB: RedisGraph / Neo4j
**When:** V4 still doesn't scale or memory becomes limiting  
**Effort:** 3-5 days (VERY HIGH)  
**Complexity:** Requires new service  
**Benefit:** Unlimited scale, persistent, query language support

```python
# Move graph to external service
# from graph_service import FraudGraphService → from redis_graph_service import FraudGraphService

# All operations become network calls:
# - add_transaction() → redisGraph.query("MERGE (u:User {id: $uid})")
# - get_graph_features() → redisGraph.query("MATCH (u:User)-[*..2]->(f:Fraudster)")
```

---

## DECISION MATRIX: When to Migrate

| Volume | Pruning Freq | Lock Contention | P99 Latency | Action |
|--------|--------------|-----------------|-------------|--------|
| 1K txn/hr | 1x/hr | LOW | <1ms | **V1 (Current)** — Stay put |
| 10K txn/hr | 10x/hr | MEDIUM | ~50ms | **V2** — Background pruning |
| 50K txn/hr | 50x/hr | HIGH | ~100ms | **V3** — Read-Write Lock |
| 100K+ txn/hr | 100x/hr | CRITICAL | >500ms | **V4** or External DB |

---

## MIGRATION CHECKLIST

### To migrate V1 → V2
```
[ ] Extract _prune_old_nodes() to separate async task
[ ] Start background loop in __init__() or FastAPI lifespan
[ ] Add monitoring: log pruning start/end with duration
[ ] Test: Load test with 10K txn/hr, verify no latency spikes
[ ] Verify: No data loss during pruning
[ ] Rollback: Keep old code for quick revert
```

### To migrate V2 → V3
```
[ ] Replace single Lock with write_lock + read_semaphore
[ ] Update all async with self.lock → async with self.write_lock
[ ] Update all reads to use async with self.read_semaphore
[ ] Load test: Verify 10x read throughput improvement
[ ] Monitor: Track active readers/writers with metrics
[ ] Benchmark: Compare P99 latency before/after
```

### To migrate V3 → V4 (Dual Snapshots)
```
[ ] Design atomic swap logic with timestamps
[ ] Implement dual-graph initialization
[ ] Add swap task that runs every 12 hours
[ ] Handle edge case: slow pruning during swap
[ ] Verify memory usage stays reasonable (2x baseline)
[ ] Test failover: What if swap fails?
```

### To migrate V4+ → External DB
```
[ ] Evaluate: RedisGraph vs Neo4j vs ArangoDB
[ ] POC: Test write/read latency with target volume
[ ] Migration plan: How to copy existing graph
[ ] Rollback plan: Fallback to in-memory if service fails
[ ] Ops: Monitor RedisGraph availability, failover strategy
```

---

## Current Architecture Summary

**Today (Commit fbadcc8):**
- V1: Single asyncio.Lock()
- Pruning every 1000 adds (~1 hour at current volume)
- Zero contention (only 1 user request at a time from this perspective)
- Memory: ~500MB (30-day window)

**Suitable for:** Current production volume (1K txn/hour)

**Next step if latency issues appear:** Migrate to V2 (Background Pruning)

---

## Monitoring Recommendations

Add these metrics to your observability stack:

```python
# In graph_service.py
metrics = {
    "graph_nodes_count": self.graph.number_of_nodes(),
    "graph_edges_count": self.graph.number_of_edges(),
    "lock_wait_time_ms": measure_lock_contention(),
    "pruning_duration_ms": measure_pruning_time(),
    "fraudsters_count": len(self.known_fraudsters),
}
```

**Alert if:**
- P99 latency for get_graph_features > 100ms (pruning happening)
- graph_nodes_count > 10M (approaching memory limits)
- lock_wait_time > 50ms (contention detected)

---

## References

- asyncio.Lock: https://docs.python.org/3/library/asyncio-sync.html#lock
- asyncio.Semaphore (for RwLock): https://docs.python.org/3/library/asyncio-sync.html#semaphore
- NetworkX performance: https://networkx.org/documentation/stable/reference/algorithms/approximation.html
- RedisGraph: https://redis.io/commands/graph.query/
