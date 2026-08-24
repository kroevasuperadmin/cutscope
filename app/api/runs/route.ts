import { timingSafeEqual } from "node:crypto";

import { NextResponse } from "next/server";

import { capacityRefusal, startRun } from "@/lib/run-store";
import type { RunMode } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const LIVE_DISABLED =
  "Live mode is switched off on this deployment, so no visitor can spend on Veo. Practice mode is open to everyone and replays the same control loop with the same decisions.";
const LIVE_REFUSED =
  "Live mode needs the operator token, because a live run submits paid Veo jobs. Practice mode is open to everyone and replays the same control loop.";

/**
 * Header first, because a query string is written into Cloud Run's request logs. The body
 * and query forms exist so an operator can trigger a live run from a plain form or a URL.
 */
function suppliedToken(request: Request, body: { token?: unknown }): string {
  const header = request.headers.get("x-cutscope-operator-token");
  if (header) return header;
  const query = new URL(request.url).searchParams.get("token");
  if (query) return query;
  return typeof body.token === "string" ? body.token : "";
}

function matches(supplied: string, expected: string): boolean {
  const a = Buffer.from(supplied);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function POST(request: Request) {
  let body: { mode?: unknown; token?: unknown };
  try {
    body = (await request.json()) as { mode?: unknown; token?: unknown };
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }
  if (body.mode !== "practice" && body.mode !== "live") {
    return NextResponse.json({ error: "mode must be practice or live." }, { status: 400 });
  }
  const mode = body.mode as RunMode;

  // Practice mode stays open to anyone. Live mode spends real money on Veo, and this
  // deployment is public, so it is closed unless an operator token is configured and sent.
  if (mode === "live") {
    const expected = process.env.CUTSCOPE_OPERATOR_TOKEN?.trim() ?? "";
    if (!expected) {
      return NextResponse.json({ error: LIVE_DISABLED }, { status: 403 });
    }
    if (!matches(suppliedToken(request, body), expected)) {
      return NextResponse.json({ error: LIVE_REFUSED }, { status: 401 });
    }
  }

  const refusal = capacityRefusal(mode);
  if (refusal) {
    return NextResponse.json({ error: refusal }, { status: 429 });
  }

  const run = startRun(mode);
  return NextResponse.json({ runId: run.id });
}
