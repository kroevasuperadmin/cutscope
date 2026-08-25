"""The deployable Google ADK decision agent used by CUTSCOPE.

The functions in this module are deliberately ordinary ADK function tools.  On
Agent Engine they run in the agent runtime, not in the Cloud Run controller.
The controller puts an immutable per-shot snapshot in the ADK session state;
the Grafana tool reconstructs that snapshot and reads the current window back
through ``GrafanaMetricsReader`` (MCP first, Prometheus only as its labelled
fallback).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

from .grafana_query import GrafanaMetricsReader, GrafanaReadConfig
from .models import AttemptOutcome, LiveShotMetrics, Shot


def _state(tool_context: ToolContext) -> dict[str, Any]:
    state = tool_context.state.get("cutscope_decision")
    if not isinstance(state, dict):
        return {}
    return state


def _shot_and_metrics(tool_context: ToolContext) -> tuple[Shot, LiveShotMetrics]:
    state = _state(tool_context)
    raw_shot = state.get("shot")
    raw_metrics = state.get("metrics")
    if not isinstance(raw_shot, dict) or not isinstance(raw_metrics, dict):
        raise ValueError("CUTSCOPE decision context is missing from this ADK session.")
    shot = Shot(
        id=str(raw_shot["id"]),
        prompt=str(raw_shot["prompt"]),
        reference_image_path=Path(str(raw_shot["reference_image_path"]))
        if raw_shot.get("reference_image_path")
        else None,
        expected_duration_seconds=int(raw_shot["expected_duration_seconds"]),
        character_ids=tuple(str(item) for item in raw_shot["character_ids"]),
        max_attempts=int(raw_shot["max_attempts"]),
        budget_ceiling_usd=Decimal(str(raw_shot["budget_ceiling_usd"])),
        difficulty=str(raw_shot["difficulty"]) if raw_shot.get("difficulty") else None,
    )
    metrics = LiveShotMetrics(shot_id=shot.id)
    for attempt in raw_metrics.get("attempts", []):
        if not isinstance(attempt, dict):
            continue
        metrics.record(
            AttemptOutcome(str(attempt["outcome"])),
            float(attempt["latency_seconds"]),
            Decimal(str(attempt["estimated_cost_usd"])),
        )
    return shot, metrics


def read_current_metrics(tool_context: ToolContext) -> dict[str, object]:
    """Read this shot's current telemetry from Grafana via its MCP query tool.

    This is not a cached controller value: ``GrafanaMetricsReader`` calls the
    configured Grafana MCP ``query_prometheus`` tool.  If that MCP server is
    down it may return the reader's explicitly-labelled Prometheus fallback.
    """
    try:
        shot, metrics = _shot_and_metrics(tool_context)
        reader = GrafanaMetricsReader(GrafanaReadConfig.from_environment())
        try:
            return reader.read_shot_window(shot, metrics)
        finally:
            reader.close()
    except Exception as exc:
        # A tool failure must be visible to Gemini so it can choose ABANDON;
        # it must not become fabricated metric evidence.
        return {"source": "grafana_unavailable", "error": _short_error(exc)}


def get_remaining_budget(tool_context: ToolContext) -> dict[str, object]:
    """Return remaining shot and production budget from the controller ledger."""
    shot, metrics = _shot_and_metrics(tool_context)
    state = _state(tool_context)
    next_attempt = Decimal(str(state.get("next_attempt_estimated_usd", "0")))
    production_ceiling = Decimal(str(state.get("production_budget_ceiling_usd", "0")))
    production_spend = Decimal(str(state.get("production_spend_usd", "0")))
    return {
        "shot_budget_ceiling_usd": float(shot.budget_ceiling_usd),
        "shot_spend_usd": float(metrics.estimated_cost_usd),
        "shot_remaining_usd": float(shot.budget_ceiling_usd - metrics.estimated_cost_usd),
        "next_attempt_estimated_usd": float(next_attempt),
        "next_attempt_within_shot_ceiling": (
            metrics.estimated_cost_usd + next_attempt <= shot.budget_ceiling_usd
        ),
        "production_budget_ceiling_usd": float(production_ceiling),
        "production_spend_usd": float(production_spend),
        "production_remaining_usd": float(production_ceiling - production_spend),
    }


def get_attempt_history(tool_context: ToolContext) -> dict[str, object]:
    """Return prompts, outcomes, latency and cost for all attempts on this shot."""
    state = _state(tool_context)
    attempts = state.get("metrics", {}).get("attempts", []) if isinstance(state.get("metrics"), dict) else []
    return {"shot_id": state.get("shot", {}).get("id"), "attempts": attempts}


INSTRUCTION = """You are CUTSCOPE's production-control decision agent.
You decide whether a failed Veo shot should be RETRY_SAME, RETRY_REPHRASED, or
ABANDON. Before deciding, you MUST call all three tools exactly once:
read_current_metrics, get_remaining_budget, and get_attempt_history. Treat
Grafana output whose source is grafana_unavailable as missing evidence; do not
invent observations. The controller, not you, enforces spend ceilings.

Return exactly one JSON object and no markdown with these keys:
action, rationale, replacement_prompt.
action must be RETRY_SAME, RETRY_REPHRASED, or ABANDON. replacement_prompt must
be a non-empty complete replacement only for RETRY_REPHRASED; otherwise null.
Never retry unchanged after a safety refusal. Be concise and base the rationale
on the actual tool results.
"""

# This module-level LlmAgent is the object wrapped by vertexai.agent_engines.AdkApp
# in deployment.  The literal model identifier is intentional: it is easy for a
# judge to verify this is Gemini 2.5 Flash, not a generic completion wrapper.
root_agent = LlmAgent(
    name="cutscope_decision_agent",
    model="gemini-2.5-flash",
    instruction=INSTRUCTION,
    tools=[read_current_metrics, get_remaining_budget, get_attempt_history],
)


def _short_error(exc: Exception) -> str:
    return (str(exc).replace("\n", " ").strip() or type(exc).__name__)[:300]
