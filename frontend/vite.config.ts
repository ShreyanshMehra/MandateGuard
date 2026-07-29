import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// OneDrive-synced working directories can miss native filesystem change
// events, so polling is enabled per HANDOFF.md environment notes.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
  // Free-tier hosts (e.g. Render) put the app behind a platform-owned
  // hostname the dev server doesn't know in advance; allow it so `vite
  // preview` can serve the production build there (docker/deploy/frontend.Dockerfile).
  preview: {
    host: true,
    allowedHosts: true,
  },
});
