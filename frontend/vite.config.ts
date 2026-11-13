import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser talks to the same origin; Vite forwards /api to the FastAPI backend.
// 127.0.0.1 (not "localhost") avoids Node resolving to ::1 while uvicorn listens on IPv4.
const apiTarget = process.env["VOLTERRA_API_URL"] ?? "http://127.0.0.1:8000";
const proxy = { "/api": { target: apiTarget } };

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 4173, strictPort: true, proxy },
  build: {
    target: "es2022",
    sourcemap: true,
    // ECharts gets its own chunk, shared by every chart page and loaded with the first of them
    // (plan §9). It is ~520 kB minified (~175 kB gzip) on its own, hence the higher warning limit.
    chunkSizeWarningLimit: 600,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: "echarts",
              test: /node_modules[\/](echarts|zrender|tslib)[\/]/,
            },
          ],
        },
      },
    },
  },
});
