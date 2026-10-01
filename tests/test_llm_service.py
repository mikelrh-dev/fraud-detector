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

        assert "transacción" in prompt.lower()
        assert "decisión" in prompt.lower()

    def test_prompt_forbids_the_model_from_restating_figures(self):
        """The model must not be asked to recite the scores.

        A 1B model handed 85.0 returned 0.0 and then concluded the rules had
        not contributed to a transaction they had flagged. The scores stay in
        the prompt as magnitude context, but the instruction has to forbid
        quoting them, because `_render_report` writes the authoritative
        figures itself.
        """
        service = LLMService()
        score_breakdown = {
            "rule_score": 60.0,
            "ml_score": 80.0,
            "ensemble_score": 72.0,
            "fired_rules": ["high_amount"],
            "threshold": 70.0,
        }
        prompt = service.build_prompt(score_breakdown, {"amount": 15000.0})

        lowered = prompt.lower()
        assert "no repitas" in lowered
        assert "puntuación" in lowered or "puntuaciones" in lowered
        # The decision is stated as already made, not as something to derive.
        assert "ya está decidida" in lowered

    def test_prompt_asks_for_two_prose_paragraphs(self):
        """The contract is prose only: two paragraphs, no structure."""
        service = LLMService()
        prompt = service.build_prompt(
            {"rule_score": 60.0, "ml_score": 80.0, "ensemble_score": 72.0,
             "fired_rules": ["high_amount"], "threshold": 70.0},
            {"amount": 15000.0},
        )

        lowered = prompt.lower()
        assert "dos párrafos" in lowered
        assert "sin títulos" in lowered

    def test_prompt_excludes_the_merchant_name(self):
        """The merchant identifier must not reach the model.

        Measured: with the name in the prompt, llama3.2:1b pasted it into the
        prose and the report was stored with it. A merchant identifier should
        not travel through a generation step, and the category carries the
        same analytical signal.
        """
        service = LLMService()
        prompt = service.build_prompt(
            {"rule_score": 35.0, "ml_score": 10.0, "ensemble_score": 30.1,
             "fired_rules": ["amount_round_number"], "threshold": 70.0},
            {"amount": 45.0, "merchant_name": "Store_3", "merchant_category": "grocery"},
        )

        assert "Store_3" not in prompt
        assert "grocery" in prompt

    def test_prompt_tells_the_model_how_many_rules_fired(self):
        """A single-rule case must not be described as a combination.

        26.6% of transactions trigger exactly one rule against 6.4% for two or
        more. Given two multi-rule examples, the model completed a one-rule
        case up to match them — inventing time-of-day, velocity and blacklist
        signals in 31 of 18 measured reports.
        """
        service = LLMService()
        base = {"rule_score": 35.0, "ml_score": 10.0, "ensemble_score": 30.1, "threshold": 70.0}

        one = service.build_prompt({**base, "fired_rules": ["high_amount"]}, {"amount": 500.0})
        assert "una sola regla" in one.lower()
        assert "no hay combinación" in one.lower()

        many = service.build_prompt(
            {**base, "fired_rules": ["high_amount", "unusual_merchant"]},
            {"amount": 500.0},
        )
        assert "2 reglas" in many.lower()
        assert "no hay combinación" not in many.lower()

    def test_prompt_forbids_facts_absent_from_the_rules(self):
        """The hard constraint the earlier prompt lacked."""
        service = LLMService()
        prompt = service.build_prompt(
            {"rule_score": 35.0, "ml_score": 10.0, "ensemble_score": 30.1,
             "fired_rules": ["high_amount"], "threshold": 70.0},
            {"amount": 500.0},
        )
        assert "no menciones hechos que no estén" in prompt.lower()

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
            "merchant_category": "retail",
            "currency": "USD",
        }
        prompt = service.build_prompt(score_breakdown, transaction)

        assert "15000" in prompt
        assert "USD" in prompt
        # The category carries the analytical signal; the identifier does not
        # belong in a generation step at all (see the exclusion test above).
        assert "retail" in prompt

    def test_render_report_writes_the_figures_itself(self):
        """Every number in the stored report comes from the inputs."""
        report = LLMService._render_report(
            {
                "rule_score": 85.0,
                "ml_score": 62.3,
                "ensemble_score": 78.4,
                "threshold": 45.0,
                "classification": "fraud",
                "fired_rules": ["high_amount", "unusual_merchant"],
            },
            {"amount": 8420.50},
            "El importe es inusualmente alto para este comercio.\n\nRevisar manualmente.",
        )

        assert "78.4" in report
        assert "45.0" in report
        assert "85.0" in report
        assert "62.3" in report
        assert "FRAUDE" in report
        assert "high_amount" in report
        assert "El importe es inusualmente alto" in report
        assert "Revisar manualmente" in report

    def test_prose_cannot_overwrite_the_decision(self):
        """A hallucinating model cannot change a figure the code already wrote.

        This is the defect the redesign exists for: the model previously
        reported 0.0 for every layer and called the transaction a review.
        """
        report = LLMService._render_report(
            {
                "rule_score": 85.0,
                "ml_score": 62.3,
                "ensemble_score": 78.4,
                "threshold": 45.0,
                "classification": "fraud",
                "fired_rules": ["high_amount"],
            },
            {"amount": 8420.50},
            "El puntaje es 0.0/100 y la transacción es REQUIERE REVISIÓN.",
        )

        assert "0.0/100" not in report.split("## Análisis")[0]
        assert "FRAUDE" in report
        assert "78.4" in report

    def test_unsourced_numbers_flags_hallucinated_figures(self):
        from src.services.llm import _numeric_fingerprints, _unsourced_numbers

        allowed = _numeric_fingerprints(85.0, 62.3, 78.4, 45.0, 8420.50)
        prose = "El score fue 78.4 y el coste 450 EUR en(reordered) 2023."

        found = _unsourced_numbers(prose, allowed)
        assert "78.4" not in found
        assert "450" in found
        assert "2023" in found

    def test_split_prose_tolerates_a_single_paragraph(self):
        """Short answers must not lose their text."""
        analysis, recommendation = LLMService._split_prose("Solo un parrafo.")
        assert analysis == "Solo un parrafo."
        assert recommendation == ""

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
    async def test_ollama_unavailable_raises_connect_error(self):
        """When Ollama is unavailable, should raise ConnectError for retry/DLQ."""
        service = LLMService(ollama_url="http://test:11434", timeout=1)

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

        with pytest.raises(httpx.ConnectError):
            await service.generate_report(
                transaction_id="test-uuid",
                score_breakdown=score_breakdown,
                transaction={"amount": 1000.0},
                _client=mock_client,
            )

    @pytest.mark.asyncio
    async def test_timeout_raises_timeout_exception(self):
        """When Ollama times out, should raise TimeoutException for retry/DLQ."""
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

        with pytest.raises(httpx.TimeoutException):
            await service.generate_report(
                transaction_id="test-uuid",
                score_breakdown=score_breakdown,
                transaction={"amount": 1000.0},
                _client=mock_client,
            )
