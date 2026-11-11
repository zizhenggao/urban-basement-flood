import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API runs on :8000. Proxying /api means the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
