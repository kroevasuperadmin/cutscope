# Langfuse — measured in the live app, 25 Aug 2026 (signed in, demo project, 95 traces)

## Computed styles (from getComputedStyle, not guessed)
- body: system-ui sans, 16px, fg rgb(2,8,23) on white
- table row: **29px tall**, 1px bottom border rgb(226,232,240)
- table cell: **11.2px**, padding 0 0 0 8px
- section heading: 17.6px / 600
- button: radius 4px, 20px tall, 10px text
- CSS tokens (shadcn defaults, unmodified):
  --foreground 222.2 84% 4.9% · --muted-foreground 215.4 16.3% 46.9%
  --border 214.3 31.8% 91.4% · --muted 210 40% 96.1% · --radius .5rem
  --destructive 0 84.2% 60.2%

## What makes it not vibe-coded (observed)
1. ONE accent (purple) on exactly two things: the trace-type icon and the histogram bars.
   Everything else is 4 greys. Red appears ONLY next to money.
2. Data is louder than labels. Timestamps are plain `2026-08-24 23:11:55`. Column headers
   are 11px grey. Nothing is uppercase-tracked.
3. Per-step cost + latency sit UNDER the step name in small mono: `5.21s  Σ $0.002715`.
   Evaluation verdicts are grey pill chips: `is_cursing: False`, `answer_relevance 0.40`.
   -> this is the exact model for a CUTSCOPE decision-log row.
4. A tiny activity histogram above the table is the whole "live" signal. No pulsing dots.
5. Density: ~18 rows visible at 589px height. Nothing has room to breathe because it
   doesn't need to.

## Steal
The trace tree: name / cost+latency underneath / verdict chips. One grey, red for money.

## Do not copy
Light theme. CUTSCOPE sits next to a Grafana panel, which is dark; stay dark.
