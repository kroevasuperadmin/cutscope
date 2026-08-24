import { TERMINAL_EVENTS, getRun, isFinished, subscribe } from "@/lib/run-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const encoder = new TextEncoder();

const SSE_HEADERS = {
  "Content-Type": "text/event-stream",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
};

function sse(event: unknown): Uint8Array {
  return encoder.encode(`data: ${JSON.stringify(event)}\n\n`);
}

// An EventSource reconnects on its own whenever the server closes the stream. Once a run
// is over — or was never on this instance — there is nothing to reconnect to, so raise the
// browser's reconnection delay to a day before closing. Without this, ending the stream
// starts a replay loop every three seconds instead of stopping it.
const NO_RECONNECT = encoder.encode("retry: 86400000\n\n");

function endedStream(message: string): Response {
  // Deliberately 200, not 404: an EventSource discards a non-2xx body, so the only way to
  // put this sentence in front of the judge is to send it as one real event and close.
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(NO_RECONNECT);
      controller.enqueue(sse({ type: "run.error", timestamp: new Date().toISOString(), data: { message } }));
      controller.close();
    },
  });
  return new Response(stream, { headers: SSE_HEADERS });
}

export async function GET(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const run = getRun(runId);
  if (!run) {
    // Cloud Run can land this request on a different container than the POST that started
    // the run, and finished runs are evicted after a while. Say so, do not hang.
    return endedStream("This run is not on this instance - start a new run.");
  }

  let cleanup = () => {};
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let closed = false;
      let keepAlive: ReturnType<typeof setInterval> | undefined;
      let unsubscribe = () => {};

      const close = () => {
        if (closed) return;
        closed = true;
        if (keepAlive) clearInterval(keepAlive);
        unsubscribe();
        try {
          controller.close();
        } catch {
          // The browser may already have closed the stream.
        }
      };
      const push = (chunk: Uint8Array) => {
        if (closed) return;
        try {
          controller.enqueue(chunk);
        } catch {
          close();
        }
      };

      cleanup = close;
      request.signal.addEventListener("abort", close, { once: true });

      for (const event of run.events) push(sse(event));

      // Nothing more will ever arrive on a finished run: replay it, then end the stream.
      if (isFinished(run)) {
        push(NO_RECONNECT);
        close();
        return;
      }

      unsubscribe = subscribe(run, (event) => {
        push(sse(event));
        if (TERMINAL_EVENTS.has(event.type)) {
          push(NO_RECONNECT);
          close();
        }
      });
      keepAlive = setInterval(() => push(encoder.encode(": keep-alive\n\n")), 15_000);
    },
    cancel() {
      cleanup();
    },
  });

  return new Response(stream, { headers: SSE_HEADERS });
}
