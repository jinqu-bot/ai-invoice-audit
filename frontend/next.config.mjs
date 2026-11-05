/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 后端是本地 FastAPI，静态资源直接走 <img>，不接 next/image 的远端优化
  images: { unoptimized: true },
};

export default nextConfig;
