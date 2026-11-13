import { defineConfig } from "vite";

export default defineConfig({
  base: "/review/",
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  build: { outDir: "../app/dashboard/dist", emptyOutDir: true },
  test: { environment: "jsdom", globals: true },
});
