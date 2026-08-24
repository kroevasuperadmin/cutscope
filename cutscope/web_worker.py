"""Streaming adapter for the CUTSCOPE web console.

This module is deliberately thin: live runs instantiate the existing SliceOneOrchestrator,
VeoVertexProvider, GrafanaTelemetry, and GeminiDecisionAgent. It only translates their
events to JSON Lines for the Next.js server. Practice mode never imports or calls Google
or Grafana SDKs/APIs.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .config import RuntimeConfig
from .errors import CutscopeError
from .grafana_query import GrafanaMimirClient, GrafanaMimirConfig
from .models import ShotRunResult
from .shotfile import load_shots


def _request_stop(_: int, __: Any) -> None:
    # The Next.js controller has already emitted the visible stopped state. Raising here
    # interrupts polling or a network wait so the worker cannot submit another attempt.
    raise InterruptedError


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def emit(event_type: str, **data: object) -> None:
    print(
        json.dumps({"type": event_type, "timestamp": _now(), "data": data}, default=_json_default),
        flush=True,
    )


def _sleep(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(min(0.1, deadline - time.monotonic()))


def _decision(headline: str, metric: str, decision: str, tone: str = "neutral") -> None:
    emit("decision.log", headline=headline, metric=metric, decision=decision, tone=tone)


def _practice_run(run_id: str) -> int:
    """Replay the Turning Point control loop without paid services."""
    return _turning_point_practice_run(run_id)


def _turning_point_practice_run(run_id: str) -> int:
    """Replay the five real Turning Point shots using their source prompts."""
    del run_id
    shots = load_shots(Path.cwd() / "shots" / "turning_point.yaml")
    expected_ids = [
        "warehouse-displacement",
        "first-sighting-2012",
        "arcade-coaching",
        "the-field-2012",
        "the-field-2000",
    ]
    if [shot.id for shot in shots] != expected_ids:
        raise ValueError("turning_point.yaml must retain the five-shot practice playback order.")

    shot_by_id = {shot.id: shot for shot in shots}
    prompts = {shot.id: shot.prompt for shot in shots}
    labels = {
        shot.id: f"SHOT {index:02d} Â· {shot.id.replace('-', ' ').upper()}"
        for index, shot in enumerate(shots, 1)
    }
    spent = 0.0
    metric_state = {
        shot.id: {"cost": 0.0, "retries": 0, "refusals": 0, "latency": None} for shot in shots
    }

    def update_metrics(shot_id: str, cost: float, retries: int, refusals: int, latency: float) -> None:
        nonlocal spent
        previous_cost = float(metric_state[shot_id]["cost"])
        spent += cost - previous_cost
        metric_state[shot_id] = {"cost": cost, "retries": retries, "refusals": refusals, "latency": latency}
        emit(
            "metrics.updated",
            shot_id=shot_id,
            cost=cost,
            retries=retries,
            refusals=refusals,
            latency_seconds=latency,
            spent=spent,
        )

    def update_shot(shot_id: str, state: str, attempt: int, cost: float, prompt: str | None = None) -> None:
        shot = shot_by_id[shot_id]
        emit(
            "shot.updated",
            shot_id=shot_id,
            state=state,
            attempt=attempt,
            max_attempts=shot.max_attempts,
            cost=cost,
            prompt=prompt or prompts[shot_id],
        )

    def keep_take(shot_id: str, prompt: str | None = None) -> None:
        emit(
            "take.updated",
            shot_id=shot_id,
            label=labels[shot_id],
            prompt=prompt or prompts[shot_id],
            media_url="/practice-take.mp4",
            is_practice=True,
        )

    emit("run.started", production_name="TURNING POINT // S1 Â· SHOT TEST", budget=15.0, mode="practice")
    _decision(
        "PRACTICE PRODUCTION ARMED",
        "Grafana: scripted telemetry stream online; project budget $0.00 / $15.00",
        "DECISION: BEGIN â€” replay the Turning Point control loop without paid APIs",
        "info",
    )

    shot_id = "warehouse-displacement"
    update_shot(shot_id, "generating", 1, 0.0)
    _decision(
        f"{labels[shot_id]} ATTEMPT 1 SUBMITTED",
        "Grafana: shot spend $0.00 / $3.00; refusals 0; run budget $0.00 / $15.00",
        "DECISION: GENERATE â€” first take is within the code-enforced ceiling",
        "info",
    )
    _sleep(0.35)
    update_metrics(shot_id, 1.50, 0, 1, 3.2)
    update_shot(shot_id, "refused", 1, 1.50)
    _decision(
        f"{labels[shot_id]} ATTEMPT 1 REFUSED (SAFETY FILTER)",
        'Grafana: refusal rate 100%; attempt cost $1.50; trigger phrase "pneumatic liquid strikes his chest"',
        "DECISION: REPHRASE â€” preserve the displacement while removing weapon-like language",
        "danger",
    )
    warehouse_rephrased = (
        "2024, dim industrial warehouse lit by scattered LEDs. A man in his late twenties wearing "
        "a matte cybernetic half-mask stands still as a glowing displacement device releases a "
        "controlled energy pulse at his chest. His body begins dissolving into white light from the "
        "point of contact outward. Handheld, cinematic 16:9, cold blue-grey grade."
    )
    update_shot(shot_id, "retrying", 2, 1.50, warehouse_rephrased)
    _decision(
        f"{labels[shot_id]} ATTEMPT 2 READY",
        "Grafana: one refusal; shot spend $1.50 / $3.00; remaining shot allowance $1.50",
        "DECISION: RETRY REPHRASED â€” submit the softened device-and-energy description",
        "warning",
    )
    _sleep(0.35)
    update_metrics(shot_id, 3.00, 1, 1, 14.4)
    update_shot(shot_id, "done", 2, 3.00, warehouse_rephrased)
    keep_take(shot_id, warehouse_rephrased)
    _decision(
        f"{labels[shot_id]} ATTEMPT 2 DONE",
        "Grafana: refusal rate 50%; retry latency 14.4s; total shot cost $3.00",
        "DECISION: KEEP TAKE â€” the softened prompt recovered the displacement shot",
        "success",
    )

    shot_id = "first-sighting-2012"
    update_shot(shot_id, "generating", 1, 0.0)
    _decision(
        f"{labels[shot_id]} ATTEMPT 1 SUBMITTED",
        "Grafana: shot spend $0.00 / $3.00; refusals 0; run spend $3.00 / $15.00",
        "DECISION: GENERATE â€” test the same person at ages 26 and 14",
        "info",
    )
    _sleep(0.35)
    update_metrics(shot_id, 2.10, 0, 0, 11.8)
    update_shot(shot_id, "done", 1, 2.10)
    keep_take(shot_id)
    _decision(
        f"{labels[shot_id]} ATTEMPT 1 DONE",
        "Grafana: latency 11.8s; refusal rate 0%; shot cost $2.10",
        "DECISION: KEEP TAKE â€” the first sighting is usable and cheap",
        "success",
    )

    shot_id = "arcade-coaching"
    update_shot(shot_id, "generating", 1, 0.0)
    _decision(
        f"{labels[shot_id]} ATTEMPT 1 SUBMITTED",
        "Grafana: shot spend $0.00 / $3.00; same-identity risk high; run spend $5.10 / $15.00",
        "DECISION: GENERATE â€” evaluate both ages of the same person in one frame",
        "info",
    )
    _sleep(0.35)
    update_metrics(shot_id, 2.80, 0, 0, 16.6)
    update_shot(shot_id, "done", 1, 2.80)
    keep_take(shot_id)
    _decision(
        f"{labels[shot_id]} ATTEMPT 1 DONE â€” CHARACTER DRIFT FLAGGED",
        "Grafana: latency 16.6s; shot cost $2.80; identity consistency 78% against 85% target",
        "DECISION: KEEP TAKE â€” log the age-to-age character drift; it is usable and a retry is not worth the budget",
        "warning",
    )

    shot_id = "the-field-2012"
    update_shot(shot_id, "generating", 1, 0.0)
    _decision(
        f"{labels[shot_id]} ATTEMPT 1 SUBMITTED",
        "Grafana: shot spend $0.00 / $2.50; run spend $7.90 / $15.00; location anchor missing",
        "DECISION: GENERATE â€” establish the geography that the 2000 shot must match",
        "info",
    )
    _sleep(0.35)
    update_metrics(shot_id, 2.20, 0, 0, 9.7)
    update_shot(shot_id, "done", 1, 2.20)
    keep_take(shot_id)
    _decision(
        f"{labels[shot_id]} ATTEMPT 1 DONE â€” REFERENCE ANCHOR SET",
        "Grafana: latency 9.7s; refusal rate 0%; shot cost $2.20; location anchor captured",
        "DECISION: KEEP TAKE â€” use this field, tree line, footpath, and framing as shot 5's reference",
        "success",
    )

    shot_id = "the-field-2000"
    update_shot(shot_id, "generating", 1, 0.0)
    _decision(
        f"{labels[shot_id]} ATTEMPT 1 SUBMITTED",
        "Grafana: shot spend $0.00 / $2.50; run spend $10.10 / $15.00; location-continuity target 90%",
        "DECISION: GENERATE â€” match the 2012 anchor while removing the later playground",
        "info",
    )
    _sleep(0.35)
    update_metrics(shot_id, 1.20, 0, 0, 15.1)
    _decision(
        f"{labels[shot_id]} ATTEMPT 1 FAILED CONTINUITY",
        "Grafana: location match 42% vs 90% target; shot cost $1.20 / $2.50; retry estimate $1.20",
        "DECISION: REPHRASE â€” explicitly bind the tree line, footpath, camera position, and 2012 reference",
        "danger",
    )
    field_rephrased = (
        "The year 2000, match the exact tree line, curving footpath, camera position, and framing "
        "established in the 2012 field reference. The field is bare and undeveloped: no playground, "
        "sparser vegetation, fewer and older houses. Same late-afternoon light, slightly cooler faded "
        "grade, cinematic 16:9."
    )
    update_shot(shot_id, "retrying", 2, 1.20, field_rephrased)
    _decision(
        f"{labels[shot_id]} ATTEMPT 2 READY",
        "Grafana: one continuity failure; remaining shot allowance $1.30; run budget $11.30 / $15.00",
        "DECISION: RETRY REPHRASED â€” spend one constrained attempt on the anchored geography",
        "warning",
    )
    _sleep(0.35)
    update_metrics(shot_id, 2.40, 1, 0, 17.3)
    update_shot(shot_id, "abandoned", 2, 2.40, field_rephrased)
    _decision(
        f"{labels[shot_id]} ATTEMPT 2 STILL DRIFTS â€” ABANDONED",
        "Grafana: location match 58% vs 90% target; shot cost $2.40 / $2.50; run spend $12.50 / $15.00; next estimate $1.20",
        "DECISION: ABANDON â€” another attempt would breach the shot ceiling for a still-unusable continuity result",
        "warning",
    )
    emit("run.finished", status="finished", spent=spent)
    return 0


def _live_run(run_id: str) -> int:
    """Run the existing production engine and translate its observer events for the console."""
    from google import genai

    from .decision import GeminiDecisionAgent
    from .orchestrator import SliceOneOrchestrator
    from .provider import VeoCostEstimator, VeoVertexProvider
    from .telemetry import GrafanaTelemetry

    config = RuntimeConfig.from_environment()
    grafana_reader = GrafanaMimirClient(GrafanaMimirConfig.from_environment())
    shots = load_shots(Path.cwd() / "shots" / "turning_point.yaml")
    labels = {shot.id: f"SHOT {index:02d} Â· {shot.id.replace('-', ' ').upper()}" for index, shot in enumerate(shots, 1)}
    stats: dict[str, dict[str, float | int | None]] = {
        shot.id: {"cost": 0.0, "retries": 0, "refusals": 0, "latency": None} for shot in shots
    }
    spent = 0.0

    def report(event_type: str, data: dict[str, Any]) -> None:
        nonlocal spent
        shot_id = str(data["shot_id"])
        if event_type == "attempt.started":
            attempt = int(data["attempt"])
            cost = float(stats[shot_id]["cost"] or 0.0)
            emit(
                "shot.updated",
                shot_id=shot_id,
                state="retrying" if attempt > 1 else "generating",
                attempt=attempt,
                max_attempts=int(data["max_attempts"]),
                cost=cost,
                prompt=str(data["prompt"]),
            )
            _decision(
                f"{labels[shot_id]} ATTEMPT {attempt} SUBMITTED",
                f"Grafana: controller telemetry force-flushed; current shot cost ${cost:.2f}",
                "DECISION: GENERATE â€” the deterministic budget guard permitted this attempt",
                "info",
            )
        elif event_type == "attempt.completed":
            outcome = str(data["outcome"])
            total_cost = float(data["estimated_cost_usd"])
            old_cost = float(stats[shot_id]["cost"] or 0.0)
            spent += total_cost - old_cost
            stats[shot_id]["cost"] = total_cost
            stats[shot_id]["retries"] = max(int(data["attempt"]) - 1, 0)
            stats[shot_id]["refusals"] = int(stats[shot_id]["refusals"] or 0) + (1 if outcome == "refused" else 0)
            stats[shot_id]["latency"] = float(data["latency_seconds"])
            emit(
                "metrics.updated",
                shot_id=shot_id,
                cost=total_cost,
                retries=stats[shot_id]["retries"],
                refusals=stats[shot_id]["refusals"],
                latency_seconds=stats[shot_id]["latency"],
                spent=spent,
            )
            if outcome == "refused":
                emit(
                    "shot.updated",
                    shot_id=shot_id,
                    state="refused",
                    attempt=int(data["attempt"]),
                    max_attempts=next(shot.max_attempts for shot in shots if shot.id == shot_id),
                    cost=total_cost,
                    prompt="",
                )
            if outcome == "success" and data.get("asset_uri"):
                emit(
                    "take.updated",
                    shot_id=shot_id,
                    label=labels[shot_id],
                    prompt=next(shot.prompt for shot in shots if shot.id == shot_id),
                    media_url=f"/api/runs/{run_id}/media",
                    asset_uri=data["asset_uri"],
                    is_practice=False,
                )
        elif event_type == "grafana.read":
            metrics = data["metrics"]
            assert isinstance(metrics, dict)
            _decision(
                f"{labels[shot_id]} GRAFANA WINDOW READ",
                "Grafana: "
                f"refusal rate {float(metrics['refusal_rate']) * 100:.0f}%; "
                f"cost ${float(metrics['estimated_cost_usd']):.2f}; "
                f"p95 latency {float(metrics['p95_latency_seconds'] or 0):.1f}s",
                "DECISION: ASK GEMINI â€” evaluate this real Mimir evidence before retrying",
                "info",
            )
        elif event_type == "decision.made":
            action = str(data["action"])
            metrics = data.get("grafana_metrics") or {}
            metric = "Grafana: verified query result supplied to Gemini"
            if isinstance(metrics, dict):
                metric = (
                    "Grafana: "
                    f"refusal rate {float(metrics.get('refusal_rate', 0)) * 100:.0f}%; "
                    f"shot cost ${float(metrics.get('estimated_cost_usd', 0)):.2f}"
                )
            _decision(
                f"{labels[shot_id]} {action}",
                metric,
                f"DECISION: {action.replace('_', ' ')} â€” {str(data['rationale'])}",
                "warning" if action == "ABANDON" else "success" if action.startswith("RETRY") else "neutral",
            )

    telemetry: Any = None
    try:
        emit("run.started", production_name="TURNING POINT // S1 Â· SHOT TEST", budget=15.0, mode="live")
        vertex_client = genai.Client(vertexai=True, project=config.gcp_project_id, location=config.gcp_region)
        telemetry = GrafanaTelemetry(config)
        orchestrator = SliceOneOrchestrator(
            provider=VeoVertexProvider(vertex_client, config),
            decision_agent=GeminiDecisionAgent(vertex_client, config.gemini_model, telemetry),
            telemetry=telemetry,
            cost_estimator=VeoCostEstimator(config.veo_model),
            event_sink=report,
            grafana_metrics_reader=grafana_reader,
        )
        results = orchestrator.run_all(shots)
        for result in results:
            _finish_live_shot(result, labels, shots, stats)
        emit("run.finished", status="finished", spent=spent)
        return 0
    finally:
        if telemetry is not None:
            telemetry.shutdown()


def _finish_live_shot(
    result: ShotRunResult,
    labels: dict[str, str],
    shots: list[Any],
    stats: dict[str, dict[str, float | int | None]],
) -> None:
    prompt = next(shot.prompt for shot in shots if shot.id == result.shot_id)
    emit(
        "shot.updated",
        shot_id=result.shot_id,
        state="done" if result.status == "success" else "abandoned",
        attempt=result.attempts,
        max_attempts=next(shot.max_attempts for shot in shots if shot.id == result.shot_id),
        cost=float(result.estimated_cost_usd),
        prompt=prompt,
    )
    if result.status != "success":
        metric = stats[result.shot_id]
        _decision(
            f"{labels[result.shot_id]} ABANDONED",
            f"Grafana: cost ${float(metric['cost'] or 0):.2f}; retries {int(metric['retries'] or 0)}; refusals {int(metric['refusals'] or 0)}",
            f"DECISION: ABANDON â€” {result.rationale}",
            "warning",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cutscope-web-worker")
    parser.add_argument("--mode", choices=("practice", "live"), required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, _request_stop)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _request_stop)
    try:
        return _practice_run(args.run_id) if args.mode == "practice" else _live_run(args.run_id)
    except InterruptedError:
        return 0
    except (CutscopeError, ValueError) as exc:
        emit("run.error", message=str(exc))
        return 2
    except Exception as exc:
        emit("run.error", message=f"{type(exc).__name__}: {str(exc)[:300]}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

