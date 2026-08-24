# CUTSCOPE web console

CUTSCOPE is a public production-control console for a multi-shot AI video run. A judge can
open the URL, click **Start practice run**, and watch the shot list, current take, Grafana
panel, and agent decision log update over SSE. There is no login, signup, or browser
configuration.

Practice mode is the default. It calls no network, Gemini, Veo, Grafana, or paid API. It
replays Turning Point's five-shot safety/refusal, continuity, and budget-control story. It
ends with the 2000 field shot deliberately abandoned at `$12.50 / $15.00`. The playback
fixture is visibly marked scripted.

Live mode is server-only and uses Gemini plus Veo on Google Vertex AI, Grafana Cloud OTLP,
a real Grafana Mimir query before Gemini advises a retry, and Google Cloud Storage to stream
a completed Veo asset. No OpenAI, Anthropic, AWS, or Microsoft model/API is in the runtime
path. Secrets are environment variables only; no `NEXT_PUBLIC_*` secret is used.

## Run locally

Requirements: Python 3.12 and Node.js 20+.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
npm install
$env:CUTSCOPE_PYTHON = "$PWD\.venv\Scripts\python.exe"
npm run dev
```

Open `http://localhost:3000` and press **Start practice run**. This needs no `.env`, Google
credentials, Grafana account, or paid credit.

For a Live run, copy `.env.example` to `.env`, set the values, and provide Application
Default Credentials with `gcloud auth application-default login`. Live mode additionally
requires `GRAFANA_PROMETHEUS_URL`; set `GRAFANA_PROMETHEUS_INSTANCE_ID` and
`GRAFANA_PROMETHEUS_TOKEN` when they differ from the OTLP credentials. The Mimir endpoint
must end in `/api/prom`. Uncheck **Practice run** before starting. It reads
`shots/turning_point.yaml` and makes real paid Veo requests. `shots/demo.yaml` remains a
fixture only.

The original hidden CLI is still available for engine-only operation:

```powershell
python -m cutscope run shots/turning_point.yaml
```

## Cloud Run

The `Dockerfile` packages Node and Python into one Cloud Run container. It has not been
deployed. Before deploying, create a Cloud Run service account with Vertex AI and read-only
access to the Veo-output bucket, then give it Secret Manager access to the Grafana tokens.

```powershell
gcloud builds submit --tag gcr.io/YOUR_PROJECT/cutscope
gcloud run deploy cutscope --image gcr.io/YOUR_PROJECT/cutscope --region us-central1 --allow-unauthenticated --service-account SERVICE_ACCOUNT_EMAIL --set-env-vars GCP_PROJECT_ID=YOUR_PROJECT,GCP_REGION=us-central1,GRAFANA_OTLP_ENDPOINT=YOUR_OTLP_ENDPOINT,GRAFANA_INSTANCE_ID=YOUR_INSTANCE_ID,GRAFANA_PROMETHEUS_URL=YOUR_PROMETHEUS_API_BASE --set-secrets GRAFANA_OTLP_TOKEN=cutscope-grafana-otlp-token:latest,GRAFANA_PROMETHEUS_TOKEN=cutscope-grafana-prometheus-token:latest
```

Add `GRAFANA_PROMETHEUS_INSTANCE_ID` with `--set-env-vars` when needed. Keep this MVP to
one Cloud Run instance: active run state is process-local so the SSE stream, stop control,
and generated-asset proxy stay on one worker process. See [docs/WEB_CONSOLE.md](docs/WEB_CONSOLE.md)
for the Next.js/Python boundary.

## Verification status

- Verified: `python -m cutscope.web_worker --mode practice --run-id local-check` completed.
  It emitted the five Turning Point shots, a safety refusal/rephrase, a character-drift keep,
  a field reference anchor, and a budget-driven abandonment at `$12.50` before `run.finished`.
- Verified: the original engine test remains runnable with `pytest`.
- Not verified: Node dependency installation and `next build` did not complete before the
  environment command timeout. Live Vertex, Grafana, Storage, and Cloud Run paths were not
  invoked because they use real credentials and paid services. No deployment was performed.
