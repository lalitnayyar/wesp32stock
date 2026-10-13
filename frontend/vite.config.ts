/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Lalit Stock Application admin UI. Owner: Lalit Nayyar. Not financial advice.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@shared": path.resolve(__dirname, "../shared") } },
  server: {
    port: 5173,
    host: true, // listen on all interfaces so LAN devices can open http://<pc-ip>:5173
    fs: { allow: [".."] },
    proxy: { "/api": { target: process.env.VITE_API_TARGET || "http://localhost:8000", changeOrigin: false } },
  },
  build: { rollupOptions: { output: { manualChunks: { charts: ["recharts"], react: ["react", "react-dom", "react-router-dom"] } } } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
