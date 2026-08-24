# CUTSCOPE web console seam

The public app is one Next.js deployment on Cloud Run. It has no browser login,
configuration screen, or browser-held credentials.

```text
Browser --SSE--> Next.js route handler --JSON Lines--> Python web_worker
                                                   |
                                                   +-- existing SliceOneOrchestrator
                                                        +-- Grafana OTLP gate
                                                        +-- Grafana Mimir query
                                                        +-- Gemini on Vertex AI
                                                        +-- Veo on Vertex AI
```

`POST /api/runs` starts a process-local Python worker. `GET /api/runs/:id/events`
replays its JSON Lines output then streams new events as SSE. `POST /api/runs/:id/stop`
terminates that worker, so no later attempt can be submitted. An already-submitted Veo
operation is not cancelled by this MVP; the worker stops polling it and cannot spend on a
follow-on attempt.

The adapter in `cutscope/web_worker.py` does not implement provider, budget, Gemini, or
telemetry logic. Live mode instantiates the existing `SliceOneOrchestrator`,
`VeoVertexProvider`, `GrafanaTelemetry`, and `GeminiDecisionAgent`. It adds an event sink
and `GrafanaMimirClient`, which queries the real Mimir window before Gemini receives a
retry decision. If the query is unavailable or returns no live data, the worker stops the
automatic retry instead of inventing a metric.

Practice mode is a separate scripted JSONL path. It makes no network, Gemini, Veo,
Grafana, or paid API call. Its visible `PRACTICE PLAYBACK` fixture is marked as a scripted
visual, not a generated take.

The live playback route only streams a `gs://` asset URI emitted by that run's worker. It
uses the Cloud Run service account to read Cloud Storage; no bucket credential or signed
URL is sent to the browser.
