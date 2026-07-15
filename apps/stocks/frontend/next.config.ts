import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Turbopack needs the monorepo root where node_modules is hoisted
  turbopack: {
    root: path.resolve(__dirname, "../../.."),
  },

  // Production optimizations
  reactStrictMode: true,

  // Security headers for production
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
        ],
      },
    ];
  },

  // Health check endpoint for Cloudflare
  async rewrites() {
    return [
      {
        source: '/healthz',
        destination: '/api/health',
      },
    ];
  },
};

export default nextConfig;
