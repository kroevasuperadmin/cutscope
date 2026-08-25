# CUTSCOPE — Devpost Submission Pack

> **Rule for everything below:** if a judge can test a sentence in 60 seconds, it has to survive the test.
> Every dollar figure in this pack was read out of an actual practice run on 25 Aug 2026, not written from the design doc.
> Where a capability is not yet exercised, this pack says so instead of rounding up. See `docs/CLAIMS.md` for the wording rules.

## Project name

CUTSCOPE

## Project URL

https://cutscope.rizqey.com

## Source code

https://github.com/kroevasuperadmin/cutscope

## License

Apache-2.0

## 1. Elevator pitch

CUTSCOPE is the spend circuit breaker for AI film shoots: it uses production telemetry to decide when to retry, keep a flawed take, or stop wasting money.

## 2. Project description

### Inspiration

CUTSCOPE is a production-control console for AI film directors. It does not pretend every imperfect generation deserves another attempt. It shows the shot, the cost, the failure signal, and the decision: retry with a bounded change, keep the take because it is good enough for its cost, or stop.

The problem is personal. The author has directed an AI-generated film series across Hailuo, Kling, Higgsfield, Veo, and other tools: about 596 prompt attempts, 85 documented failures, and 22 character-consistency problems. The frustrating part was not making a single clip; it was judging a multi-shot production while failures, continuity drift, and paid retries accumulated across it.

This is also an economic problem, not just a creative one. An independent [AI-video pricing guide](https://apiframe.ai/blog/ai-video-api-pricing-2026) calls failed generations "the quiet budget killer." Its 70% first-take-success example means a usable clip costs about 1.4× list price on average before other overhead: 1 ÷ 0.70 = 1.43. CUTSCOPE exists to make that hidden multiplier visible before the next paid attempt.

**Potential impact:** directors and small production teams need a way to govern multi-shot AI-video work without trusting an opaque agent to spend freely. CUTSCOPE makes the trade-off inspectable at the shot level, where the money and creative damage actually happen.

### What it does

A judge opens the public console at https://cutscope.rizqey.com, clicks **Start practice run**, and watches an original five-shot production, *Turning Point*, progress in real time. The whole replay runs about 60 seconds. The console shows the shot list, current take, spend and quality signals, a metrics panel, and the agent decision log over a live stream. There is no login, signup, browser setup, API key, or paid credit required.

The practice run demonstrates four different kinds of judgment:

- **Shot 01 — a refusal becomes a rephrase.** The safety filter refuses attempt one. The agent names the trigger phrase, preserves the visual intent without the weapon-like wording, and retries once. The second take is kept, at `$0.96` of a `$3.00` shot ceiling.
- **Shot 03 — keep an imperfect take.** Identity consistency scores 78% against an 85% target. CUTSCOPE logs the age-to-age drift and keeps the take anyway: another paid retry is not worth it at that margin.
- **Shot 04 — set the reference anchor.** The 2012 field take establishes the field, tree line, footpath, and framing that Shot 05 has to match.
- **Shot 05 — abandon.** Location continuity reaches 42%, then 58%, against a 90% target. Both anchored attempts drift the same way, which reads as a model limit rather than a prompt fault, so CUTSCOPE stops the shot at `$0.80` of its `$2.50` ceiling and leaves the remaining `$11.88` of the `$15.00` run budget unspent.

The run ends at `$3.12 / $15.00`. Note what that means: **the circuit breaker did not have to trip.** The agent stopped on evidence well before the ceiling. The hard ceiling is still there underneath as the thing that cannot be argued with — `enforce_decision()` in `cutscope/decision.py` runs after the model returns, can only ever downgrade an outcome to `ABANDON`, and is evaluated against the controller's own attempt ledger rather than anything a dashboard returned. `tests/test_decide.py` proves Gemini advising `RETRY_SAME` at the ceiling still yields `ABANDON`.

Practice mode is deliberately scripted and visibly labelled as such: a `PRACTICE` pill stays in the header for the whole run — reading `PRACTICE · scripted replay · no paid API calls` at desktop width — and every evidence line the worker writes is prefixed `Scripted:`. Only a live run is permitted to prefix a line `Grafana:`. The scripted dollars are not prose — they are derived from the same `VeoCostEstimator` a live run uses, at published `veo-3.1-fast` pricing (`$0.08` per second of 720p video), and the worker raises rather than print a figure that would breach a ceiling.

**Design:** CUTSCOPE is a complete, focused control surface rather than a generic chat box or a video editor. It gives a director one clear loop — observe a shot, understand the evidence, accept a bounded decision — with an end state that can be "abandon."

### How we built it

CUTSCOPE runs a Next.js console and a Python worker together in one container on Google Cloud Run, in project `cutscope`, region `us-central1`. The live public site uses a custom domain with a Google Trust Services certificate. Run state is process-local, so the service is pinned to a single instance (`maxScale=1`); a second instance would be asked for SSE events belonging to runs it had never seen.

Live mode uses **Gemini 2.5 Flash and Veo 3.1 Fast through Vertex AI**, called directly with the `google-genai` SDK. Gemini evaluates the evidence around a retry decision; Veo performs real video generation. Google Cloud Storage streams a completed live Veo asset back to the console.

To be exact about the agent, because it is testable: this is a Gemini model call on Vertex AI inside the Cloud Run worker. There is no Agent Builder or Agent Engine resource and no ADK agent in the repository. The agentic part is the loop — observe telemetry, reason over it, choose one of a bounded action set — not a managed agent runtime.

The telemetry loop is split across two directions on purpose:

- **Write.** The worker exports metrics and spans to Grafana Cloud over OTLP (`cutscope/telemetry.py`). Verified: a `POST` to the OTLP gateway with the project's credentials returns HTTP 200.
- **Read.** Before Gemini is asked for advice, the worker reads the shot's metric window back out of Grafana (`cutscope/grafana_query.py`). The primary path is a `query_prometheus` tool call on the **Grafana MCP server** (`cutscope/mcp_grafana.py`); a direct Mimir HTTP query is the fallback. Neither path is asserted — every metrics window handed to the agent carries a `source` field (`grafana_mcp` or `grafana_prometheus_http_fallback`) and an `mcp_used` boolean, so a run can never look like it used MCP when it did not. A live run refuses to start with neither read path configured, rather than run blind.

> **Gate before this text is pasted into Devpost.** As of 25 Aug 2026 the MCP read path has never completed a call: `GRAFANA_MCP_URL` / `GRAFANA_MCP_TOKEN` are unset and the stack URL returns HTTP 404. The bullet above describes shipped code, which is fair, but do not publish it until a live run has been observed reporting `mcp_used: true`. If that has not happened by submission, replace the bullet's second sentence with: "The read is a Prometheus query against Grafana Cloud; a Grafana MCP client (`cutscope/mcp_grafana.py`) is implemented as the primary path but has not yet been exercised against a live stack." Then drop the Model Context Protocol tag. An unexercised MCP claim is exactly the thing a Grafana-track judge will check first.

Grafana is not decorative reporting. The product pairs the signal with the decision it causes: a refusal rate can cause a rephrase, a continuity score can lead to a keep, and budget plus retry cost can trigger an abandonment.

**Technological implementation:** Google Cloud hosts the public control surface on Cloud Run and supplies the live Gemini and Veo capabilities through Vertex AI. Grafana Cloud is the operational evidence layer — telemetry is exported there over OTLP, and the read back out of Grafana is part of the retry decision rather than an after-the-fact dashboard.

### Challenges

The hard part was defining a useful agent decision without pretending an AI can objectively judge cinema. A score alone is not a decision. A 78% take can be worth keeping; a 58% take can be unacceptable; a strong-looking take can still be too expensive to pursue. CUTSCOPE therefore treats quality, continuity, safety, budget, and expected retry cost as a single production decision with a visible rationale.

The second challenge was creating a demo judges can run safely. Practice mode uses no network, Gemini, Veo, Grafana, or paid API. It replays the exact five-shot control loop while Live mode remains available for real Vertex AI calls. That avoids a dead demo without representing scripted results as live model output — which is why the `Scripted:` prefix is enforced in the worker rather than left to the copy.

The third was resisting the temptation to describe the intended architecture instead of the shipped one. The plan document specifies a deployed agent resource; the build is a direct Vertex call. Rather than let the plan's wording leak into the console and the README, `docs/CLAIMS.md` fixes the exact sentence each surface is allowed to use, and the README carries a table of what is verified and what is not.

### Accomplishments that we're proud of

We shipped a public, no-login console at https://cutscope.rizqey.com with a safe, repeatable, roughly 60-second practice run. The result is a coherent product experience: a production starts, each decision changes visible shot state and telemetry, and the run finishes on a refusal to spend rather than on a success-shaped ending.

We also made the demo content ours. *Turning Point* is an original 13-episode screenplay written by the author. Its five demo shots were chosen to stress real AI-video failure modes: safety wording, one character at two ages, two ages in one frame, a location anchor, and the same location twelve years earlier. No third-party film IP is needed to demonstrate the product.

**Ownership disclosure:** the author owns the *Turning Point* screenplay and the five-shot demo concept used in this submission.

The author brings execution experience beyond this project: first place in Superteam Malaysia Solana Lab DevLeague 2026; founder of Rizqey; previously shipped a perception API for AI agents with paying customers and VC backing; and took an app concept to the App Store in 48 hours.

### What we learned

The product's most valuable output is not "generate again." It is a defensible **no**. A director does not need another dashboard telling them a score went down. They need a system that can connect that score to the cost of the next attempt and say, visibly, why continuing is unjustified.

The sharpest version of that lesson is Shot 05. Two attempts drifting in the same direction is different information from one bad attempt: it separates a prompt problem from a model limit. The first is worth another paid try, the second is not — and only the run's own history can tell them apart.

We also learned that observability becomes creatively useful when it changes an action. A refusal rate beside a prompt rewrite, or a cost ceiling beside an abandonment, gives Grafana a role in the production loop instead of treating it as infrastructure that only engineers see.

**Quality of idea:** CUTSCOPE's non-obvious integration is a spend circuit breaker for creative work. Rather than using AI to maximize generations or chase a perfect score, it uses Gemini, Vertex AI, and Grafana to make the economically rational creative decision — including keeping an imperfect take and refusing a wasteful retry.

### What's next

The next product shape is a low-friction proxy or middleware layer: a director changes one base URL, keeps using their existing generation workflow, and CUTSCOPE meters calls, records refusals and drift, and trips the same shot-level spend circuit breaker. That approach preserves the existing creative workflow while making the control loop available wherever generation happens.

After that, CUTSCOPE can become a judgment service for other agents through its own MCP interface: "Is this generation worth the money — retry, keep, or stop?" The scope will remain intentionally narrow. CUTSCOPE is not an editing suite and not an autonomous bot with no human control surface; it is the system that makes paid generation decisions legible and bounded.

## 3. Three-minute demo video script

**Runtime target: 2:58.**

Three rules for the recording:

1. The header `PRACTICE` pill must stay visible for every second of console footage. Record at desktop width so it reads in full — `PRACTICE · scripted replay · no paid API calls`. Do not crop it out for a tighter frame.
2. Every figure spoken below was read out of a real run. If a number on screen disagrees with the narration, the narration is wrong — re-read the run, do not fix it in the edit.
3. Do not cut to a logo after the final abandonment. The abandoned shot is the ending.

**Recording note.** The replay runs about 60 seconds unattended, and this script covers roughly 2 minutes of it, so record at natural speed and cut between beats rather than trying to narrate live. `CUTSCOPE_PRACTICE_SPEED=0.5` (local only) stretches the replay if a beat needs more room on screen.

### 0:00–0:14 — The problem

**On screen:** Fast, silent montage of an AI-video generation history: duplicate takes, failed status cards, continuity notes, and rising spend. End on a production spreadsheet that is impossible to read at a glance. No CUTSCOPE logo yet.

**Said:** "AI film production does not fail once. It fails take after take: a safety refusal, a character that changes, a location that drifts, and a budget disappearing one clip at a time."

**Scoring:** Potential Impact.

### 0:14–0:29 — Why this is a real problem

**On screen:** Text over a clean original *Turning Point* still: "596 prompt attempts. 85 documented failures. 22 character-consistency problems." Then reveal the author's original screenplay cover: "Turning Point — 13 episodes."

**Said:** "I know that loop firsthand. While directing an AI-generated film series, I logged roughly 596 prompt attempts, 85 failures, and 22 character-consistency problems. The hard job was deciding which next attempt was actually worth buying."

**Scoring:** Potential Impact; Quality of Idea.

### 0:29–0:43 — Introduce the control surface

**On screen:** Navigate to https://cutscope.rizqey.com. Show the five-shot list, current-take area, metrics panel, and decision log in one composed desktop view. Hover over **Start practice run** in the header.

**Said:** "This is CUTSCOPE: a production-control console for AI film shoots. It turns telemetry into one bounded decision for every shot — retry, keep, or stop."

**Scoring:** Design.

### 0:43–0:57 — Honest, runnable demo

**On screen:** Click **Start practice run** in the header. Hold on the mode pill — "PRACTICE · scripted replay · no paid API calls" — and on the header spend readout: "Simulated spend `$0.00 / $15.00`". Point out that the first decision-log line already reads `Scripted:`.

**Said:** "This public practice run needs no account or credentials, and it takes about a minute. It is visibly scripted — every evidence line says so — so anyone can inspect the control loop safely. In Live mode, the same worker uses Gemini and Veo through Vertex AI."

**Scoring:** Design; Technological Implementation.

### 0:57–1:18 — Shot 01: safety refusal becomes a rephrase

**On screen:** **SHOT 01 - WAREHOUSE DISPLACEMENT**, attempt one. The card turns to **refused**; the log line reads `Scripted: refusal rate 100%; attempt cost $0.48; trigger phrase "pneumatic liquid strikes his chest"` and the decision `REPHRASE`. Attempt two completes and the card becomes **KEEP TAKE** at `$0.96`.

**Said:** "Shot one is refused by the safety filter. CUTSCOPE reads a hundred-percent refusal rate, names the phrase that caused it, preserves the visual idea without the weapon-like wording, and retries once. Forty-eight cents to learn that; ninety-six cents total to recover the shot."

**Scoring:** Technological Implementation; Potential Impact.

### 1:18–1:37 — Prove the metric causes the decision

**On screen:** Hold a deliberate side-by-side view: metrics panel on the left, decision log on the right. Highlight refusal rate, shot spend against the `$3.00` ceiling, and the matching **RETRY REPHRASED** decision. Caption: "Metric → decision, not dashboard theater."

**Said:** "Here is the point of observability in CUTSCOPE. The metric and the decision it caused are on screen together. In Live mode, telemetry goes to Grafana Cloud over OTLP, and the shot's metric window is read back out of Grafana — through the Grafana MCP server — before Gemini is asked whether to retry."

**Scoring:** Technological Implementation; Quality of Idea.

> **Gate on this beat.** Record the sentence above only once a live run has been observed reporting `source: grafana_mcp`. If the read path is still falling back, the honest line is: "…telemetry goes to Grafana Cloud over OTLP, and the shot's metric window is read back out of Grafana before Gemini is asked whether to retry." Never narrate MCP over a run whose payload says `grafana_prometheus_http_fallback`.

### 1:37–1:56 — Shot 03: keep an imperfect take

**On screen:** **SHOT 03 - ARCADE COACHING**. Show the two-age character frame, then the log line: `identity consistency 78% against 85% target`, decision **KEEP TAKE**. Do not present 78% as a success badge.

**Said:** "Shot three is not a pass-fail test. Identity consistency is seventy-eight percent against an eighty-five-percent target. CUTSCOPE logs the drift and keeps the take anyway, because a costly retry is not justified for seven points."

**Scoring:** Quality of Idea; Design.

### 1:56–2:08 — Shot 04: set the reference anchor

**On screen:** **SHOT 04 - THE FIELD 2012** completing at `$0.40`. Highlight the field, tree line, curving footpath, and framing. The decision log reads **REFERENCE ANCHOR SET**.

**Said:** "The next take sets the reference. This field, tree line, footpath, and camera framing are now the geography the 2000 shot has to match."

**Scoring:** Design.

### 2:08–2:28 — Shot 05, attempt one: a bounded retry

**On screen:** **SHOT 05 - THE FIELD 2000**, target "location-continuity 90%." Attempt one lands at 42%. The log shows `$0.40 / $2.50` shot ceiling and a `$0.40` retry estimate, then the rephrase binding the 2012 reference, tree line, footpath, and camera position.

**Said:** "Shot five asks for the same location twelve years earlier, before the playground existed. The first attempt matches only forty-two percent against a ninety-percent target. There is room for one constrained, reference-bound retry."

**Scoring:** Technological Implementation; Quality of Idea.

### 2:28–2:46 — Shot 05, attempt two: abandon

**On screen:** Attempt two returns 58%. Metrics panel and decision log side by side: `shot spend $0.80 / $2.50`, `run spend $3.12 / $15.00`, `next attempt estimate $0.40`, and finally **ABANDONED**.

**Said:** "The second attempt improves only to fifty-eight percent. Two anchored attempts drifting the same way is not a prompt fault — it is a model limit. CUTSCOPE could afford another try. It has spent three-twelve of fifteen dollars. It stops anyway, and leaves eleven-eighty-eight unspent."

**Scoring:** Quality of Idea; Potential Impact; Technological Implementation.

### 2:46–2:58 — End on the thesis

**On screen:** Keep the final abandoned Shot 05 card and its decision log on screen. Slow zoom into **DECISION: ABANDON**. No logo, no montage, no resolution after this.

**Said:** "That is CUTSCOPE. Not an agent that keeps spending until something looks successful — an agent that knows when the next generation is not worth the money, even when the money is still there."

**Scoring:** Potential Impact; Quality of Idea.

## 4. Built with tag list

Google Cloud

Cloud Run

Vertex AI

Gemini 2.5 Flash

Veo 3.1

Grafana Cloud

OpenTelemetry

Model Context Protocol

Next.js

Python

> Drop the **Model Context Protocol** tag if the MCP read path is not working at submission time.

## 5. Judge quickstart — try it in 60 seconds, no credentials

1. Open https://cutscope.rizqey.com.
2. Click **Start practice run** in the header. Practice mode is the default and requires no login, API key, Google account, Grafana account, or paid credit.
3. Watch for about a minute. The five shot cards, metrics panel, and decision log update together.
4. Look for the four decisions: Shot 01 rephrased after a safety refusal and kept at `$0.96`; Shot 03 kept at 78% identity consistency against an 85% target; Shot 04 setting the location anchor; Shot 05 abandoned after 42% then 58% against a 90% continuity target. The run ends at `$3.12 / $15.00` — under budget, because the agent stopped on evidence rather than on exhaustion.
5. Everything in that run is scripted and says so: the mode pill, and a `Scripted:` prefix on every evidence line. Live mode is the real Vertex AI path (Gemini 2.5 Flash, Veo 3.1 Fast, Grafana Cloud telemetry) and is closed on the public deployment behind an operator token so a visitor cannot spend money.

To check the same loop without a browser, clone the repo and run `python -m cutscope.web_worker --mode practice --run-id check`. It prints the identical JSON event stream, including every dollar figure quoted above.

## 6. Pre-submission checklist

Ordered by what breaks the entry if skipped. Unchecked items are genuinely outstanding as of 25 Aug 2026.

### Blocking — the entry is weaker or non-compliant without these

- [ ] **Get the Grafana read path actually working, or stop claiming it.** The Grafana track requires the stack to be used at runtime "primarily through the Grafana Cloud MCP server." OTLP push alone does not satisfy it. Two known blockers: the stack URL `https://narrowamaranth830.grafana.net` currently returns HTTP 404, and the only token held is scoped `otlp:write`, which the hosted MCP endpoint rejects with 401. Fix per `docs/GRAFANA_MCP_SETUP.md`, then run live and confirm the payload reports `source: grafana_mcp` / `mcp_used: true`.
- [ ] **Perform one bounded Live-mode run with real Vertex AI credentials** and keep the evidence: the Grafana read occurring before Gemini's advice, and the `source` field it reported. If Live mode cannot be demonstrated during judging, label it unavailable — never present a scripted practice event as a live call.
- [ ] **Deploy the current working tree.** The deployed build still accepts `POST /api/runs {"mode":"live"}` from an anonymous caller (it returns a run id, then fails on missing config). The operator-token gate exists in the repo but is not live. Ship it, set `CUTSCOPE_OPERATOR_TOKEN`, and re-test that an unauthenticated live request returns 403.
- [ ] **Record and upload the 2:58 demo video** using the script above, then verify the Devpost video link plays in a logged-out browser.
- [ ] **Make https://github.com/kroevasuperadmin/cutscope public** immediately before submission. Confirm the Apache-2.0 license renders, and that the public tree contains no `.env`, tokens, or private production data.
- [ ] **Select the GRAFANA partner track** and enter the Built with tags above. Use the public app URL and public repo URL exactly as written in this pack.
- [ ] **Submit before 9 September 2026, 2:00pm PDT**, after rechecking the competition page's displayed deadline and judging-period requirements.

### Verification — cheap, and each one is a claim a judge can test

- [ ] Re-run the practice replay after the final deploy and confirm the numbers in this pack still match: ends `$3.12 / $15.00`, Shot 01 `$0.96`, Shot 05 abandoned at `$0.80 / $2.50`. Changing `VEO_MODEL` changes all of them.
- [ ] Test https://cutscope.rizqey.com from an incognito browser on desktop and mobile: no login, **Start practice run** works from the header, the SSE stream updates, and Shot 05 ends **ABANDONED**.
- [ ] Confirm the `PRACTICE` pill is visible throughout and that no practice line is prefixed `Grafana:`.
- [ ] Confirm README, `components/production-console.tsx`, `docs/BRIEF_JUDGE.md`, and this pack all describe the agent identically — Gemini 2.5 on Vertex AI, not Agent Builder. `docs/CLAIMS.md` holds the approved wording.
- [ ] Confirm the Cloud Run service is still pinned to `maxScale=1`; concurrent runs on a second instance would break the SSE stream.

### Assets and rights

- [ ] Capture submission screenshots: the public console; Shot 01's refusal-to-rephrase; Shot 03's 78% keep; Shot 05's 42% → 58% abandonment; the metrics panel beside the decision log.
- [ ] Capture technical proof: the Cloud Run service and custom domain with its Google-issued certificate; the Vertex AI configuration for Gemini 2.5 Flash and Veo 3.1 Fast; and a Grafana Cloud OTLP ingestion returning HTTP 200. Redact every secret before capture.
- [ ] Confirm *Turning Point* remains entirely original work by the author, and that every video, image, audio file, font, and logo in the demo is original, licensed, or permitted.

### Done

- [x] LICENSE copyright line filled in — "Copyright 2026 Faris Irfan" (was the Apache placeholder).
- [x] README reconciled with the code: no Agent Builder claim, correct practice-run figures, an explicit table of what is and is not verified.
- [x] Cloud Run pinned to one instance (`autoscaling.knative.dev/maxScale=1`), matching the in-memory run store.
- [x] Practice replay paced to about 60 seconds, with `Scripted:` on every evidence line.
- [x] Grafana OTLP write path verified — HTTP 200 from the OTLP gateway with the project's credentials.
