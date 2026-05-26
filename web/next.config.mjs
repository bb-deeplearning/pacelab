/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.PACELAB_API_URL ?? "http://127.0.0.1:8200"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
