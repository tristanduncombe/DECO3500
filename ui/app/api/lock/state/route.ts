import { NextRequest } from "next/server";
import { getBackendBase, pickForwardHeaders } from "@/app/api/_backend";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const url = `${getBackendBase(req)}/lock/state`;
  const headers = pickForwardHeaders(req);
  const res = await fetch(url, { headers, next: { revalidate: 0 } });
  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json" },
  });
}
