import type { NextConfig } from "next";

/** Older addresses keep working: the interface uses the glossary's names (docs/PAGE-AUDIT.md, brief WP3). */
const RENAMED: [string, string][] = [["/repo", "/library"], ["/agents", "/playbooks"], ["/pools", "/teams"], ["/upstream", "/reference"], ["/activity", "/runs"]];

const nextConfig: NextConfig = {
  images: { unoptimized: true },
  async redirects() {
    return RENAMED.flatMap(([from, to]) => [
      { source: from, destination: to, permanent: true },
      { source: `${from}/:path*`, destination: `${to}/:path*`, permanent: true },
    ]);
  },
};

export default nextConfig;
