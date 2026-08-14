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
from src.schemas.transaction import (
    ScoreBreakdown,
    ShapContribution,
    TransactionResponse,
)


class TestAuthSchemas:
    """Auth schema validation tests."""

    def test_login_request_valid(self):
        """LoginRequest should accept a valid email and password."""
        data = LoginRequest(email="analyst1@example.com", password="secure_pass_123")
        assert data.email == "analyst1@example.com"
        assert data.password == "secure_pass_123"

    def test_login_request_empty_email_raises(self):
        """LoginRequest with empty email should fail validation."""
        with pytest.raises(ValidationError):
            LoginRequest(email="", password="secure_pass_123")

    def test_login_request_empty_password_raises(self):
        """LoginRequest with empty password should fail validation."""
        with pytest.raises(ValidationError):
            LoginRequest(email="analyst1@example.com", password="")

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

    def test_password_too_short(self):
        """Password with fewer than 8 characters should fail validation."""
        with pytest.raises(ValidationError):
            RegisterRequest(username="testuser", email="test@example.com", password="short1")

    def test_password_too_long(self):
        """Password longer than 64 characters should fail validation (bcrypt 72-byte limit)."""
        long_pw = "a" * 65
        with pytest.raises(ValidationError):
            RegisterRequest(username="testuser", email="test@example.com", password=long_pw)

    def test_password_is_common(self):
        """Common/weak passwords should fail validation."""
        for common_pw in ["password", "12345678", "qwerty123", "admin123"]:
            with pytest.raises(ValidationError):
                RegisterRequest(username="testuser", email="test@example.com", password=common_pw)

    def test_password_matches_email_local_part(self):
        """Password derived from the email local part should fail validation."""
        with pytest.raises(ValidationError):
            RegisterRequest(username="testuser", email="alice@example.com", password="alice123")

    def test_password_equals_email_local_part(self):
        """Password equal to the email local part should fail validation."""
        with pytest.raises(ValidationError):
            RegisterRequest(username="testuser", email="johnsmith@example.com", password="johnsmith")

    def test_password_matches_username(self):
        """Password containing the username should fail validation."""
        with pytest.raises(ValidationError):
            RegisterRequest(username="bob", email="test@example.com", password="bob12345")

    def test_password_matches_username_case_insensitive(self):
        """Password containing the username in different case should fail validation."""
        with pytest.raises(ValidationError):
            RegisterRequest(username="bob", email="test@example.com", password="BOB12345")

    def test_valid_strong_password(self):
        """A strong password should be accepted."""
        req = RegisterRequest(
            username="testuser",
            email="test@example.com",
            password="SecureP@ssw0rd123",
        )
        assert req.password == "SecureP@ssw0rd123"

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


class TestShapContribution:
    """ShapContribution schema validation tests (FRD-SHP-001)."""

    def test_valid_contribution(self):
        """ShapContribution should accept feature and signed contribution."""
        contribution = ShapContribution(feature="amount", contribution=0.75)
        assert contribution.feature == "amount"
        assert contribution.contribution == 0.75

    def test_negative_contribution_preserved(self):
        """Negative contributions (pushing toward legitimate) must be kept signed."""
        contribution = ShapContribution(feature="amount_vs_user_avg", contribution=-0.25)
        assert contribution.model_dump() == {
            "feature": "amount_vs_user_avg",
            "contribution": -0.25,
        }

    def test_invalid_contribution_type_raises(self):
        """Non-numeric contribution should fail validation."""
        with pytest.raises(ValidationError):
            ShapContribution(feature="amount", contribution="high")


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
        # FraudScore has no shap_contributions attribute — must default to null
        score.shap_contributions = None

        breakdown = ScoreBreakdown.model_validate(score)

        assert breakdown.rule_score == 45.0
        assert breakdown.ml_score == 60.0
        assert breakdown.ensemble_score == 52.0
        assert breakdown.threshold == 70.0
        assert breakdown.classification == "review"
        assert breakdown.shap_contributions is None

    def test_shap_contributions_defaults_to_none(self):
        """shap_contributions should default to None when not provided."""
        breakdown = ScoreBreakdown(
            rule_score=45.0,
            ml_score=60.0,
            ensemble_score=52.0,
            threshold=70.0,
            classification="review",
        )
        assert breakdown.shap_contributions is None

    def test_shap_contributions_accepts_ordered_list(self):
        """shap_contributions should accept an ordered list of contributions."""
        breakdown = ScoreBreakdown(
            rule_score=45.0,
            ml_score=60.0,
            ensemble_score=52.0,
            threshold=70.0,
            classification="fraud",
            shap_contributions=[
                ShapContribution(feature="amount", contribution=0.80),
                ShapContribution(feature="merchant_risk_level", contribution=-0.30),
            ],
        )
        assert breakdown.shap_contributions is not None
        assert breakdown.shap_contributions[0].feature == "amount"
        assert breakdown.shap_contributions[0].contribution == 0.80
        assert breakdown.shap_contributions[1].feature == "merchant_risk_level"
        assert breakdown.shap_contributions[1].contribution == -0.30

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
