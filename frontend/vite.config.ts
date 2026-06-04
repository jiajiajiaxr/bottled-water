import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { fileURLToPath } from "url";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, ".."), "");
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      port: parseInt(env.VITE_FRONTEND_PORT || "5173"),
      proxy: {
        "/api/v1": {
          target: env.VITE_API_BASE_URL || "http://localhost:8888",
          changeOrigin: true,
        },
        "/ws": {
          target: env.VITE_WS_URL || "ws://localhost:8888",
          ws: true,
        },
      },
    },
  };
});
