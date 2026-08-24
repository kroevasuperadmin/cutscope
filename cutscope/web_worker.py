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
    """A no-cost demo proving the refusal/rephrase/budget-stop control loop."""
    del run_id
    prompts = {
        "rooftop-reveal": "Original sci-fi film: Mara steps onto a rain-soaked rooftop at blue hour, amber visor glowing, slow dolly reveal, cinematic 16:9.",
        "alley-exit": "Original sci-fi film: Mara exits a narrow neon alley into rain, keep her amber visor and dark hooded silhouette consistent, handheld follow shot, cinematic 16:9.",
        "signal-room": "Original sci-fi film: Mara and Noa study a pulsing city map in a quiet signal room, retain Mara's amber visor and Noa's silver jacket, controlled push-in, cinematic 16:9.",
    }
    labels = {
        "rooftop-reveal": "SHOT 01 · ROOFTOP REVEAL",
        "alley-exit": "SHOT 02 · ALLEY EXIT",
        "signal-room": "SHOT 03 · SIGNAL ROOM",
    }
    spent = 0.0
    metric_state = {
        shot_id: {"cost": 0.0, "retries": 0, "refusals": 0, "latency": None}
        for shot_id in prompts
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

    emit("run.started", production_name="MARA // SIGNAL AT BLUE HOUR", budget=15.0, mode="practice")
    _decision(
        "PRACTICE PRODUCTION ARMED",
        "Grafana: scripted telemetry stream online; project budget $0.00 / $15.00",
        "DECISION: BEGIN — replay the control loop without paid APIs",
        "info",
    )

    emit("shot.updated", shot_id="rooftop-reveal", state="generating", attempt=1, max_attempts=2, cost=0.0, prompt=prompts["rooftop-reveal"])
    _decision(
        "SHOT 01 ATTEMPT 1 SUBMITTED",
        "Grafana: $0.00 spent on this shot; 0 retries; budget headroom $0.64",
        "DECISION: GENERATE — first take is within the code-enforced ceiling",
        "info",
    )
    _sleep(0.8)
    update_metrics("rooftop-reveal", 1.44, 0, 0, 22.4)
    emit("shot.updated", shot_id="rooftop-reveal", state="done", attempt=1, max_attempts=2, cost=1.44, prompt=prompts["rooftop-reveal"])
    emit(
        "take.updated",
        shot_id="rooftop-reveal",
        label=labels["rooftop-reveal"],
        prompt=prompts["rooftop-reveal"],
        media_url="/practice-take.mp4",
        is_practice=True,
    )
    _decision(
        "SHOT 01 ATTEMPT 1 DONE",
        "Grafana: latency 22.4s; refusal rate 0%; shot cost $1.44",
        "DECISION: KEEP TAKE — no retry is justified",
        "success",
    )

    emit("shot.updated", shot_id="alley-exit", state="generating", attempt=1, max_attempts=2, cost=0.0, prompt=prompts["alley-exit"])
    _decision(
        "SHOT 02 ATTEMPT 1 SUBMITTED",
        "Grafana: $0.00 spent on this shot; 0 retries; refusal rate 0%",
        "DECISION: GENERATE — establish a baseline take",
        "info",
    )
    _sleep(0.8)
    update_metrics("alley-exit", 0.80, 0, 1, 4.6)
    emit("shot.updated", shot_id="alley-exit", state="refused", attempt=1, max_attempts=2, cost=0.80, prompt=prompts["alley-exit"])
    _decision(
        "SHOT 02 ATTEMPT 1 REFUSED (SAFETY FILTER)",
        "Grafana: refusal rate 100% on this shot; attempt cost $0.80",
        "DECISION: REPHRASE — remove ambiguous weapon language; keep blocking and wardrobe continuity",
        "danger",
    )
    rephrased = (
        "Original sci-fi film: Mara exits a narrow neon alley into rain, keep her amber visor and dark hooded silhouette consistent, "
        "empty hands, handheld follow shot, cinematic 16:9. Clarified retry: preserve identity and one clear camera action."
    )
    emit("shot.updated", shot_id="alley-exit", state="retrying", attempt=2, max_attempts=2, cost=0.80, prompt=rephrased)
    _decision(
        "SHOT 02 ATTEMPT 2 READY",
        "Grafana: one refusal, 100% refusal rate; remaining shot allowance $0.80",
        "DECISION: RETRY REPHRASED — submit one constrained replacement",
        "warning",
    )
    _sleep(0.8)
    update_metrics("alley-exit", 1.60, 1, 1, 18.2)
    emit("shot.updated", shot_id="alley-exit", state="done", attempt=2, max_attempts=2, cost=1.60, prompt=rephrased)
    emit("take.updated", shot_id="alley-exit", label=labels["alley-exit"], prompt=rephrased, media_url="/practice-take.mp4", is_practice=True)
    _decision(
        "SHOT 02 ATTEMPT 2 DONE",
        "Grafana: refusal rate fell to 50%; retry latency 18.2s; total shot cost $1.60",
        "DECISION: KEEP TAKE — the clarified prompt recovered the shot",
        "success",
    )

    emit("shot.updated", shot_id="signal-room", state="generating", attempt=1, max_attempts=2, cost=0.0, prompt=prompts["signal-room"])
    _decision(
        "SHOT 03 ATTEMPT 1 SUBMITTED",
        "Grafana: $0.00 spent on this shot; next attempt estimate $1.08; ceiling $1.08",
        "DECISION: GENERATE ONCE — one take fits the shot cap",
        "info",
    )
    _sleep(0.8)
    update_metrics("signal-room", 1.08, 0, 0, 37.6)
    emit("shot.updated", shot_id="signal-room", state="abandoned", attempt=1, max_attempts=2, cost=1.08, prompt=prompts["signal-room"])
    _decision(
        "SHOT 03 ATTEMPT 1 TIMED OUT",
        "Grafana: p95 latency 37.6s; shot cost $1.08 / $1.08; next estimate $1.08",
        "DECISION: ABANDON — a second attempt would exceed the code-enforced shot budget",
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
    shots = load_shots(Path.cwd() / "shots" / "demo.yaml")
    labels = {shot.id: f"SHOT {index:02d} · {shot.id.replace('-', ' ').upper()}" for index, shot in enumerate(shots, 1)}
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
                "DECISION: GENERATE — the deterministic budget guard permitted this attempt",
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
                "DECISION: ASK GEMINI — evaluate this real Mimir evidence before retrying",
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
                f"DECISION: {action.replace('_', ' ')} — {str(data['rationale'])}",
                "warning" if action == "ABANDON" else "success" if action.startswith("RETRY") else "neutral",
            )

    telemetry: Any = None
    try:
        emit("run.started", production_name="MARA // SIGNAL AT BLUE HOUR", budget=15.0, mode="live")
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
            f"DECISION: ABANDON — {result.rationale}",
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
