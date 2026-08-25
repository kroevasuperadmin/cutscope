# Where CUTSCOPE sits — evidenced, 25 Aug 2026

## The one line
Runway can cap what ONE generation costs. It cannot tell you that you have spent $12 on a
shot that is never going to work. CUTSCOPE watches the PRODUCTION, not the generation.

## The closest competitor, and exactly where it stops
**Runway Media Router** (announced 2026, Runway raised a $315M Series E) — the only shipped
product doing cost-aware routing for AI video. From their own announcement:

| Capability | Media Router | CUTSCOPE |
|---|---|---|
| Model routing | across their catalog incl. Seedance, GPT Image 2, ElevenLabs | across the user's OWN provider accounts |
| Spend cap | "a hard ceiling **per generation**, in USD per second" | per shot AND per production |
| Retry on failure | not mentioned | retries, and REPHRASES based on why it failed |
| Safety-refusal detection | not mentioned | first-class outcome, drives the next decision |
| Character / continuity drift | not mentioned | scored, and can decide a take is good enough |
| Cost history, failure analytics | not mentioned | the whole point |

Source: https://runway.com/news/company-news/introducing-runway-media-router

## The metric nobody else can compute
**Cost per APPROVED shot** — what the usable footage actually cost, including every refusal,
retry and rejected take. Sticker price per generation is what everyone quotes; it is not what
a producer pays. You can only compute it if you recorded the failures, and nobody is.

## Why the category is not invented
This is observability, pointed at video for the first time.
- Sentry / Datadog: watch your app, tell you what broke, how often, at what cost.
- Helicone: same, for LLM calls. ~$1M revenue, 5 people, YC W23. A PROXY — you change one
  line, `api.openai.com` -> `oai.helicone.ai`.
- Langfuse: same, acquired by ClickHouse.
- CUTSCOPE: same, for video generation. Nobody has done it.

## The honest caveat
Research on 24 Aug found NO company publicly spending $2k+/month on AI video generation, and
no creator asking for a monitoring tool — they switch providers instead. The pain is
evidenced and severe (creators report wasting most of their credits); the willingness to buy
a tool is not yet evidenced. This is a strong hackathon entry and an unproven business.
See docs/ROADMAP.md and the strata research in dev/hackathon-radar/strata-cutscope/.
