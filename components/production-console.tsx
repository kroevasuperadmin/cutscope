"use client";

import {
  Activity,
  Ban,
  CircleStop,
  Film,
  Gauge,
  Play,
  Radio,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

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

const stateColor: Record<ShotState, string> = {
  queued: "bg-muted-foreground",
  generating: "bg-info signal-pulse",
  retrying: "bg-warning signal-pulse",
  done: "bg-success",
  refused: "bg-danger",
  abandoned: "bg-warning",
};

const toneColor: Record<DecisionLog["tone"], string> = {
  neutral: "border-border",
  success: "border-success/50",
  warning: "border-warning/50",
  danger: "border-danger/50",
  info: "border-info/50",
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
    case "decision.log":
      return { ...previous, decisions: [newLog(event), ...previous.decisions] };
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
          {
            id: `${event.timestamp}-stopped`,
            time: time(event.timestamp),
            headline: "OPERATOR STOPPED THE PRODUCTION",
            metric: "Grafana: further collection halted with the worker",
            decision: "DECISION: STOP — no further Veo submissions allowed",
            tone: "warning",
          },
          ...previous.decisions,
        ],
      };
    case "run.error":
      return { ...previous, status: "error", error: text(event.data, "message", "The worker could not continue.") };
    default:
      return previous;
  }
}

export function ProductionConsole() {
  const [state, setState] = useState<ConsoleState>(() => createInitialState());
  const [mode, setMode] = useState<RunMode>("practice");
  const streamRef = useRef<EventSource | null>(null);

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

  const start = async () => {
    if (state.status === "starting" || state.status === "running") return;
    closeStream();
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
  const runLabel = mode === "practice" ? "Start practice run" : "Start live run";

  return (
    <main className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center gap-3 px-4 py-3 md:px-6">
          <div className="flex items-center gap-2 font-mono text-sm font-semibold tracking-[0.2em] text-primary">
            <Radio className="h-4 w-4" aria-hidden="true" />
            CUTSCOPE
          </div>
          <span className="hidden text-muted-foreground sm:inline" aria-hidden="true">·</span>
          <p className="min-w-0 flex-1 truncate text-sm font-medium tracking-wide">{state.productionName}</p>
          <div className="flex items-baseline gap-1 font-mono text-sm" aria-label={`Live spend ${formatMoney(state.spent)} of ${formatMoney(state.budget)}`}>
            <span className="text-muted-foreground">LIVE SPEND</span>
            <span className="font-semibold">{formatMoney(state.spent)} / {formatMoney(state.budget)}</span>
          </div>
          <label className="flex min-h-10 cursor-pointer items-center gap-2 rounded-md border bg-panel px-3 text-xs font-medium text-muted-foreground focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background">
            <input
              checked={mode === "practice"}
              className="h-4 w-4 accent-primary"
              disabled={active}
              onChange={(event) => setMode(event.target.checked ? "practice" : "live")}
              type="checkbox"
            />
            Practice run
          </label>
          <button
            aria-label="Stop the production"
            className="inline-flex min-h-10 items-center gap-2 rounded-md border border-danger/70 bg-danger/10 px-3 text-sm font-semibold text-foreground transition-colors duration-100 ease-out hover:bg-danger/20 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-45"
            disabled={!active}
            onClick={stop}
            type="button"
          >
            <CircleStop className="h-4 w-4" aria-hidden="true" />
            STOP
          </button>
        </div>
      </header>

      <div className="mx-auto grid max-w-screen-2xl gap-4 px-4 py-4 md:px-6 xl:grid-cols-12">
        <section aria-labelledby="shot-list-heading" className="rounded-lg border bg-panel xl:col-span-3">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h1 id="shot-list-heading" className="font-mono text-xs font-semibold tracking-[0.16em] text-muted-foreground">SHOT LIST</h1>
            <span className="font-mono text-xs text-muted-foreground">{state.shots.length} SHOTS</span>
          </div>
          <ol className="divide-y">
            {state.shots.map((shot) => (
              <li key={shot.id} className="flex items-start gap-3 px-4 py-4">
                <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${stateColor[shot.state]}`} aria-label={stateLabel[shot.state]} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{shot.label}</p>
                  <p className="mt-1 font-mono text-xs text-muted-foreground">
                    {stateLabel[shot.state]}
                    {shot.state === "retrying" ? ` (${shot.attempt}/${shot.maxAttempts})` : ""}
                  </p>
                </div>
                <span className="font-mono text-xs text-muted-foreground">{formatMoney(shot.cost)}</span>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="take-heading" className="overflow-hidden rounded-lg border bg-panel xl:col-span-5">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h2 id="take-heading" className="font-mono text-xs font-semibold tracking-[0.16em] text-muted-foreground">CURRENT TAKE</h2>
            <span className={`inline-flex items-center gap-2 font-mono text-xs ${active ? "text-primary" : "text-muted-foreground"}`}>
              <span className={`h-2 w-2 rounded-full ${active ? "bg-primary signal-pulse" : "bg-muted-foreground"}`} />
              {active ? "STREAMING" : state.status === "finished" ? "COMPLETE" : "READY"}
            </span>
          </div>
          <div className="p-4">
            {state.take ? (
              <div className="overflow-hidden rounded-md border bg-background">
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
                        <span className="pointer-events-none absolute left-3 top-3 rounded bg-background/80 px-2 py-1 font-mono text-xs font-semibold tracking-wide text-primary">
                          PRACTICE PLAYBACK · SCRIPTED VISUAL
                        </span>
                      ) : null}
                    </div>
                  ) : (
                    <div className="scanlines flex h-full flex-col items-center justify-center gap-3 bg-panel-raised p-6 text-center">
                      <Film className="h-9 w-9 text-primary" aria-hidden="true" />
                      <p className="font-mono text-xs text-muted-foreground">VEO TAKE STORED · PLAYBACK URL PENDING</p>
                    </div>
                  )}
                </div>
                <div className="border-t px-4 py-3">
                  <p className="font-mono text-xs text-primary">{state.take.label}</p>
                </div>
              </div>
            ) : (
              <div className="scanlines flex aspect-video flex-col items-center justify-center rounded-md border bg-panel-raised p-6 text-center">
                <Film className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
                <h3 className="mt-4 text-base font-semibold">The stage is ready.</h3>
                <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
                  {mode === "practice"
                    ? "Practice mode replays a refusal and a deliberate budget stop without calling paid APIs."
                    : "Live mode uses only Vertex AI Gemini, Vertex AI Veo, and Grafana. Server credentials stay on the server."}
                </p>
                <button
                  className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground transition-colors duration-100 ease-out hover:bg-primary/85 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={active}
                  onClick={start}
                  type="button"
                >
                  {active ? <Activity className="h-4 w-4 animate-pulse" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
                  {active ? "Production running" : runLabel}
                </button>
              </div>
            )}
            <div className="mt-4 rounded-md border bg-background p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
                <Gauge className="h-4 w-4" aria-hidden="true" />
                EXACT PROMPT USED
              </div>
              <p className="whitespace-pre-wrap font-mono text-sm leading-6 text-foreground">
                {state.take?.prompt ?? state.shots.find((shot) => shot.state === "generating" || shot.state === "retrying")?.prompt ?? "The submitted prompt will appear here, exactly as Veo received it."}
              </p>
            </div>
            {state.status === "finished" || state.status === "stopped" ? (
              <button
                className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-md border px-3 text-sm font-medium transition-colors duration-100 ease-out hover:bg-panel-raised focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                onClick={start}
                type="button"
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Run again
              </button>
            ) : null}
            {state.error ? (
              <div className="mt-4 flex items-start gap-3 rounded-md border border-danger/50 bg-danger/10 p-4">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden="true" />
                <div>
                  <p className="text-sm font-semibold">The run needs attention.</p>
                  <p className="mt-1 text-sm text-muted-foreground">{state.error}</p>
                  <button
                    className="mt-3 inline-flex min-h-10 items-center gap-2 rounded-md border px-3 text-sm font-medium transition-colors duration-100 ease-out hover:bg-panel-raised focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                    onClick={start}
                    type="button"
                  >
                    <RotateCcw className="h-4 w-4" aria-hidden="true" />
                    Try again
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </section>

        <section aria-labelledby="decision-log-heading" className="flex min-h-[32rem] flex-col overflow-hidden rounded-lg border bg-panel xl:col-span-4">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h2 id="decision-log-heading" className="font-mono text-xs font-semibold tracking-[0.16em] text-muted-foreground">AGENT DECISION LOG</h2>
            <span className="font-mono text-xs text-primary">NEWEST FIRST</span>
          </div>
          {state.decisions.length ? (
            <ol className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
              {state.decisions.map((entry) => (
                <li key={entry.id} className={`border-l-2 pl-3 ${toneColor[entry.tone]}`}>
                  <p className="font-mono text-xs leading-5 text-foreground"><span className="text-muted-foreground">{entry.time}</span> {entry.headline}</p>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground"><span className="text-primary">↳ Grafana:</span> {entry.metric.replace(/^Grafana:\s*/i, "")}</p>
                  <p className="text-xs font-semibold leading-5 text-foreground"><span className="text-primary">↳ DECISION:</span> {entry.decision.replace(/^DECISION:\s*/i, "")}</p>
                </li>
              ))}
            </ol>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
              <Ban className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
              <p className="mt-4 text-sm font-semibold">No decision yet</p>
              <p className="mt-2 max-w-xs text-sm leading-6 text-muted-foreground">Start a run to watch Grafana evidence cause each next action.</p>
            </div>
          )}
        </section>
      </div>

      <footer aria-labelledby="grafana-panel-heading" className="mx-auto max-w-screen-2xl px-4 pb-4 md:px-6">
        <section className="overflow-hidden rounded-lg border bg-panel">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h2 id="grafana-panel-heading" className="flex items-center gap-2 font-mono text-xs font-semibold tracking-[0.16em] text-muted-foreground"><Activity className="h-4 w-4 text-primary" aria-hidden="true" /> GRAFANA · LIVE TELEMETRY</h2>
            <span className="font-mono text-xs text-muted-foreground">{mode === "practice" ? "PRACTICE SIGNAL" : "MIMIR QUERY WINDOW"}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[42rem] text-left text-sm">
              <thead className="border-b bg-background text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Shot</th>
                  <th className="px-4 py-3">Cost</th>
                  <th className="px-4 py-3">Retries</th>
                  <th className="px-4 py-3">Refusals</th>
                  <th className="px-4 py-3">Latency</th>
                </tr>
              </thead>
              <tbody className="divide-y font-mono text-xs">
                {state.metrics.map((metric) => (
                  <tr key={metric.shotId}>
                    <td className="px-4 py-3 font-sans text-sm font-medium">{metric.shotId.replace(/-/g, " ")}</td>
                    <td className="px-4 py-3">{formatMoney(metric.cost)}</td>
                    <td className="px-4 py-3">{metric.retries}</td>
                    <td className="px-4 py-3">{metric.refusals}</td>
                    <td className="px-4 py-3">{metric.latencySeconds === null ? "—" : `${metric.latencySeconds.toFixed(1)}s`}</td>
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
