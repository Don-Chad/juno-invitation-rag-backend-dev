/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    // Disable ESLint during production builds due to version conflicts
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
