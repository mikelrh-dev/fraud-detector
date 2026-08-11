"""Tests for Pydantic schemas."""

import uuid
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.models.fraud_score import FraudClassification
from src.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from src.schemas.transaction import ScoreBreakdown, TransactionResponse


class TestAuthSchemas:
    """Auth schema validation tests."""

    def test_login_request_valid(self):
        """LoginRequest should accept valid username and password."""
        data = LoginRequest(username="analyst1", password="secure_pass_123")
        assert data.username == "analyst1"
        assert data.password == "secure_pass_123"

    def test_login_request_empty_username_raises(self):
        """LoginRequest with empty username should fail validation."""
        with pytest.raises(ValidationError):
            LoginRequest(username="", password="secure_pass_123")

    def test_login_request_empty_password_raises(self):
        """LoginRequest with empty password should fail validation."""
        with pytest.raises(ValidationError):
            LoginRequest(username="analyst1", password="")

    def test_register_request_valid(self):
        """RegisterRequest should accept valid user data."""
        data = RegisterRequest(
            username="new_analyst",
            email="analyst@example.com",
            password="secure_pass_123",
            role="analyst",
        )
        assert data.username == "new_analyst"
        assert data.email == "analyst@example.com"

    def test_register_request_invalid_email_raises(self):
        """RegisterRequest with invalid email should fail validation."""
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="new_analyst",
                email="not-an-email",
                password="secure_pass_123",
                role="analyst",
            )

    def test_register_request_invalid_role_raises(self):
        """RegisterRequest with invalid role should fail validation."""
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="new_analyst",
                email="analyst@example.com",
                password="secure_pass_123",
                role="superadmin",
            )

    def test_token_response_valid(self):
        """TokenResponse should accept valid token data."""
        data = TokenResponse(
            access_token="eyJ...",
            refresh_token="eyJ...",
            token_type="bearer",
        )
        assert data.access_token == "eyJ..."
        assert data.token_type == "bearer"

    def test_token_response_default_type(self):
        """TokenResponse should default token_type to 'bearer'."""
        data = TokenResponse(
            access_token="eyJ...",
            refresh_token="eyJ...",
        )
        assert data.token_type == "bearer"

    def test_user_response_valid(self):
        """UserResponse should accept valid user data."""
        user_id = uuid.uuid4()
        data = UserResponse(
            id=user_id,
            username="analyst1",
            email="analyst@example.com",
            role="analyst",
            is_active=True,
        )
        assert data.id == user_id
        assert data.role == "analyst"
        assert data.is_active is True


class TestScoreBreakdown:
    """ScoreBreakdown nested schema validation tests."""

    def test_model_validate_from_fraud_score_maps_all_attrs(self):
        """ScoreBreakdown should map all five fields from a FraudScore."""
        score = MagicMock()
        score.rule_score = 45.0
        score.ml_score = 60.0
        score.ensemble_score = 52.0
        score.threshold = 70.0
        score.classification = FraudClassification.REVIEW

        breakdown = ScoreBreakdown.model_validate(score)

        assert breakdown.rule_score == 45.0
        assert breakdown.ml_score == 60.0
        assert breakdown.ensemble_score == 52.0
        assert breakdown.threshold == 70.0
        assert breakdown.classification == "review"

    def test_transaction_response_optional_fields_default_to_none(self):
        """risk_score/classification/scoring should default to None."""
        txn_id = uuid.uuid4()
        data = TransactionResponse(
            id=txn_id,
            amount=100.0,
            currency="USD",
            merchant_name="Test Store",
            merchant_category="retail",
            card_last4="1234",
            status="pending",
            user_id=uuid.uuid4(),
            created_at="2024-01-15T12:00:00+00:00",
            updated_at="2024-01-15T12:00:00+00:00",
        )
        assert data.risk_score is None
        assert data.classification is None
        assert data.scoring is None

    def test_transaction_response_accepts_scoring_breakdown(self):
        """TransactionResponse should accept a nested scoring breakdown."""
        txn_id = uuid.uuid4()
        data = TransactionResponse(
            id=txn_id,
            amount=100.0,
            currency="USD",
            merchant_name="Test Store",
            merchant_category="retail",
            card_last4="1234",
            status="flagged",
            user_id=uuid.uuid4(),
            risk_score=52.0,
            classification="review",
            scoring=ScoreBreakdown(
                rule_score=45.0,
                ml_score=60.0,
                ensemble_score=52.0,
                threshold=70.0,
                classification="review",
            ),
            created_at="2024-01-15T12:00:00+00:00",
            updated_at="2024-01-15T12:00:00+00:00",
        )
        assert data.risk_score == 52.0
        assert data.classification == "review"
        assert data.scoring.ensemble_score == 52.0
        assert data.scoring.classification == "review"
