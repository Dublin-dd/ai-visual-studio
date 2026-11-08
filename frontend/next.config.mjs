/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || process.env.BACKEND_ORIGIN || "http://127.0.0.1:8010";

const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
