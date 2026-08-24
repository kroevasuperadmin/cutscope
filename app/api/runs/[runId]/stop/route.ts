import { NextResponse } from "next/server";

import { getRun, stopRun } from "@/lib/run-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(_: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const run = getRun(runId);
  if (!run) return NextResponse.json({ error: "Run not found." }, { status: 404 });
  stopRun(run);
  return NextResponse.json({ stopped: true });
}
