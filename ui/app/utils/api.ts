// Utility to compute the API base URL consistently from env or window
// Priority:
// 1) NEXT_PUBLIC_API_BASE_URL env (already provided via docker-compose)
// 2) If running in browser, infer from current host but port 8000 for API
// 3) Fallback to http://localhost:8000

export function getApiBase(): string {
  const env = typeof process !== 'undefined' && process && (process as unknown as { env?: Record<string, string | undefined> }).env
    ? (process as unknown as { env?: Record<string, string | undefined> }).env!.NEXT_PUBLIC_API_BASE_URL
    : undefined;
  // If we have a browser hostname available, prefer deriving from it unless
  // the env explicitly points to a non-localhost host.
  if (typeof window !== 'undefined') {
    const host = window.location.hostname || 'localhost';
    const isLocalHost = host === 'localhost' || host === '127.0.0.1' || host === '::1';
    const envUrl = typeof env === 'string' ? env.trim() : '';
    const envIsNonLocal = envUrl && !/localhost|127\.0\.0\.1|::1/i.test(envUrl);
    if (envIsNonLocal || (envUrl && isLocalHost)) {
      return trimTrailingSlash(envUrl);
    }
    const protocol = window.location.protocol === 'https:' ? 'https' : 'http';
    return `${protocol}://${host}:8000`;
  }
  // On server side (rare for our usage in client comp), fall back to env or localhost.
  if (env && env.trim()) return trimTrailingSlash(env.trim());
  return 'http://localhost:8000';
}

function trimTrailingSlash(u: string): string {
  return u.endsWith('/') ? u.slice(0, -1) : u;
}
