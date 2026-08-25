from __future__ import annotations

import json
import asyncio
import os
import uuid
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
    return Decision(model_advice.action, model_advice.rationale, replacement_prompt=model_advice.replacement_prompt)


class GeminiDecisionAgent:
    """ADK decision agent on Agent Engine, with an explicit direct-Vertex fallback.

    ``GeminiDecisionAgent`` keeps its original public name so existing callers
    remain compatible.  Its primary implementation is the deployed ADK
    ``LlmAgent`` in :mod:`cutscope.adk_decision_agent`; the direct
    ``google-genai`` call exists only for a visible availability fallback.
    """

    def __init__(
        self,
        client: Any,
        model: str,
        telemetry: Any,
        *,
        project_id: str | None = None,
        region: str | None = None,
        agent_engine_id: str | None = None,
        production_budget_ceiling_usd: Decimal | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._telemetry = telemetry
        self._project_id = project_id or os.environ.get("GCP_PROJECT_ID", "").strip()
        self._region = region or os.environ.get("GCP_REGION", "us-central1").strip()
        self._agent_engine_id = agent_engine_id or os.environ.get("CUTSCOPE_AGENT_ENGINE_ID", "").strip()
        self._production_budget_ceiling_usd = production_budget_ceiling_usd or Decimal(
            os.environ.get("CUTSCOPE_PRODUCTION_BUDGET_USD", "15.00")
        )
        self.last_execution: dict[str, object] = {}

    def advise(
        self,
        shot: Shot,
        live_metrics: LiveShotMetrics,
        next_attempt_estimated_usd: Decimal,
        grafana_metrics: dict[str, object] | None = None,
        *,
        production_spend_usd: Decimal = Decimal("0"),
        attempt_prompts: list[str] | None = None,
    ) -> AgentAdvice:
        context = _adk_context(
            shot,
            live_metrics,
            next_attempt_estimated_usd,
            production_spend_usd,
            attempt_prompts or [],
            self._production_budget_ceiling_usd,
        )
        if self._agent_engine_id:
            try:
                advice = _run_async(self._advise_via_agent_engine(context))
                self.last_execution = {
                    "mode": "agent_engine",
                    "resource_name": self._agent_engine_id,
                }
                return advice
            except Exception as exc:
                # The fallback is deliberately recorded for the caller/UI.  It
                # must be safe to demo through an Agent Engine outage without
                # pretending the deployed resource answered.
                fallback_reason = _short_error(exc)
        else:
            fallback_reason = "CUTSCOPE_AGENT_ENGINE_ID is unset"
        advice = self._advise_direct(shot, live_metrics, next_attempt_estimated_usd, grafana_metrics)
        self.last_execution = {
            "mode": "direct_vertex_fallback",
            "agent_engine_resource_name": self._agent_engine_id or None,
            "fallback_reason": fallback_reason,
        }
        return advice

    async def _advise_via_agent_engine(self, context: dict[str, object]) -> AgentAdvice:
        from vertexai import agent_engines

        remote_app = agent_engines.get(self._agent_engine_id)
        user_id = "cutscope-controller"
        session = await remote_app.async_create_session(
            user_id=user_id,
            state={"cutscope_decision": context},
        )
        text_parts: list[str] = []
        try:
            async for event in remote_app.async_stream_query(
                user_id=user_id,
                session_id=session.id,
                message=(
                    "Evaluate the current failed shot. Call every required tool, then return the required JSON decision."
                ),
            ):
                text_parts.extend(_event_text(event))
        finally:
            try:
                await remote_app.async_delete_session(user_id=user_id, session_id=session.id)
            except Exception:
                pass
        return _parse_advice("\n".join(text_parts))

    def _advise_direct(
        self,
        shot: Shot,
        live_metrics: LiveShotMetrics,
        next_attempt_estimated_usd: Decimal,
        grafana_metrics: dict[str, object] | None,
    ) -> AgentAdvice:
        metric_snapshot = live_metrics.for_agent(next_attempt_estimated_usd)
        prompt = (
            "You are CUTSCOPE's emergency production-control fallback. Decide only whether a failed "
            "Veo shot should retry unchanged, retry with a clarified prompt, or stop. "
            "GRAFANA_QUERY_RESULT below was read back out of Grafana Cloud; its 'source' "
            "field says whether it arrived through the Grafana MCP server ('grafana_mcp') "
            "or through the direct Prometheus fallback. Return exactly one JSON "
            "object with keys action, rationale, and replacement_prompt. action must be RETRY_SAME, "
            "RETRY_REPHRASED, or ABANDON. Do not recommend a retry after a safety refusal "
            "unless the prompt can be safely clarified. replacement_prompt must be a complete "
            "replacement only for RETRY_REPHRASED, otherwise null.\n\n"
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


def _adk_context(
    shot: Shot,
    metrics: LiveShotMetrics,
    next_attempt_estimated_usd: Decimal,
    production_spend_usd: Decimal,
    attempt_prompts: list[str],
    production_budget_ceiling_usd: Decimal,
) -> dict[str, object]:
    attempts = []
    for index, outcome in enumerate(metrics.outcomes):
        attempts.append(
            {
                "attempt": index + 1,
                "prompt": attempt_prompts[index] if index < len(attempt_prompts) else shot.prompt,
                "outcome": outcome.value,
                "latency_seconds": metrics.latencies_seconds[index],
                "estimated_cost_usd": float(metrics.estimated_cost_usd / metrics.attempt_count)
                if metrics.attempt_count
                else 0.0,
            }
        )
    return {
        "shot": _shot_for_agent(shot),
        "metrics": {"attempts": attempts},
        "next_attempt_estimated_usd": float(next_attempt_estimated_usd),
        "production_budget_ceiling_usd": float(production_budget_ceiling_usd),
        "production_spend_usd": float(production_spend_usd),
    }


def _parse_advice(text: str | None) -> AgentAdvice:
    try:
        data = json.loads((text or "").strip())
        action = AdviceAction(data["action"])
        rationale = data["rationale"]
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("rationale must be a non-empty string")
        replacement_prompt = data.get("replacement_prompt")
        if action is AdviceAction.RETRY_REPHRASED:
            if not isinstance(replacement_prompt, str) or not replacement_prompt.strip():
                raise ValueError("RETRY_REPHRASED needs a non-empty replacement_prompt")
            replacement_prompt = replacement_prompt.strip()
        elif replacement_prompt is not None:
            raise ValueError("replacement_prompt must be null unless action is RETRY_REPHRASED")
        return AgentAdvice(action, rationale.strip(), replacement_prompt)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        raise CutscopeError("Gemini returned an invalid retry decision; automatic retry is stopped.") from exc


def _short_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    return message[:400] or type(exc).__name__


def _looks_like_missing_adc(exc: Exception) -> bool:
    message = str(exc).lower()
    return "default credentials" in message or "application default credentials" in message


def _run_async(coroutine: Any) -> Any:
    """Run the Agent Engine async client from the synchronous controller."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    # The current production controller is synchronous.  This protects future
    # ASGI callers without nesting an event loop in the worker thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coroutine)).result()


def _event_text(event: object) -> list[str]:
    """Extract model text from the dict events returned by AdkApp."""
    if not isinstance(event, dict):
        return []
    content = event.get("content")
    if not isinstance(content, dict):
        return []
    parts = content.get("parts")
    if not isinstance(parts, list):
        return []
    return [str(part["text"]) for part in parts if isinstance(part, dict) and part.get("text")]


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
