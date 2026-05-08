#!/usr/bin/env node
/**
 * Mirror the Python project's `data/` and `modules/` folders into the
 * Next.js public/ directory so the web app reads the same JSON files
 * the Python game does.
 *
 *   <repo>/data/*           → web/public/data/*
 *   <repo>/modules/<name>/* → web/public/modules/<name>/*
 *
 * Run as part of `predev` and `prebuild`. Idempotent — copies only
 * what's changed (mtime + size). The target tree is treated as a
 * mirror: extra files in the target are pruned, so removing a
 * module/file in the source removes it on the web side too.
 *
 * Two entry points:
 *   - CLI (default `node scripts/sync-modules.mjs`): one-shot sync,
 *     prints stats, exits.
 *   - `import { syncModules, SOURCES }`: programmatic — used by the
 *     `dev` launcher to re-sync whenever a JSON changes.
 */

import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = join(__dirname, "..", "..");      // .../<repo>
const PUBLIC = join(__dirname, "..", "public"); // .../<repo>/web/public

export const SOURCES = [
  { src: join(REPO, "data"),    dst: join(PUBLIC, "data") },
  { src: join(REPO, "modules"), dst: join(PUBLIC, "modules") },
];

/** File extensions that are safe to mirror. We deliberately skip
 *  Mac '.DS_Store', Python '__pycache__', and anything binary. */
const ALLOWED = new Set([".json"]);

function shouldCopy(srcStat, dstPath) {
  if (!existsSync(dstPath)) return true;
  const dstStat = statSync(dstPath);
  return srcStat.size !== dstStat.size || srcStat.mtimeMs > dstStat.mtimeMs;
}

function walkAndCopy(srcDir, dstDir) {
  const desired = new Set();
  function walk(s, d) {
    if (!existsSync(s)) return;
    mkdirSync(d, { recursive: true });
    for (const name of readdirSync(s)) {
      if (name.startsWith(".")) continue;
      if (name === "saves" || name === "__pycache__") continue;
      const sp = join(s, name);
      const dp = join(d, name);
      const st = statSync(sp);
      if (st.isDirectory()) {
        walk(sp, dp);
      } else if (st.isFile()) {
        const ext = name.slice(name.lastIndexOf("."));
        if (!ALLOWED.has(ext)) continue;
        desired.add(dp);
        if (shouldCopy(st, dp)) {
          copyFileSync(sp, dp);
        }
      }
    }
  }
  walk(srcDir, dstDir);
  return desired;
}

function pruneExtras(dstDir, keep) {
  if (!existsSync(dstDir)) return { removed: 0, skipped: 0 };
  let removed = 0;
  let skipped = 0;
  function walk(d) {
    for (const name of readdirSync(d)) {
      const p = join(d, name);
      let st;
      try { st = statSync(p); } catch { continue; }
      if (st.isDirectory()) {
        walk(p);
        if (readdirSync(p).length === 0) {
          try { rmSync(p, { recursive: true, force: true }); } catch { /* tolerate */ }
        }
      } else if (st.isFile()) {
        if (!keep.has(p)) {
          try { rmSync(p); removed++; }
          catch (e) {
            // Some sandboxes refuse to delete files written by the
            // host. Don't crash the whole sync — just report.
            if (e.code === "EPERM" || e.code === "EACCES") { skipped++; }
            else throw e;
          }
        }
      }
    }
  }
  walk(dstDir);
  return { removed, skipped };
}

/**
 * Run the full sync once. Returns counts so callers can log/track.
 * `quiet` suppresses the per-source line and the prune lines — useful
 * for the dev watcher where chatter on every keystroke is noise.
 */
export function syncModules({ quiet = false } = {}) {
  let total = 0;
  let prunedTotal = 0;
  let skippedTotal = 0;
  for (const { src, dst } of SOURCES) {
    if (!existsSync(src)) {
      if (!quiet) console.warn(`sync-modules: source missing, skipping: ${src}`);
      continue;
    }
    const kept = walkAndCopy(src, dst);
    const { removed, skipped } = pruneExtras(dst, kept);
    total += kept.size;
    prunedTotal += removed;
    skippedTotal += skipped;
    if (!quiet) {
      console.log(
        `sync-modules: ${relative(REPO, src)} → ${relative(REPO, dst)}  (${kept.size} files)`
      );
    }
  }
  if (!quiet && prunedTotal) console.log(`sync-modules: pruned ${prunedTotal} stale file(s)`);
  if (!quiet && skippedTotal) {
    console.log(`sync-modules: skipped pruning ${skippedTotal} file(s) (permission denied)`);
  }
  return { total, pruned: prunedTotal, skipped: skippedTotal };
}

// CLI entry — run a one-shot sync when invoked directly.
const isCli = (() => {
  try { return process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]; }
  catch { return false; }
})();
if (isCli) syncModules();
