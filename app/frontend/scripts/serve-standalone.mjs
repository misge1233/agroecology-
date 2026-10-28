#!/usr/bin/env node
/**
 * Serve the production build. `next.config.ts` uses `output: "standalone"`,
 * which `next start` cannot serve; the standalone server also expects
 * `public/` and `.next/static` next to it (the Dockerfile copies them the
 * same way). Used by `npm start` and by the Playwright webServer.
 *
 *   npm run build && npm start          # PORT / HOSTNAME honoured
 */
import { cpSync, existsSync, rmSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const standalone = path.join(root, ".next", "standalone");

if (!existsSync(path.join(standalone, "server.js"))) {
  console.error("No standalone build found. Run `npm run build` first.");
  process.exit(1);
}
for (const rel of ["public", path.join(".next", "static")]) {
  const target = path.join(standalone, rel);
  rmSync(target, { recursive: true, force: true });
  cpSync(path.join(root, rel), target, { recursive: true });
}

const child = spawn(process.execPath, ["server.js"], {
  cwd: standalone,
  stdio: "inherit",
  env: {
    ...process.env,
    PORT: process.env.PORT || "3000",
    HOSTNAME: process.env.HOSTNAME || "0.0.0.0",
  },
});
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}
child.on("exit", (code) => process.exit(code ?? 0));
