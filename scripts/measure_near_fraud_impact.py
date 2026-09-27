"""Measure whether the near-fraud graph signal can ever fire. No behaviour change.

WHY THIS EXISTS
`FraudGraphService` is a `DiGraph` and `add_transaction` only ever creates
`sender -> receiver` and `sender -> card` edges. `get_graph_features` runs BFS
following **outgoing** edges only, so from a merchant node (a receiver) there is
nowhere to go, and from a user node the only reachable fraudsters are ones that
user already transacted with directly.

That means `is_near_fraud` may be structurally unreachable in the production
topology. Before deciding whether to add reverse edges — which would change
scoring behaviour on day one — this script measures what the signal would
actually do on a realistic topology.

Run:
    python -m scripts.measure_near_fraud_impact
"""

import argparse
import json
import random
from collections import Counter

import networkx as nx

from src.services.graph_service import FraudGraphService


def build_production_like_graph(
    service: FraudGraphService,
    *,
    users: int,
    transactions: int,
    fraud_rate: float,
    shared_merchant_rate: float,
    seed: int = 7,
) -> None:
    """Populate the graph the way the API does.

    Mirrors `create_and_score_transaction`: sender is the authenticated user,
    receiver is a merchant node derived from the merchant name, card is the
    last-4. A share of transactions reuse a small merchant pool, which is what
    makes networks form at all.
    """
    rng = random.Random(seed)
    merchants = [f"merchant_{i}" for i in range(40)]
    cards = [f"card_{i:04d}" for i in range(users)]

    for i in range(transactions):
        sender = f"user_{rng.randrange(users)}"
        if rng.random() < shared_merchant_rate:
            receiver = rng.choice(merchants)
        else:
            receiver = f"merchant_{rng.randrange(users * 2)}"
        card = cards[rng.randrange(users)]
        service.add_transaction(
            sender_id=sender,
            receiver_id=receiver,
            card_id=card,
            is_fraud=rng.random() < fraud_rate,
        )


def measure(graph: nx.DiGraph, known_fraudsters: set[str]) -> dict:
    """How many nodes would BFS reach a fraudster from, following out-edges?"""
    stats = Counter()
    for node in graph.nodes():
        reachable = nx.single_source_shortest_path_length(graph, node, cutoff=2)
        hit = any(f in reachable for f in known_fraudsters)
        self_hit = node in known_fraudsters
        if self_hit:
            stats["is_fraudster"] += 1
        elif hit:
            stats["near_fraud_1_or_2_hops"] += 1
        else:
            stats["no_signal"] += 1

    total = graph.number_of_nodes()
    return {
        "nodes": total,
        "edges": graph.number_of_edges(),
        "known_fraudsters": len(known_fraudsters),
        **dict(stats),
        "pct_near_fraud": round(
            100.0 * stats["near_fraud_1_or_2_hops"] / total, 2
        )
        if total
        else 0.0,
    }


def measure_undirected(graph: nx.DiGraph, known_fraudsters: set[str]) -> dict:
    """Same measurement on the undirected view — the counterfactual.

    This is what the signal would report if edges were traversable in both
    directions. It is the upper bound of what adding reverse edges would buy.
    """
    undirected = graph.to_undirected()
    stats = Counter()
    for node in undirected.nodes():
        reachable = nx.single_source_shortest_path_length(undirected, node, cutoff=2)
        hit = any(f in reachable for f in known_fraudsters)
        if node in known_fraudsters:
            stats["is_fraudster"] += 1
        elif hit:
            stats["near_fraud_1_or_2_hops"] += 1
        else:
            stats["no_signal"] += 1

    total = undirected.number_of_nodes()
    return {
        "nodes": total,
        **dict(stats),
        "pct_near_fraud": round(
            100.0 * stats["near_fraud_1_or_2_hops"] / total, 2
        )
        if total
        else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=200)
    parser.add_argument("--transactions", type=int, default=2000)
    parser.add_argument("--fraud-rate", type=float, default=0.02)
    parser.add_argument(
        "--shared-merchant-rate",
        type=float,
        default=0.5,
        help="share of transactions hitting a shared merchant pool",
    )
    args = parser.parse_args()

    service = FraudGraphService()
    build_production_like_graph(
        service,
        users=args.users,
        transactions=args.transactions,
        fraud_rate=args.fraud_rate,
        shared_merchant_rate=args.shared_merchant_rate,
    )

    report = {
        "topology": {
            "users": args.users,
            "transactions": args.transactions,
            "fraud_rate": args.fraud_rate,
            "shared_merchant_rate": args.shared_merchant_rate,
        },
        "as_shipped_directed": measure(
            service.graph, service.known_fraudsters
        ),
        "counterfactual_undirected": measure_undirected(
            service.graph, service.known_fraudsters
        ),
    }

    print(json.dumps(report, indent=2))

    shipped = report["as_shipped_directed"]
    counterfactual = report["counterfactual_undirected"]
    print(
        "\n--- VERDICT ---\n"
        f"as shipped (directed): {shipped['pct_near_fraud']}% of nodes flagged "
        f"near-fraud\n"
        f"if edges were traversable both ways: "
        f"{counterfactual['pct_near_fraud']}%\n"
        "The gap is the behaviour change that adding reverse edges would cause."
    )


if __name__ == "__main__":
    main()
