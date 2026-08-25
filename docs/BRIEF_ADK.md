Implement the decision agent on Google ADK + Vertex AI Agent Engine. This closes the last
MANDATORY requirement gap in the hackathon entry. Read these first, fully:
  cutscope/decision.py      (the current direct Vertex call that must be replaced)
  cutscope/orchestrator.py  (the caller)
  cutscope/grafana_query.py (where the metric evidence comes from)
  cutscope/mcp_grafana.py   (the Grafana MCP client, written last night)
  docs/CLAIMS.md            (the honest accounting of what does NOT exist yet)

## WHY THIS EXISTS
The competition rule is: "a functional agent powered by Gemini AND Google Cloud Agent
Builder." The README currently states, truthfully, that there is no Agent Builder / Agent
Engine resource and no ADK agent in the repo. That is an open admission of missing a
mandatory item. $75,000, 8,050 registrants, deadline 9 Sep 2026. Close it properly.

## WHAT TO BUILD
1. A real **ADK agent**. Use the `google-adk` package. Define an `LlmAgent` on
   gemini-2.5-flash whose job is: given a shot's live telemetry, decide RETRY_SAME,
   RETRY_REPHRASED, or ABANDON, and when rephrasing, produce the replacement prompt.

2. Give it **tools**, so the agent genuinely reasons over tool output rather than being a
   dressed-up completion call:
   - a tool that reads the shot's current metrics (wire it to the Grafana MCP path in
     mcp_grafana.py / grafana_query.py — this makes the Grafana integration load-bearing
     inside the agent, which the partner track also requires)
   - a tool that reports remaining budget for the shot and the production
   - a tool that returns the shot's attempt history (prompts tried, outcomes, costs)

3. **The budget ceiling stays enforced in CODE.** The model ADVISES; a hard rule in Python
   overrides it. If spend would exceed the ceiling, the decision is ABANDON regardless of
   what the agent returns. There is already a test asserting this — tests/test_decide.py —
   it must still pass. Do not weaken it.

4. **Deploy to Vertex AI Agent Engine** in project `cutscope`, region us-central1, and invoke
   the deployed resource from the orchestrator by its resource name. Credentials are in .env;
   Authenticate with your own deployment account and enable the required APIs. Store the deployed reasoning-engine resource ID in .env as
   CUTSCOPE_AGENT_ENGINE_ID and read it at runtime.

5. **Graceful degradation.** If the Agent Engine resource is unreachable, fall back to the
   existing direct Vertex call and SAY SO in the emitted decision log line, so the demo never
   dies in front of a judge but also never silently pretends. Never fall back silently.

## CONSTRAINTS
- Google only at runtime. No OpenAI, Anthropic, AWS, Microsoft — check transitive deps too.
- Python 3.12. Add `google-adk` and any Agent Engine extras to requirements.txt AND
  pyproject.toml, pinned.
- The container is Python 3.12-slim + Node 22 (see Dockerfile). Whatever you add must install
  cleanly there — if a dep is heavy or pulls a forbidden vendor, say so rather than adding it.

## VERIFY BEFORE REPORTING — do not claim success you did not observe
- `python -m pytest tests/ -q` passes, including the budget-override test.
- The agent runs locally and returns a valid decision for a synthetic shot. Paste the actual
  decision JSON in your report.
- If you deployed to Agent Engine, paste the real resource name and the response from one
  invocation. If deployment FAILED, say exactly why and what a human must do — do not
  pretend it deployed.
- Report honestly which of the five items above are done, partial, or blocked.

## THEN
Write docs/AGENT_ARCHITECTURE.md: what runs where, the exact ADK objects used, the Agent
Engine resource name, how the Grafana MCP evidence reaches the agent, and where the hard
budget rule sits relative to the model. One page, precise, for a judge scoring
"Technological Implementation".
