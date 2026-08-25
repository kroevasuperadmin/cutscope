Make the Grafana MCP call actually work in production. This is the LAST mandatory
requirement gap. Read docs/GRAFANA_MCP_SETUP.md, cutscope/mcp_grafana.py,
cutscope/grafana_query.py and Dockerfile fully first.

## WHERE THINGS STAND — verified, not assumed
- The partner-track rule says the project must use Grafana at runtime "primarily through the
  Grafana Cloud MCP server (the official grafana/mcp-grafana server, or the hosted Grafana
  Cloud MCP endpoint)".
- The HOSTED endpoint (https://mcp.grafana.com/mcp) authorises with **OAuth 2.1 only**.
  Probed 25 Aug with a valid service-account token: **HTTP 401**. No static token works.
  It is therefore unusable from a headless Cloud Run container. Do not keep trying it.
- A Grafana **service account token now exists and WORKS** for reads:
    service account `cutscope-mcp`, id 18, role Viewer
    GRAFANA_SERVICE_ACCOUNT_TOKEN / GRAFANA_MCP_TOKEN in .env (glsa_...)
    GRAFANA_URL=https://narrowamaranth830.grafana.net
  Verified: GET /api/datasources -> HTTP 200, returns prometheus uid `grafanacloud-prom`.
- CUTSCOPE's own metrics are confirmed present in that datasource:
    cutscope_generation_attempts_total          labels: cutscope_shot_id, gen_ai_request_model
    cutscope_generation_outcomes_total
    cutscope_generation_duration_seconds_bucket/_count/_sum
    cutscope_generation_estimated_cost_usd_USD_total   <- note the DOUBLED unit suffix

## YOUR JOB — run the official server ourselves (Option A in the setup doc)
1. Add **grafana/mcp-grafana** to the container. It is a Go binary with published releases.
   Fetch a pinned release in the Dockerfile (verify the checksum), or build from source if
   that is more reliable. Do NOT add a forbidden vendor — check what it pulls in.
2. Start it inside the container alongside the Next.js server, listening on localhost only
   (it must never be reachable from the internet). Configure it with
   GRAFANA_URL + GRAFANA_SERVICE_ACCOUNT_TOKEN from the environment.
   The container CMD currently runs `node server.js` — you will need a small supervisor
   (a shell entrypoint that starts mcp-grafana in the background then execs node is fine;
   keep it simple and make sure the container still dies correctly if either process dies).
3. Point cutscope/mcp_grafana.py at the local server by default (GRAFANA_MCP_URL), keeping
   the hosted endpoint reachable only if someone sets it explicitly.
4. Confirm `query_prometheus` (or whatever the tool is really called — LIST THE TOOLS, do not
   assume the name) returns real data for one of the metrics above.

## THE POINT — this must be LOAD-BEARING, not decorative
The agent's decision must consume the value that came back through MCP. Trace it end to end:
mcp-grafana -> mcp_grafana.py -> grafana_query.py -> the decision. If the decision would be
identical without the MCP call, the integration does not count. Make sure a judge reading the
code can see the metric causing the decision.

## GRACEFUL DEGRADATION
If the MCP server is down, fall back to the direct Prometheus HTTP query that already works,
and SAY SO in the emitted decision line. Never fail silently, never pretend MCP was used when
it was not.

## VERIFY BEFORE REPORTING — no unobserved claims
- Start the server locally, run `python -m cutscope.mcp_grafana --probe`, and paste the REAL
  tool list it returns.
- Run one real query and paste the actual returned data.
- Build the container (`docker build`) and confirm both processes start. If Docker is not
  available locally, say so plainly rather than claiming it works.
- Report which of the four steps are done, partial, or blocked, and exactly what a human
  must do for anything blocked.
