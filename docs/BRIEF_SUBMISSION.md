Write the complete Devpost submission package for this project. Read README.md, docs/PLAN.md,
docs/ROADMAP.md, cutscope/web_worker.py (especially `_practice_run`, for the exact decision
narrative) and shots/turning_point.yaml before writing a word.

Output ONE file: docs/SUBMISSION.md. It is a copy-paste pack — every section must be ready to
paste into a form with no editing.

## THE COMPETITION
"Agentic Cinema: The Blockbuster Hackathon", run by Google Cloud. $75,000. Deadline
9 Sep 2026 2:00pm PDT. 8,050 registrants. Partner track: GRAFANA.
Judged EQUALLY on four criteria — write to all four explicitly:
  1. Technological Implementation — how effectively Google Cloud AND Grafana are used
  2. Design — a complete coherent product, not a proof of concept
  3. Potential Impact — solves a real problem credibly
  4. Quality of Idea — creative, non-obvious integration showing genuine problem understanding

## HARD FACTS — use these, invent nothing
- Live: https://cutscope.rizqey.com (Cloud Run, custom domain, Google-issued SSL)
- Repo: github.com/kroevasuperadmin/cutscope (private until submission), Apache-2.0
- Stack: Next.js console + Python worker in ONE container on Cloud Run. Gemini 2.5 Flash and
  Veo 3.1 via Vertex AI. Telemetry to Grafana Cloud over OTLP, verified returning 200.
- Practice mode: scripted replay, no paid API calls, works with zero credentials.
- Live mode: real Vertex AI calls.
- Author's credibility: directed an AI-generated film series across Hailuo, Kling, Higgsfield,
  Veo and others — ~596 prompt attempts, 85 documented failures, 22 character-consistency
  problems. He lived this problem. Also: 1st place, Superteam Malaysia Solana Lab DevLeague
  2026; founder of Rizqey; previously shipped a perception API for AI agents with paying
  customers and VC backing; took an app concept to the App Store in 48 hours.
- Demo content: "Turning Point", an ORIGINAL 13-episode screenplay written by the author.
  Five shots. State the originality plainly — the rules require entrants to own their work.
- Independent validation to cite: an AI-video pricing guide called failed generations "the
  quiet budget killer" and noted a 70% first-take success rate means every clip really costs
  1.4x list price.

## SECTIONS REQUIRED

### 1. Elevator pitch (one sentence, under 200 characters)

### 2. Project description (Devpost "About the project")
Sub-sections: Inspiration / What it does / How we built it / Challenges / Accomplishments /
What we learned / What's next. Lead with what it DOES, not how it works. Every one of the
four judging criteria must be visibly answered somewhere. No hype, no invented traction.

### 3. THREE-MINUTE DEMO VIDEO SCRIPT — the most important section
Beat by beat with timestamps to the second, totalling under 3:00. For each beat give:
what is ON SCREEN, what is SAID (write the actual voiceover words), and which judging
criterion that beat is scoring.
The spine must be the real practice run narrative, which already works:
  - shot 01 refused by the safety filter, agent reads the refusal rate, rephrases, recovers
  - shot 03 flags character drift at 78% against an 85% target and KEEPS the take anyway
    because a retry is not worth the budget — this beat proves judgement, not pass/fail
  - shot 05 attempted twice at 42% then 58% against a 90% continuity target, then ABANDONED
    at $12.50 of $15.00
Open on the problem, not the product. Close on the abandoned shot — the agent refusing to
waste money is the whole thesis. Show the Grafana panel and the decision log side by side at
least once, so a metric is visibly causing a decision.

### 4. "Built with" tag list for the Devpost form

### 5. Judge quickstart — how to try it in 30 seconds, no credentials

### 6. A pre-submission checklist of everything still outstanding
