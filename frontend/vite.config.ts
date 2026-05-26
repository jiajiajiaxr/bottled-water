import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "../", "");
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": new URL("./src", import.meta.url).pathname,
      },
    },
    server: {
      port: parseInt(env.FRONTEND_PORT || "5173"),
      proxy: {
        "/api/v1": {
          target: env.API_BASE_URL || "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
