/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";
import type { Plugin } from "vite";

// Dev only: serve ../firmware/dist at /firmware/ like Caddy does in Docker (web flasher binaries).
function firmwareDist(): Plugin {
  const root = path.resolve(__dirname, "../firmware/dist");
  return {
    name: "lalitstock-firmware-dist",
    configureServer(server) {
      server.middlewares.use("/firmware", (req, res, next) => {
        const rel = decodeURIComponent((req.url ?? "/").split("?")[0]);
        const file = path.resolve(root, "." + rel);
        if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
          res.statusCode = 404;
          return res.end("not found");
        }
        res.setHeader("Cache-Control", "no-cache");
        res.setHeader("Content-Type", file.endsWith(".json") ? "application/json" : "application/octet-stream");
        fs.createReadStream(file).pipe(res);
        void next;
      });
    },
  };
}

// Lalit Stock Application admin UI. Owner: Lalit Nayyar. Not financial advice.
export default defineConfig({
  plugins: [react(), firmwareDist()],
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
