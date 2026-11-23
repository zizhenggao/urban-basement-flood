import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

declare const process: { env: { GITHUB_PAGES?: string } };

// The API runs on :8000. Proxying /api means the browser sees one origin.
// GITHUB_PAGES publishes the map under the project site path. Chat still calls /api.
export default defineConfig(({ command }) => ({
  base: command === "build" && process.env.GITHUB_PAGES === "true" ? "/urban-basement-flood/" : "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
}));
