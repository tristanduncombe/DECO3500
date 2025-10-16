// Helper to resolve the FastAPI backend base URL for server-side route handlers
export function getBackendBase(): string {
  const fromEnv = process.env.API_PROXY_TARGET || process.env.NEXT_PUBLIC_API_BASE_URL;
  return (fromEnv && fromEnv.trim()) || "http://localhost:8000";
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
