import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev proxies the API + media to the FastAPI backend on :8000, so the browser
// talks to one origin. The production build is served by the backend itself.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/media": "http://127.0.0.1:8000",
      "/examples": "http://127.0.0.1:8000",
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
