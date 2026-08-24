export type RunMode = "practice" | "live";

export type ShotState =
  | "queued"
  | "generating"
  | "retrying"
  | "done"
  | "refused"
  | "abandoned";

export type ShotView = {
  id: string;
  label: string;
  state: ShotState;
  attempt: number;
  maxAttempts: number;
  cost: number;
  prompt: string;
};

export type TakeView = {
  shotId: string;
  label: string;
  prompt: string;
  mediaUrl?: string;
  isPractice?: boolean;
};

export type DecisionLog = {
  id: string;
  time: string;
  headline: string;
  metric: string;
  decision: string;
  tone: "neutral" | "success" | "warning" | "danger" | "info";
};

export type MetricView = {
  shotId: string;
  cost: number;
  retries: number;
  refusals: number;
  latencySeconds: number | null;
};

export type RunEvent = {
  type: string;
  timestamp: string;
  data: Record<string, unknown>;
};

export type ConsoleState = {
  runId: string | null;
  mode: RunMode;
  status: "idle" | "starting" | "running" | "stopped" | "finished" | "error";
  productionName: string;
  spent: number;
  budget: number;
  shots: ShotView[];
  take: TakeView | null;
  decisions: DecisionLog[];
  metrics: MetricView[];
  error: string | null;
};

export const initialShots: ShotView[] = [
  {
    id: "rooftop-reveal",
    label: "SHOT 01 · ROOFTOP REVEAL",
    state: "queued",
    attempt: 0,
    maxAttempts: 2,
    cost: 0,
    prompt: "Original sci-fi film: Mara steps onto a rain-soaked rooftop at blue hour, amber visor glowing, slow dolly reveal, cinematic 16:9.",
  },
  {
    id: "alley-exit",
    label: "SHOT 02 · ALLEY EXIT",
    state: "queued",
    attempt: 0,
    maxAttempts: 2,
    cost: 0,
    prompt: "Original sci-fi film: Mara exits a narrow neon alley into rain, keep her amber visor and dark hooded silhouette consistent, handheld follow shot, cinematic 16:9.",
  },
  {
    id: "signal-room",
    label: "SHOT 03 · SIGNAL ROOM",
    state: "queued",
    attempt: 0,
    maxAttempts: 2,
    cost: 0,
    prompt: "Original sci-fi film: Mara and Noa study a pulsing city map in a quiet signal room, retain Mara's amber visor and Noa's silver jacket, controlled push-in, cinematic 16:9.",
  },
];

export const initialMetrics: MetricView[] = initialShots.map((shot) => ({
  shotId: shot.id,
  cost: 0,
  retries: 0,
  refusals: 0,
  latencySeconds: null,
}));

export function createInitialState(mode: RunMode = "practice"): ConsoleState {
  return {
    runId: null,
    mode,
    status: "idle",
    productionName: "MARA // SIGNAL AT BLUE HOUR",
    spent: 0,
    budget: 15,
    shots: initialShots.map((shot) => ({ ...shot })),
    take: null,
    decisions: [],
    metrics: initialMetrics.map((metric) => ({ ...metric })),
    error: null,
  };
}

export function formatMoney(amount: number): string {
  return `$${amount.toFixed(2)}`;
}
