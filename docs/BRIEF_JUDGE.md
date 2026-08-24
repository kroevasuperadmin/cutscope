Two fixes so a judge who has never heard of this understands it in ten seconds.
Read components/production-console.tsx, app/page.tsx and README.md fully first.

## PROBLEM 1 — the page never explains itself
Right now a judge lands on a control panel showing five shot names and a spend meter, with
no statement of what CUTSCOPE is or what problem it solves. Two of the four judging criteria
are "Design — a complete coherent product, not a proof of concept" and "Quality of Idea —
creative, non-obvious integration showing genuine problem understanding." The page currently
demonstrates neither, because it never says what the idea IS.

Add a compact explanation ABOVE the console. Not a marketing landing page — three or four
lines that a judge reads in ten seconds, then presses the button. It must convey:

  - THE PROBLEM: AI film production is blind. A director fires hundreds of generations across
    providers with no visibility into cost, failure rate, safety refusals, or character drift.
    Ground it in the real number: this project's author directed an AI-generated film series
    across Hailuo, Kling, Higgsfield and Veo — 596 prompt attempts, 85 documented failures.
  - WHAT THIS IS: a Gemini agent on Google Cloud Agent Builder that runs the production shot
    by shot and reads its own live Grafana metrics to decide retry, rephrase, or stop spending.
  - WHAT TO WATCH: tell them explicitly that in the run they are about to see, shot 01 gets
    refused and recovers, and shot 05 is deliberately ABANDONED when the agent judges further
    spend unjustified. A judge who is told what to look for sees it; one who is not, misses it.
  - THE SOURCE: the shots come from "Turning Point", an original 13-episode screenplay by the
    author. Say it is original work — the rules require entrants to own their submission, and
    stating it plainly removes any doubt.

Keep the existing dark aesthetic. Must not push the console below the fold on a laptop, and
must stay readable on a phone. Collapsible is acceptable if it is expanded by default.

## PROBLEM 2 — README is not judge-ready
Rewrite README.md for someone who has never seen this repo and may try to run it:
  - What it is and the problem it solves, in the first three lines. Lead with what it DOES.
  - The live URL: https://cutscope.rizqey.com — and say practice mode needs no credentials
    and costs nothing, so it works even if cloud credits have expired. (Judges being unable
    to run entries after credits lapse is a known, documented complaint about this hackathon.)
  - Architecture: what runs where. Gemini and Veo on Vertex AI, Grafana Cloud over OTLP,
    Next.js console and Python worker in one container on Cloud Run.
  - Exact local setup steps that actually work, tested against the current repo.
  - An honest "what is real vs simulated" section: practice mode is a scripted replay with no
    paid calls; live mode calls Vertex AI for real. Do not blur this — judges verify, and
    being caught overstating is fatal.
  - Apache-2.0 licence noted.
No hype, no emoji, no invented traction numbers.

Verify the build compiles (`npm run build`) before reporting. Report what you changed.
