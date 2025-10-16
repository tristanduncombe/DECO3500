import type { NextConfig } from "next";

// Determine API proxy target. Prefer explicit env, otherwise default to localhost:8000
const API_PROXY_TARGET = process.env.API_PROXY_TARGET || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  /* config options here */
  typescript: {
    ignoreBuildErrors: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_PROXY_TARGET}/:path*`,
      },
    ];
  },
  // For fonts preload warning, keep default; can tune in future
};

export default nextConfig;
