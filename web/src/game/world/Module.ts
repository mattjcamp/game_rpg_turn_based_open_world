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

/** Build a /-prefixed URL into the active module's data folder. */
export function modulePath(file: string): string {
  return `/modules/${ACTIVE_MODULE}/${file}`;
}

/** Build a /-prefixed URL into the shared `data/` folder (system data
 *  shared across modules: tile defs, classes, races, etc.). */
export function dataPath(file: string): string {
  return `/data/${file}`;
}
