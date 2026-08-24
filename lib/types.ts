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
    id: "warehouse-displacement",
    label: "SHOT 01 · WAREHOUSE DISPLACEMENT",
    state: "queued",
    attempt: 0,
    maxAttempts: 3,
    cost: 0,
    prompt: "2024, dim industrial warehouse lit by scattered LEDs. A man in his late twenties wearing a matte cybernetic half-mask stands still as a stream of luminous pneumatic liquid strikes his chest. His body begins dissolving into white light from the point of impact outward. Handheld, cinematic 16:9, cold blue-grey grade.",
  },
  {
    id: "first-sighting-2012",
    label: "SHOT 02 · FIRST SIGHTING 2012",
    state: "queued",
    attempt: 0,
    maxAttempts: 3,
    cost: 0,
    prompt: "2012, sunlit suburban Malaysian street, warm saturated colour. A 26-year-old man stands frozen on the pavement, staring across the road at a 14-year-old boy laughing with school friends. The boy and the man are unmistakably the same person twelve years apart. Slow push-in on the man's face. Cinematic 16:9.",
  },
  {
    id: "arcade-coaching",
    label: "SHOT 03 · ARCADE COACHING",
    state: "queued",
    attempt: 0,
    maxAttempts: 3,
    cost: 0,
    prompt: "2012 arcade at night, pulsing neon reflecting off glass. A 26-year-old man leans beside a 14-year-old boy at a pinball machine, speaking quietly to him as the boy adjusts his timing. Both faces visible in the same frame, clearly the same person at two ages. Neon rim light, cinematic 16:9.",
  },
  {
    id: "the-field-2012",
    label: "SHOT 04 · THE FIELD 2012",
    state: "queued",
    attempt: 0,
    maxAttempts: 3,
    cost: 0,
    prompt: "2012, late afternoon golden light over an open grass field beside a suburban playground. Mature trees along the far edge, a footpath curving left, low houses beyond. Wide static establishing shot, warm saturated grade, cinematic 16:9.",
  },
  {
    id: "the-field-2000",
    label: "SHOT 05 · THE FIELD 2000",
    state: "queued",
    attempt: 0,
    maxAttempts: 4,
    cost: 0,
    prompt: "The year 2000, same open field and identical tree line and curving footpath as the previous shot, but bare and undeveloped: no playground, sparser vegetation, fewer and older houses on the horizon. Same camera position and framing, same late afternoon light, slightly cooler and more faded grade. Cinematic 16:9.",
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
    productionName: "TURNING POINT // S1 · SHOT TEST",
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
