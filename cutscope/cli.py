from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from .config import RuntimeConfig
from .errors import ConfigurationError, CutscopeError, TelemetryUnavailable, VertexCredentialsUnavailable
from .shotfile import load_shots


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cutscope", description="Grafana-gated Veo shot controller")
    subcommands = parser.add_subparsers(dest="command", required=True)
    run_parser = subcommands.add_parser("run", help="run all declared shots")
    run_parser.add_argument("shot_file", type=Path, help="YAML shot declaration file")
    args = parser.parse_args(argv)

    if args.command == "run":
        return _run(args.shot_file)
    return 2


def _run(shot_file: Path) -> int:
    telemetry = None
    try:
        config = RuntimeConfig.from_environment()
        shots = load_shots(shot_file)
        # Delay optional SDK imports so missing configuration is always reported cleanly.
        from google import genai

        from .decision import GeminiDecisionAgent
        from .orchestrator import SliceOneOrchestrator
        from .provider import VeoCostEstimator, VeoVertexProvider
        from .telemetry import GrafanaTelemetry

        telemetry = GrafanaTelemetry(config)
        vertex_client = genai.Client(
            vertexai=True,
            project=config.gcp_project_id,
            location=config.gcp_region,
        )
        provider = VeoVertexProvider(vertex_client, config)
        orchestrator = SliceOneOrchestrator(
            provider=provider,
            decision_agent=GeminiDecisionAgent(
                vertex_client,
                config.gemini_model,
                telemetry,
                project_id=config.gcp_project_id,
                region=config.gcp_region,
                agent_engine_id=config.agent_engine_id,
                production_budget_ceiling_usd=config.production_budget_ceiling_usd,
            ),
            telemetry=telemetry,
            cost_estimator=VeoCostEstimator(config.veo_model),
        )
        results = orchestrator.run_all(shots)
        print(json.dumps([_serialize_result(result) for result in results], indent=2))
        return 0 if all(result.status == "success" for result in results) else 1
    except VertexCredentialsUnavailable as exc:
        print(f"CUTSCOPE stopped: {exc}", file=sys.stderr)
        return 2
    except (ConfigurationError, TelemetryUnavailable, CutscopeError) as exc:
        print(f"CUTSCOPE stopped: {exc}", file=sys.stderr)
        return 2
    except ModuleNotFoundError as exc:
        print(
            f"CUTSCOPE stopped: Python dependency {exc.name!r} is missing. "
            "Run: python -m pip install -e '.[dev]'",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        if _looks_like_missing_adc(exc):
            print(
                "CUTSCOPE stopped: Vertex AI credentials are unavailable. "
                "Configure Application Default Credentials with 'gcloud auth application-default login' "
                "or set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON file.",
                file=sys.stderr,
            )
            return 2
        print(f"CUTSCOPE stopped: {type(exc).__name__}: {_short_error(exc)}", file=sys.stderr)
        return 2
    finally:
        if telemetry is not None:
            telemetry.shutdown()


def _serialize_result(result: object) -> dict[str, object]:
    data = asdict(result)
    for key, value in data.items():
        if isinstance(value, Decimal):
            data[key] = float(value)
    return data


def _looks_like_missing_adc(exc: Exception) -> bool:
    message = str(exc).lower()
    return "default credentials" in message or "application default credentials" in message


def _short_error(exc: Exception) -> str:
    return (str(exc).replace("\n", " ").strip() or "Unexpected runtime failure.")[:400]
