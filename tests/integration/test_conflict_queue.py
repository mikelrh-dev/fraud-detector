"""The conflict queue endpoint wiring — `GET /api/v1/transactions?conflict=true`.

SCOPE, AND WHY IT IS NOT IN THE PREDICATE'S OWN TEST FILE
==========================================================
`tests/unit/test_conflict_predicate.py` proves the SQL selects the right rows,
against a real database. This file proves three things no unit test can see:

1. The endpoint actually puts that predicate into its queries. A predicate that
   is correct and never called is a feature that does not exist, and the only
   evidence available under a mocked session is the `Select` the endpoint
   hands to `db.execute`.
2. It puts it into BOTH the page query and the count query. Filtering the page
   and not the count is the exact bug R4 was filed about in this endpoint, and
   it is invisible in the response unless you read the counter.
3. The list response carries both layer scores, which is what makes the queue
   readable at all — a disagreement you cannot see the two numbers behind is
   not reviewable.

HOW THE SQL IS ASSERTED
=======================
`db.execute` is called with the `Select` itself, so the statement the endpoint
built is inspectable after the request. It is compiled with `literal_binds` so
the predicate renders with its values inline rather than as bind parameters,
which is what lets the assertion name the comparison rather than a placeholder.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from src.models.fraud_score import FraudClassification, FraudScore
from src.models.transaction import Transaction, TransactionStatus

pytestmark = pytest.mark.asyncio

# The owner the `auth_headers` fixture authenticates as (see tests/conftest.py),
# matching `_make_mock_transaction` in test_transaction_api.py.
ANALYST_ID = UUID("00000000-0000-0000-0000-000000000001")


def _txn(**overrides) -> MagicMock:
    txn = MagicMock(spec=Transaction)
    txn.id = overrides.get("id", uuid4())
    txn.amount = overrides.get("amount", 100.0)
    txn.currency = "USD"
    txn.merchant_name = "Test Store"
    txn.merchant_category = "retail"
    txn.card_last4 = "1234"
    txn.status = overrides.get("status", TransactionStatus.PENDING)
    txn.user_id = overrides.get("user_id", ANALYST_ID)
    txn.deleted_at = None
    txn.created_at = "2024-01-15T12:00:00+00:00"
    txn.updated_at = "2024-01-15T12:00:00+00:00"
    return txn


def _score(txn_id, **overrides) -> MagicMock:
    score = MagicMock(spec=FraudScore)
    score.transaction_id = txn_id
    score.rule_score = overrides.get("rule_score", 85.0)
    score.ml_score = overrides.get("ml_score", 27.55)
    score.ensemble_score = overrides.get("ensemble_score", 62.0)
    score.threshold = overrides.get("threshold", 50.0)
    score.classification = overrides.get("classification", FraudClassification.REVIEW)
    return score


def _stub_db(mock_db, txns, scores, total=None):
    """Wire the endpoint's three queries: count, page, batched scores."""
    count = MagicMock()
    count.scalar.return_value = len(txns) if total is None else total

    page_scalar = MagicMock()
    page_scalar.all.return_value = txns
    page = MagicMock()
    page.scalars.return_value = page_scalar

    score_scalar = MagicMock()
    score_scalar.all.return_value = scores
    score_result = MagicMock()
    score_result.scalars.return_value = score_scalar

    mock_db.execute = AsyncMock(side_effect=[count, page, score_result])
    return mock_db


def _executed_sql(mock_db) -> list[str]:
    """The compiled SQL of every statement the endpoint executed, in order."""
    return [
        str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
        for call in mock_db.execute.call_args_list
    ]


class TestConflictFilterIsWiredIntoBothQueries:
    async def test_conflict_true_filters_the_page_and_the_count(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        txn = _txn()
        _stub_db(mock_db, [txn], [_score(txn.id)])

        response = await test_client.get(
            "/api/v1/transactions?conflict=true", headers=auth_headers
        )

        assert response.status_code == 200
        count_sql, page_sql, _scores_sql = _executed_sql(mock_db)

        # The predicate, in both. A page filtered without the count would render
        # "page 1 of 4" over one row — the R4 bug in a new place.
        for label, sql in (("count", count_sql), ("page", page_sql)):
            assert "fraud_scores" in sql, f"{label} query lost the conflict filter"
            assert "fraud_scores.rule_score > fraud_scores.threshold" in sql, label
            assert "fraud_scores.ml_score > fraud_scores.threshold" in sql, label

        # And the subquery form specifically, not a JOIN: a JOIN would fan a
        # transaction out across its (unconstrained) score rows.
        assert "IN (SELECT" in page_sql

    async def test_the_predicate_reads_the_stored_threshold_not_a_literal(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The comparison must be column-to-column, never against a written number.

        A hardcoded 40 here would re-grade every row against one tier instead of
        the tier its own threshold column records.
        """
        txn = _txn()
        _stub_db(mock_db, [txn], [_score(txn.id)])

        await test_client.get("/api/v1/transactions?conflict=true", headers=auth_headers)

        _count_sql, page_sql, _ = _executed_sql(mock_db)
        assert "fraud_scores.ml_score <= fraud_scores.threshold" in page_sql
        assert "fraud_scores.rule_score <= fraud_scores.threshold" in page_sql

    async def test_absent_conflict_leaves_both_queries_unfiltered(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The default path is byte-for-byte the old one — the filter is opt-in."""
        txn = _txn()
        _stub_db(mock_db, [txn], [_score(txn.id)])

        response = await test_client.get("/api/v1/transactions", headers=auth_headers)

        assert response.status_code == 200
        count_sql, page_sql, scores_sql = _executed_sql(mock_db)
        for label, sql in (("count", count_sql), ("page", page_sql)):
            assert "fraud_scores" not in sql, f"{label} query was filtered unasked"
        # The batched score read is the only statement that may name the table.
        assert "fraud_scores" in scores_sql

    async def test_conflict_false_is_the_same_as_absent(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        txn = _txn()
        _stub_db(mock_db, [txn], [_score(txn.id)])

        response = await test_client.get(
            "/api/v1/transactions?conflict=false", headers=auth_headers
        )

        assert response.status_code == 200
        count_sql, page_sql, _ = _executed_sql(mock_db)
        assert "fraud_scores" not in count_sql
        assert "fraud_scores" not in page_sql

    async def test_ownership_scoping_still_applies_to_the_queue(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The conflict filter must narrow the queue, never widen it.

        An analyst's queue is their own transactions that disagree. If the
        subquery were applied instead of the owner filter rather than alongside
        it, the endpoint would return every user's conflicts — a cross-tenant
        read created by a read-side convenience.
        """
        txn = _txn()
        _stub_db(mock_db, [txn], [_score(txn.id)])

        response = await test_client.get(
            "/api/v1/transactions?conflict=true", headers=auth_headers
        )

        assert response.status_code == 200
        _count_sql, page_sql, _ = _executed_sql(mock_db)
        assert "transactions.user_id" in page_sql
        assert "fraud_scores" in page_sql

    async def test_the_queue_costs_no_extra_round_trip(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """Three queries with the filter on: count, page, one batched score read.

        The conflict predicate is a SUBQUERY inside the page statement, not a
        statement of its own. If this ever becomes four, something started
        fetching conflicts separately from the page.
        """
        txn = _txn()
        _stub_db(mock_db, [txn], [_score(txn.id)])

        await test_client.get("/api/v1/transactions?conflict=true", headers=auth_headers)

        assert mock_db.execute.call_count == 3


class TestConflictListExposesBothScores:
    async def test_a_queued_row_carries_both_layer_scores(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        txn = _txn()
        score = _score(txn.id, rule_score=85.0, ml_score=27.55399949848652)
        _stub_db(mock_db, [txn], [score])

        response = await test_client.get(
            "/api/v1/transactions?conflict=true", headers=auth_headers
        )

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["rule_score"] == 85.0
        assert item["ml_score"] == 27.55399949848652
        # Still the ensemble number the rest of the product already renders.
        assert item["risk_score"] == 62.0

    async def test_both_directions_are_visible_to_the_client(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """The two populations, in one response, distinguishable by the numbers.

        The client is handed the scores, not a pre-computed "direction" label,
        so it cannot disagree with the filter about which layer was loud.
        """
        loud_rules = _txn()
        loud_model = _txn()
        _stub_db(
            mock_db,
            [loud_rules, loud_model],
            [
                _score(loud_rules.id, rule_score=85.0, ml_score=27.55),
                _score(loud_model.id, rule_score=12.0, ml_score=91.0),
            ],
        )

        response = await test_client.get(
            "/api/v1/transactions?conflict=true", headers=auth_headers
        )

        items = {item["id"]: item for item in response.json()["items"]}
        assert items[str(loud_rules.id)]["rule_score"] > items[str(loud_rules.id)]["ml_score"]
        assert items[str(loud_model.id)]["ml_score"] > items[str(loud_model.id)]["rule_score"]

    async def test_an_unscored_transaction_reports_null_not_a_zero(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """A fabricated 0.0 would be a claim: "the model ran and said nothing".

        The product already makes that distinction explicitly (A15: an absent ML
        layer is reported through `layers_used`, never by nulling the score), so
        the list path must not invent a zero either.
        """
        txn = _txn()
        _stub_db(mock_db, [txn], [])

        response = await test_client.get(
            "/api/v1/transactions?conflict=true", headers=auth_headers
        )

        item = response.json()["items"][0]
        assert item["rule_score"] is None
        assert item["ml_score"] is None
        assert item["risk_score"] is None

    async def test_the_detail_path_does_not_duplicate_the_breakdown(
        self, test_client: AsyncClient, mock_db: AsyncMock, auth_headers: dict
    ):
        """`GET /transactions/{id}` keeps both scores inside `scoring` only.

        Adding the two fields to the shared schema made them available on every
        path that returns `TransactionResponse`. Populating them on the detail
        path too would put the same two numbers in the payload twice, under two
        names, which is the kind of duplication that later disagrees with itself.
        """
        txn = _txn()

        # The detail path runs two queries, not the list path's three: load the
        # transaction, then read its scores. Stubbed separately rather than by
        # extending `_stub_db`, because a shared helper would have to know both
        # shapes and would hide which one each test is exercising.
        found = MagicMock()
        found.scalar_one_or_none.return_value = txn
        score_scalar = MagicMock()
        score_scalar.all.return_value = [_score(txn.id)]
        score_result = MagicMock()
        score_result.scalars.return_value = score_scalar
        # Third query: the SHAP attribution rows, which the detail path reads
        # whenever a score exists. Empty here, so `scoring.shap_contributions`
        # stays null and the assertion is about the two score fields only.
        shap_scalar = MagicMock()
        shap_scalar.all.return_value = []
        shap_result = MagicMock()
        shap_result.scalars.return_value = shap_scalar
        mock_db.execute = AsyncMock(side_effect=[found, score_result, shap_result])

        response = await test_client.get(
            f"/api/v1/transactions/{txn.id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["scoring"]["rule_score"] == 85.0
        assert data["scoring"]["ml_score"] == 27.55
        assert data["rule_score"] is None
        assert data["ml_score"] is None