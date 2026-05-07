/**
 * Active-module configuration.
 *
 * The Python project ships multiple modules under `modules/<name>/` —
 * each is a self-contained world definition (overview map, towns,
 * dungeons, quests, buildings). The web app mirrors that folder
 * verbatim under `web/public/modules/<name>/` (see
 * `web/scripts/sync-modules.mjs`) and reads the same JSON files at
 * runtime, with the same filenames the Python game uses.
 *
 * To swap to a different module, change the constant below and the
 * web app loads that module on next refresh. No code changes required
 * for the data — only this one constant.
 *
 * (A future iteration can read the module name from a URL parameter,
 * a New-Game form, or a save file.)
 */

export const ACTIVE_MODULE = "the_dragon_of_dagorn";

/**
 * Path prefix for static assets and data when the app is hosted under
 * a sub-path (e.g. GitHub Pages: `https://user.github.io/<repo>/`).
 * Empty string for local dev / root-hosted deploys.
 *
 * Driven by `NEXT_PUBLIC_BASE_PATH`, which next.config.mjs also reads
 * to set Next's own `basePath`. Keeping both in sync means that
 * Next-aware code (<Link>, <Image>) and our raw fetch/Phaser asset
 * loads land at the same URL.
 */
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/**
 * Prepend `BASE_PATH` to any absolute URL we hand to `fetch()` or
 * Phaser's loader. No-op for already-absolute URLs (http://) and for
 * paths that don't start with "/" (which Phaser treats as relative to
 * its loader's baseURL — not our concern here).
 */
export function withBase(path: string): string {
  if (!path) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  if (!path.startsWith("/")) return path;
  return `${BASE_PATH}${path}`;
}

/** Build a /-prefixed URL into the active module's data folder. */
export function modulePath(file: string): string {
  return withBase(`/modules/${ACTIVE_MODULE}/${file}`);
}

/** Build a /-prefixed URL into the shared `data/` folder (system data
 *  shared across modules: tile defs, classes, races, etc.). */
export function dataPath(file: string): string {
  return withBase(`/data/${file}`);
}

/**
 * Build a /-prefixed URL for an asset under `public/assets/`. Used by
 * code paths that hold sprite paths as strings — fighters.ts, monsters.ts,
 * Tiles.ts, etc. The argument may already start with `/assets/` (in
 * which case we just prefix base) or be a bare key like
 * `"characters/fighter.png"`.
 */
export function assetUrl(path: string): string {
  if (!path) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  if (path.startsWith("/")) return withBase(path);
  return withBase(`/assets/${path}`);
}
