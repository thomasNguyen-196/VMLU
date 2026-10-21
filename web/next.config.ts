import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for the Docker image (see web/Dockerfile).
  output: "standalone",
  // Docker binds Next to 0.0.0.0; the local browser uses this loopback origin.
  // Without it the dev HMR handshake is blocked and client hydration hangs.
  allowedDevOrigins: ["127.0.0.1"],
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
