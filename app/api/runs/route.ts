import { NextResponse } from "next/server";

import { startRun } from "@/lib/run-store";
import type { RunMode } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let body: { mode?: unknown };
  try {
    body = (await request.json()) as { mode?: unknown };
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }
  if (body.mode !== "practice" && body.mode !== "live") {
    return NextResponse.json({ error: "mode must be practice or live." }, { status: 400 });
  }
  const run = startRun(body.mode as RunMode);
  return NextResponse.json({ runId: run.id });
}
