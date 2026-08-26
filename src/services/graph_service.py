"""Graph Analytics Service for Fraud Network Detection.

Maintains an in-memory fraud network using NetworkX. Detects if a user or card
is connected to known fraudsters (2 hops or less), indicating potential mule accounts.

Thread-Safe: Uses threading.Lock() to prevent race conditions on concurrent access.
Memory-Safe: Implements pruning to prevent unbounded growth.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone

import networkx as nx

logger = logging.getLogger(__name__)


class FraudGraphService:
    """Detects fraud networks using graph analysis.
    
    Maintains a directed graph where:
    - Nodes: user IDs and card IDs
    - Edges: transactions between users/cards
    - Attributes: fraud labels on nodes, timestamps for pruning
    
    Thread-Safe: All operations protected by asyncio.Lock() to handle concurrent requests.
    Memory-Safe: Automatic pruning keeps graph bounded (default: 30-day retention).
    """

    def __init__(self, retention_days: int = 30):
        """Initialize the fraud graph.
        
        Args:
            retention_days: Days to retain transaction nodes (default: 30)
        """
        self.graph = nx.DiGraph()
        self.known_fraudsters: set[str] = set()
        self.lock = threading.Lock()  # Thread-safety lock (sync, for to_thread)
        self.retention_days = retention_days
        self.last_pruned = datetime.now(tz=timezone.utc)
        logger.info("FraudGraphService initialized with empty graph (retention: %d days)", retention_days)

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
                    logger.warning(
                        "Marked as fraudster: sender=%s, card=%s (known_fraudsters=%d)",
                        sender_id,
                        card_id,
                        len(self.known_fraudsters),
                    )
                
                # Prune old nodes if needed (check every 1000 adds)
                if self.graph.number_of_nodes() % 1000 == 0:
                    self._prune_old_nodes()

            except Exception as exc:
                logger.error("Failed to add transaction to graph: %s", exc)

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
                # Degree centrality
                degree_centrality = nx.degree_centrality(self.graph).get(user_id, 0.0)

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

    def _prune_old_nodes(self) -> None:
        """Remove nodes older than retention_days (memory management).
        
        Called periodically (every 1000 adds) to prevent unbounded growth.
        Removes transaction nodes but preserves fraudster nodes.
        """
        try:
            cutoff_time = datetime.now(tz=timezone.utc) - timedelta(days=self.retention_days)
            nodes_to_remove = []
            
            for node in self.graph.nodes():
                node_timestamp = self.graph.nodes[node].get("timestamp")
                if node_timestamp and node_timestamp < cutoff_time:
                    # Don't remove fraudsters (keep for detection)
                    if node not in self.known_fraudsters:
                        nodes_to_remove.append(node)
            
            if nodes_to_remove:
                self.graph.remove_nodes_from(nodes_to_remove)
                self.last_pruned = datetime.now(tz=timezone.utc)
                logger.info(
                    "Pruned %d old nodes (retention: %d days). Graph size: %d nodes, %d edges",
                    len(nodes_to_remove),
                    self.retention_days,
                    self.graph.number_of_nodes(),
                    self.graph.number_of_edges(),
                )
        except Exception as exc:
            logger.error("Failed to prune old nodes: %s", exc)
