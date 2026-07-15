import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Turbopack needs the monorepo root where node_modules is hoisted
  turbopack: {
    root: path.resolve(__dirname, "../../.."),
  },
};

export default nextConfig;
