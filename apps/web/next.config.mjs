/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@deck.gl/core", "@deck.gl/layers", "@deck.gl/mapbox", "@deck.gl/react"],
};

export default nextConfig;
