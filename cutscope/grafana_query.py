"""Read the shot's live metrics back out of Grafana before advising a retry.

CUTSCOPE writes telemetry over OTLP (cutscope/telemetry.py) and reads it back
through the Grafana MCP server (cutscope/mcp_grafana.py). This module is the
read side.

  primary  : query_prometheus tool call on the Grafana MCP server.
  fallback : direct HTTP GET against the Grafana Cloud Prometheus/Mimir API,
             used only when MCP is unconfigured or unreachable. The dict this
             module returns always names which of the two produced it, so a
             run can never silently look like it used MCP when it did not.

Metric and label names below are the OTLP-normalised forms that actually land
in Mimir, not the names passed to the OpenTelemetry SDK. Verified against
prometheus/otlptranslator v1.0.0, the translator Prometheus and Mimir use:

  cutscope_generation_attempts_total          unit {attempt} -> unchanged
  cutscope_generation_estimated_cost_usd_total unit USD      -> ..._usd_USD_total
  cutscope_generation_duration_seconds        unit s         -> unchanged
  cutscope_generation_outcomes_total          unit {attempt} -> unchanged
  attribute cutscope.shot.id                                 -> cutscope_shot_id
  attribute cutscope.outcome                                 -> cutscope_outcome

Units wrapped in braces are annotations and are dropped. "USD" is not a known
unit, so the translator inserts it verbatim before the _total suffix, which is
why the cost series is matched by __name__ regex rather than by literal name.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .errors import ConfigurationError, TelemetryUnavailable
from .mcp_grafana import GrafanaMcpUnavailable, McpClient, McpConfig
from .models import LiveShotMetrics, Shot

# Dots are not legal in Prometheus label names; OTLP replaces them with
# underscores. The previous dotted selectors made every query a parse error.
LABEL_SHOT_ID = "cutscope_shot_id"
LABEL_OUTCOME = "cutscope_outcome"

METRIC_ATTEMPTS = "cutscope_generation_attempts_total"
METRIC_OUTCOMES = "cutscope_generation_outcomes_total"
METRIC_DURATION_BUCKET = "cutscope_generation_duration_seconds_bucket"
# Matches the name with or without the inserted USD unit suffix, so the query is
# correct whether or not the OTLP gateway applies unit suffixing.
METRIC_COST_PATTERN = "cutscope_generation_estimated_cost_usd(_USD)?_total"

WINDOW = "5m"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable for live Grafana queries: {name}")
    return value


@dataclass(frozen=True)
class GrafanaReadConfig:
    """Both read paths. MCP is primary; Mimir over HTTP is the fallback."""

    mcp: McpConfig | None
    prometheus_url: str
    instance_id: str
    token: str
    datasource_uid: str = ""

    @classmethod
    def from_environment(cls) -> "GrafanaReadConfig":
        mcp = McpConfig.from_environment()
        prometheus_url = os.environ.get("GRAFANA_PROMETHEUS_URL", "").strip().rstrip("/")
        if not mcp and not prometheus_url:
            raise ConfigurationError(
                "Live mode needs a way to read metrics back out of Grafana. Set "
                "GRAFANA_MCP_URL and GRAFANA_MCP_TOKEN to read through the Grafana MCP "
                "server (the supported path), or GRAFANA_PROMETHEUS_URL to use the "
                "direct Mimir HTTP fallback. See docs/GRAFANA_MCP_SETUP.md."
            )
        return cls(
            mcp=mcp,
            prometheus_url=prometheus_url,
            instance_id=os.environ.get("GRAFANA_PROMETHEUS_INSTANCE_ID", "").strip()
            or os.environ.get("GRAFANA_INSTANCE_ID", "").strip(),
            token=os.environ.get("GRAFANA_PROMETHEUS_TOKEN", "").strip()
            or os.environ.get("GRAFANA_OTLP_TOKEN", "").strip(),
            datasource_uid=os.environ.get("GRAFANA_PROMETHEUS_DATASOURCE_UID", "").strip(),
        )


class GrafanaMetricsReader:
    """Reads the actual Grafana window before Gemini can advise a retry."""

    def __init__(self, config: GrafanaReadConfig) -> None:
        self._config = config
        self._mcp: McpClient | None = None
        self._datasource_uid: str = config.datasource_uid
        self._mcp_disabled_reason: str | None = None

    # -- public -------------------------------------------------------------

    def read_shot_window(self, shot: Shot, local_metrics: LiveShotMetrics) -> dict[str, object]:
        queries = _shot_queries(shot.id)
        if self._config.mcp and not self._mcp_disabled_reason:
            try:
                values, provenance = self._read_via_mcp(queries)
                return _assemble(shot, local_metrics, values, provenance)
            except GrafanaMcpUnavailable as exc:
                if not self._config.prometheus_url:
                    raise TelemetryUnavailable(
                        f"Grafana MCP could not supply the shot window and no direct "
                        f"Prometheus fallback is configured. {exc}"
                    ) from exc
                # ponytail: first MCP failure downgrades the whole run to the
                # fallback, so a 5-shot run does not re-pay a 20s timeout 20
                # times. Ceiling: a transient blip is never retried. Add a
                # retry-after timestamp here if runs get long enough to care.
                self._mcp_disabled_reason = str(exc)
                self._close_mcp()

        if not self._config.prometheus_url:
            raise TelemetryUnavailable(
                "No Grafana read path is configured; automatic retry is stopped."
            )
        values = {key: self._query_direct(expr) for key, expr in queries.items()}
        provenance: dict[str, object] = {
            "source": "grafana_prometheus_http_fallback",
            "transport": "https",
            "mcp_used": False,
        }
        if self._mcp_disabled_reason:
            provenance["mcp_error"] = self._mcp_disabled_reason
        elif not self._config.mcp:
            provenance["mcp_error"] = "GRAFANA_MCP_URL / GRAFANA_MCP_TOKEN are not configured."
        return _assemble(shot, local_metrics, values, provenance)

    def close(self) -> None:
        self._close_mcp()

    # -- MCP path -----------------------------------------------------------

    def _read_via_mcp(self, queries: dict[str, str]) -> tuple[dict[str, float | None], dict[str, object]]:
        client = self._ensure_mcp()
        uid = self._ensure_datasource_uid(client)
        values: dict[str, float | None] = {}
        warnings: list[str] = []
        for key, expr in queries.items():
            result = client.call_tool(
                "query_prometheus",
                {
                    "datasourceUid": uid,
                    "expr": expr,
                    "queryType": "instant",
                    # endTime is required by the tool schema even for instant queries.
                    "endTime": "now",
                },
            )
            value, query_warnings = _first_instant_value(result.payload)
            values[key] = value
            warnings.extend(query_warnings)
        provenance: dict[str, object] = {
            "source": "grafana_mcp",
            "transport": "mcp/streamable-http",
            "mcp_used": True,
            "mcp_endpoint": self._config.mcp.url if self._config.mcp else "",
            "mcp_tool": "query_prometheus",
            "mcp_server": client.server_info,
            "datasource_uid": uid,
        }
        if warnings:
            provenance["warnings"] = sorted(set(warnings))
        return values, provenance

    def _ensure_mcp(self) -> McpClient:
        if self._mcp is None:
            assert self._config.mcp is not None  # guarded by the caller
            self._mcp = McpClient(self._config.mcp)
            self._mcp.connect()
        return self._mcp

    def _ensure_datasource_uid(self, client: McpClient) -> str:
        if self._datasource_uid:
            return self._datasource_uid
        result = client.call_tool("list_datasources", {"type": "prometheus"})
        payload = result.payload
        # The tool returns {"datasources": [...]}; older builds returned a bare list.
        entries = payload.get("datasources") if isinstance(payload, dict) else payload
        if not isinstance(entries, list) or not entries:
            raise GrafanaMcpUnavailable(
                "Grafana MCP reported no Prometheus datasource on this stack. Set "
                "GRAFANA_PROMETHEUS_DATASOURCE_UID to name one explicitly."
            )
        chosen = next(
            (e for e in entries if isinstance(e, dict) and e.get("isDefault")),
            entries[0],
        )
        uid = chosen.get("uid") if isinstance(chosen, dict) else None
        if not uid:
            raise GrafanaMcpUnavailable("Grafana MCP returned a datasource with no uid.")
        self._datasource_uid = str(uid)
        return self._datasource_uid

    def _close_mcp(self) -> None:
        if self._mcp is not None:
            self._mcp.close()
            self._mcp = None

    # -- direct Mimir fallback ---------------------------------------------

    def _direct_headers(self) -> dict[str, str]:
        if not self._config.instance_id or not self._config.token:
            raise TelemetryUnavailable(
                "The direct Prometheus fallback needs GRAFANA_INSTANCE_ID and a read token "
                "(GRAFANA_PROMETHEUS_TOKEN, or GRAFANA_OTLP_TOKEN if it carries read scope)."
            )
        encoded = base64.b64encode(
            f"{self._config.instance_id}:{self._config.token}".encode("utf-8")
        ).decode("ascii")
        return {"Authorization": f"Basic {encoded}", "Accept": "application/json"}

    def _query_direct(self, expression: str) -> float | None:
        query = urlencode({"query": expression})
        request = Request(
            f"{self._config.prometheus_url}/api/v1/query?{query}", headers=self._direct_headers()
        )
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - operator-provided env var
                payload: Any = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise TelemetryUnavailable(
                f"Grafana Mimir query failed with HTTP {exc.code}; no retry was submitted."
            ) from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise TelemetryUnavailable(
                "Grafana Mimir could not be queried; no retry was submitted."
            ) from exc
        if payload.get("status") != "success":
            raise TelemetryUnavailable("Grafana Mimir rejected the metrics query; no retry was submitted.")
        return _first_instant_value(payload.get("data"))[0]


# Back-compat names: cutscope/web_worker.py and cutscope/cli.py construct these.
GrafanaMimirConfig = GrafanaReadConfig
GrafanaMimirClient = GrafanaMetricsReader


def _shot_queries(shot_id: str) -> dict[str, str]:
    selector = f'{LABEL_SHOT_ID}="{_promql_escape(shot_id)}"'
    return {
        "attempts": f"sum({METRIC_ATTEMPTS}{{{selector}}})",
        "cost": f'sum({{__name__=~"{METRIC_COST_PATTERN}",{selector}}})',
        "refusals": f'sum({METRIC_OUTCOMES}{{{selector},{LABEL_OUTCOME}="refused"}})',
        "p95_latency": (
            "histogram_quantile(0.95, "
            f"sum(rate({METRIC_DURATION_BUCKET}{{{selector}}}[{WINDOW}])) by (le))"
        ),
    }


def _assemble(
    shot: Shot,
    local_metrics: LiveShotMetrics,
    values: dict[str, float | None],
    provenance: dict[str, object],
) -> dict[str, object]:
    attempts = values.get("attempts")
    cost = values.get("cost")
    refusals = values.get("refusals")
    if attempts is None or cost is None or refusals is None:
        missing = [k for k in ("attempts", "cost", "refusals") if values.get(k) is None]
        raise TelemetryUnavailable(
            f"Grafana returned no live {', '.join(missing)} data for shot {shot.id!r}; "
            "automatic retry is stopped."
        )
    window: dict[str, object] = {
        "shot_id": shot.id,
        "window": WINDOW,
        "attempt_count": attempts,
        "estimated_cost_usd": cost,
        "refusal_count": refusals,
        "refusal_rate": round(refusals / attempts, 4) if attempts else 0.0,
        "retry_count": max(attempts - 1, 0),
        "p95_latency_seconds": values.get("p95_latency"),
        # Reconciliation aid only; never a substitute for what Grafana returned.
        "local_controller_cost_usd": float(local_metrics.estimated_cost_usd),
    }
    window.update(provenance)
    return window


def _first_instant_value(payload: Any) -> tuple[float | None, list[str]]:
    """Extract one instant-vector sample from either read path's response.

    MCP query_prometheus returns {"data": <vector>, "warnings": [...]}; the
    Prometheus HTTP API returns {"resultType": ..., "result": <vector>}. Both
    wrap the same sample shape: {"metric": {...}, "value": [ts, "number"]}.
    """
    warnings: list[str] = []
    if isinstance(payload, dict):
        raw_warnings = payload.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [str(w) for w in raw_warnings]
        for key in ("data", "result"):
            if key in payload:
                nested, more = _first_instant_value(payload[key])
                return nested, warnings + more
        if "value" in payload:
            return _sample_value(payload.get("value")), warnings
        return None, warnings
    if isinstance(payload, list):
        if not payload:
            return None, warnings
        nested, more = _first_instant_value(payload[0])
        return nested, warnings + more
    return None, warnings


def _sample_value(value: Any) -> float | None:
    if not isinstance(value, list) or len(value) < 2:
        return None
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return None


def _promql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _selfcheck() -> None:
    queries = _shot_queries('sh-1"; drop')
    assert '\\"' in queries["attempts"], queries["attempts"]
    # The bug this replaces: dotted label names are a PromQL parse error.
    for expr in queries.values():
        assert "cutscope.shot.id" not in expr and "cutscope.outcome" not in expr, expr
    assert queries["refusals"].count('cutscope_outcome="refused"') == 1, queries["refusals"]
    assert "__name__=~" in queries["cost"], queries["cost"]

    # MCP shape: {"data": [ ... ]}
    mcp_payload = {
        "data": [{"metric": {"cutscope_shot_id": "sh-1"}, "value": [1756000000.0, "3"]}],
        "warnings": ["partial response"],
    }
    assert _first_instant_value(mcp_payload) == (3.0, ["partial response"])
    # Prometheus HTTP shape: {"resultType": "vector", "result": [ ... ]}
    http_payload = {"resultType": "vector", "result": [{"value": [1756000000.0, "0.42"]}]}
    assert _first_instant_value(http_payload) == (0.42, [])
    # Empty vector must read as "no data", which stops the retry rather than
    # being mistaken for a zero-cost, zero-attempt shot.
    assert _first_instant_value({"data": []}) == (None, [])
    assert _first_instant_value({"data": [{"value": [1, "NaN"]}]})[0] != _first_instant_value({"data": []})[0]

    class _Shot:
        id = "sh-1"

    class _Local:
        estimated_cost_usd = 0

    for missing in ({"attempts": None}, {"cost": None}, {"refusals": None}):
        values: dict[str, float | None] = {"attempts": 1.0, "cost": 1.0, "refusals": 0.0}
        values.update(missing)
        try:
            _assemble(_Shot(), _Local(), values, {"source": "x"})
        except TelemetryUnavailable:
            pass
        else:
            raise AssertionError(f"missing {missing} did not stop the retry")

    window = _assemble(
        _Shot(), _Local(), {"attempts": 4.0, "cost": 2.0, "refusals": 1.0, "p95_latency": None},
        {"source": "grafana_mcp", "mcp_used": True},
    )
    assert window["refusal_rate"] == 0.25 and window["retry_count"] == 3.0, window
    assert window["source"] == "grafana_mcp" and window["mcp_used"] is True, window
    print("grafana_query selfcheck: ok")


if __name__ == "__main__":  # pragma: no cover
    _selfcheck()
