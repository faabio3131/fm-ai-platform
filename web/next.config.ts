import type { NextConfig } from "next";

const backendUrl = process.env.KORDENA_BACKEND_URL?.replace(/\/+$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    if (!backendUrl) {
      return [];
    }

    return [
      {
        source: "/backend/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
