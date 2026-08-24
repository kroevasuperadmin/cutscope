# CUTSCOPE

An agentic production controller for AI-generated film.

A Gemini agent on Google Cloud Agent Builder orchestrates video generation shot by
shot, and reads its own live Grafana telemetry — cost per shot, retry counts,
provider refusals, character-consistency drift — to decide whether to retry, change
prompt strategy, or stop spending.

Built for **Agentic Cinema: The Blockbuster Hackathon** (Grafana track).

## Why

Multi-model GenAI film production is blind. A director fires hundreds of generations
across many providers with no visibility into what failed, what it cost, or which
prompts actually worked. That is an observability problem, and observability is a
solved discipline — it has just never been pointed at this.

## Status

Scaffold. See `docs/PLAN.md`.

## Licence

Apache-2.0
