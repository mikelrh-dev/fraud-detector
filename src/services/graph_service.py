"""Graph Analytics Service for Fraud Network Detection.

Maintains an in-memory fraud network using NetworkX. Detects if a user or card
is connected to known fraudsters (2 hops or less), indicating potential mule accounts.
"""

import logging
from typing import Optional

import networkx as nx

logger = logging.getLogger(__name__)


class FraudGraphService:
    """Detects fraud networks using graph analysis.
    
    Maintains a directed graph where:
    - Nodes: user IDs and card IDs
    - Edges: transactions between users/cards
    - Attributes: fraud labels on nodes
    """

    def __init__(self):
        """Initialize the fraud graph."""
        self.graph = nx.DiGraph()
        self.known_fraudsters = set()
        logger.info("FraudGraphService initialized with empty graph")

    def add_transaction(
        self,
        sender_id: str,
        receiver_id: str,
        card_id: str,
        is_fraud: bool = False,
    ) -> None:
        """Add a transaction to the fraud network.
        
        Creates edges between sender/receiver and marks the card.
        If is_fraud=True, marks both sender and card as fraudsters.
        
        Args:
            sender_id: User ID of sender
            receiver_id: User ID of receiver
            card_id: Card identifier (last 4 digits or full card hash)
            is_fraud: Whether this transaction was flagged as fraud
        """
        try:
            # Add nodes if they don't exist
            self.graph.add_node(sender_id, node_type="user", is_fraud=False)
            self.graph.add_node(receiver_id, node_type="user", is_fraud=False)
            self.graph.add_node(card_id, node_type="card", is_fraud=False)

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

        except Exception as exc:
            logger.error("Failed to add transaction to graph: %s", exc)

    def get_graph_features(self, user_id: str) -> dict:
        """Get graph-based features for a user.
        
        Args:
            user_id: User ID to analyze
            
        Returns:
            Dict with keys:
            - is_near_fraud: 1 if user is ≤2 hops from fraudster, 0 otherwise
            - degree_centrality: User's connection count (0-1 normalized)
            - shortest_path_to_fraud: Hops to nearest fraudster (999 if unreachable)
            - connected_fraudsters: Count of connected fraudsters
        """
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

            # Find shortest path to any fraudster
            shortest_path = 999
            connected_fraudsters = 0

            for fraudster_id in self.known_fraudsters:
                if fraudster_id == user_id:
                    # User IS a fraudster
                    shortest_path = 0
                    connected_fraudsters += 1
                    continue

                try:
                    path_length = nx.shortest_path_length(self.graph, user_id, fraudster_id)
                    if path_length < shortest_path:
                        shortest_path = path_length
                    connected_fraudsters += 1
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    # No path to this fraudster
                    continue

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
        """Get overall graph statistics."""
        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "known_fraudsters": len(self.known_fraudsters),
            "graph_density": nx.density(self.graph),
        }
