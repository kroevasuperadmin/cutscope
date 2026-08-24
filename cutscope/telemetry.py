from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterator

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import RuntimeConfig
from .errors import TelemetryUnavailable
from .models import AttemptOutcome


@dataclass(frozen=True)
class AttemptTelemetry:
    shot_id: str
    attempt_number: int
    provider: str
    model: str
    estimated_cost_usd: Decimal


class GrafanaTelemetry:
    """OTLP telemetry that gates attempts instead of decorating a later dashboard."""

    def __init__(self, config: RuntimeConfig) -> None:
        auth = base64.b64encode(
            f"{config.grafana_instance_id}:{config.grafana_otlp_token}".encode("utf-8")
        ).decode("ascii")
        headers = {"Authorization": f"Basic {auth}"}
        resource = Resource.create(
            {
                SERVICE_NAME: "cutscope-slice1",
                "service.version": "0.1.0",
                "gcp.project_id": config.gcp_project_id,
            }
        )
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=_signal_endpoint(config.grafana_otlp_endpoint, "metrics"), headers=headers
            ),
            export_interval_millis=30_000,
        )
        self._meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        self._tracer_provider = TracerProvider(resource=resource)
        self._tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=_signal_endpoint(config.grafana_otlp_endpoint, "traces"), headers=headers)
            )
        )
        metrics.set_meter_provider(self._meter_provider)
        trace.set_tracer_provider(self._tracer_provider)
        meter = self._meter_provider.get_meter("cutscope.generation")
        self._tracer = self._tracer_provider.get_tracer("cutscope.generation")
        self._attempts = meter.create_counter("cutscope_generation_attempts_total", unit="{attempt}")
        self._estimated_cost = meter.create_counter("cutscope_generation_estimated_cost_usd_total", unit="USD")
        self._duration = meter.create_histogram("cutscope_generation_duration_seconds", unit="s")
        self._outcomes = meter.create_counter("cutscope_generation_outcomes_total", unit="{attempt}")

    def begin_attempt(
        self,
        *,
        shot_id: str,
        attempt_number: int,
        provider: str,
        model: str,
        estimated_cost_usd: Decimal,
    ) -> AttemptTelemetry:
        record = AttemptTelemetry(shot_id, attempt_number, provider, model, estimated_cost_usd)
        attributes = _attributes(record)
        # This closed span and the two metrics are force-flushed before Veo is called.
        with self._tracer.start_as_current_span("cutscope.attempt.telemetry_gate") as span:
            span.set_attribute("cutscope.attempt.number", attempt_number)
            span.set_attribute("cutscope.estimated_cost_usd", float(estimated_cost_usd))
            span.add_event("attempt.telemetry_emitted")
            self._attempts.add(1, attributes=attributes)
            self._estimated_cost.add(float(estimated_cost_usd), attributes=attributes)
        self._flush_or_raise("attempt-start telemetry")
        return record

    def finish_attempt(self, record: AttemptTelemetry, outcome: AttemptOutcome, latency_seconds: float) -> None:
        attributes = _attributes(record) | {"cutscope.outcome": outcome.value}
        with self._tracer.start_as_current_span("cutscope.video_attempt") as span:
            span.set_attribute("cutscope.attempt.number", record.attempt_number)
            span.set_attribute("cutscope.outcome", outcome.value)
            span.set_attribute("cutscope.latency_seconds", latency_seconds)
            span.set_attribute("cutscope.estimated_cost_usd", float(record.estimated_cost_usd))
            span.add_event("attempt.completed")
            self._duration.record(latency_seconds, attributes=attributes)
            self._outcomes.add(1, attributes=attributes)
        self._flush_or_raise("attempt-complete telemetry")

    @contextmanager
    def gemini_span(self, shot_id: str, model: str) -> Iterator[None]:
        try:
            with self._tracer.start_as_current_span("cutscope.gemini_decision") as span:
                span.set_attribute("cutscope.shot.id", shot_id)
                span.set_attribute("gen_ai.provider.name", "gcp.vertex_ai")
                span.set_attribute("gen_ai.request.model", model)
                yield
        finally:
            self._flush_or_raise("Gemini decision telemetry")

    def shutdown(self) -> None:
        self._meter_provider.shutdown()
        self._tracer_provider.shutdown()

    def _flush_or_raise(self, signal: str) -> None:
        metrics_flushed = self._meter_provider.force_flush(timeout_millis=15_000)
        traces_flushed = self._tracer_provider.force_flush(timeout_millis=15_000)
        if not metrics_flushed or not traces_flushed:
            raise TelemetryUnavailable(
                f"Grafana OTLP did not confirm {signal}. No Veo submission will be made."
            )


def _attributes(record: AttemptTelemetry) -> dict[str, str]:
    # Shot ids are explicitly small, finite IDs from the input file; prompts never become labels.
    return {
        "cutscope.shot.id": record.shot_id,
        "gen_ai.provider.name": record.provider,
        "gen_ai.request.model": record.model,
    }


def _signal_endpoint(base_endpoint: str, signal: str) -> str:
    endpoint = base_endpoint.rstrip("/")
    suffix = f"/v1/{signal}"
    if endpoint.endswith(suffix):
        return endpoint
    return f"{endpoint}{suffix}"
