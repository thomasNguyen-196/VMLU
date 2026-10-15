import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for the Docker image (see web/Dockerfile).
  output: "standalone",
  async redirects() {
    return [
      {
        source: "/results",
        destination: "/benchmark",
        permanent: false,
      },
      {
        source: "/result",
        destination: "/benchmark",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
