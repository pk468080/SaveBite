import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The API client is a workspace package written in
  // TypeScript source; transpile it for the browser.
  transpilePackages: ["@savebite/api-client"],
};

export default nextConfig;
