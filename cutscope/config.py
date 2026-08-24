from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigurationError


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs without adding a dotenv dependency."""
    if not path.exists():
        return
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(f"Invalid .env line {line_number}: expected KEY=VALUE.")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            raise ConfigurationError(f"Invalid .env line {line_number}: empty variable name.")
        os.environ.setdefault(key, value)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class RuntimeConfig:
    gcp_project_id: str
    gcp_region: str
    grafana_otlp_endpoint: str
    grafana_instance_id: str
    grafana_otlp_token: str
    veo_model: str
    gemini_model: str
    veo_resolution: str
    veo_generate_audio: bool
    poll_interval_seconds: float
    poll_timeout_seconds: float

    @classmethod
    def from_environment(cls, env_file: Path | None = None) -> "RuntimeConfig":
        load_dotenv(env_file or Path.cwd() / ".env")
        return cls(
            gcp_project_id=_required("GCP_PROJECT_ID"),
            gcp_region=_required("GCP_REGION"),
            grafana_otlp_endpoint=_required("GRAFANA_OTLP_ENDPOINT"),
            grafana_instance_id=_required("GRAFANA_INSTANCE_ID"),
            grafana_otlp_token=_required("GRAFANA_OTLP_TOKEN"),
            veo_model=os.environ.get("VEO_MODEL", "veo-3.1-fast-generate-001"),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            veo_resolution=os.environ.get("VEO_RESOLUTION", "720p"),
            veo_generate_audio=os.environ.get("VEO_GENERATE_AUDIO", "false").lower()
            in {"1", "true", "yes"},
            poll_interval_seconds=_positive_float("VEO_POLL_INTERVAL_SECONDS", 15.0),
            poll_timeout_seconds=_positive_float("VEO_POLL_TIMEOUT_SECONDS", 900.0),
        )


def _positive_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a positive number.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive number.")
    return value
