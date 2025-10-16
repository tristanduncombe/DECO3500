// Helper to resolve the FastAPI backend base URL for server-side route handlers
// Accepts the incoming Request to allow environment-aware resolution.
export function getBackendBase(req?: Request): string {
  const envProxy = process.env.API_PROXY_TARGET?.trim();
  const envPublic = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();

  // If running locally (host header is localhost/127.0.0.1) prefer localhost backend
  const host = req?.headers?.get("host") || "";
  const isLocalHost = /(^|:)localhost(:|$)|(^|:)127\.0\.0\.1(:|$)/i.test(host);
  if (isLocalHost) {
    // Use explicit override if provided, else default to local FastAPI
    return envPublic || "http://localhost:8000";
  }

  // In Docker or deployed: prefer API_PROXY_TARGET if set, else fall back to public/base
  return envProxy || envPublic || "http://localhost:8000";
}

// Only forward a safe subset of headers downstream
export function pickForwardHeaders(req: Request, extra: Record<string, string> = {}): Headers {
  const headers = new Headers();
  const src = req.headers;
  // Preserve content-type for multipart/form-data and JSON
  const ct = src.get("content-type");
  if (ct) headers.set("content-type", ct);
  // Forward auth if present (backend can ignore if unused)
  const auth = src.get("authorization");
  if (auth) headers.set("authorization", auth);
  // Allow custom extras
  for (const [k, v] of Object.entries(extra)) headers.set(k, v);
  return headers;
}
