import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { localizeJsxText } from "./src/localizeVite.js";
import { normalizeCognitoOrigin } from "./src/auth/cognitoOrigin.js";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  if (env.VITE_RELEASE_CHANNEL === "production") {
    const missing = ["VITE_COGNITO_DOMAIN", "VITE_COGNITO_CLIENT_ID", "VITE_COGNITO_USER_POOL_ID", "VITE_SUPPORT_EMAIL"]
      .filter((key) => !env[key] || /REPLACE|your-|example\./i.test(env[key]));
    if (missing.length) throw new Error(`Production public configuration missing: ${missing.join(", ")}`);
    normalizeCognitoOrigin(env.VITE_COGNITO_DOMAIN);
    if (mode === "mock" || env.VITE_USE_MOCK === "1" || env.VITE_ENABLE_REACT_AUTH_UI !== "true") {
      throw new Error("Production requires the real API and React Cognito sign-in");
    }
    if (Object.keys(env).some((key) => /^VITE_.*(SECRET|PRIVATE|PASSWORD|GEMINI_API_KEY|AWS_ACCESS_KEY)/i.test(key))) {
      throw new Error("Private credentials must never use the VITE_ prefix");
    }
    if (!["true", "false"].includes(env.VITE_ENABLE_OCR)) throw new Error("Set VITE_ENABLE_OCR explicitly for production");
    if (!["true", "false"].includes(env.VITE_SELF_SIGN_UP)) throw new Error("Set VITE_SELF_SIGN_UP explicitly for production");
  }
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
