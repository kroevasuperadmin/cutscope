"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { Film, Play, RotateCcw, Square, TriangleAlert } from "@/components/icons";
import {
  createInitialState,
  formatMoney,
  type ConsoleState,
  type DecisionLog,
  type MetricView,
  type RunEvent,
  type RunMode,
  type ShotState,
} from "@/lib/types";

const stateLabel: Record<ShotState, string> = {
  queued: "QUEUED",
  generating: "GENERATING",
  retrying: "RETRYING",
  done: "DONE",
  refused: "REFUSED",
  abandoned: "ABANDONED",
};

// One accent (Grafana blue) marks the shot being worked on. Amber marks the exceptions.
// Everything else is the foreground colour at reduced opacity, as Grafana does it.
const stateDot: Record<ShotState, string> = {
  queued: "bg-foreground/25",
  generating: "bg-primary",
  retrying: "bg-warning",
  done: "bg-foreground/55",
  refused: "bg-warning",
  abandoned: "bg-warning",
};

// Tone is carried by ONE colour: amber, and only on the entries that are exceptions.
// Side-specific colour only, so the row dividers stay grey.
const toneRule: Record<DecisionLog["tone"], string> = {
  neutral: "border-l-foreground/15",
  success: "border-l-foreground/15",
  info: "border-l-foreground/15",
  warning: "border-l-warning",
  danger: "border-l-warning",
};

function text(data: Record<string, unknown>, key: string, fallback = ""): string {
  return typeof data[key] === "string" ? data[key] : fallback;
}

function number(data: Record<string, unknown>, key: string, fallback = 0): number {
  return typeof data[key] === "number" && Number.isFinite(data[key]) ? data[key] : fallback;
}

function time(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

/** "SHOT 01 · WAREHOUSE DISPLACEMENT" -> ["SHOT 01", "WAREHOUSE DISPLACEMENT"]. */
function splitLabel(label: string): [string, string] {
  const match = /^(SHOT\s*\d+)\s*[·\-–—]\s*(.+)$/i.exec(label.trim());
  return match ? [match[1].toUpperCase(), match[2]] : ["", label];
}

/**
 * The worker labels its own evidence: "Grafana: ..." on a live run, "Scripted: ..." in
 * practice. Read that label off the string instead of asserting one, so practice mode is
 * never captioned as a Grafana query.
 */
function splitSource(line: string): [string, string] {
  const at = line.indexOf(":");
  if (at < 1 || at > 20) return ["", line];
  return [line.slice(0, at), line.slice(at + 1).trim()];
}

/** "DECISION: RETRY REPHRASED - submit the ..." -> ["RETRY REPHRASED", "submit the ..."]. */
function splitDecision(line: string): [string, string] {
  const body = line.replace(/^DECISION:\s*/i, "").trim();
  const at = body.indexOf(" - ");
  if (at < 0 || at > 24) return [body, ""];
  return [body.slice(0, at), body.slice(at + 3)];
}

function upsertMetric(metrics: MetricView[], patch: MetricView): MetricView[] {
  const index = metrics.findIndex((metric) => metric.shotId === patch.shotId);
  if (index < 0) return [...metrics, patch];
  return metrics.map((metric, metricIndex) => (metricIndex === index ? patch : metric));
}

function newLog(event: RunEvent): DecisionLog {
  const tone = text(event.data, "tone", "neutral");
  return {
    id: `${event.timestamp}-${text(event.data, "headline")}`,
    time: time(event.timestamp),
    headline: text(event.data, "headline"),
    metric: text(event.data, "metric"),
    decision: text(event.data, "decision"),
    tone: ["neutral", "success", "warning", "danger", "info"].includes(tone)
      ? (tone as DecisionLog["tone"])
      : "neutral",
  };
}

function reduceEvent(previous: ConsoleState, event: RunEvent): ConsoleState {
  const shotId = text(event.data, "shot_id");
  switch (event.type) {
    case "run.started":
      return {
        ...previous,
        status: "running",
        productionName: text(event.data, "production_name", previous.productionName),
        budget: number(event.data, "budget", previous.budget),
      };
    case "shot.updated":
      return {
        ...previous,
        shots: previous.shots.map((shot) =>
          shot.id === shotId
            ? {
                ...shot,
                state: text(event.data, "state", shot.state) as ShotState,
                attempt: number(event.data, "attempt", shot.attempt),
                maxAttempts: number(event.data, "max_attempts", shot.maxAttempts),
                cost: number(event.data, "cost", shot.cost),
                prompt: text(event.data, "prompt", shot.prompt),
              }
            : shot,
        ),
      };
    case "metrics.updated": {
      const metric: MetricView = {
        shotId,
        cost: number(event.data, "cost"),
        retries: number(event.data, "retries"),
        refusals: number(event.data, "refusals"),
        latencySeconds:
          typeof event.data.latency_seconds === "number" ? event.data.latency_seconds : null,
      };
      return {
        ...previous,
        spent: number(event.data, "spent", previous.spent),
        metrics: upsertMetric(previous.metrics, metric),
      };
    }
    case "take.updated":
      return {
        ...previous,
        take: {
          shotId,
          label: text(event.data, "label"),
          prompt: text(event.data, "prompt"),
          mediaUrl: text(event.data, "media_url") || undefined,
          isPractice: event.data.is_practice === true,
        },
      };
    // Oldest first: the log reads forwards, the way the run happened.
    case "decision.log":
      return { ...previous, decisions: [...previous.decisions, newLog(event)] };
    case "run.finished":
      return { ...previous, status: "finished" };
    case "run.stopped":
      return {
        ...previous,
        status: "stopped",
        shots: previous.shots.map((shot) =>
          shot.state === "generating" || shot.state === "retrying" ? { ...shot, state: "abandoned" } : shot,
        ),
        decisions: [
          ...previous.decisions,
          {
            id: `${event.timestamp}-stopped`,
            time: time(event.timestamp),
            headline: "Operator stopped the production",
            metric:
              previous.mode === "practice"
                ? "Scripted: the replay was halted with the worker"
                : "Grafana: further collection halted with the worker",
            decision: "DECISION: STOP - no further Veo submissions allowed",
            tone: "warning",
          },
        ],
      };
    case "run.error":
      return { ...previous, status: "error", error: text(event.data, "message", "The worker could not continue.") };
    default:
      return previous;
  }
}

const brief: Array<{ label: string; body: ReactNode }> = [
  {
    label: "Problem",
    body: "AI film production is blind: 596 prompt attempts and 85 documented failures across Hailuo, Kling, Higgsfield, and Veo left no clear view of cost, refusals, failure rate, or character drift.",
  },
  {
    label: "System",
    body: "A Gemini agent on Google Cloud Agent Builder runs each shot and reads live Grafana metrics to decide whether to retry, rephrase, or stop spending.",
  },
  {
    label: "Watch",
    body: (
      <>
        Shot 01 is refused, then recovers. Shot 05 is deliberately{" "}
        <span className="text-warning">abandoned</span> when another attempt is not worth the spend.
      </>
    ),
  },
  {
    label: "Source",
    body: (
      <>
        These shots come from <span className="text-foreground">Turning Point</span>, the author&apos;s original
        13-episode screenplay; the submission uses the author&apos;s original work.
      </>
    ),
  },
];

export function ProductionConsole() {
  const [state, setState] = useState<ConsoleState>(() => createInitialState());
  const [mode, setMode] = useState<RunMode>("practice");
  const streamRef = useRef<EventSource | null>(null);
  const logRef = useRef<HTMLOListElement | null>(null);
  const pinnedRef = useRef(true);

  const closeStream = useCallback(() => {
    streamRef.current?.close();
    streamRef.current = null;
  }, []);

  useEffect(() => {
    if (!state.runId) return;
    closeStream();
    const stream = new EventSource(`/api/runs/${state.runId}/events`);
    streamRef.current = stream;
    stream.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as RunEvent;
        setState((current) => reduceEvent(current, event));
      } catch {
        setState((current) => ({ ...current, status: "error", error: "The live event stream sent an invalid update." }));
      }
    };
    stream.onerror = () => {
      if (stream.readyState === EventSource.CLOSED) {
        setState((current) =>
          current.status === "running" || current.status === "starting"
            ? { ...current, status: "error", error: "The live event stream disconnected. Try a new run." }
            : current,
        );
      }
    };
    return () => stream.close();
  }, [state.runId, closeStream]);

  useEffect(() => () => closeStream(), [closeStream]);

  // The log grows downwards, so keep the newest entry in view unless the judge has
  // scrolled up to read an earlier decision.
  useEffect(() => {
    const list = logRef.current;
    if (list && pinnedRef.current) list.scrollTop = list.scrollHeight;
  }, [state.decisions.length]);

  const start = async () => {
    if (state.status === "starting" || state.status === "running") return;
    closeStream();
    pinnedRef.current = true;
    setState({ ...createInitialState(mode), status: "starting" });
    try {
      const response = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      const payload = (await response.json()) as { runId?: string; error?: string };
      if (!response.ok || !payload.runId) throw new Error(payload.error || "Could not start the worker.");
      setState((current) => ({ ...current, runId: payload.runId ?? null }));
    } catch (error) {
      setState((current) => ({
        ...current,
        status: "error",
        error: error instanceof Error ? error.message : "Could not start the worker.",
      }));
    }
  };

  const stop = async () => {
    if (!state.runId || (state.status !== "running" && state.status !== "starting")) return;
    try {
      const response = await fetch(`/api/runs/${state.runId}/stop`, { method: "POST" });
      if (!response.ok) throw new Error("The stop request was not accepted.");
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : "Could not stop the worker.",
      }));
    }
  };

  const active = state.status === "starting" || state.status === "running";
  // Before a run the toggle is the truth; from the moment one starts, the run's own mode is.
  const shownMode: RunMode = state.status === "idle" ? mode : state.mode;
  const practice = shownMode === "practice";
  const startLabel = active ? "Running" : mode === "practice" ? "Start practice run" : "Start live run";

  return (
    <main className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 md:px-6">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <span className="text-base font-semibold tracking-[0.08em] text-foreground">CUTSCOPE</span>
            <span
              className={`inline-flex shrink-0 items-center gap-2 rounded border px-2 py-1 font-mono text-2xs ${
                practice ? "border-border text-muted-foreground" : "border-primary/60 text-foreground"
              }`}
              title={practice ? "Scripted replay. No paid API is called." : "Live run against Vertex AI."}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${practice ? "bg-foreground/40" : "bg-primary"}`} />
              {practice ? "PRACTICE" : "LIVE"}
              <span className="hidden sm:inline">{practice ? "· scripted replay" : "· Vertex AI"}</span>
              {practice ? <span className="hidden xl:inline">· no paid API calls</span> : null}
            </span>
            <p className="hidden min-w-0 truncate text-muted-foreground lg:block">{state.productionName}</p>
          </div>

          <div
            className="shrink-0 text-right"
            aria-label={`${practice ? "Simulated" : "Live"} spend ${formatMoney(state.spent)} of ${formatMoney(state.budget)}`}
          >
            <p className="text-2xs text-muted-foreground">{practice ? "Simulated spend" : "Live spend"}</p>
            <p className="font-mono tabular-nums">
              {formatMoney(state.spent)} <span className="text-muted-foreground">/ {formatMoney(state.budget)}</span>
            </p>
          </div>

          <div className="flex w-full items-center gap-2 md:w-auto">
            <div className="inline-flex shrink-0 rounded border p-0.5" role="group" aria-label="Run mode">
              {(["practice", "live"] as RunMode[]).map((option) => (
                <button
                  key={option}
                  aria-pressed={mode === option}
                  className={`rounded px-2.5 py-1.5 text-xs capitalize transition-colors duration-100 ease-out focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-45 ${
                    mode === option ? "bg-panel-raised text-foreground" : "text-muted-foreground hover:text-foreground"
                  }`}
                  disabled={active}
                  onClick={() => setMode(option)}
                  type="button"
                >
                  {option}
                </button>
              ))}
            </div>
            <button
              aria-label={startLabel}
              className="inline-flex h-9 min-w-0 flex-1 items-center justify-center gap-2 rounded bg-primary px-3 font-medium text-primary-foreground transition-colors duration-100 ease-out hover:bg-primary/85 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-45 md:flex-none"
              disabled={active}
              onClick={start}
              type="button"
            >
              <Play className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {/* The mode is already stated twice beside this button, so the phone label is short. */}
              <span className="truncate sm:hidden">{active ? "Running" : "Start run"}</span>
              <span className="hidden truncate sm:inline">{startLabel}</span>
            </button>
            <button
              aria-label="Stop the production"
              className="inline-flex h-9 shrink-0 items-center gap-2 rounded border border-danger/60 px-3 font-medium text-danger transition-colors duration-100 ease-out hover:bg-danger/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:border-border disabled:text-muted-foreground disabled:opacity-45"
              disabled={!active}
              onClick={stop}
              type="button"
            >
              <Square className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span className="hidden sm:inline">Stop</span>
            </button>
          </div>
        </div>
      </header>

      <section aria-labelledby="cutscope-brief-heading" className="border-b">
        <div className="mx-auto max-w-screen-2xl px-4 py-5 md:px-6">
          <h1 id="cutscope-brief-heading" className="text-2xl font-normal text-foreground">
            Agentic production control for AI film
          </h1>
          <div className="mt-4 grid gap-x-10 gap-y-3 md:grid-cols-2 xl:grid-cols-4">
            {brief.map((item) => (
              <div key={item.label}>
                <p className="text-2xs text-muted-foreground">{item.label}</p>
                <p className="mt-1 text-muted-foreground">{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="mx-auto grid max-w-screen-2xl gap-4 px-4 py-4 md:px-6 xl:grid-cols-12">
        <section aria-labelledby="shot-list-heading" className="rounded border bg-panel xl:col-span-3">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <h2 id="shot-list-heading" className="font-medium text-foreground">Shot list</h2>
            <span className="text-2xs text-muted-foreground">{state.shots.length} shots</span>
          </div>
          <ol className="divide-y">
            {state.shots.map((shot) => {
              const [code, title] = splitLabel(shot.label);
              return (
                <li key={shot.id} className="flex items-start gap-3 px-4 py-2.5">
                  <span
                    className={`mt-[7px] h-2 w-2 shrink-0 rounded-full ${stateDot[shot.state]}`}
                    aria-label={stateLabel[shot.state]}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-foreground">
                      {code ? <span className="mr-2 font-mono text-2xs text-muted-foreground">{code}</span> : null}
                      {title}
                    </p>
                    <p className="mt-0.5 font-mono text-2xs text-muted-foreground">
                      {stateLabel[shot.state].toLowerCase()}
                      {shot.state === "retrying" ? ` ${shot.attempt}/${shot.maxAttempts}` : ""}
                      {shot.cost > 0 ? `  ·  ${formatMoney(shot.cost)}` : ""}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        <section aria-labelledby="take-heading" className="overflow-hidden rounded border bg-panel xl:col-span-5">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <h2 id="take-heading" className="font-medium text-foreground">Current take</h2>
            <span className="inline-flex items-center gap-2 text-2xs text-muted-foreground">
              <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-primary" : "bg-foreground/30"}`} />
              {active ? "streaming" : state.status === "finished" ? "complete" : state.status === "stopped" ? "stopped" : "ready"}
            </span>
          </div>
          <div className="p-4">
            {state.take ? (
              <div className="overflow-hidden rounded border">
                <div className="aspect-video bg-background">
                  {state.take.mediaUrl ? (
                    <div className="relative h-full w-full">
                      <video
                        autoPlay
                        className="h-full w-full object-cover"
                        controls
                        loop={state.take.isPractice}
                        muted={state.take.isPractice}
                        playsInline
                        src={state.take.mediaUrl}
                      >
                        Your browser cannot play this take.
                      </video>
                      {state.take.isPractice ? (
                        <span className="pointer-events-none absolute left-3 top-3 rounded bg-background/85 px-2 py-1 font-mono text-2xs text-muted-foreground">
                          PRACTICE PLAYBACK · SCRIPTED VISUAL
                        </span>
                      ) : null}
                    </div>
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center gap-3 bg-panel-raised p-6 text-center">
                      <Film className="h-7 w-7 text-muted-foreground" aria-hidden="true" />
                      <p className="font-mono text-2xs text-muted-foreground">VEO TAKE STORED · PLAYBACK URL PENDING</p>
                    </div>
                  )}
                </div>
                <div className="border-t px-4 py-2">
                  <p className="font-mono text-2xs text-muted-foreground">{state.take.label}</p>
                </div>
              </div>
            ) : (
              <div className="flex aspect-video flex-col items-center justify-center rounded border bg-muted p-6 text-center">
                <Film className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
                <h3 className="mt-4 text-lg font-normal">The stage is ready.</h3>
                <p className="mt-2 max-w-sm text-muted-foreground">
                  {mode === "practice"
                    ? "Practice mode replays a refusal and a deliberate budget stop without calling paid APIs."
                    : "Live mode uses only Vertex AI Gemini, Vertex AI Veo, and Grafana. Server credentials stay on the server."}
                </p>
                <button
                  className="mt-5 inline-flex h-9 items-center gap-2 rounded border px-3 font-medium transition-colors duration-100 ease-out hover:bg-panel-raised focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-45"
                  disabled={active}
                  onClick={start}
                  type="button"
                >
                  <Play className="h-3.5 w-3.5" aria-hidden="true" />
                  {startLabel}
                </button>
              </div>
            )}

            <div className="mt-4 rounded border p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <span className="text-2xs text-muted-foreground">Prompt</span>
                <span className="font-mono text-2xs text-muted-foreground">
                  {practice ? "practice · scripted, not sent to Veo" : "live · exactly as Veo received it"}
                </span>
              </div>
              <p className="mt-2 whitespace-pre-wrap font-mono text-xs leading-5 text-foreground">
                {state.take?.prompt ??
                  state.shots.find((shot) => shot.state === "generating" || shot.state === "retrying")?.prompt ??
                  (practice
                    ? "The scripted prompt for the shot in progress will appear here. Practice mode sends nothing to Veo."
                    : "The submitted prompt will appear here, exactly as Veo received it.")}
              </p>
            </div>

            {state.status === "finished" || state.status === "stopped" ? (
              <button
                className="mt-4 inline-flex h-9 items-center gap-2 rounded border px-3 font-medium transition-colors duration-100 ease-out hover:bg-panel-raised focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                onClick={start}
                type="button"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                Run again
              </button>
            ) : null}

            {state.error ? (
              <div className="mt-4 flex items-start gap-3 rounded border border-danger/50 p-4">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden="true" />
                <div>
                  <p className="font-medium">The run needs attention.</p>
                  <p className="mt-1 text-muted-foreground">{state.error}</p>
                  <button
                    className="mt-3 inline-flex h-9 items-center gap-2 rounded border px-3 font-medium transition-colors duration-100 ease-out hover:bg-panel-raised focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                    onClick={start}
                    type="button"
                  >
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                    Try again
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </section>

        {/* Capped so the list itself scrolls and stays pinned to the newest entry, instead of
            growing the page and pushing the newest decision out of sight. */}
        <section
          aria-labelledby="decision-log-heading"
          className="flex max-h-[38rem] min-h-[24rem] flex-col overflow-hidden rounded border bg-panel xl:col-span-4"
        >
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <h2 id="decision-log-heading" className="font-medium text-foreground">Agent decision log</h2>
            <span className="text-2xs text-muted-foreground">oldest first</span>
          </div>
          {state.decisions.length ? (
            <ol
              aria-live="polite"
              className="flex-1 divide-y overflow-y-auto"
              onScroll={(event) => {
                const list = event.currentTarget;
                pinnedRef.current = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
              }}
              ref={logRef}
            >
              {state.decisions.map((entry) => {
                const [source, evidence] = splitSource(entry.metric);
                const [verb, rationale] = splitDecision(entry.decision);
                return (
                  <li key={entry.id} className={`border-l-2 px-4 py-3 ${toneRule[entry.tone]}`}>
                    <p className="font-mono text-2xs text-muted-foreground">{entry.time}</p>
                    <p className="mt-0.5 text-foreground">{entry.headline}</p>
                    {evidence ? (
                      <p className="mt-1.5 font-mono text-2xs leading-4 text-muted-foreground">
                        {source ? <span className="text-foreground/50">{source} </span> : null}
                        {evidence}
                      </p>
                    ) : null}
                    {verb ? (
                      <p className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs">
                        <span className="rounded border px-1.5 py-0.5 font-mono text-2xs text-foreground">{verb}</span>
                        <span className="text-muted-foreground">{rationale}</span>
                      </p>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
              <p className="font-medium">No decision yet</p>
              <p className="mt-2 max-w-xs text-muted-foreground">
                Start a run to watch each metric cause the next action.
              </p>
            </div>
          )}
        </section>
      </div>

      <footer aria-labelledby="grafana-panel-heading" className="mx-auto max-w-screen-2xl px-4 pb-6 md:px-6">
        <section className="overflow-hidden rounded border bg-panel">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <h2 id="grafana-panel-heading" className="font-medium text-foreground">Telemetry</h2>
            <span className="text-2xs text-muted-foreground">
              {practice ? "scripted · nothing queried from Grafana" : "Grafana Cloud · Mimir query window"}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[42rem] text-left">
              <thead className="text-2xs text-muted-foreground">
                <tr className="border-b">
                  <th className="px-4 py-2 font-normal">Shot</th>
                  <th className="px-4 py-2 text-right font-normal">Cost</th>
                  <th className="px-4 py-2 text-right font-normal">Retries</th>
                  <th className="px-4 py-2 text-right font-normal">Refusals</th>
                  <th className="px-4 py-2 text-right font-normal">Latency</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {state.metrics.map((metric) => (
                  <tr key={metric.shotId}>
                    <td className="px-4 py-1.5">{metric.shotId.replace(/-/g, " ")}</td>
                    <td className="px-4 py-1.5 text-right font-mono text-xs tabular-nums">{formatMoney(metric.cost)}</td>
                    <td className="px-4 py-1.5 text-right font-mono text-xs tabular-nums">{metric.retries}</td>
                    <td className="px-4 py-1.5 text-right font-mono text-xs tabular-nums">{metric.refusals}</td>
                    <td className="px-4 py-1.5 text-right font-mono text-xs tabular-nums">
                      {metric.latencySeconds === null ? "—" : `${metric.latencySeconds.toFixed(1)}s`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </footer>
    </main>
  );
}
