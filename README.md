# CUTSCOPE

CUTSCOPE runs an AI film production shot by shot, using live evidence to decide whether to retry, rephrase, keep a take, or stop spending.
It solves the blind spot in multi-provider AI filmmaking: cost, failure rate, safety refusals, and character drift otherwise accumulate without a production-level decision record.
The demo uses the author's original *Turning Point* screenplay and makes each decision visible in the console.

Live console: [https://cutscope.rizqey.com](https://cutscope.rizqey.com)

Start with **Practice run**. It needs no account, credentials, or cloud credit, and costs nothing. It remains usable even when a reviewer does not have access to the live cloud services.

## What the demo shows

The five shots are derived from *Turning Point*, an original 13-episode screenplay written by the author. The author owns the source work used in this submission.

The practice replay takes about 60 seconds end to end and produces four kinds of judgment:

- **Shot 01 — safety refusal, then recovery.** Attempt 1 is refused. The controller names the trigger phrase, rephrases to keep the visual intent without weapon-like wording, and the second attempt is kept. Shot cost `$0.96` of a `$3.00` ceiling.
- **Shot 03 — keep a flawed take.** Identity consistency lands at 78% against an 85% target. The drift is logged and the take is kept, because a paid retry is not worth it at this margin.
- **Shot 04 — set the anchor.** The 2012 field take becomes the geography Shot 05 must match.
- **Shot 05 — abandon.** Location continuity reaches only 42%, then 58%, against a 90% target. Both attempts drift the same way, which reads as a model limit rather than a prompt fault, so the run stops on the shot at `$0.80` of its `$2.50` ceiling and leaves the remaining `$11.88` of the `$15.00` run budget unspent.

The run finishes at `$3.12 / $15.00`. These figures are not hardcoded prose: the replay derives every dollar from the same `VeoCostEstimator` a live run uses (`veo-3.1-fast-generate-001`, `$0.08`/second of 720p video), and the worker raises rather than print a figure that would breach a shot ceiling or the run budget.

The production problem is based on the author's own AI-film work: 596 prompt attempts and 85 documented failures across Hailuo, Kling, Higgsfield, and Veo.

## Architecture

| Component | Runs where | Responsibility |
| --- | --- | --- |
| Next.js console and API routes | One container on Cloud Run | Public control console, practice/live toggle, SSE event stream, stop control, and playback proxy. |
| Python worker | The same Cloud Run container | Runs the shot loop and emits the production events consumed by the console. |
| Gemini decision agent and Veo | Vertex AI | Gemini advises the next action from the production evidence; Veo generates live video attempts. |
| Grafana Cloud | OTLP ingestion, then a metrics read | Receives telemetry over OTLP. On a live run the worker reads the shot's metric window back out before Gemini is asked for advice. |
| Cloud Storage | Google Cloud | Stores a completed live Veo asset for server-side playback. |

The production controller is a **Gemini 2.5 agent called on Vertex AI** through the `google-genai` SDK (`cutscope/decision.py`). It advises; a hard budget and attempt ceiling in the same module decides. The model cannot authorise spending — `enforce_decision()` runs after the model returns and can only ever downgrade the outcome to `ABANDON`, against the controller's own attempt ledger rather than against anything Grafana returned. `tests/test_decide.py` proves Gemini advising `RETRY_SAME` at the ceiling still yields `ABANDON`.

There is no Agent Builder / Agent Engine resource and no ADK agent in this repository. Where `docs/PLAN.md` describes one, that is the intended future shape, not what ships.

Active run state is process-local (`lib/run-store.ts` holds runs and their event buffers in memory), so the Cloud Run service is pinned to a single instance — `autoscaling.knative.dev/maxScale=1`. A second instance would serve SSE requests for runs it has never heard of.

## Real versus simulated

**Practice mode is simulated.** It is a scripted replay of the five-shot decision story. It makes no network requests and does not call Gemini, Veo, Grafana, or any paid API. Every evidence line it writes is prefixed `Scripted:`; only a live run is allowed to prefix a line `Grafana:`. The console header carries a `PRACTICE` pill for the whole run — reading `PRACTICE · scripted replay · no paid API calls` at desktop width, and shortening on narrow screens — and the displayed playback is labelled as scripted.

**Live mode is real.** It runs the Python worker against Vertex AI for Gemini and Veo, exports telemetry to Grafana Cloud over OTLP, and reads a metrics window back out of Grafana before a retry decision. It requires valid Google Cloud and Grafana credentials and can incur Vertex AI charges.

Live mode is closed on the public deployment by design: `POST /api/runs` with `mode: "live"` is rejected with HTTP 403 unless `CUTSCOPE_OPERATOR_TOKEN` is set on the server, and HTTP 401 unless the caller presents it. A reviewer on cutscope.rizqey.com sees the practice path; a live run is an operator action.

### What is verified today

Stated plainly so nothing here is a surprise under test:

| Path | Status (checked 25 Aug 2026) |
| --- | --- |
| Practice replay, locally and on the public site | Working. 61s, 41 events, ends `$3.12 / $15.00`. |
| Grafana OTLP **write** credentials | Working. `POST` to the OTLP gateway with the `.env` credentials returns HTTP 200. |
| Grafana **read** path | Not currently available. The stack URL returns HTTP 404, and `GRAFANA_MCP_URL` / `GRAFANA_MCP_TOKEN` are unset, so the read would fall back to direct Mimir HTTP — and that needs `GRAFANA_PROMETHEUS_URL`, which is not set either. See `docs/GRAFANA_MCP_SETUP.md`. |
| Live Vertex AI run | Not exercised from this checkout. |

The read path labels its own provenance rather than asserting one. Every metrics window handed to Gemini carries a `source` field — `grafana_mcp` when the Grafana MCP server served it, `grafana_prometheus_http_fallback` when the direct Mimir query did — plus an `mcp_used` boolean. A run can therefore never look like it used MCP when it did not.

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
.\.venv\Scripts\python.exe -m pytest -q
```

The worker prints the same JSON event stream the console consumes. Set `CUTSCOPE_PRACTICE_SPEED=3` to compress the 60-second replay when recording.

## Configure a live run

Practice mode is the safe default. Only configure live mode when you intend to make real Vertex AI calls.

```powershell
Copy-Item .env.example .env
gcloud auth application-default login
```

Set `GCP_PROJECT_ID`, `GCP_REGION`, `GRAFANA_OTLP_ENDPOINT`, `GRAFANA_INSTANCE_ID`, and `GRAFANA_OTLP_TOKEN` for the write path.

For the read path, set **either** `GRAFANA_MCP_URL` and `GRAFANA_MCP_TOKEN` (the Grafana MCP server, which is the primary path) **or** `GRAFANA_PROMETHEUS_URL` for the direct Mimir fallback — that URL must end in `/api/prom`. Set `GRAFANA_PROMETHEUS_INSTANCE_ID` and `GRAFANA_PROMETHEUS_TOKEN` only if they differ from the OTLP credentials. A live run refuses to start with neither configured, rather than silently running blind.

Set `CUTSCOPE_OPERATOR_TOKEN` on the server to enable the live path at all, then clear **Practice run** in the console and start the run. Live runs load `shots/turning_point.yaml`; `shots/demo.yaml` is only a fixture.

## Container and deployment

The `Dockerfile` packages Node.js and Python into one Cloud Run container. The public deployment is available at [cutscope.rizqey.com](https://cutscope.rizqey.com), in project `cutscope`, region `us-central1`, pinned to one instance. For the application boundary and event flow, see [docs/WEB_CONSOLE.md](docs/WEB_CONSOLE.md).

## Licence

Licensed under the [Apache License 2.0](LICENSE).
