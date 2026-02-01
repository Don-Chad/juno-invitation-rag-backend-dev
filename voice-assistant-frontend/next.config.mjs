/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",  // <--- Required for Cloudflare Free Tier
  eslint: {
    // Disable ESLint during production builds due to version conflicts
    ignoreDuringBuilds: true,
  },
  // Note: 'headers' are removed here because they are not supported in static exports.
  // We use public/_headers instead.
  images: {
    unoptimized: true, // Required for static export if you use Next/Image
  },
};

export default nextConfig;
