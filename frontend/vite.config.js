import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The demo/mobile path serves the built dist/ from FastAPI on one origin (see PLAN.md).
// For local dev convenience, proxy /ws to the backend so `npm run dev` works against :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // expose on LAN for desktop testing
    proxy: {
      "/ws": { target: "ws://localhost:8000", ws: true },
      "/health": "http://localhost:8000",
    },
  },
});
