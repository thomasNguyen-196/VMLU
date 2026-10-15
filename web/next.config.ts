import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
