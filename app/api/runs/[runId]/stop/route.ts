import { NextResponse } from "next/server";

import { getRun, isFinished, stopRun } from "@/lib/run-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(_: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const run = getRun(runId);
  if (!run) {
    // Not a mystery 404: either the run already finished and was cleared, or Cloud Run put
    // this request on a different container than the one holding the worker.
    return NextResponse.json(
      { error: "This run is not on this instance - it has finished and been cleared, or your request reached a different container. Start a new run." },
      { status: 404 },
    );
  }
  if (isFinished(run)) {
    return NextResponse.json({ stopped: false, message: "This run has already ended. Nothing is still spending." });
  }
  stopRun(run);
  return NextResponse.json({ stopped: true });
}
