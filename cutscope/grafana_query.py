from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .errors import ConfigurationError, TelemetryUnavailable
from .models import LiveShotMetrics, Shot


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable for live Grafana queries: {name}")
    return value


@dataclass(frozen=True)
class GrafanaMimirConfig:
    prometheus_url: str
    instance_id: str
    token: str

    @classmethod
    def from_environment(cls) -> "GrafanaMimirConfig":
        return cls(
            prometheus_url=_required("GRAFANA_PROMETHEUS_URL").rstrip("/"),
            instance_id=os.environ.get("GRAFANA_PROMETHEUS_INSTANCE_ID", "").strip()
            or _required("GRAFANA_INSTANCE_ID"),
            token=os.environ.get("GRAFANA_PROMETHEUS_TOKEN", "").strip()
            or _required("GRAFANA_OTLP_TOKEN"),
        )


class GrafanaMimirClient:
    """Reads the actual Grafana Mimir window before Gemini can advise a retry."""

    def __init__(self, config: GrafanaMimirConfig) -> None:
        self._config = config
        encoded = base64.b64encode(f"{config.instance_id}:{config.token}".encode("utf-8")).decode("ascii")
        self._headers = {"Authorization": f"Basic {encoded}", "Accept": "application/json"}

    def read_shot_window(self, shot: Shot, local_metrics: LiveShotMetrics) -> dict[str, object]:
        selector = f'cutscope.shot.id="{_promql_escape(shot.id)}"'
        attempts = self._query_number(f"sum(cutscope_generation_attempts_total{{{selector}}})")
        cost = self._query_number(f"sum(cutscope_generation_estimated_cost_usd_total{{{selector}}})")
        refusals = self._query_number(
            f'sum(cutscope_generation_outcomes_total{{{selector},cutscope.outcome="refused"}})'
        )
        p95_latency = self._query_number(
            "histogram_quantile(0.95, "
            f"sum(rate(cutscope_generation_duration_seconds_bucket{{{selector}}}[5m])) by (le))"
        )
        if attempts is None or cost is None or refusals is None:
            raise TelemetryUnavailable(
                "Grafana Mimir returned no live attempt, cost, or refusal data; automatic retry is stopped."
            )
        return {
            "source": "grafana_mimir",
            "shot_id": shot.id,
            "window": "5m",
            "attempt_count": attempts,
            "estimated_cost_usd": cost,
            "refusal_count": refusals,
            "refusal_rate": round(refusals / attempts, 4) if attempts else 0.0,
            "retry_count": max(attempts - 1, 0),
            "p95_latency_seconds": p95_latency,
            # This is included only as a reconciliation aid, not used as a substitute for Mimir.
            "local_controller_cost_usd": float(local_metrics.estimated_cost_usd),
        }

    def _query_number(self, expression: str) -> float | None:
        query = urlencode({"query": expression})
        request = Request(f"{self._config.prometheus_url}/api/v1/query?{query}", headers=self._headers)
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - endpoint is an operator-provided env var
                payload: Any = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise TelemetryUnavailable(f"Grafana Mimir query failed with HTTP {exc.code}; no retry was submitted.") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise TelemetryUnavailable("Grafana Mimir could not be queried; no retry was submitted.") from exc
        if payload.get("status") != "success":
            raise TelemetryUnavailable("Grafana Mimir rejected the metrics query; no retry was submitted.")
        results = payload.get("data", {}).get("result", [])
        if not results:
            return None
        value = results[0].get("value")
        if not isinstance(value, list) or len(value) < 2:
            return None
        try:
            return float(value[1])
        except (TypeError, ValueError):
            return None


def _promql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
