from __future__ import annotations

import time
from decimal import Decimal
from typing import Iterable

from .decision import GeminiDecisionAgent, enforce_decision
from .errors import VertexCredentialsUnavailable
from .models import AdviceAction, AgentAdvice, AttemptOutcome, AttemptResult, LiveShotMetrics, Shot, ShotRunResult
from .provider import VeoCostEstimator, VideoProvider
from .telemetry import GrafanaTelemetry


class SliceOneOrchestrator:
    def __init__(
        self,
        provider: VideoProvider,
        decision_agent: GeminiDecisionAgent,
        telemetry: GrafanaTelemetry,
        cost_estimator: VeoCostEstimator,
    ) -> None:
        self._provider = provider
        self._decision_agent = decision_agent
        self._telemetry = telemetry
        self._cost_estimator = cost_estimator

    def run_all(self, shots: Iterable[Shot]) -> list[ShotRunResult]:
        return [self.run_shot(shot) for shot in shots]

    def run_shot(self, shot: Shot) -> ShotRunResult:
        estimated_attempt_cost = Decimal(str(self._cost_estimator.estimate(shot.expected_duration_seconds)))
        metrics = LiveShotMetrics(shot_id=shot.id)
        prompt = shot.prompt

        while metrics.attempt_count < shot.max_attempts:
            if metrics.estimated_cost_usd + estimated_attempt_cost > shot.budget_ceiling_usd:
                return _abandoned_result(
                    shot,
                    metrics,
                    "The next estimated generation would exceed the budget ceiling; no submission made.",
                )

            attempt_number = metrics.attempt_count + 1
            telemetry_record = self._telemetry.begin_attempt(
                shot_id=shot.id,
                attempt_number=attempt_number,
                provider=self._provider.name,
                model=self._provider.model,
                estimated_cost_usd=estimated_attempt_cost,
            )
            generation_started = time.monotonic()
            try:
                result, latency_seconds = self._generate_one(shot, prompt)
            except VertexCredentialsUnavailable:
                # A credential failure is still a completed attempted call from the
                # controller's point of view, so Grafana receives its terminal error.
                self._telemetry.finish_attempt(
                    telemetry_record,
                    AttemptOutcome.ERROR,
                    time.monotonic() - generation_started,
                )
                raise
            self._telemetry.finish_attempt(telemetry_record, result.outcome, latency_seconds)
            metrics.record(result.outcome, latency_seconds, estimated_attempt_cost)

            if result.outcome is AttemptOutcome.SUCCESS:
                return ShotRunResult(
                    shot_id=shot.id,
                    status="success",
                    attempts=metrics.attempt_count,
                    estimated_cost_usd=metrics.estimated_cost_usd,
                    decision="SUCCESS",
                    rationale="Veo returned a generated video.",
                    asset_uri=result.asset_uri,
                )

            if metrics.attempt_count >= shot.max_attempts:
                return _abandoned_result(shot, metrics, "Maximum attempts reached; no retry made.")

            # Gemini receives exactly the metrics just force-flushed to Grafana.
            advice = self._decision_agent.advise(shot, metrics, estimated_attempt_cost)
            decision = enforce_decision(advice, shot, metrics, estimated_attempt_cost)
            if decision.action is AdviceAction.ABANDON:
                return _abandoned_result(shot, metrics, decision.rationale)
            if decision.action is AdviceAction.RETRY_REPHRASED:
                prompt = _rephrase_for_retry(shot.prompt, shot.character_ids)

        return _abandoned_result(shot, metrics, "Maximum attempts reached; no retry made.")

    def _generate_one(self, shot: Shot, prompt: str) -> tuple[AttemptResult, float]:
        started = time.monotonic()
        operation_name: str | None = None
        try:
            submission = self._provider.submit(shot, prompt)
            operation_name = submission.operation_name
            result = self._provider.poll(submission)
        except Exception as exc:
            if _looks_like_missing_adc(exc):
                raise VertexCredentialsUnavailable(
                    "Vertex AI credentials are unavailable. Configure Application Default Credentials "
                    "with 'gcloud auth application-default login' or set GOOGLE_APPLICATION_CREDENTIALS."
                ) from exc
            result = AttemptResult(
                outcome=_outcome_from_exception(exc),
                operation_name=operation_name,
                reason=_short_error(exc),
            )
        return result, time.monotonic() - started


def _abandoned_result(shot: Shot, metrics: LiveShotMetrics, rationale: str) -> ShotRunResult:
    return ShotRunResult(
        shot_id=shot.id,
        status="abandoned",
        attempts=metrics.attempt_count,
        estimated_cost_usd=metrics.estimated_cost_usd,
        decision=AdviceAction.ABANDON.value,
        rationale=rationale,
    )


def _rephrase_for_retry(original_prompt: str, character_ids: tuple[str, ...]) -> str:
    characters = ", ".join(character_ids)
    return (
        f"{original_prompt}\n\n"
        f"Clarified retry: preserve the established identity and visual continuity of {characters}; "
        "make one clear camera action, avoid conflicting details, and keep the scene physically coherent."
    )


def _outcome_from_exception(exc: Exception) -> AttemptOutcome:
    message = str(exc).lower()
    if any(marker in message for marker in ("safety", "filtered", "blocked", "policy violation", "prohibited")):
        return AttemptOutcome.REFUSED
    return AttemptOutcome.ERROR


def _short_error(exc: Exception) -> str:
    return (str(exc).replace("\n", " ").strip() or type(exc).__name__)[:400]


def _looks_like_missing_adc(exc: Exception) -> bool:
    message = str(exc).lower()
    return "default credentials" in message or "application default credentials" in message
