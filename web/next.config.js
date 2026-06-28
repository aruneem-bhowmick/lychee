/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Note: MDX configuration will be added here later.
  // Note: Not setting `output: 'export'` because we use route-level `force-static`. This ensures dynamic route params still build properly.
};

module.exports = nextConfig;
