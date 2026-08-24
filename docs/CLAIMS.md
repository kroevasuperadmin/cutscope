# CLAIMS.md — wording that matches what the code actually does

Every line below is a claim a judge can test. Where the current copy overstates
the build, the exact replacement text is given. **Use the "Say this" column
verbatim.** A claim a judge checks and finds false costs more than a missing
feature.

---

## 1. The decision agent is NOT on Agent Builder / Agent Engine

**What the code does.** `cutscope/decision.py` → `GeminiDecisionAgent.advise()`
calls `client.models.generate_content(...)` through the `google-genai` SDK
against **Vertex AI**, with `response_mime_type="application/json"`. It is a
direct model call inside the Cloud Run worker. There is no ADK agent, no
`LlmAgent`, no deployed Agent Engine resource, no reasoning-engine ID.

**Why it was left that way** (decision taken deliberately, not by omission):

- Agent Engine requires deploying a separate GCP resource with a staging
  bucket and IAM, and invoking it over the Agent Engine API. That is a
  deploy-time dependency that could not be exercised or verified in this
  environment — `gcloud auth application-default print-access-token` returns an
  error here, so no Vertex call of any kind is runnable.
- Shipping an unverifiable rewrite of the one component that gates spending,
  two weeks before the deadline, trades a working system for an untested one.
- **It is still rules-compliant.** The track requires Google Cloud AI tools —
  "Gemini models on Agent Platform, BigQuery ML, and relevant APIs". Gemini on
  Vertex AI is exactly that. The compliance problem was never the architecture,
  only the word "Agent Builder".

So the fix is the wording, not the code.

### Replace these three

| File | Line | Currently says | Say this |
|---|---|---|---|
| `components/production-console.tsx` | 201 | "A Gemini agent on Google Cloud Agent Builder runs each shot and reads live Grafana metrics to decide whether to retry, rephrase, or stop spending." | "A Gemini 2.5 agent on Vertex AI runs each shot and reads live Grafana metrics back through the Grafana MCP server to decide whether to retry, rephrase, or stop spending. The budget ceiling is enforced in code, not by the model." |
| `README.md` | 33 | "The production controller is a Gemini agent built on Google Cloud Agent Builder." | "The production controller is a Gemini 2.5 agent called on Vertex AI. It advises; a hard budget and attempt ceiling in `cutscope/decision.py` decides. The model cannot authorise spending." |
| `docs/BRIEF_JUDGE.md` | 18 | "a Gemini agent on Google Cloud Agent Builder that runs the production shot…" | "a Gemini 2.5 agent on Vertex AI that runs the production shot…" |

`docs/PLAN.md` describes Agent Engine as the *intended* design. That is fine —
it is a plan document. Do not let its wording leak into README, UI, or the
submission text as though it shipped.

### Safe phrasings

- ✅ "Gemini 2.5 on Vertex AI"
- ✅ "a Gemini agent" — it observes metrics, reasons, and picks an action
- ✅ "agentic retry loop", "agent-driven production control"
- ❌ "Agent Builder" / "Agent Engine" / "deployed agent resource" / "ADK"

---

## 2. The agent advises — code decides

Worth stating outright, because it is a strength and it is verifiable.

`enforce_decision()` in `cutscope/decision.py` runs **after** the model returns
and can only ever downgrade the outcome to `ABANDON`. Three ceilings, all in
code:

- spend already at or above the shot's ceiling
- spend **plus the next attempt's estimate** would exceed the ceiling
- attempt count at or above the shot's `max_attempts`

They are evaluated against the controller's own attempt ledger, not against the
numbers returned by Grafana, so a stale or unavailable dashboard can never widen
a budget. A `Decision` produced this way carries `enforced_by_code=True`, which
the UI can show. `tests/test_decide.py` proves Gemini advising `RETRY_SAME` at
the ceiling still yields `ABANDON`.

**Say:** "The model recommends. A hard rule in code enforces. Gemini cannot talk
CUTSCOPE into spending money."

---

## 3. Grafana — write over OTLP, read over MCP

**Say:** "CUTSCOPE writes metrics and traces to Grafana Cloud over OTLP, and
reads them back through the Grafana MCP server's `query_prometheus` tool. The
numbers the agent reasons over are fetched out of Grafana, not out of local
memory."

Conditions on that claim:

- It is true **only when `GRAFANA_MCP_URL` / `GRAFANA_MCP_TOKEN` are set.**
  Setup in `docs/GRAFANA_MCP_SETUP.md`. As of this writing they are not, and two
  things block it: the Grafana stack is suspended (503, needs a browser click),
  and the only token in `.env` is scoped `otlp:write`, which the hosted MCP
  endpoint rejects with 401 (verified).
- When MCP is unavailable the code falls back to a direct Prometheus HTTP query
  and **labels the result** `source: "grafana_prometheus_http_fallback"` with
  `mcp_used: false`. The MCP path sets `source: "grafana_mcp"`, `mcp_used: true`,
  and records the endpoint, tool name and datasource UID.
- ❌ Do not say "reads via MCP" while a run is showing
  `grafana_prometheus_http_fallback`. The field is in the payload; a judge can
  see it.

---

## 4. Practice mode

**Say:** "Practice mode replays a scripted run and makes no paid API calls.
Live mode calls Vertex AI for real." Never present a practice run's output as a
live generation.

---

## 5. Content

"Turning Point" is the author's own original screenplay. This is a genuine
differentiator against prompt-collage entries — say it plainly, once.
