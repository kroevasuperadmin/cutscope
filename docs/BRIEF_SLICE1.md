Read ./docs/PLAN.md first — it is the architecture you produced earlier for this project.
Then build SLICE 1 into this repo. Working code, not a sketch.

## HARD CONSTRAINTS (hackathon rules — violating any of these disqualifies)
- Runtime LLM/video calls: GOOGLE ONLY. Gemini and Veo via Vertex AI.
- FORBIDDEN at runtime: any OpenAI, Anthropic, AWS or Microsoft model or API. No exceptions.
- Grafana observability must be genuinely called at runtime and load-bearing, not decorative.
- Python 3.12. Standard library plus google-genai / google-cloud-* and the OTel SDK.
  Do not add heavy frameworks.

## ALREADY PROVISIONED — read from .env, never hardcode
  GRAFANA_OTLP_ENDPOINT   (verified working, returns 200)
  GRAFANA_INSTANCE_ID
  GRAFANA_OTLP_TOKEN      (auth = Basic base64("<INSTANCE_ID>:<TOKEN>"))
  GCP_PROJECT_ID=cutscope (billing live, Vertex AI verified with a real call)
Verified available Vertex models: gemini-2.5-flash, gemini-3.7-flash, veo-3.1-generate-001,
veo-3.1-fast-generate-001, veo-2.0-generate-001. Region us-central1.

## WHAT SLICE 1 MUST DO
The smallest end-to-end loop that proves the thesis:

1. A shot is declared in a small schema (id, prompt, reference image path, expected
   duration, character ids present, max attempts, budget ceiling in USD).
2. A generator submits that shot to Veo and polls the long-running operation to completion.
3. EVERY attempt emits telemetry to Grafana over OTLP before anything else happens:
     - attempt count per shot
     - wall-clock latency
     - estimated USD cost
     - outcome enum: success | refused | error | timeout
     - provider and model id
   Refusals must be detected and labelled distinctly from errors. A safety refusal is a
   first-class outcome in this system, not an exception to swallow.
4. A Gemini agent (gemini-2.5-flash) is given the shot's own live metrics and decides:
   RETRY_SAME | RETRY_REPHRASED | ABANDON. Cost ceiling breach forces ABANDON in code,
   not by asking the model — the model advises, the budget rule is hard.
5. Everything runs from one CLI: `python -m cutscope run shots/demo.yaml`

## ALSO REQUIRED
- Provider behind ONE interface (`VideoProvider` ABC with `submit()` / `poll()`), so a
  second provider can be added later without touching the orchestrator.
- Graceful degradation: if a credential is missing, the run must fail with a clear message
  naming the missing variable — never a stack trace.
- One runnable check: a `tests/test_decide.py` that proves the budget rule overrides the
  model's advice. Assert-based, no framework beyond pytest.
- A `shots/demo.yaml` with 3 example shots.
- Update README with exact run instructions.

Do not build: web UI, auth, database, Cloud Run deployment, multi-user anything.
Those are later slices. Write the code, run it as far as credentials allow, and report
what you verified versus what is untested.
