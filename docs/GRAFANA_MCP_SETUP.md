# Grafana MCP — what a human has to click

CUTSCOPE splits its telemetry loop across two protocols on purpose:

| Direction | Protocol | Code |
|---|---|---|
| **Write** metrics + spans into Grafana Cloud | OTLP over HTTP | `cutscope/telemetry.py` |
| **Read** the shot window back out | **Grafana MCP server** (`tools/call query_prometheus`) | `cutscope/mcp_grafana.py` → `cutscope/grafana_query.py` |

The Grafana partner track requires the Grafana stack to be used at runtime
"primarily through the Grafana Cloud MCP server". An OTLP push alone does not
satisfy it. The read path is therefore MCP-first, and every metrics window the
Gemini agent is shown carries a `source` field naming which path produced it
(`grafana_mcp` or `grafana_prometheus_http_fallback`) so the run can never look
like it used MCP when it did not.

---

## Status right now — two things block a live MCP call

**1. The Grafana stack is asleep.** Every request to
`https://narrowamaranth830.grafana.net` currently returns HTTP 503:

```
{"code":"Loading","message":"Click on the checkbox to continue loading your instance"}
```

Grafana Cloud free stacks suspend when idle and only a browser session wakes
them. **Fix:** sign in at <https://narrowamaranth830.grafana.net>, click the
checkbox, wait for the dashboard to load. Nothing in this repo can do it.

**2. The only token we hold cannot read.** `GRAFANA_OTLP_TOKEN` decodes to:

```json
{"o":"1816661","n":"stack-1695752-otlp-write-claude-code-1","m":{"r":"prod-ap-southeast-1"}}
```

It is an access-policy token scoped to **`otlp:write`**. It is push-only. It was
verified to be rejected with **HTTP 401** by `https://mcp.grafana.com/mcp`:

```
{"error":"invalid_token","error_description":"missing or invalid Bearer token"}
```

A read credential has to be created. Pick one of the two options below.

---

## Option A (recommended) — run the open source `grafana/mcp-grafana` server

This is literally "the official grafana/mcp-grafana server" the rule names, it
takes a static token so it works headless on Cloud Run, and it needs no OAuth
browser dance.

**Step 1 — create a Grafana service account token.**

1. Wake the stack (see above).
2. <https://narrowamaranth830.grafana.net> → **Administration → Users and access
   → Service accounts → Add service account**.
3. Name it `cutscope-mcp`, role **Viewer**.
   *Viewer is enough:* the read path only calls `list_datasources` and
   `query_prometheus`, which need `datasources:read` and `datasources:query`.
   Do not grant Editor or Admin — CUTSCOPE never writes through MCP.
4. **Add service account token** → copy the `glsa_…` value. It is shown once.

**Step 2 — run the server.** It listens on `/mcp` with Streamable HTTP.

```bash
docker run -d --name cutscope-mcp -p 8000:8000 \
  -e GRAFANA_URL=https://narrowamaranth830.grafana.net \
  -e GRAFANA_SERVICE_ACCOUNT_TOKEN=glsa_xxxxxxxx \
  mcp/grafana -t streamable-http
```

For Cloud Run, add the same binary to the image as a second process and point
`GRAFANA_MCP_URL` at `http://127.0.0.1:8000/mcp`. (The Dockerfile change is
owned by whoever owns `Dockerfile`; this file only states what it needs.)

**Step 3 — point CUTSCOPE at it.** In `.env`:

```
GRAFANA_MCP_URL=http://127.0.0.1:8000/mcp
# Only needed if the server was started with MCP_GRAFANA_SERVER_TOKEN.
GRAFANA_MCP_TOKEN=
```

---

## Option B — Grafana's hosted MCP endpoint

Endpoint `https://mcp.grafana.com/mcp`, Streamable HTTP (SSE is not supported).

The catch: it authorises with **OAuth 2.1 only**. There is no static
service-account or access-policy token that works, which is why the OTLP token
returns 401. You have to complete the browser consent flow and supply the
resulting **access token**:

```
GRAFANA_MCP_URL=https://mcp.grafana.com/mcp
GRAFANA_MCP_TOKEN=<oauth access token>
GRAFANA_URL=https://narrowamaranth830.grafana.net
```

`GRAFANA_URL` becomes the `X-Grafana-URL` header, which tells the hosted server
which stack to talk to. Grant **Read** on the consent screen; CUTSCOPE never
needs Write.

Access tokens expire. For an unattended Cloud Run job that is a real operational
problem, which is why Option A is the recommendation.

---

## Verifying it works

```bash
# offline: protocol framing, PromQL construction, failure handling
python -m cutscope.mcp_grafana
python -m cutscope.grafana_query

# live: connect, list tools, print the Prometheus tool schemas
python -m cutscope.mcp_grafana --probe
```

`--probe` prints the negotiated server info and the tool list. If the credential
is wrong it fails with the exact scope you are missing rather than falling
through silently.

---

## Environment variables this adds

| Variable | Meaning |
|---|---|
| `GRAFANA_MCP_URL` | MCP endpoint. Defaults to the hosted endpoint if only a token is set. |
| `GRAFANA_MCP_TOKEN` | Bearer token. Service-account token (Option A) or OAuth access token (Option B). |
| `GRAFANA_URL` | Stack URL, sent as `X-Grafana-URL`. Only needed for the hosted endpoint. |
| `GRAFANA_MCP_TIMEOUT_SECONDS` | Per-call timeout, default 20. |
| `GRAFANA_PROMETHEUS_DATASOURCE_UID` | Skip `list_datasources` discovery and use this uid. |
| `GRAFANA_PROMETHEUS_URL` | Direct Mimir URL — **fallback only**, no longer required for live mode. |

Neither read path is required at import time. Live mode needs at least one of
`GRAFANA_MCP_URL` or `GRAFANA_PROMETHEUS_URL`, and says so if both are missing.

---

## Metric names — why the queries look the way they do

The names passed to the OpenTelemetry SDK are **not** the names that land in
Mimir. Verified by running `prometheus/otlptranslator` v1.0.0, the translator
Prometheus and Mimir actually use:

| SDK name | unit | lands in Mimir as |
|---|---|---|
| `cutscope_generation_attempts_total` | `{attempt}` | `cutscope_generation_attempts_total` |
| `cutscope_generation_estimated_cost_usd_total` | `USD` | **`cutscope_generation_estimated_cost_usd_USD_total`** |
| `cutscope_generation_duration_seconds` | `s` | `cutscope_generation_duration_seconds` |
| `cutscope_generation_outcomes_total` | `{attempt}` | `cutscope_generation_outcomes_total` |

Attributes lose their dots: `cutscope.shot.id` → `cutscope_shot_id`,
`cutscope.outcome` → `cutscope_outcome`. **Dots are not legal in Prometheus
label names**, so the previous selectors were parse errors, not just misses.

Braced units are annotations and get dropped. `USD` is not a recognised unit, so
the translator inserts it verbatim before `_total`. The cost query therefore
matches on `__name__=~"cutscope_generation_estimated_cost_usd(_USD)?_total"`,
which is correct whether or not the gateway applies unit suffixing.

> **Optional cleanup for whoever owns `cutscope/telemetry.py`:** changing that
> counter's unit from `"USD"` to `"{usd}"` makes the braces-are-annotations rule
> drop it, and the series becomes the clean
> `cutscope_generation_estimated_cost_usd_total`. The regex above keeps working
> either way, so this is cosmetic, not required.
