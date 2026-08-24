# CUTSCOPE — shape roadmap

Decided 24 Aug 2026 by Council T1+T2 (8 models incl. IlmuClaw and Codex).

## Now — Web App (hackathon, deadline 9 Sep 2026)
Hosted console. Unanimous, 8/8. Required by the rules: judges need a public URL.
Not throwaway — every proxy business needs this console anyway.

## Next — Proxy / middleware
The real business shape. 4 of 8 incl. Codex.
The director repoints their base URL at CUTSCOPE and keeps working. CUTSCOPE sits
between them and Veo/Kling/Hailuo/Higgsfield, meters every call, catches refusals,
tracks consistency drift, and trips the spend circuit breaker.
Adoption cost: one line changed. This is how Datadog, Segment, Cloudflare and
OpenRouter all work. Observability is what it SELLS; the proxy is HOW it works.
Open risk: custody of other people's API keys and spend. Security burden before
revenue.

## Later — MCP server
CUTSCOPE is a judgement service, not a human tool: "was this generation worth the
money, retry or stop?" Other AI agents should call it directly. Becomes correct as
agents, not humans, drive generation. Distribution channel, not the core.

## Later — Discord bot
AI film communities live on Discord — that is where generations happen and where
failures get complained about in public. Distribution where the pain is already
being voiced.

## Explicitly NOT
- **Editing app / editing-suite plugin** — that is Veezho's lane. Do not compete
  with our own product.
- **Autonomous agent with no control surface** — nobody trusts a bot that spends
  their money unsupervised.

## Killer feature (Codex, best line of the session)
A shot-level **spend circuit breaker**: retries intelligently, or stops the waste
automatically.
