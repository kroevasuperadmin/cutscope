from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from .errors import CutscopeError, VertexCredentialsUnavailable
from .models import AdviceAction, AgentAdvice, Decision, LiveShotMetrics, Shot


def enforce_decision(
    model_advice: AgentAdvice,
    shot: Shot,
    live_metrics: LiveShotMetrics,
    next_attempt_estimated_usd: Decimal,
) -> Decision:
    """Apply non-negotiable production controls after Gemini has advised."""
    if live_metrics.estimated_cost_usd >= shot.budget_ceiling_usd:
        return Decision(
            AdviceAction.ABANDON,
            "Budget ceiling reached; CUTSCOPE will not submit another generation.",
            enforced_by_code=True,
        )
    if live_metrics.estimated_cost_usd + next_attempt_estimated_usd > shot.budget_ceiling_usd:
        return Decision(
            AdviceAction.ABANDON,
            "The next estimated generation would exceed the budget ceiling.",
            enforced_by_code=True,
        )
    if live_metrics.attempt_count >= shot.max_attempts:
        return Decision(
            AdviceAction.ABANDON,
            "Maximum attempts reached; CUTSCOPE will not submit another generation.",
            enforced_by_code=True,
        )
    return Decision(model_advice.action, model_advice.rationale)


class GeminiDecisionAgent:
    """The only policy model in Slice 1: Gemini on Vertex AI."""

    def __init__(self, client: Any, model: str, telemetry: Any) -> None:
        self._client = client
        self._model = model
        self._telemetry = telemetry

    def advise(
        self,
        shot: Shot,
        live_metrics: LiveShotMetrics,
        next_attempt_estimated_usd: Decimal,
        grafana_metrics: dict[str, object] | None = None,
    ) -> AgentAdvice:
        metric_snapshot = live_metrics.for_agent(next_attempt_estimated_usd)
        prompt = (
            "You are CUTSCOPE's production-control agent. Decide only whether a failed "
            "Veo shot should retry unchanged, retry with a clarified prompt, or stop. "
            "You receive live metrics already emitted to Grafana. Return exactly one JSON "
            "object with keys action and rationale. action must be RETRY_SAME, "
            "RETRY_REPHRASED, or ABANDON. Do not recommend a retry after a safety refusal "
            "unless the prompt can be safely clarified.\n\n"
            f"SHOT\n{json.dumps(_shot_for_agent(shot), sort_keys=True)}\n\n"
            f"LIVE_CONTROLLER_METRICS\n{json.dumps(metric_snapshot, sort_keys=True)}\n\n"
            "GRAFANA_QUERY_RESULT\n"
            f"{json.dumps(grafana_metrics or {'source': 'not_queried'}, sort_keys=True)}"
        )
        with self._telemetry.gemini_span(shot.id, self._model):
            try:
                from google.genai import types

                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
            except Exception as exc:  # The CLI turns provider/API detail into a clear result.
                if _looks_like_missing_adc(exc):
                    raise VertexCredentialsUnavailable(
                        "Vertex AI credentials are unavailable. Configure Application Default Credentials "
                        "with 'gcloud auth application-default login' or set GOOGLE_APPLICATION_CREDENTIALS."
                    ) from exc
                raise CutscopeError(f"Gemini decision call failed: {_short_error(exc)}") from exc
        return _parse_advice(getattr(response, "text", ""))


def _shot_for_agent(shot: Shot) -> dict[str, object]:
    return {
        "id": shot.id,
        "prompt": shot.prompt,
        "expected_duration_seconds": shot.expected_duration_seconds,
        "character_ids": list(shot.character_ids),
        "max_attempts": shot.max_attempts,
        "budget_ceiling_usd": float(shot.budget_ceiling_usd),
    }


def _parse_advice(text: str | None) -> AgentAdvice:
    try:
        data = json.loads((text or "").strip())
        action = AdviceAction(data["action"])
        rationale = data["rationale"]
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("rationale must be a non-empty string")
        return AgentAdvice(action, rationale.strip())
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        raise CutscopeError("Gemini returned an invalid retry decision; automatic retry is stopped.") from exc


def _short_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    return message[:400] or type(exc).__name__


def _looks_like_missing_adc(exc: Exception) -> bool:
    message = str(exc).lower()
    return "default credentials" in message or "application default credentials" in message
