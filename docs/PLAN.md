## 1. Product concept — **CUTSCOPE**

CUTSCOPE is an AI production-control agent for directors using multiple GenAI video tools. A creator imports a generation log or starts a new scene brief; CUTSCOPE traces every prompt, seed, reference, provider result, cost estimate, retry, failure, and character-drift score. Its Gemini-powered director agent diagnoses where production is wasting generations, proposes a tightly bounded next experiment, submits it to Veo when enabled, then recommends the best take with evidence. Grafana is not a dashboard bolted on afterward: the agent reads live Grafana metrics to decide whether to retry, switch prompt strategy, or stop burning budget.

## 2. Three-minute trailer narrative

| Time | What the judge sees | What proves |
|---|---|---|
| 0:00–0:15 | “Making AI films means hundreds of attempts across models. The director knows something is failing, but not where money and consistency are being lost.” Show a clean original cyberpunk-scene workspace, not Batman/IP footage. | Real problem and credible founder insight. |
| 0:15–0:35 | Upload `production-log.json` containing 222 historic-style generation events: prompts, seeds, references, provider, status, cost estimate, and failure reason. CUTSCOPE parses it into 12 shots. | Product accepts messy real workflow data rather than requiring a new workflow. |
| 0:35–0:55 | Show the CUTSCOPE timeline: 85 failures, 31% retry rate, the same character drifting on Shot 08, and one prompt/seed family producing the highest usable-take rate. | Clear product design and meaningful analysis. |
| 0:55–1:25 | Enter: “Give me a 7-second rainy rooftop reveal. Keep Mara’s amber visor and silhouette. Max $8.” The UI visibly invokes the deployed agent, not a frontend text completion. | Gemini + Google Cloud Agent Builder orchestration. |
| 1:25–1:50 | Agent activity stream: `Workspace Analyst → Grafana Telemetry Tool → Experiment Planner → Veo Job Tool`. It says: “Do not retry seed 8821: it has a 67% failure rate and high drift. Reuse reference pack R-14 and test two prompt variants.” | Tool use, deterministic evidence, and Grafana being decision-critical. |
| 1:50–2:15 | Open Grafana Cloud dashboard and Agent Observability trace. Show the same request ID: Gemini generation, tool calls, Veo job, Pub/Sub worker, latency, cost, retry, and result. | Genuine imported-and-runtime Grafana integration. |
| 2:15–2:35 | One Veo-generated candidate returns. CUTSCOPE compares it against the reference pack, marks a drift score, stores it, and recommends either “approve” or one constrained retry. | Google video generation at runtime and a closed-loop workflow. |
| 2:35–2:52 | Click “Approve take.” CUTSCOPE records the decision and creates a reusable “shot recipe”: prompt, seed, reference IDs, provider settings, cost, and reason it won. | Compounding production knowledge. |
| 2:52–3:00 | End card: “CUTSCOPE: stop guessing which generations work.” Show public URL, GitHub URL, and Grafana/Gemini/Google Cloud marks. | Clean handoff to submission. |

Use an original scene and synthetic/anonymized production metadata in the trailer. Do not show DC/Batman assets; the advantage is the workflow knowledge, not the IP.

## 3. Architecture

```text
Next.js UI on Cloud Run
        |
        v
Agent API / session endpoint
        |
        v
Vertex AI Agent Engine
Google ADK SequentialAgent, Gemini
  ├─ Workspace Analyst
  ├─ Telemetry Diagnostician
  ├─ Experiment Planner
  └─ Take Reviewer
        |                 \
        v                  v
Firestore + GCS          Grafana Cloud APIs
        |
        v
Pub/Sub -> Cloud Run generation worker -> Vertex AI Veo
        |
        +-> Firestore/GCS result records
        +-> Grafana Agent Observability + OTLP
```

### Runtime components

- **Next.js/TypeScript UI, deployed to Cloud Run**
  - Uploads a JSON/CSV event log and reference images.
  - Shows shot timeline, agent stream, proposed experiment, candidate takes, and decision history.
  - Cloud Run is preferable to Vercel here: the public web app, API proxy, and Google identity all live in one deployable Google Cloud surface.

- **Vertex AI Agent Engine / Google Cloud Agent Builder**
  - Build with Python Google ADK, deploy as an actual Agent Engine resource, and invoke it through the Agent Engine API.
  - Pin a tested Gemini model available in the selected Vertex region; use a fast Gemini model for analysis and a stronger Gemini model only for final director reports if needed.
  - Google documents Agent Engine dependencies through `google-cloud-aiplatform[agent_engines,adk]`; use that supported route rather than presenting a Cloud Run chatbot as the agent. [Google Cloud Agent Engine setup](https://cloud.google.com/agent-builder/agent-engine/set-up)

- **ADK orchestration**
  - `WorkspaceAnalystAgent`: calls `load_workspace`, `get_shot_history`, and `get_reference_pack`.
  - `TelemetryDiagnosticianAgent`: must call `query_grafana_window` before recommending a retry or a provider change.
  - `ExperimentPlannerAgent`: produces a structured plan constrained by budget, visual constraints, and maximum attempts; calls `create_experiment` and optionally `submit_generation`.
  - `TakeReviewerAgent`: calls `get_generation_status`, `score_candidate`, and `record_take_decision`.
  - Use an ADK `SequentialAgent` around these agents. The UI invokes one root agent; the handoffs and tool results are visible in the trace.

- **Firestore**
  - Projects, shots, prompt variants, seeds, generation attempts, decisions, and agent session state.
  - Use Firestore, not Cloud SQL. The MVP needs flexible nested records and fast iteration, not relational reporting.

- **Cloud Storage**
  - Raw imported logs, reference images, generated clips, thumbnails, and exported shot recipes.
  - Store metadata in Firestore; do not put video binaries in Firestore.

- **Pub/Sub**
  - `generation.requested` and `generation.completed` events.
  - Separates a long-running video operation from the agent request and makes retries idempotent.

- **Cloud Run generation worker**
  - Consumes Pub/Sub events, calls the provider adapter, polls long-running operations, persists the result, and emits telemetry.
  - Use a service account with only Storage, Firestore, Pub/Sub, Vertex AI, and Secret Manager permissions required.

### Agent tool contracts

```python
load_workspace(project_id) -> {shots, budget, references}
get_shot_history(project_id, shot_id) -> {attempts, seeds, failure_taxonomy}
query_grafana_window(project_id, shot_id, window) -> {retry_rate, cost, drift, p95_latency}
create_experiment(project_id, shot_id, constraints) -> {experiment_id, variants}
submit_generation(experiment_id, provider, variant_id) -> {job_id, status}
get_generation_status(job_id) -> {status, asset_uri, cost_estimate, error}
score_candidate(shot_id, asset_uri, reference_pack_id) -> {drift_score, rubric}
record_take_decision(shot_id, candidate_id, decision, rationale) -> {recipe_id}
```

The model decides *which* tool to call and how to interpret evidence. Code, not Gemini, enforces budget ceilings, max retries, schema validation, and provider submission.

## 4. Grafana integration

Use **Grafana Cloud Agent Observability + Grafana Cloud OTLP ingestion**. This gives a purposeful agent-observability view plus Mimir metrics, Tempo traces, and Loki logs. Grafana’s Agent Observability supports Google ADK and captures agent generations, workflow steps, tool calls, cost, latency, and errors. [Grafana framework support](https://grafana.com/docs/grafana-cloud/observe-and-act/agent-observability/guides/instrument-agents/)

### Mandatory runtime code evidence

Lock tested versions in `requirements.txt`:

```txt
google-adk
google-cloud-aiplatform[agent_engines,adk]
agento11y
agento11y-google-adk
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
```

At agent startup, instantiate the Grafana client and configure OpenTelemetry before the ADK agent is created:

```python
from agento11y import Client
from opentelemetry import metrics, trace

grafana_client = Client()  # reads AGENTO11Y_* credentials
```

Install and wire the `agento11y-google-adk` adapter to the ADK runner according to the tested package release. The documented Python package name is `agento11y-google-adk`; do not guess an adapter symbol without checking that release’s README. [Grafana Python instrumentation](https://grafana.com/docs/grafana-cloud/observe-and-act/agent-observability/get-started/python/)

This is stronger than merely emitting generic logs: the Grafana SDK is imported, instantiated, receives every Gemini agent generation and workflow step at runtime, and exports directly to Grafana Agent Observability. Configure OTLP with Grafana Cloud’s endpoint and scoped access token so traces and metrics reach the same stack. Grafana explicitly requires a configured `TracerProvider` and `MeterProvider`; otherwise these signals are silently dropped. [Grafana setup requirements](https://grafana.com/docs/grafana-cloud/observe-and-act/agent-observability/get-started/grafana-cloud/)

### Instrumented signals

- `cinema_generation_requests_total{provider,model,status,shot_type}`
- `cinema_generation_cost_usd_total{provider,model}`
- `cinema_generation_duration_seconds` histogram
- `cinema_generation_failures_total{provider,failure_code}`
- `cinema_generation_retries_total{provider}`
- `cinema_character_drift_score` histogram
- `cinema_queue_age_seconds` histogram
- `cinema_prompt_variant_wins_total{strategy}`
- Standard `gen_ai.*` spans/metrics for Gemini calls, token use, tool calls, and latency.

Keep labels bounded. Never use full prompt text, raw seed, user ID, or generation ID as a metric label. Put request/job IDs in Tempo trace attributes and Loki structured metadata instead.

### Runtime flow

1. Agent Engine receives an agent request and creates a root trace.
2. ADK/Gemini calls and tool workflow steps are sent through `agento11y`.
3. The agent’s `query_grafana_window` tool queries the Grafana Mimir datasource through Grafana’s authenticated query API.
4. Cloud Run worker propagates the trace context into Pub/Sub attributes and records the Veo operation lifecycle.
5. JSON logs go to Loki; traces go to Tempo; metrics go to Mimir; agent conversations and workflow graph go to Agent Observability.

### Dashboard: “CUTSCOPE Production Control Room”

- Cost burn and remaining budget, by provider and shot.
- Failure/retry heatmap by provider, model, and shot type.
- Character drift distribution, sorted by shot.
- Prompt/seed strategy leaderboard: usable-take rate versus cost.
- Queue age and generation latency.
- Click-through from a failed generation to its Tempo trace and Loki logs.
- Agent Observability conversation showing the exact Gemini reasoning/tool sequence.

Grafana is indispensable because `query_grafana_window` is a required agent tool: retry recommendations use live rolling failure, cost, and drift signals from Mimir, not a static database query. If Grafana is unavailable, the agent must return “telemetry unavailable; no automatic retry recommendation,” not fabricate a recommendation.

## 5. Video-model layer

Use one narrow provider interface:

```ts
interface VideoProvider {
  name: "veo" | "imported";
  estimate(input: GenerationInput): Promise<CostEstimate>;
  submit(input: GenerationInput): Promise<{ jobId: string }>;
  status(jobId: string): Promise<GenerationStatus>;
}
```

### MVP provider: Vertex AI Veo

- Implement `VeoVertexAdapter` only.
- The worker submits a text-to-video request to Vertex AI, stores the long-running operation name, polls it, and writes the resulting asset URI to GCS/Firestore.
- Start with one seven- or eight-second generation in the live demo. Do not make the trailer depend on a batch of costly jobs.
- Veo text-to-video is a documented Vertex AI surface; its model IDs, regions, quotas, and preview status can change, so validate the exact chosen model and region on day 2 before building around it. [Veo on Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos-from-text)

### Imported-run adapter

- `ImportedRunAdapter` does not generate video.
- It accepts a prior result exported from another tool: provider name, prompt, seed, references, status, cost estimate, file URL, and failure reason.
- This is what makes CUTSCOPE useful to directors who already use Hailuo, Kling, Higgsfield, Luma, or similar tools without requiring an unreliable unofficial API integration.

### Compliance rule

- **Sora is banned. Do not include its SDK, API, demo footage, fallback, or reference in runtime code.**
- The only live generation provider in the MVP should be **Google Veo**.
- Hailuo/MiniMax, Kling, Higgsfield, Luma, Udio, and ElevenLabs are not named in the stated ban, but do not call them from the product unless their official API availability, terms, and underlying service path are confirmed during the contest. Their public API surfaces are not reliable enough to make them a hackathon dependency.
- If Veo credentials or quota are unavailable, the app remains a functional Gemini/Agent Engine analysis and experiment-planning agent using imported runs. The UI must clearly say “Veo connection not configured”; it must not fake a generation.

## 6. Fifteen-day build schedule

| Day | Deliverable |
|---|---|
| 1 | Create brand-new public Git repository, initial commit, Apache-2.0 `LICENSE`, issue board, one-page architecture, GCP project, Grafana Cloud stack. |
| 2 | Verify Gemini region/model, deploy a minimal ADK Gemini agent to Agent Engine, make one real invocation, and capture it in Grafana Agent Observability. This is the first hard technical gate. |
| 3 | Build Firestore schema, GCS upload path, import validator, and seeded original demo workspace. |
| 4 | Build Next.js UI: project page, shot timeline, import flow, candidate card. |
| 5 | Build ADK tool layer: workspace/history/reference tools and deterministic scoring helpers. |
| 6 | Add the three-agent sequential orchestration and stream its progress to the UI. |
| 7 | Add OTLP metrics, logs, traces, Grafana dashboard JSON, and `query_grafana_window` tool. |
| 8 | **Demo-able milestone:** imported workspace → deployed Gemini agent → Grafana-informed diagnosis → experiment plan → saved shot recipe. Record a rough end-to-end screen capture. |
| 9 | Build Pub/Sub and Cloud Run worker with the `ImportedRunAdapter`; prove async status and telemetry correlation. |
| 10 | Implement and verify `VeoVertexAdapter` with one real generated clip. If blocked, freeze the imported-run path and preserve the working demo. |
| 11 | Candidate reviewer, character-drift heuristic, approval decision, and recipe export. |
| 12 | Design pass: empty states, clear telemetry language, loading/error states, mobile-safe public presentation. |
| 13 | Deploy production environment, add budget alert, quota guard, public read-only demo project, and smoke tests. |
| 14 | Record final 3-minute trailer, create architecture diagram/screenshots, write README and Devpost answers. |
| 15 | Rehearse from a fresh browser, verify public URL/repo/license/video, submit at least 12 hours before deadline. |

## 7. Scope cuts

Do not build:

- A full NLE/editor, timeline renderer, or video stitching system.
- Direct integration with five external video providers.
- Automatic semantic video-quality judgment claiming to replace a director.
- Team collaboration, billing, OAuth, marketplace, or mobile app.
- Fine-tuning, RAG, vector search, or a knowledge graph.
- A generic “chat with your project” interface.

Smallest winning version:

- One original project with 12 imported shots.
- One real Gemini/ADK workflow deployed to Agent Engine.
- One live Veo generation.
- One Grafana-driven retry/no-retry decision.
- One usable shot recipe export.
- One exceptional, legible Grafana trace/dashboard showing the agent’s decisions against actual production telemetry.

## 8. Top risks and mitigations

| Risk | Mitigation |
|---|---|
| Veo access, region, quota, or preview API changes block live generation. | Validate on day 2. Keep Veo behind one adapter. Make imported-run analysis the core product; record the live Veo segment immediately after it works. |
| Judges see a polished UI but conclude it is a plain web app. | Show the Agent Engine resource, streamed ADK sub-agent/tool sequence, Gemini generation in Grafana Agent Observability, and the tool-driven decision in the trailer. Put deployment commands and architecture in README. |
| Grafana looks decorative. | Make `query_grafana_window` mandatory for retry recommendations. Demonstrate a recommendation changing because the Grafana failure/cost/drift window is bad. Include SDK imports, runtime credentials, trace IDs, dashboards, and query-tool code. |
| Provider costs or retries consume credits. | Enforce per-project budget and max-attempt policy in code; one live Veo run only; Cloud Billing budget alerts; Cloud Run scale-to-zero; retain a small paid billing reserve through judging. |
| Judges cannot use the product after credits expire. | Do not rely solely on promotional credits. Keep billing active through the judging window, set low service caps, preserve a public seeded demo workspace, and add a health endpoint checked daily. If live generation must be disabled, the deployed Gemini Agent Engine analysis path remains live and explicitly labels Veo as unavailable; never substitute a fake result. |
| Imported metadata is inconsistent or lacks seeds/costs. | Validate into a minimal canonical schema; mark unknown fields as unknown; never invent costs or seed lineage. Include a clean sample import in the public repo. |
