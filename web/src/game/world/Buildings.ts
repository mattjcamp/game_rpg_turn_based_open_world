/**
 * Buildings — standalone structures on the overworld the party can
 * enter. Each building carries one or more "spaces" (Main Hall,
 * Basement, Citadel 2, …) and each space is structurally identical
 * to a town's interior: a tile grid, per-cell `tile_properties`,
 * optional NPCs, an entry coordinate.
 *
 * Source data lives at `modules/<name>/buildings.json`. The link
 * format on the overworld and inside other buildings is:
 *
 *   "building:<BuildingName>:<SpaceName>"   — explicit space
 *   "building:<BuildingName>"                — first space (default)
 *
 * Because a space is just a Town with extra building metadata, we
 * reuse `townFromRaw` to parse each one — the renderer / scene then
 * gets a `Town` it can hand straight to `tileMapForTown` and the
 * lighting collector.
 */

import { townFromRaw, type Town } from "./Towns";
import { modulePath } from "./Module";

export interface BuildingSpace extends Town {
  /** Name of the parent building, for round-trip path construction. */
  buildingName: string;
}

export interface Building {
  name: string;
  description: string;
  spaces: BuildingSpace[];
}

interface RawBuildingSpace {
  name?: string;
  width?: number;
  height?: number;
  entry_col?: number;
  entry_row?: number;
  tiles?: Record<string, unknown> | unknown[][];
  tile_properties?: Record<string, unknown>;
  npcs?: Array<Record<string, unknown>>;
  encounters?: unknown;
}

interface RawBuilding {
  name?: string;
  description?: string;
  spaces?: RawBuildingSpace[];
}

/** Build a path string the scene loader recognises. */
export function buildingPath(building: string, space?: string): string {
  return space ? `building:${building}:${space}` : `building:${building}`;
}

/**
 * Parse a "building:<name>[:<space>]" path into its parts. Returns
 * null when the input doesn't have the building: prefix so callers
 * can chain into other resolvers.
 */
export function parseBuildingPath(path: string): { building: string; space: string | null } | null {
  if (!path.startsWith("building:")) return null;
  const rest = path.slice("building:".length);
  const sep = rest.indexOf(":");
  if (sep < 0) return { building: rest, space: null };
  return { building: rest.slice(0, sep), space: rest.slice(sep + 1) };
}

export function buildingFromRaw(raw: RawBuilding): Building {
  const name = raw.name ?? "Unknown";
  const spaces: BuildingSpace[] = (raw.spaces ?? []).map((s) => {
    // RawBuildingSpace's tile shapes match what townFromRaw accepts —
    // we just cast and pass it through, then attach buildingName.
    const town = townFromRaw({
      name: s.name,
      width: s.width,
      height: s.height,
      tiles: s.tiles as Parameters<typeof townFromRaw>[0]["tiles"],
      entry_col: s.entry_col,
      entry_row: s.entry_row,
      tile_properties: s.tile_properties,
      npcs: s.npcs as Parameters<typeof townFromRaw>[0]["npcs"],
    });
    return Object.assign(town, { buildingName: name });
  });
  return { name, description: raw.description ?? "", spaces };
}

let _buildingCache: Building[] | null = null;

/** Fetch and parse the active module's buildings.json. Cached. */
export async function loadBuildings(url = modulePath("buildings.json")): Promise<Building[]> {
  if (_buildingCache) return _buildingCache;
  const res = await fetch(url);
  if (!res.ok) {
    // A module without standalone buildings is fine — return [] so
    // callers don't have to special-case 404s.
    if (res.status === 404) {
      _buildingCache = [];
      return _buildingCache;
    }
    throw new Error(`Failed to load ${url}: ${res.status}`);
  }
  const raw = (await res.json()) as RawBuilding[];
  if (!Array.isArray(raw)) throw new Error("buildings.json is not an array");
  _buildingCache = raw.map(buildingFromRaw);
  return _buildingCache;
}

export function getBuildingByName(buildings: Building[], name: string): Building | null {
  return buildings.find((b) => b.name === name) ?? null;
}

/**
 * Resolve a "BuildingName" or "BuildingName:SpaceName" reference to
 * the BuildingSpace it points at. When the space is omitted, the
 * first space wins — that's what the editor does when authors mark a
 * door as `building:Abandoned Building` without picking a room.
 */
export function getBuildingSpace(
  buildings: Building[],
  ref: string
): BuildingSpace | null {
  const colon = ref.indexOf(":");
  const buildingName = colon < 0 ? ref : ref.slice(0, colon);
  const spaceName = colon < 0 ? null : ref.slice(colon + 1);
  const building = getBuildingByName(buildings, buildingName);
  if (!building) return null;
  if (spaceName == null) return building.spaces[0] ?? null;
  return building.spaces.find((s) => s.name === spaceName) ?? null;
}

/** Test-only cache reset. */
export function _clearBuildingCache(): void {
  _buildingCache = null;
}
