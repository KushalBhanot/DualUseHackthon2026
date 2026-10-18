import path from "node:path";
import type { NextConfig } from "next";

// Where the FastAPI backend runs. The browser only ever talks to this Next.js server; /api/* is
// proxied, so there is no CORS to set up. Rewrites are resolved at build time: set BACKEND_URL
// before `next build` when the backend isn't on localhost:8000.
const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  turbopack: {
    root: path.join(__dirname), // the repo root has its own package-lock.json (the Retell CLI)
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;
