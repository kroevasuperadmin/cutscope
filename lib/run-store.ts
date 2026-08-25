import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomUUID } from "node:crypto";
import { setTimeout as setNodeTimeout } from "node:timers";

import type { RunEvent, RunMode } from "@/lib/types";

type ManagedRun = {
  id: string;
  mode: RunMode;
  child: ChildProcessWithoutNullStreams;
  events: RunEvent[];
  listeners: Set<(event: RunEvent) => void>;
  stopped: boolean;
  finished: boolean;
  assetUri: string | null;
};

type RunRegistry = Map<string, ManagedRun>;

declare global {
  // This keeps route handlers in the same Cloud Run process on one shared registry.
  // eslint-disable-next-line no-var
  var cutscopeRuns: RunRegistry | undefined;
}

const runs: RunRegistry = globalThis.cutscopeRuns ?? new Map<string, ManagedRun>();
globalThis.cutscopeRuns = runs;

/** A run is over the moment one of these lands. The SSE route closes the stream on them. */
export const TERMINAL_EVENTS = new Set(["run.finished", "run.error", "run.stopped"]);

// Long enough that a judge can still replay a finished take through /media, short enough
// that a day of judging cannot grow the registry without bound.
const EVICT_AFTER_MS = 15 * 60_000;

// One instance can hold one paid production. Live mode is also operator-gated in the
// route; this is the second lock, so a token holder cannot start two by accident.
const MAX_LIVE_RUNS = 1;

// A flat per-instance ceiling on worker processes, not a queue. Each run is a Python child
// process, so an unbounded count is how one instance runs out of memory. Tunable because
// the container's memory limit is set outside this repo: lower it if the instance is small,
// raise it only if practice runs are actually being refused.
const DEFAULT_MAX_TOTAL_RUNS = 20;

function maxTotalRuns(): number {
  const parsed = Number.parseInt(process.env.CUTSCOPE_MAX_RUNS ?? "", 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : DEFAULT_MAX_TOTAL_RUNS;
}

// Stop tells the operator "no further Veo submissions will be made". The worker traps
// SIGTERM and unwinds, which makes that true — unless it is wedged in a blocking call, where
// a Python signal handler does not run until the call returns. Without an escalation the
// only backstop is the 15-minute eviction, so the promise could be false for 15 minutes.
const STOP_ESCALATION_MS = 10_000;

function emit(run: ManagedRun, event: RunEvent): void {
  // Nothing may follow a terminal event: the SSE stream is already closed by then, and a
  // late enqueue would throw into a dead controller.
  if (run.finished) return;
  if (run.stopped && event.type !== "run.stopped") return;
  if (event.type === "take.updated" && typeof event.data.asset_uri === "string") {
    run.assetUri = event.data.asset_uri;
  }
  run.events.push(event);
  if (TERMINAL_EVENTS.has(event.type)) finish(run);
  for (const listener of run.listeners) listener(event);
}

/**
 * Signalling a worker that never spawned, or has already exited, throws instead of
 * returning false. Both callers can hit that, and one of them runs on a timer, where an
 * uncaught throw would take down the whole instance.
 */
function kill(run: ManagedRun, signal: NodeJS.Signals): void {
  try {
    run.child.kill(signal);
  } catch {
    // No worker to signal. Nothing left to stop.
  }
}

function finish(run: ManagedRun): void {
  if (run.finished) return;
  run.finished = true;
  setNodeTimeout(() => {
    runs.delete(run.id);
    run.listeners.clear();
    // A worker that somehow outlived its own terminal event must not keep spending.
    kill(run, "SIGKILL");
  }, EVICT_AFTER_MS).unref();
}

function now(): string {
  return new Date().toISOString();
}

function pythonCommand(): string {
  return process.env.CUTSCOPE_PYTHON || (process.platform === "win32" ? "python" : "python3");
}

/**
 * Whether this instance can take another run right now, and the sentence to show if it
 * cannot. Node runs one request at a time up to the next await, and the caller starts the
 * run without awaiting, so this cannot be raced past on a single instance.
 */
export function capacityRefusal(mode: RunMode): string | null {
  let live = 0;
  let total = 0;
  for (const run of runs.values()) {
    if (run.finished) continue;
    total += 1;
    if (run.mode === "live") live += 1;
  }
  if (mode === "live" && live >= MAX_LIVE_RUNS) {
    return "A live production is already running on this instance. Wait for it to finish, or stop it, then start again.";
  }
  if (total >= maxTotalRuns()) {
    return "CUTSCOPE is already running as many productions as one instance can hold. Give it a moment, then start again.";
  }
  return null;
}

export function startRun(mode: RunMode): ManagedRun {
  const id = randomUUID();
  const child = spawn(pythonCommand(), ["-m", "cutscope.web_worker", "--mode", mode, "--run-id", id], {
    cwd: process.cwd(),
    env: process.env,
    stdio: "pipe",
    windowsHide: true,
  });
  const run: ManagedRun = {
    id,
    mode,
    child,
    events: [],
    listeners: new Set(),
    stopped: false,
    finished: false,
    assetUri: null,
  };
  runs.set(id, run);

  let pending = "";
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk: string) => {
    pending += chunk;
    const lines = pending.split(/\r?\n/);
    pending = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const event = JSON.parse(line) as RunEvent;
        if (event.type && event.timestamp && event.data) emit(run, event);
      } catch {
        emit(run, { type: "run.error", timestamp: now(), data: { message: "Worker emitted an unreadable event." } });
      }
    }
  });

  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk: string) => {
    if (!run.stopped) {
      emit(run, { type: "run.worker_notice", timestamp: now(), data: { message: chunk.trim().slice(0, 500) } });
    }
  });

  child.on("error", (error) => {
    if (!run.finished) emit(run, { type: "run.error", timestamp: now(), data: { message: `Could not start Python worker: ${error.message}` } });
  });

  child.on("close", (code) => {
    // A worker that exits without a terminal event would leave the stream open forever.
    if (run.finished) return;
    emit(run, {
      type: "run.error",
      timestamp: now(),
      data: {
        message:
          code === 0
            ? "The worker exited without finishing the production. Start a new run."
            : "The worker stopped before the production completed. Check server logs, then try again.",
      },
    });
  });

  return run;
}

export function getRun(id: string): ManagedRun | undefined {
  return runs.get(id);
}

export function isFinished(run: ManagedRun): boolean {
  return run.finished;
}

export function subscribe(run: ManagedRun, listener: (event: RunEvent) => void): () => void {
  run.listeners.add(listener);
  return () => run.listeners.delete(listener);
}

export function stopRun(run: ManagedRun): void {
  if (run.stopped || run.finished) return;
  run.stopped = true;
  emit(run, {
    type: "run.stopped",
    timestamp: now(),
    data: { message: "Stopped by operator. No further Veo submissions will be made." },
  });
  kill(run, "SIGTERM");
  // A no-op once the worker has already exited, so this needs no liveness check.
  // ponytail: flat 10s, no backoff. Make it configurable only if a worker legitimately
  // needs longer to unwind than a judge is willing to watch a "stopping" spinner.
  setNodeTimeout(() => kill(run, "SIGKILL"), STOP_ESCALATION_MS).unref();
}

export function getAssetUri(run: ManagedRun): string | null {
  return run.assetUri;
}
