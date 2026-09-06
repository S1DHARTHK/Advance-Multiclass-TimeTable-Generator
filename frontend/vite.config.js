import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Take the port the launcher assigns when there is one, so this app can
    // run alongside other dev servers; fall back to Vite's usual 5173.
    port: Number(process.env.PORT) || 5173,
    open: true,
    proxy: {
      // the timetable editor service (editor_server.py); when it is not
      // running the UI falls back to the bundled timetable, read-only
      "/api": {
        target: process.env.EDITOR_API || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
