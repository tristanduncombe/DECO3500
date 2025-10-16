import { NextRequest } from "next/server";
import { getBackendBase, pickForwardHeaders } from "@/app/api/_backend";

export async function GET() {
  const url = `${getBackendBase()}/inventory/items`;
  const res = await fetch(url, { next: { revalidate: 0 } });
  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json" },
  });
}

export async function POST(req: NextRequest) {
  const url = `${getBackendBase()}/inventory/items`;
  // Pass through multipart form-data as-is
  const headers = pickForwardHeaders(req);
  const res = await fetch(url, {
    method: "POST",
    headers,
    body: req.body, // stream passthrough
  });
  const body = await res.text();
  // Preserve content-type for data URLs/json
  return new Response(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json" },
  });
}
