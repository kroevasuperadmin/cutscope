import { Storage } from "@google-cloud/storage";
import { Readable } from "node:stream";

import { getAssetUri, getRun } from "@/lib/run-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const storage = new Storage();

function parseGsUri(uri: string): { bucket: string; object: string } | null {
  if (!uri.startsWith("gs://")) return null;
  const [bucket, ...path] = uri.slice(5).split("/");
  if (!bucket || !path.length) return null;
  return { bucket, object: path.join("/") };
}

export async function GET(_: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const run = getRun(runId);
  const asset = run ? getAssetUri(run) : null;
  const parsed = asset ? parseGsUri(asset) : null;
  if (!parsed) return new Response("A browser-playable Veo asset is not available for this run.", { status: 404 });

  try {
    const file = storage.bucket(parsed.bucket).file(parsed.object);
    const [metadata] = await file.getMetadata();
    const stream = Readable.toWeb(file.createReadStream()) as ReadableStream;
    return new Response(stream, {
      headers: {
        "Content-Type": metadata.contentType || "video/mp4",
        "Cache-Control": "private, max-age=300",
        "Content-Disposition": "inline",
      },
    });
  } catch {
    return new Response("CUTSCOPE could not read the Veo asset from Cloud Storage.", { status: 502 });
  }
}
