import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    if (process.env.KORDENA_PREVIEW_PROXY !== "1") return [];
    const backend = process.env.KORDENA_PREVIEW_BACKEND_URL;
    if (!backend || !backend.startsWith("https://")) {
      throw new Error("Preview proxy exige backend HTTPS explícito.");
    }
    return [{ source: "/v1/:path*", destination: `${backend}/v1/:path*` }];
  },
};

export default nextConfig;
