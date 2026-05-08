/**
 * Encounter table loader.
 *
 * Reads `data/encounters.json` (the same file the Python game uses)
 * and exposes a weighted-sampler keyed by area + level band. The
 * dungeon generator places one encounter per non-entrance room by
 * calling `sampleEncounter("dungeon", ...)`.
 *
 * The JSON format groups encounters by area (`"dungeon"`,
 * `"overworld"`, `"house_basement"`); each entry has:
 *
 *   { name, level (1-8), weight, terrain, monster_party_tile, monsters[] }
 *
 * `monster_party_tile` is the catalog name shown on the map (the lead
 * monster). `monsters` is the full encounter roster handed to combat.
 */
import { dataPath } from "./Module";
import { defaultRng, type RNG } from "../rng";

export interface EncounterTemplate {
  name: string;
  /** 1..8, used by area / difficulty filters. */
  level: number;
  weight: number;
  terrain: "land" | "sea";
  /** Catalog name of the monster shown on the map (the lead). */
  monsterPartyTile: string;
  /** Full roster handed to CombatScene. First entry should match the lead. */
  monsters: string[];
}

interface RawEncounter {
  name?: string;
  level?: number;
  weight?: number;
  terrain?: string;
  monster_party_tile?: string;
  monsters?: string[];
}

interface RawEncounters {
  encounters?: Record<string, RawEncounter[]>;
}

let _cache: Record<string, EncounterTemplate[]> | null = null;

function fromRaw(raw: RawEncounter): EncounterTemplate | null {
  const monsters = Array.isArray(raw.monsters)
    ? raw.monsters.filter((m): m is string => typeof m === "string" && m.length > 0)
    : [];
  if (monsters.length === 0) return null;
  const lead = typeof raw.monster_party_tile === "string" && raw.monster_party_tile.length > 0
    ? raw.monster_party_tile
    : monsters[0];
  return {
    name: raw.name ?? "Encounter",
    level: typeof raw.level === "number" && Number.isFinite(raw.level) ? raw.level : 1,
    weight: typeof raw.weight === "number" && raw.weight > 0 ? raw.weight : 1,
    terrain: raw.terrain === "sea" ? "sea" : "land",
    monsterPartyTile: lead,
    monsters,
  };
}

export async function loadEncounters(
  url = dataPath("encounters.json"),
): Promise<Record<string, EncounterTemplate[]>> {
  if (_cache) return _cache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawEncounters;
  const out: Record<string, EncounterTemplate[]> = {};
  for (const [area, list] of Object.entries(raw.encounters ?? {})) {
    if (!Array.isArray(list)) continue;
    out[area] = list
      .map(fromRaw)
      .filter((e): e is EncounterTemplate => e !== null);
  }
  _cache = out;
  return out;
}

/** Test-only: clear the encounter cache. */
export function _clearEncountersCache(): void {
  _cache = null;
}

export interface SampleOptions {
  /** Inclusive lower bound on encounter level. Default 1. */
  minLevel?: number;
  /** Inclusive upper bound on encounter level. Default 8. */
  maxLevel?: number;
  rng?: RNG;
}

/**
 * Roll one encounter from the named area, restricted to the given
 * level band. Returns null when nothing matches (caller decides
 * whether to leave the room empty or fall back to a hardcoded fight).
 */
export function sampleEncounter(
  table: Record<string, EncounterTemplate[]>,
  area: string,
  opts: SampleOptions = {},
): EncounterTemplate | null {
  const list = table[area];
  if (!list || list.length === 0) return null;
  const minLv = opts.minLevel ?? 1;
  const maxLv = opts.maxLevel ?? 8;
  const rng = opts.rng ?? defaultRng;
  const eligible = list.filter((e) => e.level >= minLv && e.level <= maxLv);
  if (eligible.length === 0) return null;
  const total = eligible.reduce((s, e) => s + e.weight, 0);
  if (total <= 0) return null;
  let roll = rng() * total;
  for (const e of eligible) {
    roll -= e.weight;
    if (roll <= 0) return e;
  }
  return eligible[eligible.length - 1];
}
