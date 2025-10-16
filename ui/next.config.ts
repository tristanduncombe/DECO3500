import type { NextConfig } from "next";

// API proxy target no longer used; route handlers handle proxying

const nextConfig: NextConfig = {
  /* config options here */
  typescript: {
    ignoreBuildErrors: true,
  },
  // Rewrites removed: we now use real Next.js API route handlers under /api
  // For fonts preload warning, keep default; can tune in future
};

export default nextConfig;
