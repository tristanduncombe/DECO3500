// lib/getAuthToken.ts
export async function getAuthToken(): Promise<string | null> {
  try {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("authToken");
      if (token) return token;
    }

    // Optional: call refresh endpoint if you have one (uncomment and adapt)
    /*
    const res = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (res.ok) {
      const json = await res.json();
      localStorage.setItem("authToken", json.accessToken);
      return json.accessToken;
    }
    */

    return null;
  } catch (err) {
    console.error("getAuthToken error", err);
    return null;
  }
}
