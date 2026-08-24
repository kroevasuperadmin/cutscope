# CUTSCOPE — Slice 1

CUTSCOPE is a production-control loop for AI video generation. This first slice takes
declared shots, submits each to **Google Veo on Vertex AI**, writes the attempt telemetry
to **Grafana Cloud over OTLP**, then asks **Gemini 2.5 Flash on Vertex AI** whether a failed
shot should retry unchanged, retry with a clarified prompt, or stop.

This is deliberately a CLI-only slice: no web UI, database, auth layer, or deployment
service is included.

## What is enforced

- Each attempted generation emits and force-flushes Grafana OTLP metrics **before Veo is
  submitted**. If Grafana does not acknowledge the flush, CUTSCOPE stops and does not spend
  on video generation.
- The final attempt metrics include a bounded shot ID, provider, model ID, outcome
  (`success`, `refused`, `error`, or `timeout`), latency, and estimated USD cost.
- Veo safety filtering is reported as `refused`, never flattened into a generic error.
- Gemini receives the exact live metric snapshot that was just flushed after a failed
  attempt. Gemini advises; code enforces the per-shot budget ceiling and maximum attempts.
- Runtime model calls are Google Vertex AI only: Veo for video and Gemini for policy.

## Requirements

- Python 3.12
- [Application Default Credentials for Google Cloud](https://cloud.google.com/docs/authentication/provide-credentials-adc)
- A Vertex AI project with Veo and `gemini-2.5-flash` access
- Grafana Cloud OTLP credentials

## Run it

From the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
gcloud auth application-default login
python -m cutscope run shots/demo.yaml
```

Fill these already-provisioned values in `.env`; do not put secrets in source code:

```dotenv
GRAFANA_OTLP_ENDPOINT=...
GRAFANA_INSTANCE_ID=...
GRAFANA_OTLP_TOKEN=...
GCP_PROJECT_ID=cutscope
GCP_REGION=us-central1
```

`VEO_MODEL`, `GEMINI_MODEL`, `VEO_RESOLUTION`, `VEO_GENERATE_AUDIO`, and polling settings
are optional controls in `.env.example`. The default is `veo-3.1-fast-generate-001` at
720p with audio disabled, and `gemini-2.5-flash`. The cost estimator uses the published
720p video-only rate for the selected Veo family; review it against
[Google's current pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing)
before production use.

The exact end-to-end command is:

```powershell
python -m cutscope run shots/demo.yaml
```

This submits real paid Veo work. `shots/demo.yaml` contains three original 4-second shots,
each with a $0.64 ceiling and no more than two attempts. The included reference image is a
small original, text-encoded PNG solely to keep the sample repository text-only; replace it
with a real PNG, JPEG, or WebP path before evaluating visual quality.

The command prints one JSON result per shot and exits non-zero when any shot is abandoned.
Missing environment variables and missing Google credentials are reported without a Python
stack trace.

## Shot file schema

`shots/demo.yaml` uses the only YAML shape Slice 1 accepts. Every field is required;
`reference_image_path` can be `null` for text-to-video, or a local PNG/JPEG/WebP path.

```yaml
shots:
  - id: rooftop-reveal
    prompt: "Original sci-fi film: a director's own character on a rooftop."
    reference_image_path: ../assets/mara_reference.png.base64
    expected_duration_seconds: 4
    character_ids: [mara]
    max_attempts: 2
    budget_ceiling_usd: 0.64
```

For a checked-in binary-free sample, a `.png.base64` path is also accepted and decoded in a
temporary file before it is passed to the Google SDK. It must contain valid base64 PNG bytes.

## Check the budget guard

```powershell
pytest tests/test_decide.py
```

This test proves that code returns `ABANDON` even when Gemini advises `RETRY_SAME` after the
budget ceiling has been reached.

## Slice 1 boundaries

- One provider interface: `VideoProvider.submit()` and `VideoProvider.poll()`.
- One implementation: `VeoVertexProvider` using the Vertex AI long-running operation API.
- Grafana's OTLP transport is an execution prerequisite, not a dashboard-only integration.
- No UI, auth system, database, Cloud Run service, or multi-user behavior yet.
