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
    """The only policy model in Slice 1: Gemini on Vertex AI.

    This is a direct `generate_content` call against Vertex AI through the
    google-genai SDK -- deliberately NOT an ADK agent deployed to Vertex AI
    Agent Engine. See docs/CLAIMS.md for why, and for the wording the UI and
    README must use so the claim matches the code.

    The model only ever *advises*. `enforce_decision` above runs afterwards and
    can only downgrade the result to ABANDON; spending limits are never
    delegated to the model.
    """

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
            "GRAFANA_QUERY_RESULT below was read back out of Grafana Cloud; its 'source' "
            "field says whether it arrived through the Grafana MCP server ('grafana_mcp') "
            "or through the direct Prometheus fallback. Return exactly one JSON "
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


def _selfcheck() -> None:
    """Money path: the model must never be able to widen a ceiling."""
    from .models import AttemptOutcome

    def shot(max_attempts: int = 3, ceiling: str = "1.00") -> Shot:
        return Shot(
            id="sc",
            prompt="An original, safe film shot.",
            reference_image_path=None,
            expected_duration_seconds=4,
            character_ids=("mara",),
            max_attempts=max_attempts,
            budget_ceiling_usd=Decimal(ceiling),
        )

    def spent(amount: str, attempts: int = 1) -> LiveShotMetrics:
        metrics = LiveShotMetrics(shot_id="sc")
        for _ in range(attempts):
            metrics.record(AttemptOutcome.ERROR, 1.0, Decimal(amount) / attempts)
        return metrics

    retry = AgentAdvice(AdviceAction.RETRY_SAME, "Gemini wants another try.")

    # At the ceiling, under it but overshooting on the next attempt, and out of
    # attempts: all must be abandoned regardless of what the model advised.
    for metrics, next_cost, max_attempts in (
        (spent("1.00"), Decimal("0.10"), 3),
        (spent("0.95"), Decimal("0.10"), 3),
        (spent("0.10", attempts=3), Decimal("0.10"), 3),
    ):
        decision = enforce_decision(retry, shot(max_attempts), metrics, next_cost)
        assert decision.action is AdviceAction.ABANDON, decision
        assert decision.enforced_by_code is True, decision

    # With headroom the model's advice is honoured and not marked code-enforced.
    ok = enforce_decision(retry, shot(), spent("0.10"), Decimal("0.10"))
    assert ok.action is AdviceAction.RETRY_SAME and ok.enforced_by_code is False, ok

    # Exactly hitting the ceiling on the next attempt is allowed; exceeding is not.
    assert enforce_decision(retry, shot(), spent("0.90"), Decimal("0.10")).action is AdviceAction.RETRY_SAME
    assert enforce_decision(retry, shot(), spent("0.90"), Decimal("0.11")).action is AdviceAction.ABANDON

    # Malformed model output must stop the run, never fall through to a retry.
    for bad in ("", "not json", '{"action":"NOPE","rationale":"x"}', '{"action":"RETRY_SAME"}',
                '{"action":"RETRY_SAME","rationale":"  "}'):
        try:
            _parse_advice(bad)
        except CutscopeError:
            pass
        else:
            raise AssertionError(f"invalid advice accepted: {bad!r}")

    assert _parse_advice('{"action":"ABANDON","rationale":"done"}').action is AdviceAction.ABANDON
    print("decision selfcheck: ok")


if __name__ == "__main__":  # pragma: no cover
    _selfcheck()
