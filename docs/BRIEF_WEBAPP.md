Build the CUTSCOPE web console. Read docs/PLAN.md, docs/ROADMAP.md, and the existing
python package in cutscope/ IN FULL before writing anything. The Python package is the
working engine — reuse it, do not rewrite it.

## WHAT THIS IS
A hosted WEB APP. A judge opens one public URL, clicks one button, and watches a Gemini
agent run a real multi-shot Veo production while live Grafana metrics drive its decisions.
The command-line tool becomes the hidden worker. A terminal is never shown to anyone.

## HARD RULES (breaking any of these disqualifies the entry)
- Runtime model calls: GOOGLE ONLY. Gemini + Veo via Vertex AI. Grafana called at runtime.
- FORBIDDEN at runtime: any OpenAI, Anthropic, AWS or Microsoft model or API.
- Must run with no login, no signup, no config. A judge lands and it works.
- Credentials come from env vars only. Never in source, never sent to the browser.

## THE SCREEN — build exactly this
One page, three columns, a header bar and a footer strip.

HEADER: product name · production name · live spend "$4.12 / $15.00" · a STOP button
        that actually halts the run.

LEFT — SHOT LIST: one row per shot, each with a state dot and its cost so far.
       States: queued · generating · retrying (n/max) · done · refused · abandoned.

CENTRE — the current take playing, and beneath it the exact prompt text used for it.

RIGHT — AGENT DECISION LOG. This is the most important element on the page. A live feed,
        newest first. EVERY entry must show three things: what happened, the Grafana
        metric the agent read, and the decision it took because of it. For example:
          14:02:11  shot 03 attempt 2 REFUSED (safety filter)
          ↳ Grafana: refusal rate 66% on this shot
          ↳ DECISION: REPHRASE — drop "ray gun", keep blocking
        A judge must be able to watch a metric cause a decision. That is what proves
        Grafana is load-bearing rather than decorative. Do not summarise these entries.

FOOTER: a live Grafana panel — cost per shot, retries, refusals, latency.

## BEHAVIOUR
- Streams updates to the browser as the run progresses (SSE or WebSocket). No page refresh.
- A run that is abandoned on budget must be visibly, deliberately shown — not hidden as an
  error. The agent refusing to waste money is the product, not a failure.
- PRACTICE MODE is mandatory and must be the default: a "Practice run" toggle that replays
  a realistic scripted production — including a refusal and a budget abandonment — calling
  NO paid APIs at all. This is how the owner tests without spending, and the judge's
  fallback if credits run dry. There is a documented risk of judges being unable to run
  entries after cloud credits expire; practice mode is the mitigation.
- A "Live run" mode does the real thing against Vertex AI.

## STACK
Next.js + TypeScript, deployed to Cloud Run (per docs/PLAN.md — one Google Cloud surface).
Python engine stays as the worker. Keep the seam between them clean and documented.

## DELIVER
Working locally first. Print exact run instructions in README. Report honestly what you
verified running versus what is untested. Do not claim a deploy you did not perform.
