import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const rootDir = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@": rootDir,
      "next/font/google": `${rootDir}/test/mocks/next-font-google.ts`
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"]
  }
});
