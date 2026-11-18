import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  // Lets a production build for screenshots sit beside a running dev server.
  distDir: process.env.RAFT_DIST_DIR ?? ".next",
};

export default config;
