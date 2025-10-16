import { NextRequest } from "next/server";
import { getBackendBaseCandidates, pickForwardHeaders } from "@/app/api/_backend";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, { params }: { params: { itemId: string } }) {
  const itemId = params.itemId;
  if (!itemId) return new Response(JSON.stringify({ error: "itemId required" }), { status: 400 });
  const bases = getBackendBaseCandidates(req);
  const path = `/inventory/items/${encodeURIComponent(itemId)}/unlock`;
  const headers = pickForwardHeaders(req);
  const init: RequestInit & { duplex?: "half" } = {
    method: "POST",
    headers,
    body: req.body as unknown as BodyInit,
    duplex: "half",
  };
  let lastErr: unknown = undefined;
  for (const base of bases) {
    const url = `${base}${path}`;
    try {
      const res = await fetch(url, init as RequestInit);
      const body = await res.text();
      return new Response(body, {
        status: res.status,
        headers: { "content-type": res.headers.get("content-type") || "application/json" },
      });
    } catch (e) {
      lastErr = e;
      // Try next base
    }
  }
  console.error("Failed to proxy unlock", lastErr);
  return new Response(JSON.stringify({ error: "Upstream unavailable" }), { status: 502 });
}
