import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.ts";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      restoreMocks: true,
      // Above setup.ts's 10 s asyncUtilTimeout, so a slow cold page import fails as a missing
      // element (with the DOM printed) rather than a bare test timeout.
      testTimeout: 15000,
      coverage: {
        provider: "v8",
        include: ["src/**/*.{ts,tsx}"],
        exclude: [
          "src/api/schema.d.ts", // generated from backend/openapi.json
          "src/main.tsx", // browser bootstrap only
          "src/components/charts/echarts.ts", // module registry; mocked in jsdom, exercised by E2E
          "src/test/**",
          "src/**/*.test.{ts,tsx}",
        ],
        reporter: ["text", "html", "lcov"],
        // Approved gate (U4): 85% of lines and branches.
        thresholds: { lines: 85, branches: 85 },
      },
    },
  }),
);
