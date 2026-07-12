/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@deck.gl/core", "@deck.gl/layers", "@deck.gl/mapbox", "@deck.gl/react"],
  // Container builds (Dockerfile) set NEXT_OUTPUT_STANDALONE=1 to get the
  // self-contained .next/standalone server. Unset locally → no effect on dev.
  ...(process.env.NEXT_OUTPUT_STANDALONE ? { output: "standalone" } : {}),
  // Single-container deploys (Hugging Face Space) set API_INTERNAL_URL and
  // build with NEXT_PUBLIC_API_URL="" so the client fetches relative /api/*;
  // Next then proxies those to the co-located FastAPI process. Locally
  // API_INTERNAL_URL is unset → no rewrites, client keeps absolute
  // NEXT_PUBLIC_API_URL (default http://localhost:8000).
  async rewrites() {
    const api = process.env.API_INTERNAL_URL;
    if (!api) return [];
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};

export default nextConfig;
