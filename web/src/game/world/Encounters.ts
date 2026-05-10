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
  /**
   * Monster difficulty tiers ("easy" / "normal" / "hard" / "deadly")
   * the dungeon will accept. When set together with `monsterDifficulty`,
   * candidate encounters get their `monsters` rosters pruned to entries
   * whose individual difficulty falls in this set. Encounters whose
   * roster empties out after pruning are excluded entirely; encounters
   * whose lead got pruned have it swapped to the first surviving
   * monster.
   *
   * When undefined the filter is a no-op — callers that don't care
   * about per-monster tiering keep the prior behaviour.
   */
  allowedDifficulties?: ReadonlySet<string>;
  /**
   * Lookup: monster catalog name → difficulty tag (from monsters.json).
   * Required when `allowedDifficulties` is set; without it the prune
   * step can't tell which monsters belong to which tier and the
   * filter no-ops to avoid silently dropping every encounter.
   */
  monsterDifficulty?: (name: string) => string | undefined;
}

/**
 * Roll one encounter from the named area, restricted to the given
 * level band. Returns null when nothing matches (caller decides
 * whether to leave the room empty or fall back to a hardcoded fight).
 *
 * When `allowedDifficulties` + `monsterDifficulty` are supplied, the
 * sampler additionally enforces per-monster tier matching: each
 * candidate encounter's roster is pruned to monsters whose individual
 * `difficulty` is in the allowed set, and encounters that lose their
 * full roster are removed from the pool. Used by dungeon generation
 * to honour per-dungeon difficulty without leaning on the encounter
 * `level` field alone (a level-6 encounter can mix hard + normal
 * monsters; we only want the matching ones).
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
  let eligible = list.filter((e) => e.level >= minLv && e.level <= maxLv);

  // Optional per-monster difficulty pruning. Both the allow-list and
  // the lookup must be present for the filter to engage — see the
  // option doc for the rationale.
  const allow = opts.allowedDifficulties;
  const lookup = opts.monsterDifficulty;
  if (allow && lookup) {
    const pruned: EncounterTemplate[] = [];
    for (const e of eligible) {
      const survivors = e.monsters.filter((name) => {
        const d = lookup(name);
        return d != null && allow.has(d);
      });
      if (survivors.length === 0) continue; // entire roster filtered out
      // Keep the original lead when it survived; otherwise promote the
      // first survivor so `monsterPartyTile` always names a monster
      // that's actually in the fight.
      const lead = survivors.includes(e.monsterPartyTile)
        ? e.monsterPartyTile
        : survivors[0];
      pruned.push({ ...e, monsters: survivors, monsterPartyTile: lead });
    }
    eligible = pruned;
  }

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
