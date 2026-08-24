import { getRun, subscribe } from "@/lib/run-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function sse(event: unknown): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`);
}

export async function GET(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const run = getRun(runId);
  if (!run) return new Response("Run not found.", { status: 404 });

  let cleanup = () => undefined;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of run.events) controller.enqueue(sse(event));
      const unsubscribe = subscribe(run, (event) => controller.enqueue(sse(event)));
      const keepAlive = setInterval(() => controller.enqueue(new TextEncoder().encode(": keep-alive\n\n")), 15_000);
      cleanup = () => {
        clearInterval(keepAlive);
        unsubscribe();
        try {
          controller.close();
        } catch {
          // The browser may already have closed the stream.
        }
      };
      request.signal.addEventListener("abort", cleanup, { once: true });
    },
    cancel() {
      cleanup();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
