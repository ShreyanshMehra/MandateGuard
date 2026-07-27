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
});
