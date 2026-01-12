import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  /* config options here */
  devIndicators: false,
  // Allow cross-origin requests from the network IP in development
  allowedDevOrigins: ['178.156.186.166:3001'],
};

export default nextConfig;
