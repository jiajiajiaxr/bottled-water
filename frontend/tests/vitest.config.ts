import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "../vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      globals: true,
      testTimeout: 20000,
      setupFiles: ["tests/setup.ts"],
      include: ["./**/*.test.ts", "./**/*.test.tsx"],
    },
  }),
);
