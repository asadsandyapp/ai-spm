import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: true,
    // Proxy API namespaces only — do NOT proxy /platform or /admin (SPA routes).
    proxy: {
      "/admin/v1": { target: "http://127.0.0.1:8090", changeOrigin: true, ws: true },
      "/public/v1": { target: "http://127.0.0.1:8090", changeOrigin: true },
      "/platform/v1": { target: "http://127.0.0.1:8090", changeOrigin: true },
      "/agent/v1": { target: "http://127.0.0.1:8090", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8090", changeOrigin: true },
      "/ready": { target: "http://127.0.0.1:8090", changeOrigin: true },
      "/metrics": { target: "http://127.0.0.1:8090", changeOrigin: true },
    },
  },
  preview: {
    port: 4173,
    host: true,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          query: ["@tanstack/react-query"],
        },
      },
    },
  },
});
