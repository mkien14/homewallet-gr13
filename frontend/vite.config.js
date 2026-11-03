import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { localizeJsxText } from "./src/localizeVite.js";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [localizeJsxText(), react()],
    server: {
      port: 5173,
      strictPort: true, 
      allowedHosts: [".trycloudflare.com"],
      proxy: {
        "/api": {
          target: env.VITE_API_TARGET || "http://localhost:5000",
          changeOrigin: true,
        },
      },
    },
  };
});
