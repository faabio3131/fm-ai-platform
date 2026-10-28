import type { NextConfig } from "next";

const backendUrl = process.env.KORDENA_BACKEND_URL?.replace(/\/+$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const routes = [];
    if (backendUrl) {
      routes.push({
        source: "/backend/:path*",
        destination: `${backendUrl}/:path*`,
      });
    }

    // Opt-in preview proxy. Existing /backend routing is preserved.
    if (process.env.KORDENA_PREVIEW_PROXY === "1") {
      const previewBackend = process.env.KORDENA_PREVIEW_BACKEND_URL?.replace(/\/+$/, "");
      if (!previewBackend || !previewBackend.startsWith("https://")) {
        throw new Error("Preview proxy exige backend HTTPS explícito.");
      }
      routes.push({
        source: "/v1/:path*",
        destination: `${previewBackend}/v1/:path*`,
      });
    }
    return routes;
  },
};

export default nextConfig;
