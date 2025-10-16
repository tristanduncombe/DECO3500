import { NextRequest } from "next/server";
import { getBackendBase, pickForwardHeaders } from "@/app/api/_backend";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, { params }: { params: { itemId: string } }) {
  const itemId = params.itemId;
  if (!itemId) return new Response(JSON.stringify({ error: "itemId required" }), { status: 400 });
  const url = `${getBackendBase()}/inventory/items/${encodeURIComponent(itemId)}/unlock`;
  const headers = pickForwardHeaders(req);
  const init: RequestInit & { duplex?: "half" } = {
    method: "POST",
    headers,
    body: req.body as unknown as BodyInit,
    duplex: "half",
  };
  const res = await fetch(url, init as RequestInit);
  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json" },
  });
}
