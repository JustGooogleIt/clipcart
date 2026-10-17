import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

const api = process.env.CLIPCART_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@contracts": fileURLToPath(new URL("../../packages/contracts/index.ts", import.meta.url)) },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": api, "/go": api },
  },
});
