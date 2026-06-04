import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const fromFileUrl = (url: URL) =>
  decodeURIComponent(url.pathname).replace(/^\/([A-Za-z]:)/, "$1");

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, fromFileUrl(new URL("..", import.meta.url)), "");
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": fromFileUrl(new URL("./src", import.meta.url)),
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
