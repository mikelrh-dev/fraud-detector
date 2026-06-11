"""LLM service tests — prompt template, timeout handling, Ollama unavailable.

Tests for the async Ollama client wrapper that generates explanatory
fraud reports in Spanish for analysts.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.services.llm import LLMService


class TestLLMPromptTemplate:
    """Prompt template must contain all scoring information and be in Spanish."""

    def test_prompt_contains_all_scores(self):
        """The prompt should include rule_score, ml_score, and ensemble_score."""
        service = LLMService()
        score_breakdown = {
            "rule_score": 60.0,
            "ml_score": 80.0,
            "ensemble_score": 72.0,
            "fired_rules": ["high_amount", "high_velocity"],
            "threshold": 70.0,
        }
        transaction = {
            "amount": 15000.0,
            "merchant_name": "Test Store",
            "currency": "USD",
        }
        prompt = service.build_prompt(score_breakdown, transaction)

        assert "60" in prompt
        assert "80" in prompt
        assert "72" in prompt

    def test_prompt_contains_fired_rules(self):
        """The prompt should list the fired rules."""
        service = LLMService()
        score_breakdown = {
            "rule_score": 60.0,
            "ml_score": 80.0,
            "ensemble_score": 72.0,
            "fired_rules": ["high_amount", "high_velocity", "unusual_hours"],
            "threshold": 70.0,
        }
        transaction = {"amount": 15000.0, "merchant_name": "Test Store"}
        prompt = service.build_prompt(score_breakdown, transaction)

        assert "high_amount" in prompt
        assert "high_velocity" in prompt
        assert "unusual_hours" in prompt

    def test_prompt_is_in_spanish(self):
        """The prompt should be written in Spanish."""
        service = LLMService()
        score_breakdown = {
            "rule_score": 60.0,
            "ml_score": 80.0,
            "ensemble_score": 72.0,
            "fired_rules": ["high_amount"],
            "threshold": 70.0,
        }
        transaction = {"amount": 15000.0, "merchant_name": "Test Store"}
        prompt = service.build_prompt(score_breakdown, transaction)

        # Should contain Spanish keywords
        assert any(word in prompt.lower() for word in ["justificación", "recomendación", "factores"])
        assert "transacción" in prompt.lower()

    def test_prompt_includes_three_sections(self):
        """The prompt should ask for: risk justification, technical recommendation,
        and contextual factors."""
        service = LLMService()
        score_breakdown = {
            "rule_score": 60.0,
            "ml_score": 80.0,
            "ensemble_score": 72.0,
            "fired_rules": ["high_amount"],
            "threshold": 70.0,
        }
        transaction = {"amount": 15000.0, "merchant_name": "Test Store"}
        prompt = service.build_prompt(score_breakdown, transaction)

        # Should contain the three required sections
        assert "justificación" in prompt.lower() or "justificacion" in prompt.lower()
        assert "recomendación" in prompt.lower() or "recomendacion" in prompt.lower()
        assert "factores" in prompt.lower() or "contexto" in prompt.lower()

    def test_prompt_contains_transaction_details(self):
        """The prompt should include transaction details like amount and merchant."""
        service = LLMService()
        score_breakdown = {
            "rule_score": 60.0,
            "ml_score": 80.0,
            "ensemble_score": 72.0,
            "fired_rules": ["high_amount"],
            "threshold": 70.0,
        }
        transaction = {
            "amount": 15000.0,
            "merchant_name": "Test Store",
            "currency": "USD",
        }
        prompt = service.build_prompt(score_breakdown, transaction)

        assert "15000" in prompt
        assert "Test Store" in prompt
        assert "USD" in prompt

    def test_no_fired_rules_still_creates_prompt(self):
        """The prompt should work even when no rules fired."""
        service = LLMService()
        score_breakdown = {
            "rule_score": 0.0,
            "ml_score": 10.0,
            "ensemble_score": 4.5,
            "fired_rules": [],
            "threshold": 70.0,
        }
        transaction = {"amount": 50.0, "merchant_name": "Normal Store"}
        prompt = service.build_prompt(score_breakdown, transaction)
        assert len(prompt) > 50
        assert "50" in prompt or "Normal Store" in prompt


class TestLLMServiceGenerate:
    """LLM report generation behavior."""

    @pytest.mark.asyncio
    async def test_generate_report_returns_string(self):
        """generate_report should return a string on success."""
        service = LLMService(ollama_url="http://test:11434")

        # Mock the httpx client (response.json() is sync in httpx)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={"response": "Análisis de fraude: la transacción es sospechosa."}
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        score_breakdown = {
            "rule_score": 60.0,
            "ml_score": 80.0,
            "ensemble_score": 72.0,
            "fired_rules": ["high_amount"],
            "threshold": 70.0,
        }

        result = await service.generate_report(
            transaction_id="test-uuid",
            score_breakdown=score_breakdown,
            transaction={"amount": 1000.0},
            _client=mock_client,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_report_contains_analysis(self):
        """generate_report should return the Ollama response text."""
        service = LLMService(ollama_url="http://test:11434")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={"response": "Análisis completo de riesgo."}
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        score_breakdown = {
            "rule_score": 60.0,
            "ml_score": 80.0,
            "ensemble_score": 72.0,
            "fired_rules": ["high_amount"],
            "threshold": 70.0,
        }

        result = await service.generate_report(
            transaction_id="test-uuid",
            score_breakdown=score_breakdown,
            transaction={"amount": 1000.0},
            _client=mock_client,
        )
        assert "Análisis completo de riesgo." in result

    @pytest.mark.asyncio
    async def test_ollama_unavailable_returns_error(self):
        """When Ollama is unavailable, should return error message, not crash."""
        service = LLMService(ollama_url="http://nonexistent:11434")

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        score_breakdown = {
            "rule_score": 60.0,
            "ml_score": 80.0,
            "ensemble_score": 72.0,
            "fired_rules": ["high_amount"],
            "threshold": 70.0,
        }

        result = await service.generate_report(
            transaction_id="test-uuid",
            score_breakdown=score_breakdown,
            transaction={"amount": 1000.0},
            _client=mock_client,
        )
        assert isinstance(result, str)
        assert "error" in result.lower() or "no disponible" in result.lower()

    @pytest.mark.asyncio
    async def test_timeout_returns_error_message(self):
        """When Ollama times out, should return error message, not crash."""
        service = LLMService(ollama_url="http://test:11434", timeout=1)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        score_breakdown = {
            "rule_score": 60.0,
            "ml_score": 80.0,
            "ensemble_score": 72.0,
            "fired_rules": ["high_amount"],
            "threshold": 70.0,
        }

        result = await service.generate_report(
            transaction_id="test-uuid",
            score_breakdown=score_breakdown,
            transaction={"amount": 1000.0},
            _client=mock_client,
        )
        assert isinstance(result, str)
        assert len(result) > 0
