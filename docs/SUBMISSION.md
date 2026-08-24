# CUTSCOPE — Devpost Submission Pack

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

This is also an economic problem, not just a creative one. An independent [AI-video pricing guide](https://apiframe.ai/blog/ai-video-api-pricing-2026) calls failed generations “the quiet budget killer.” Its 70% first-take-success example means a usable clip costs about 1.4× list price on average before other overhead: 1 ÷ 0.70 = 1.43. CUTSCOPE exists to make that hidden multiplier visible before the next paid attempt.

**Potential impact:** directors and small production teams need a way to govern multi-shot AI-video work without trusting an opaque agent to spend freely. CUTSCOPE makes the trade-off inspectable at the shot level, where the money and creative damage actually happen.

### What it does

A judge opens the public console at https://cutscope.rizqey.com, clicks **Start practice run**, and watches an original five-shot production, *Turning Point*, progress in real time. The console shows the shot list, current take, spend and quality signals, a Grafana panel, and the agent decision log over a live stream. There is no login, signup, browser setup, API key, or paid credit required for the practice run.

The practice run demonstrates three different kinds of judgment:

- Shot 01 is refused by the safety filter. The agent reads the refusal signal, rephrases the prompt to preserve the visual intent without weapon-like wording, and recovers the shot.
- Shot 03 scores 78% identity consistency against an 85% target. CUTSCOPE keeps the take anyway: the age-to-age drift is logged, but another paid retry is not worth the budget.
- Shot 05 misses its location-continuity target twice: 42%, then 58%, against 90%. With $12.50 of a $15.00 run budget spent and a $2.50 shot ceiling nearly exhausted, CUTSCOPE abandons it rather than buy another poor attempt.

Practice mode is deliberately scripted and visibly labelled as such. It makes the decision path safe to inspect with zero credentials and zero paid API calls. In Live mode, the same product makes real Vertex AI calls.

**Design:** CUTSCOPE is a complete, focused control surface rather than a generic chat box or a video editor. It gives a director one clear loop—observe a shot, understand the evidence, and accept a bounded decision—with an end state that can be “abandon.”

### How we built it

CUTSCOPE runs a Next.js console and a Python worker together in one container on Google Cloud Run. The live public site uses a custom domain and Google-issued SSL. The worker streams state into the console so the shot cards, metrics, and decision log move together rather than leaving the director to reconcile separate dashboards.

Live mode uses Gemini 2.5 Flash and Veo 3.1 through Vertex AI. Gemini evaluates the evidence around a retry decision; Veo performs real video generation. The worker sends telemetry to Grafana Cloud through OTLP, with ingestion verified by an HTTP 200 response. In the live decision path, a real Grafana Mimir metrics query is read before Gemini advises whether to retry. Google Cloud Storage streams a completed live Veo asset back to the console.

Grafana is not decorative reporting. The product pairs the Grafana signal with the decision it causes: refusal rate can cause a rephrase, a continuity score can lead to a keep, and budget plus retry cost can trigger an abandonment. The agent’s recommendation is constrained by code-enforced shot ceilings and attempt limits; it cannot simply talk its way around the spend policy.

**Technological implementation:** Google Cloud hosts the public control surface on Cloud Run and supplies the live Gemini and Veo capabilities through Vertex AI. Grafana Cloud is the operational evidence layer—OTLP telemetry is exported there, and live Grafana data is part of the retry decision rather than an after-the-fact dashboard.

### Challenges

The hard part was defining a useful agent decision without pretending an AI can objectively judge cinema. A score alone is not a decision. A 78% take can be worth keeping; a 58% take can be unacceptable; a strong-looking take can still be too expensive to pursue. CUTSCOPE therefore treats quality, continuity, safety, budget, and expected retry cost as a single production decision with a visible rationale.

The other challenge was creating a demo judges can run safely. Practice mode uses no network, Gemini, Veo, Grafana, or paid API. It replays the exact five-shot control loop, while Live mode remains available for real Vertex AI calls. This avoids a dead demo without representing scripted results as live model output.

### Accomplishments that we’re proud of

We shipped a public, no-login console at https://cutscope.rizqey.com with a safe, repeatable practice run. The result is a coherent product experience: a production starts, each decision changes visible shot state and telemetry, and the run finishes with a decision that protects the remaining budget rather than forcing a success-shaped ending.

We also made the demo content ours. *Turning Point* is an original 13-episode screenplay written by the author. Its five demo shots were chosen to stress real AI-video failure modes: safety wording, one character at two ages, two ages in one frame, a location anchor, and the same location twelve years earlier. No third-party film IP is needed to demonstrate the product.

**Ownership disclosure:** the author owns the *Turning Point* screenplay and the five-shot demo concept used in this submission.

The author brings execution experience beyond this project: first place in Superteam Malaysia Solana Lab DevLeague 2026; founder of Rizqey; previously shipped a perception API for AI agents with paying customers and VC backing; and took an app concept to the App Store in 48 hours.

### What we learned

The product’s most valuable output is not “generate again.” It is a defensible **no**. A director does not need another dashboard telling them a score went down. They need a system that can connect that score to the cost of the next attempt and say, visibly, why continuing is unjustified.

We also learned that observability becomes creatively useful when it changes an action. A refusal rate beside a prompt rewrite, or a cost ceiling beside an abandonment, gives Grafana a role in the production loop instead of treating it as infrastructure that only engineers see.

**Quality of idea:** CUTSCOPE’s non-obvious integration is a spend circuit breaker for creative work. Rather than using AI to maximize generations or chase a perfect score, it uses Gemini, Vertex AI, and Grafana to make the economically rational creative decision—including keeping an imperfect take and refusing a wasteful retry.

### What's next

The next product shape is a low-friction proxy or middleware layer: a director changes one base URL, keeps using their existing generation workflow, and CUTSCOPE meters calls, records refusals and drift, and trips the same shot-level spend circuit breaker. That approach preserves the existing creative workflow while making the control loop available wherever generation happens.

After that, CUTSCOPE can become a judgment service for other agents through an MCP interface: “Is this generation worth the money—retry, keep, or stop?” The scope will remain intentionally narrow. CUTSCOPE is not an editing suite and not an autonomous bot with no human control surface; it is the system that makes paid generation decisions legible and bounded.

## 3. Three-minute demo video script

**Runtime: 2:58.** Keep the practice-mode label visible whenever scripted telemetry is on screen. Do not cut to a logo after the final abandonment; the abandoned shot is the ending.

### 0:00–0:14 — The problem

**On screen:** Fast, silent montage of an AI-video generation history: duplicate takes, failed status cards, continuity notes, and rising spend. End on a production spreadsheet that is impossible to read at a glance. No CUTSCOPE logo yet.

**Said:** “AI film production does not fail once. It fails take after take: a safety refusal, a character that changes, a location that drifts, and a budget disappearing one clip at a time.”

**Scoring:** Potential Impact.

### 0:14–0:29 — Why this is a real problem

**On screen:** Text over a clean original *Turning Point* still: “596 prompt attempts. 85 documented failures. 22 character-consistency problems.” Then reveal the author’s original screenplay cover: “Turning Point — 13 episodes.”

**Said:** “I know that loop firsthand. While directing an AI-generated film series, I logged roughly 596 prompt attempts, 85 failures, and 22 character-consistency problems. The hard job was deciding which next attempt was actually worth buying.”

**Scoring:** Potential Impact; Quality of Idea.

### 0:29–0:43 — Introduce the control surface

**On screen:** Navigate to https://cutscope.rizqey.com. Show the five-shot list, current-take area, Grafana panel, and decision log in one composed desktop view. Hover over **Start practice run**.

**Said:** “This is CUTSCOPE: a production-control console for AI film shoots. It turns telemetry into one bounded decision for every shot: retry, keep, or stop.”

**Scoring:** Design.

### 0:43–0:57 — Honest, runnable demo

**On screen:** Click **Start practice run**. Keep the visible badge: “Practice mode — scripted replay — no paid APIs.” Show the run budget: “$0.00 / $15.00.”

**Said:** “This public practice run needs no account or credentials. It is visibly scripted so anyone can inspect the control loop safely. In Live mode, the same worker uses Gemini and Veo through Vertex AI.”

**Scoring:** Design; Technological Implementation.

### 0:57–1:18 — Shot 01: safety refusal becomes a rephrase

**On screen:** Shot 01, **WAREHOUSE DISPLACEMENT**, enters attempt one. The metrics update to a 100% refusal rate and $1.50 cost. The decision log identifies the trigger phrase, then shows the softened “device-and-energy” rephrase. Attempt two completes and the card becomes **KEEP TAKE** at $3.00.

**Said:** “Shot one is refused by the safety filter. CUTSCOPE reads a one-hundred-percent refusal rate, preserves the visual idea, removes the weapon-like wording, and retries once. The second take recovers the displacement shot.”

**Scoring:** Technological Implementation; Potential Impact.

### 1:18–1:37 — Prove Grafana causes the decision

**On screen:** Hold a deliberate side-by-side view: Grafana panel on the left, decision log on the right. Highlight refusal rate, shot spend, remaining allowance, and the matching **RETRY REPHRASED** decision. Add a small caption: “Metric → decision, not dashboard theater.”

**Said:** “Here is the point of Grafana in CUTSCOPE. The metric and the decision are visible together. In Live mode, telemetry arrives in Grafana Cloud over OTLP, and a Grafana metrics read is part of the evidence Gemini receives before it recommends a retry.”

**Scoring:** Technological Implementation; Quality of Idea.

### 1:37–1:56 — Shot 03: keep an imperfect take

**On screen:** Jump to **ARCADE COACHING**. Show the two-age character frame, then the visible metric: “Identity consistency 78% / target 85%.” The log states **KEEP TAKE — retry is not worth the budget**. Do not present 78% as a success badge.

**Said:** “Shot three is not a pass-fail test. Identity consistency is seventy-eight percent against an eighty-five-percent target. CUTSCOPE logs the drift and keeps the take anyway, because a costly retry is not justified.”

**Scoring:** Quality of Idea; Design.

### 1:56–2:08 — Shot 04: set the reference anchor

**On screen:** Show **THE FIELD — 2012** completing at $2.20. Highlight the established field, tree line, curving footpath, and framing. The decision log reads **REFERENCE ANCHOR SET**.

**Said:** “The next usable take sets the reference: this field, tree line, footpath, and camera framing are now the geography the 2000 shot has to match.”

**Scoring:** Design.

### 2:08–2:28 — Shot 05, attempt one: a bounded retry

**On screen:** Show **THE FIELD — 2000**, target “Location continuity: 90%.” Attempt one lands at 42%. The log displays $1.20 of a $2.50 shot ceiling and the exact rephrase binding the 2012 reference, tree line, footpath, and camera position.

**Said:** “Shot five asks for the same location twelve years earlier, before the playground existed. The first attempt matches only forty-two percent against a ninety-percent continuity target. There is room for one constrained, reference-bound retry.”

**Scoring:** Technological Implementation; Quality of Idea.

### 2:28–2:46 — Shot 05, attempt two: abandon

**On screen:** Attempt two returns at 58%. The Grafana panel and decision log are side by side again: “$2.40 / $2.50 shot ceiling,” “$12.50 / $15.00 run budget,” “Next estimate: $1.20,” and finally **ABANDONED**.

**Said:** “The second attempt improves only to fifty-eight percent. CUTSCOPE has spent two-forty of this shot’s two-fifty ceiling and twelve-fifty of the fifteen-dollar run budget. Another attempt is estimated at one-twenty. It abandons the shot.”

**Scoring:** Quality of Idea; Potential Impact; Technological Implementation.

### 2:46–2:58 — End on the thesis

**On screen:** Keep the final abandoned Shot 05 card and its final decision log on screen. Slow zoom into **DECISION: ABANDON**. No logo, no montage, no resolution after this.

**Said:** “That is CUTSCOPE. Not an agent that keeps spending until something looks successful—an agent that knows when the next generation is not worth the money.”

**Scoring:** Potential Impact; Quality of Idea.

## 4. Built with tag list

Google Cloud

Cloud Run

Vertex AI

Gemini 2.5 Flash

Veo 3.1

Grafana Cloud

OpenTelemetry

Next.js

Python

## 5. Judge quickstart — try it in 30 seconds, no credentials

1. Open https://cutscope.rizqey.com.
2. Click **Start practice run**. Practice mode is the default and requires no login, API key, Google account, Grafana account, or paid credit.
3. Watch the five shot cards, Grafana panel, and agent decision log update together.
4. Look for the three decisions: Shot 01 is rephrased after a safety refusal; Shot 03 is kept at 78% identity consistency because a retry is not worth it; Shot 05 is abandoned at $12.50 of the $15.00 production budget after reaching only 58% against a 90% continuity target.
5. The practice run is intentionally marked scripted. Live mode is the real Vertex AI path and uses Gemini 2.5 Flash, Veo 3.1, and Grafana Cloud telemetry.

## 6. Pre-submission checklist — everything still outstanding

- [ ] Upload a final 2:58 demo video using the script above, and verify that its Devpost video link plays in a logged-out browser.
- [ ] Make https://github.com/kroevasuperadmin/cutscope public immediately before submission, verify the Apache-2.0 license is visible, and confirm the public repository has no credentials, tokens, or private production data.
- [ ] Reconcile the current README deployment-status text with the live submission claims. It currently says the Cloud Run deployment and live paths were not verified; leaving that contradiction public will undermine the entry.
- [ ] Test https://cutscope.rizqey.com from an incognito browser on desktop and mobile: no login, **Start practice run** works, the SSE stream updates, and Shot 05 ends at **ABANDONED** with $12.50 / $15.00 displayed.
- [ ] Capture submission-ready screenshots: the public console; the Shot 01 metric-to-rephrase decision; the Shot 03 78% keep decision; the Shot 05 42% → 58% abandonment; and the Grafana panel beside the decision log.
- [ ] Capture technical proof for judges: Cloud Run service/custom domain with Google-issued SSL; Vertex AI configuration for Gemini 2.5 Flash and Veo 3.1; and Grafana Cloud OTLP ingestion returning HTTP 200. Do not expose secrets in any capture.
- [ ] Perform one bounded Live-mode smoke test with real Vertex AI credentials and retain evidence that the Mimir read occurs before Gemini’s retry advice. If Live mode is unavailable during judging, label it unavailable; never present a scripted practice event as a live call.
- [ ] Confirm *Turning Point* remains entirely original work written by the author, and verify every video, image, audio, font, and logo used in the demo is original, licensed, or permitted for the submission.
- [ ] Select the **GRAFANA** partner track and include every tag in the Built with list above. Use the public app URL and public source repository URL exactly as written in this pack.
- [ ] Submit before **9 September 2026, 2:00pm PDT**, after rechecking the competition page’s displayed deadline and judging-period requirements.
