# CUTSCOPE

CUTSCOPE runs an AI film production shot by shot, using live evidence to decide whether to retry, rephrase, keep a take, or stop spending.
It solves the blind spot in multi-provider AI filmmaking: cost, failure rate, safety refusals, and character drift otherwise accumulate without a production-level decision record.
The demo uses the author's original *Turning Point* screenplay and makes each decision visible in the console.

Live console: [https://cutscope.rizqey.com](https://cutscope.rizqey.com)

Start with **Practice run**. It needs no account, credentials, or cloud credit, and costs nothing. It remains usable even when a reviewer does not have access to the live cloud services.

## What the demo shows

The five shots are derived from *Turning Point*, an original 13-episode screenplay written by the author. The author owns the source work used in this submission.

In the practice replay:

- Shot 01 is refused by a safety filter, then recovered with a rephrased prompt.
- Shot 03 records character drift but keeps a usable take when a retry is not justified.
- Shot 05 is abandoned after a second continuity failure: the controller stops at `$12.50 / $15.00` rather than buy another likely unusable attempt.

The production problem is based on the author's own AI-film work: 596 prompt attempts and 85 documented failures across Hailuo, Kling, Higgsfield, and Veo.

## Architecture

| Component | Runs where | Responsibility |
| --- | --- | --- |
| Next.js console and API routes | One container on Cloud Run | Public control console, practice/live toggle, SSE event stream, stop control, and playback proxy. |
| Python worker | The same Cloud Run container | Runs the shot loop and emits the production events consumed by the console. |
| Gemini decision agent and Veo | Vertex AI | Gemini decides the next action from the production evidence; Veo generates live video attempts. |
| Grafana Cloud | OTLP ingestion and Mimir query API | Receives telemetry over OTLP; the worker reads the live metric window before Gemini can advise a retry. |
| Cloud Storage | Google Cloud | Stores a completed live Veo asset for server-side playback. |

The production controller is a Gemini agent built on Google Cloud Agent Builder. Active run state is process-local, so the Cloud Run service is intentionally kept to one instance for this MVP.

## Real versus simulated

**Practice mode is simulated.** It is a scripted replay of the five-shot decision story. It makes no network requests and does not call Gemini, Veo, Grafana, or any paid API. The displayed playback is labelled as scripted.

**Live mode is real.** It runs the Python worker against Vertex AI for Gemini and Veo, exports telemetry to Grafana Cloud over OTLP, and queries Grafana Mimir before a retry decision. It requires valid Google Cloud and Grafana credentials and can incur Vertex AI charges.

## Run locally

These PowerShell commands are the local setup path for the current repository. They use Python 3.12, Node.js 22 or newer, the locked Node dependencies, and explicitly point the Next.js server at the virtual environment's Python executable.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm ci
$env:CUTSCOPE_PYTHON = "$PWD\.venv\Scripts\python.exe"
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and press **Start practice run**. No `.env` file, Google account, Grafana account, or paid credit is needed for that path.

To verify the production engine without the browser after setup:

```powershell
.\.venv\Scripts\python.exe -m cutscope.web_worker --mode practice --run-id local-check
```

## Configure a live run

Practice mode is the safe default. Only configure live mode when you intend to make real Vertex AI calls.

```powershell
Copy-Item .env.example .env
gcloud auth application-default login
```

Set the required values in `.env`: `GCP_PROJECT_ID`, `GCP_REGION`, `GRAFANA_OTLP_ENDPOINT`, `GRAFANA_INSTANCE_ID`, `GRAFANA_OTLP_TOKEN`, and `GRAFANA_PROMETHEUS_URL`. The Prometheus/Mimir URL must end in `/api/prom`. Set `GRAFANA_PROMETHEUS_INSTANCE_ID` and `GRAFANA_PROMETHEUS_TOKEN` only if they differ from the OTLP credentials. Then clear **Practice run** in the console and start the run. Live runs load `shots/turning_point.yaml`; `shots/demo.yaml` is only a fixture.

## Container and deployment

The `Dockerfile` packages Node.js and Python into one Cloud Run container. The public deployment is available at [cutscope.rizqey.com](https://cutscope.rizqey.com). For the application boundary and event flow, see [docs/WEB_CONSOLE.md](docs/WEB_CONSOLE.md).

## Licence

Licensed under the [Apache License 2.0](LICENSE).
