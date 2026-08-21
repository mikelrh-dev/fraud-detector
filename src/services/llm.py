"""LLM service — async Ollama client wrapper for fraud report generation.

Generates explanatory fraud analysis reports in Spanish using a local
Ollama model. The prompt is structured to ask for: risk justification,
technical recommendation, and contextual factors. The LLM provides
analysis only — it does NOT make fraud determinations.
"""

import logging
from typing import Any

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """Eres un analista técnico de sistemas de detección. Analiza los siguientes datos de una transacción y genera un informe explicativo en español.

## Datos de la Transacción
- Monto: ${amount} {currency}
- Comercio: {merchant_name}
- ID de Transacción: {transaction_id}

## Análisis de Puntajes
- Motor de Reglas (determinista): {rule_score:.1f}/100
- Modelo ML (anomalía): {ml_score:.1f}/100
- Puntaje Ensemble (combinado): {ensemble_score:.1f}/100
- Umbral de decisión: {threshold:.1f}/100

## Resultado del Sistema
El sistema clasificó esta transacción como: **{classification_label}**
(Score {ensemble_score:.1f} comparado con umbral {threshold:.1f})

## Reglas Que Se Activaron
{rule_details}

## Instrucciones
Basándote en los datos anteriores, genera un informe con las siguientes secciones:

1. **Análisis de Puntajes**: Explica qué puntajes contribuyeron al resultado final. Menciona si fue más por reglas deterministas, anomalías del ML, o una combinación.

2. **Explicación de la Decisión**: Describe por qué el sistema llegó a la conclusión de **{classification_label}** basándote en los números mostrados.

3. **Factores Contextuales**: Menciona factores que podrían influir en la interpretación (hora del día, tipo de comercio, patrón de transacciones, etc.).

Nota: Tu análisis es explicativo. El motor de reglas y ML ya han tomado la decisión de clasificar esto como **{classification_label}**."""


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
            "legitimate": "APROBADA - Transacción legítima",
            "fraud": "BLOQUEADA - Transacción fraudulenta",
            "review": "PENDIENTE - Requiere revisión manual",
        }
        decision = decision_map.get(classification, "DESCONOCIDA")

        return _PROMPT_TEMPLATE.format(
            amount=transaction.get("amount", "N/A"),
            currency=transaction.get("currency", "USD"),
            merchant_name=transaction.get("merchant_name", "N/A"),
            transaction_id=transaction.get("id", "N/A"),
            rule_score=score_breakdown.get("rule_score", 0),
            ml_score=score_breakdown.get("ml_score", 0),
            ensemble_score=score_breakdown.get("ensemble_score", 0),
            threshold=score_breakdown.get("threshold", 70),
            rule_details=rule_details,
            classification_label=classification_label,
            decision=decision,
        )

    async def generate_report(
        self,
        transaction_id: str,
        score_breakdown: dict[str, Any],
        transaction: dict[str, Any] | None = None,
        _client: httpx.AsyncClient | None = None,
    ) -> str:
        """Generate a fraud analysis report via Ollama.

        Calls the Ollama /api/generate endpoint with a structured prompt
        in Spanish. Handles connection errors and timeouts gracefully.

        Args:
            transaction_id: UUID of the transaction being analyzed.
            score_breakdown: Dict with scoring details.
            transaction: Optional transaction details for the prompt.
            _client: Optional injected client for testing.

        Returns:
            Report text string, or error message if generation fails.
        """
        prompt = self.build_prompt(
            score_breakdown,
            transaction or {},
        )

        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }

        client = _client or httpx.AsyncClient(timeout=self._timeout)

        try:
            response = await client.post(
                f"{self._ollama_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "No se generó contenido.")

        except httpx.ConnectError:
            logger.error(
                "Ollama connection refused for transaction %s",
                transaction_id,
            )
            return (
                "Error: No se pudo conectar con el servicio Ollama. "
                "Verifique que el servicio esté disponible."
            )
        except httpx.TimeoutException:
            logger.error(
                "Ollama timeout for transaction %s (timeout=%ss)",
                transaction_id,
                self._timeout,
            )
            return (
                f"Error: La generación del reporte excedió el tiempo "
                f"máximo de {self._timeout} segundos."
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Ollama HTTP error for transaction %s: %s",
                transaction_id,
                exc,
            )
            return (
                f"Error: El servicio Ollama respondió con código "
                f"{exc.response.status_code}."
            )
        except Exception as exc:
            logger.exception(
                "Unexpected error generating LLM report for transaction %s",
                transaction_id,
            )
            return f"Error inesperado al generar el reporte: {exc}"
        finally:
            if _client is None:
                await client.aclose()
