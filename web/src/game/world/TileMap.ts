/**
 * Pure-TS overworld tile map.
 *
 * Mirrors the relevant subset of `src/tile_map.py` from the Python
 * project — width/height, the 2D tile id grid, plus the per-tile
 * properties dict that the module editor writes for walkability
 * overrides and inter-map links (towns / dungeons / buildings).
 *
 * Loading happens via `loadTileMap()` which fetches a JSON file from
 * the Next.js `public/` directory at runtime. Both the
 * `module_editor`'s `overview_map.json` shape and the older
 * `overworld.json` `{ size: { width, height } }` shape are accepted.
 *
 * Tile properties on the map look like:
 *
 *   "10,14": {
 *     "walkable": "yes (override)" | "no (override)" | "inherit (yes)" | true | false,
 *     "linked": true,
 *     "link_map": "town:Plainstown" | "dungeon:Goblin's Nest",
 *     "link_x": "11", "link_y": "2"
 *   }
 *
 * `link_x` / `link_y` are stored as strings in the source JSON; the
 * loader coerces to numbers. `link_map` is split on the first colon.
 */

import { tileDef } from "./Tiles";

export interface GridPos {
  col: number;
  row: number;
}

/** A link from an overworld tile to an interior map. */
export interface TileLink {
  /** Which kind of interior — "town", "dungeon", "building", … */
  kind: string;
  /** Name of the named interior to load (the part after the colon). */
  name: string;
  /** Optional entry coordinates inside the interior. */
  x?: number;
  y?: number;
}

/**
 * Per-cell property entry from the module editor. The named fields
 * are the ones the engine reads directly; everything else is allowed
 * through so authors can attach extra metadata (effects, items,
 * shop_type, lighting hints, etc.) without us having to enumerate it
 * here.
 */
interface TilePropEntry {
  walkable?: boolean | string;
  linked?: boolean;
  link_map?: string;
  link_x?: string | number;
  link_y?: string | number;
  light_source?: boolean | string;
  light_range?: string | number;
  effect?: string;
  item?: string;
  shop_type?: string;
  label?: string;
  // Authors are free to add other keys; the lighting / decoration /
  // future-feature code just type-narrows what it cares about.
  [key: string]: unknown;
}

export class TileMap {
  readonly width: number;
  readonly height: number;
  /** tiles[row][col] — note row-major to match the JSON layout. */
  readonly tiles: number[][];
  /** Map editor's per-tile properties dict, keyed by "col,row". */
  readonly tileProperties: Record<string, TilePropEntry>;
  /** Optional default party spawn from the map JSON. */
  readonly partyStart: GridPos | null;
  /** Display label from the map JSON, if any. */
  readonly label: string | null;

  constructor(
    width: number,
    height: number,
    tiles: number[][],
    options: {
      tileProperties?: Record<string, TilePropEntry>;
      partyStart?: GridPos | null;
      label?: string | null;
    } = {}
  ) {
    this.width = width;
    this.height = height;
    this.tiles = tiles;
    this.tileProperties = options.tileProperties ?? {};
    this.partyStart = options.partyStart ?? null;
    this.label = options.label ?? null;
  }

  inBounds(col: number, row: number): boolean {
    return col >= 0 && col < this.width && row >= 0 && row < this.height;
  }

  getTile(col: number, row: number): number {
    if (!this.inBounds(col, row)) return -1;
    return this.tiles[row][col];
  }

  /**
   * Walkability — per-tile override beats the tile-id default.
   *
   * Authors store overrides on `tile_properties["<col>,<row>"].walkable`
   * in any of the value forms the Python module editor produces:
   *
   *   - boolean true / false               — explicit force
   *   - string "yes (override)" / "no (override)"  — explicit force
   *   - string "True" / "False"            — Python-stringified bool
   *   - string "inherit (yes)" / "inherit (no)" — defer to tile_def
   *   - any other value                    — defer to tile_def
   *
   * The "inherit" forms exist so authors can attach OTHER properties
   * to a tile (light_source, item, link_map…) without having to also
   * pin down its walkability — the tile keeps its tile_defs default.
   *
   * Anything we don't recognise falls back to `tileDef(id).walkable`
   * to stay consistent with the Python game's behaviour.
   */
  isWalkable(col: number, row: number): boolean {
    if (!this.inBounds(col, row)) return false;
    const id = this.getTile(col, row);
    const baseWalkable = tileDef(id).walkable;
    const props = this.tileProperties[`${col},${row}`];
    if (!props || props.walkable === undefined) return baseWalkable;
    const w = props.walkable;
    if (w === true) return true;
    if (w === false) return false;
    if (typeof w === "string") {
      const s = w.trim().toLowerCase();
      if (s === "yes (override)" || s === "true") return true;
      if (s === "no (override)" || s === "false") return false;
      // "inherit (yes)" / "inherit (no)" / anything else defers
    }
    return baseWalkable;
  }

  /**
   * Return link metadata for the tile, or null. Honors both `linked`
   * and a present `link_map`; either alone is enough — the editor is
   * inconsistent about which it sets first.
   *
   * `link_map` comes in two shapes from the editor:
   *   - "<kind>:<name>"  e.g. "town:Plainstown", "dungeon:Goblin's Nest"
   *   - "<kind>"         e.g. "overworld"   (no name — the overworld is unique)
   *
   * We only require `kind` to be non-empty; `name` is left as the empty
   * string for kind-only links so callers like TownScene's exit check
   * can still see `link.kind === "overworld"`.
   */
  getTileLink(col: number, row: number): TileLink | null {
    const props = this.tileProperties[`${col},${row}`];
    if (!props) return null;
    if (!props.linked && !props.link_map) return null;
    if (!props.link_map) return null;
    // Split on the FIRST colon — town/dungeon names can contain ":"
    // (rare, but possible — "town:Plainstown:branch", e.g.).
    const idx = props.link_map.indexOf(":");
    const kind = idx >= 0 ? props.link_map.slice(0, idx) : props.link_map;
    const name = idx >= 0 ? props.link_map.slice(idx + 1) : "";
    if (!kind) return null;
    const x = props.link_x !== undefined ? Number(props.link_x) : undefined;
    const y = props.link_y !== undefined ? Number(props.link_y) : undefined;
    return {
      kind,
      name,
      x: Number.isFinite(x) ? x : undefined,
      y: Number.isFinite(y) ? y : undefined,
    };
  }
}

interface RawOverworld {
  label?: string;
  map_config?: { width?: number; height?: number };
  size?: { width?: number; height?: number };
  tiles?: number[][];
  tile_properties?: Record<string, TilePropEntry>;
  party_start?: { col?: number; row?: number };
  start_position?: { col?: number; row?: number };
}

/**
 * Build a TileMap from a raw module-editor JSON payload.
 *
 * Accepts both the `map_config + party_start` shape (newer modules
 * like the Dragon of Dagorn) and the older `size + start_position`
 * shape (asoloth overworld.json).
 */
export function tileMapFromOverview(raw: unknown): TileMap {
  if (!raw || typeof raw !== "object") {
    throw new Error("Overworld JSON payload is not an object");
  }
  const obj = raw as RawOverworld;
  const w = obj.map_config?.width ?? obj.size?.width ?? 0;
  const h = obj.map_config?.height ?? obj.size?.height ?? 0;
  const tiles = obj.tiles;
  if (!w || !h) throw new Error("Overworld JSON missing width/height");
  if (!Array.isArray(tiles) || tiles.length !== h) {
    throw new Error(
      `Overworld JSON tiles array length ${tiles?.length ?? "?"} != declared height ${h}`
    );
  }
  for (let r = 0; r < h; r++) {
    if (!Array.isArray(tiles[r]) || tiles[r].length !== w) {
      throw new Error(
        `Overworld row ${r} has ${tiles[r]?.length ?? "?"} cols, expected ${w}`
      );
    }
  }
  const startSrc = obj.party_start ?? obj.start_position;
  const partyStart =
    startSrc && typeof startSrc.col === "number" && typeof startSrc.row === "number"
      ? { col: startSrc.col, row: startSrc.row }
      : null;
  return new TileMap(w, h, tiles, {
    tileProperties: obj.tile_properties ?? {},
    partyStart,
    label: obj.label ?? null,
  });
}

/** Fetch and parse the bundled overworld map at /data/overworld.json. */
export async function loadTileMap(url = "/data/overworld.json"): Promise<TileMap> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load ${url}: ${res.status} ${res.statusText}`);
  }
  const raw = await res.json();
  return tileMapFromOverview(raw);
}
