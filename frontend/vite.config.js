import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const target = env.VITE_DEV_API_TARGET || "http://127.0.0.1:5000";
  const url = new URL(target);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password
  ) {
    throw new Error(
      "VITE_DEV_API_TARGET phải là địa chỉ HTTP(S) không chứa thông tin đăng nhập.",
    );
  }
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: { "/api": { target, changeOrigin: true } },
    },
    preview: { port: 4173, strictPort: true },
    build: { sourcemap: false },
    test: {
      environment: "jsdom",
      setupFiles: ["./tests/setup.js"],
      include: ["tests/**/*.test.{js,jsx}"],
      clearMocks: true,
      restoreMocks: true,
    },
  };
});
