// FICTIONAL example: production server started by the config; deploys to AWS via deploy/*.yml.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  use: { baseURL: "http://localhost:3111" },
  webServer: { command: "npx next start -p 3111", url: "http://localhost:3111" },
});
