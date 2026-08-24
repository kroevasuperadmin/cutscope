Replace the placeholder demo content with the real story. Read cutscope/web_worker.py and
shots/turning_point.yaml fully first.

## CONTEXT
"Mara" and "Noa" are invented placeholder characters. The real source material is
**Turning Point**, an original 13-episode screenplay written by the founder. It is already
in shots/turning_point.yaml with five shots and a `difficulty:` field on each.

Premise, for writing accurate labels: a broke 26-year-old man in 2024 is sent back to 2012,
finds his own 14-year-old self, and coaches him. The hardest things to generate are (a) the
same person at two ages, sometimes in one frame, and (b) the same field seen in 2012 and
again in 2000 before a playground was built on it.

## CHANGES
1. Live mode: load `shots/turning_point.yaml`, not `shots/demo.yaml`. Do not delete
   demo.yaml; leave it as a fixture.
2. Replace the production name "MARA // SIGNAL AT BLUE HOUR" everywhere (practice AND live)
   with "TURNING POINT // S1 · SHOT TEST".
3. Rewrite `_practice_run()` to replay these five shots in this exact order, using the real
   prompts from turning_point.yaml. The narrative must be:

   1. warehouse-displacement — attempt 1 REFUSED by the safety filter (weapon language:
      "pneumatic liquid strikes his chest"). Agent reads the refusal rate, DECIDES REPHRASE,
      softens to a device/energy description, attempt 2 succeeds.
   2. first-sighting-2012 — succeeds first attempt, cheap. Agent decides KEEP.
   3. arcade-coaching — succeeds, but the agent flags CHARACTER DRIFT between the two ages
      of the same person and notes it without retrying, because the take is within budget
      and usable. This shows judgement, not just pass/fail.
   4. the-field-2012 — succeeds first attempt. Agent notes it is now the reference anchor
      that shot 5 must match.
   5. the-field-2000 — the hardest shot. Attempt 1 fails continuity against shot 4.
      Attempt 2 rephrased, still drifts. Agent reads spend against the ceiling and DECIDES
      ABANDON rather than spend more. Run ends with this shot marked abandoned.

   Total practice spend must land near $12-13 of the $15 ceiling so the budget pressure is
   visible and the abandonment is obviously justified.

4. Every decision log entry keeps the existing three-part shape: what happened, the Grafana
   metric read, the decision taken. Never drop the metric line — it is the whole point.

Keep timings snappy; the practice run should complete in well under a minute. Run it locally
and paste the emitted decision log lines in your report so the narrative can be checked.
