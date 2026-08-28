/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 사내 데이터가 담긴 데모라 검색엔진 색인을 전부 막는다 (robots.txt + 메타태그와 이중 방어).
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" }],
      },
    ];
  },
};

module.exports = nextConfig;
