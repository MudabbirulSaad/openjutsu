import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  timeout: 45000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:9781",
    viewport: { width: 1440, height: 960 },
    trace: "retain-on-failure",
  },
  reporter: "list",
});
