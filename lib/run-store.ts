import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomUUID } from "node:crypto";

import type { RunEvent, RunMode } from "@/lib/types";

type ManagedRun = {
  id: string;
  mode: RunMode;
  child: ChildProcessWithoutNullStreams;
  events: RunEvent[];
  listeners: Set<(event: RunEvent) => void>;
  stopped: boolean;
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

function emit(run: ManagedRun, event: RunEvent): void {
  if (run.stopped && event.type !== "run.stopped") {
    return;
  }
  if (event.type === "take.updated" && typeof event.data.asset_uri === "string") {
    run.assetUri = event.data.asset_uri;
  }
  run.events.push(event);
  for (const listener of run.listeners) {
    listener(event);
  }
}

function now(): string {
  return new Date().toISOString();
}

function pythonCommand(): string {
  return process.env.CUTSCOPE_PYTHON || (process.platform === "win32" ? "python" : "python3");
}

export function startRun(mode: RunMode): ManagedRun {
  const id = randomUUID();
  const child = spawn(pythonCommand(), ["-m", "cutscope.web_worker", "--mode", mode, "--run-id", id], {
    cwd: process.cwd(),
    env: process.env,
    stdio: "pipe",
    windowsHide: true,
  });
  const run: ManagedRun = { id, mode, child, events: [], listeners: new Set(), stopped: false, assetUri: null };
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
    if (!run.stopped) emit(run, { type: "run.error", timestamp: now(), data: { message: `Could not start Python worker: ${error.message}` } });
  });

  child.on("close", (code) => {
    if (run.stopped) return;
    if (code !== 0) {
      emit(run, { type: "run.error", timestamp: now(), data: { message: "The worker stopped before the production completed. Check server logs, then try again." } });
    }
  });

  return run;
}

export function getRun(id: string): ManagedRun | undefined {
  return runs.get(id);
}

export function subscribe(run: ManagedRun, listener: (event: RunEvent) => void): () => void {
  run.listeners.add(listener);
  return () => run.listeners.delete(listener);
}

export function stopRun(run: ManagedRun): void {
  if (run.stopped) return;
  run.stopped = true;
  emitStopped(run, "Stopped by operator. No further Veo submissions will be made.");
  run.child.kill("SIGTERM");
}

function emitStopped(run: ManagedRun, message: string): void {
  const event: RunEvent = { type: "run.stopped", timestamp: now(), data: { message } };
  run.events.push(event);
  for (const listener of run.listeners) listener(event);
}

export function getAssetUri(run: ManagedRun): string | null {
  return run.assetUri;
}
