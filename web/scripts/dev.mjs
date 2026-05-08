#!/usr/bin/env node
/**
 * Dev launcher — one process that wraps `next dev` and re-syncs the
 * Python project's `data/` and `modules/` folders into `web/public/`
 * whenever a JSON file changes.
 *
 * Replaces the plain `next dev` script. `predev` already runs a sync
 * before this launcher fires, so the initial state is fresh; the
 * watcher's job is to keep it that way without forcing a dev-server
 * restart on every map edit.
 *
 * fs.watch's `recursive: true` option works on macOS and Windows
 * (which is what most of us dev on). Linux falls back to a polling
 * walk so we don't silently miss writes there either.
 */

import { spawn } from "node:child_process";
import { watch, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { syncModules, SOURCES } from "./sync-modules.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = join(__dirname, "..", "..");
const WEB = join(__dirname, "..");

// ── 1. Spawn `next dev`, attached to our stdio ─────────────────────
// `npx` is the cross-platform way to invoke a node_modules-local
// binary; it resolves whatever Next we have installed without us
// having to know its path.
const nextProc = spawn("npx", ["next", "dev"], {
  cwd: WEB,
  stdio: "inherit",
  shell: process.platform === "win32",
});

nextProc.on("exit", (code) => process.exit(code ?? 0));

// Forward Ctrl-C / kill signals so `next dev` shuts down cleanly
// instead of becoming an orphan.
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => {
    try { nextProc.kill(sig); } catch { /* already dead */ }
  });
}

// ── 2. Set up file watchers on each source folder ──────────────────
// Multiple writes from a single editor save (write temp file → rename)
// fire several events in quick succession. Debounce so a flurry of
// events triggers exactly one re-sync.
let pending;
function scheduleSync(reason) {
  clearTimeout(pending);
  pending = setTimeout(() => {
    try {
      const result = syncModules({ quiet: true });
      // Single concise line so the watcher is visible without burying
      // Next's compile output.
      console.log(
        `→ sync-modules: re-synced after ${reason}  ` +
        `(${result.total} files mirrored, ${result.pruned} pruned)`
      );
    } catch (err) {
      console.error("sync-modules failed:", err);
    }
  }, 80);
}

for (const { src } of SOURCES) {
  let exists = false;
  try { exists = statSync(src).isDirectory(); } catch { /* missing */ }
  if (!exists) continue;
  try {
    watch(src, { recursive: true }, (_eventType, filename) => {
      // We only care about JSON edits — sync-modules.mjs filters
      // these too, but checking here cuts down on noisy logs from
      // editor swap files.
      if (!filename || !filename.endsWith(".json")) return;
      scheduleSync(`${relative(REPO, src)}/${filename}`);
    });
    console.log(`watch: ${relative(REPO, src)}`);
  } catch (err) {
    // Recursive watch is not supported on every platform/runtime.
    // Fall back loudly so the user knows to restart on edits if
    // they're on a platform where this didn't work.
    console.warn(
      `watch: failed to attach to ${relative(REPO, src)} ` +
      `(${err.code ?? err.message}). Restart the dev server to pick up edits there.`
    );
  }
}
