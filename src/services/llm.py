"""LLM service — async Ollama client wrapper for fraud report generation.

Generates explanatory fraud analysis reports in Spanish using a local
Ollama model. The LLM provides analysis only — it does NOT make fraud
determinations, and it does not own the numbers either.

The division of labour is deliberate. A small local model can write prose but
cannot be trusted to restate figures: asked for the ensemble score, a 1B model
returned 0.0 and then concluded the rules did not contribute. So the scores,
the classification and the fired rules are rendered here, from the values the
deterministic engine already computed, and the model is given one job — write
two qualitative paragraphs. Its output is never parsed for figures.
"""

import logging
import re
from typing import Any

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """Eres un analista de sistemas de detección de fraude.

## Datos de la Transacción
- Monto: ${amount} {currency}
- Comercio: {merchant_name}
- Sector: {merchant_category}

## Contexto del Score
Estos valores son de referencia para que entiendas la magnitud del caso. La
clasificación ya está decidida de forma determinista por las reglas y el modelo
ML, y no depende de ti.

- Motor de Reglas (determinista): {rule_score:.1f}/100
- Modelo ML (anomalía): {ml_score:.1f}/100
- Puntaje Ensemble: {ensemble_score:.1f}/100
- Umbral aplicado: {threshold:.1f}/100

## Decisión del Sistema
**{classification_label}** — {decision}

## Reglas Que Se Activaron
{rule_details}

## Cómo responde un buen analista
Un buen analista no enumera las reglas: describe el comportamiento que
combinan. Dos ejemplos del registro que se busca.

### Ejemplo A
Reglas activadas: high_amount, off_hours_crypto, merchant_blacklisted
Respuesta: El caso combina un importe alto, una franja horaria en la que la
actividad legítima es escasa y un comercio que ya consta como bloqueado.
Ninguna de las tres señales cierra el caso por separado; la combinación sí,
porque un reintento nocturno sobre un medio de pago comprometido es
exactamente el patrón que las tres reglas buscan a la vez.

### Ejemplo B
Reglas activadas: high_amount, velocity_5min
Respuesta: Dos señales que apuntan al mismo comportamiento: el importe excede
lo habitual para el segmento y el cliente ha comprimido varias operaciones en
una ventana muy corta. Eso apunta a una operación troceada para evitar el
umbral de revisión, más que a un robo directo.

## Tu Tarea
Escribe DOS párrafos en español y nada más:

1. Qué comportamiento combinado representan las reglas que se activaron,
   descrito como una conducta, sin enumerar las reglas ni sus nombres.

2. Qué debería hacer un analista a continuación.

REGLAS ESTRICTAS:
- NO repitas ninguna puntuación, umbral ni cifra. Los números ya están
  escritos por el sistema; tú solo narras.
- NO inventes datos que no estén aquí.
- NO menciones que eres un modelo de lenguaje.
- Devuelve solo los dos párrafos, sin títulos, sin listas, sin numeración."""

# A number the model emitted that never appeared in the input it was given.
_NUMERIC_TOKEN = re.compile(r"\d+(?:[.,]\d+)?")


def _numeric_fingerprints(*values: Any) -> set[str]:
    """Normalised digit-strings of every number we supplied to the model."""
    out: set[str] = set()
    for value in values:
        if value is None:
            continue
        for token in _NUMERIC_TOKEN.findall(str(value)):
            out.add(token.replace(",", ""))
    return out


def _unsourced_numbers(text: str, allowed: set[str]) -> list[str]:
    """Numbers in `text` that were never in the input (hallucinated figures)."""
    return sorted(
        {
            token.replace(",", "")
            for token in _NUMERIC_TOKEN.findall(text)
            if token.replace(",", "") not in allowed
        }
    )


class LLMService:
    """Async client wrapper for Ollama API to generate fraud analysis reports.

    Builds structured prompts in Spanish and calls Ollama's /api/generate
    endpoint with configurable timeout and retry logic.
    """

    def __init__(
        self,
        ollama_url: str | None = None,
        model: str | None = None,
        timeout: int = 60,
    ) -> None:
        """Initialize the LLM service.

        Args:
            ollama_url: Base URL for Ollama API (default from settings).
            model: Model name to use (default from settings).
            timeout: HTTP client timeout in seconds (default 15).
        """
        self._ollama_url = (ollama_url or settings.ollama_host).rstrip("/")
        self._model = model or settings.ollama_model
        self._timeout = timeout

    def build_prompt(
        self,
        score_breakdown: dict[str, Any],
        transaction: dict[str, Any],
    ) -> str:
        """Build a structured prompt for the LLM in Spanish.

        The scores stay in the prompt as magnitude context — the model reasons
        better when it knows the case is extreme — but the instruction forbids
        it from repeating them, because `generate_report` renders the
        authoritative figures itself.

        Args:
            score_breakdown: Dict with rule_score, ml_score, ensemble_score,
                fired_rules, threshold, classification.
            transaction: Dict with amount, merchant_name, currency, etc.

        Returns:
            Formatted prompt string.
        """
        fired_rules = score_breakdown.get("fired_rules", [])
        if fired_rules:
            rule_details = "\n".join(f"- {rule}" for rule in fired_rules)
        else:
            rule_details = "- Ninguna regla activada"

        # Map classification to Spanish labels and decision text
        classification = score_breakdown.get("classification", "review")
        classification_map = {
            "legitimate": "LEGÍTIMA",
            "fraud": "FRAUDE",
            "review": "REQUIERE REVISIÓN",
        }
        classification_label = classification_map.get(classification, "DESCONOCIDA")

        decision_map = {
            "legitimate": "APROBADA — la transacción se considera legítima.",
            "fraud": "BLOQUEADA — la transacción se considera fraudulenta.",
            "review": "PENDIENTE — requiere revisión manual.",
        }
        decision = decision_map.get(classification, "CLASIFICACIÓN DESCONOCIDA.")

        return _PROMPT_TEMPLATE.format(
            amount=self._format_amount(transaction.get("amount")),
            currency=transaction.get("currency") or "USD",
            merchant_name=transaction.get("merchant_name") or "desconocido",
            merchant_category=transaction.get("merchant_category") or "sin especificar",
            rule_score=score_breakdown.get("rule_score", 0),
            ml_score=score_breakdown.get("ml_score", 0),
            ensemble_score=score_breakdown.get("ensemble_score", 0),
            threshold=score_breakdown.get("threshold", 70),
            rule_details=rule_details,
            classification_label=classification_label,
            decision=decision,
        )

    @staticmethod
    def _render_report(
        score_breakdown: dict[str, Any],
        transaction: dict[str, Any],
        prose: str,
    ) -> str:
        """Compose the stored report: every figure is written from the inputs.

        The model never sees this half. Asking a small model to restate the
        score is how a report came to claim the rules contributed 0.0 to a
        transaction they had flagged; here the code owns them, so the worst a
        hallucinating model can do is produce a weak sentence.
        """
        classification = score_breakdown.get("classification", "review")
        label = {
            "legitimate": "LEGÍTIMA",
            "fraud": "FRAUDE",
            "review": "REQUIERE REVISIÓN",
        }.get(classification, "DESCONOCIDA")

        ensemble = score_breakdown.get("ensemble_score", 0)
        threshold = score_breakdown.get("threshold", 70)
        fired = score_breakdown.get("fired_rules") or []

        lines = [
            "## Resultado del sistema",
            "",
            f"**{label}** — puntaje ensemble {float(ensemble):.1f} sobre un umbral "
            f"de {float(threshold):.1f}.",
            "",
            f"- Motor de reglas (determinista): {float(score_breakdown.get('rule_score', 0)):.1f}/100",
            f"- Modelo ML (anomalía): {float(score_breakdown.get('ml_score', 0)):.1f}/100",
            f"- Reglas activadas: {', '.join(fired) if fired else 'ninguna'}",
            "",
            "## Análisis",
            "",
        ]

        analysis, recommendation = LLMService._split_prose(prose)
        lines.append(analysis or "No se generó análisis.")
        lines.extend(["", "## Recomendación", ""])
        lines.append(recommendation or analysis or "No se generó recomendación.")

        return "\n".join(lines).strip()

    @staticmethod
    def _split_prose(prose: str) -> tuple[str, str]:
        """Two paragraphs in, two slots out.

        Falls back to putting everything in the first slot: a short or
        single-paragraph answer is still a usable report, and dropping prose on
        the floor would lose it.
        """
        cleaned = re.sub(r"^\s*(?:1[\.\)]|2[\.\)])\s*", "", prose, flags=re.MULTILINE)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
        if not paragraphs:
            return "", ""
        if len(paragraphs) == 1:
            return paragraphs[0], ""
        return paragraphs[0], "\n\n".join(paragraphs[1:])

    @staticmethod
    def _format_amount(value: Any) -> str:
        """Plain two-decimal amount for the prompt.

        No thousands separator: a grouped figure like `15,000.00` is US
        formatting in a Spanish report, and it splits into two tokens for the
        hallucination guard. Human-facing formatting belongs to
        `_render_report`, not to what the model is shown.
        """
        if value is None:
            return "N/A"
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return str(value)

    async def generate_report(
        self,
        transaction_id: str,
        score_breakdown: dict[str, Any],
        transaction: dict[str, Any] | None = None,
        _client: httpx.AsyncClient | None = None,
    ) -> str:
        """Generate a fraud analysis report via Ollama.

        Calls the Ollama /api/generate endpoint with a structured prompt
        in Spanish. Raises exceptions on failure so the worker can apply
        retry/DLQ logic.

        Args:
            transaction_id: UUID of the transaction being analyzed.
            score_breakdown: Dict with scoring details.
            transaction: Optional transaction details for the prompt.
            _client: Optional injected client for testing.

        Returns:
            Report text string.

        Raises:
            httpx.ConnectError: If Ollama is unreachable.
            httpx.TimeoutException: If generation exceeds timeout.
            httpx.HTTPStatusError: If Ollama returns an error status.
            Exception: On unexpected errors.
        """
        prompt = self.build_prompt(
            score_breakdown,
            transaction or {},
        )

        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            # Ollama defaults to temperature 0.8, which is tuned for variety
            # rather than for a document an analyst reads as a description of
            # what happened. 0.3 keeps the register of the few-shot examples
            # without flattening it, and num_predict stops a 1B model from
            # rambling past the two paragraphs that were asked for.
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": 400,
            },
        }

        client = _client or httpx.AsyncClient(timeout=self._timeout)

        try:
            response = await client.post(
                f"{self._ollama_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            prose = (result.get("response") or "").strip()

            allowed = _numeric_fingerprints(
                score_breakdown.get("rule_score"),
                score_breakdown.get("ml_score"),
                score_breakdown.get("ensemble_score"),
                score_breakdown.get("threshold"),
                (transaction or {}).get("amount"),
                *(score_breakdown.get("fired_rules") or []),
            )
            hallucinated = _unsourced_numbers(prose, allowed)
            if hallucinated:
                logger.warning(
                    "LLM prose for transaction %s emitted %d figure(s) absent "
                    "from the input: %s. The rendered block below is code-owned, "
                    "so the report's figures are unaffected, but the prose is not "
                    "reliable for a 1B model.",
                    transaction_id,
                    len(hallucinated),
                    ", ".join(hallucinated),
                )

            return self._render_report(score_breakdown, transaction or {}, prose)

        except httpx.ConnectError:
            logger.error(
                "Ollama connection refused for transaction %s",
                transaction_id,
            )
            raise
        except httpx.TimeoutException:
            logger.error(
                "Ollama timeout for transaction %s (timeout=%ss)",
                transaction_id,
                self._timeout,
            )
            raise
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Ollama HTTP error for transaction %s: %s",
                transaction_id,
                exc,
            )
            raise
        except Exception:
            logger.exception(
                "Unexpected error generating LLM report for transaction %s",
                transaction_id,
            )
            raise
        finally:
            if _client is None:
                await client.aclose()
