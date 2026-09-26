import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy the API to keep browser requests on one origin.
    proxy: {
      "/api": {
        target: process.env.SIDEKICK_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true
      }
    }
  },
  build: { outDir: "dist", sourcemap: true }
});
