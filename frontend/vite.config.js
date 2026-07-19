import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite serves the SPA on :5173 and proxies API calls to FastAPI on :8000.
// Build: outputs to ../app/static, which FastAPI serves at / in prod/test.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/documents": "http://localhost:8000",
      "/sessions": "http://localhost:8000",
      "/jobs": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  build: {
    outDir: "../app/static",
    emptyOutDir: true,
  },
});
