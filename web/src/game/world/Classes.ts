/**
 * Class & race templates — port of the small slice of `data/classes/*.json`
 * and `data/races.json` the leveling system needs (HP/MP/XP per level
 * and the casting-stat source for MP gains).
 *
 * The Python game loads these lazily per-character; here we cache by
 * lowercase name on first fetch and reuse forever. Failing fetches
 * throw — leveling falls back to sane defaults via the helpers in
 * Leveling.ts so combat doesn't soft-lock if a class file is missing.
 */

import { dataPath } from "./Module";

export interface MpSource {
  /** Single-stat caster: which ability feeds the per-level MP gain. */
  ability?: "strength" | "dexterity" | "intelligence" | "wisdom";
  /** Dual-stat caster (Druid). One of "higher" / "average"; absent
   *  falls back to the lower value (Python's default). */
  abilities?: Array<"strength" | "dexterity" | "intelligence" | "wisdom">;
  mode?: "higher" | "average";
}

/**
 * Non-spell class ability — Pick Locks, Detect Traps, Turn Undead
 * (when wired as a class ability rather than a spell), Herbalism, etc.
 *
 * Mirrors the per-class JSON's `class_abilities` array. `minLevel`
 * is the level the ability becomes available; absent or `1` means
 * "available from character creation". Level-up dialogs diff this
 * against the member's old/new level to surface fresh unlocks.
 */
export interface ClassAbility {
  name: string;
  description: string;
  minLevel: number;
}

export interface ClassTemplate {
  name: string;
  hpPerLevel: number;
  mpPerLevel: number;
  expPerLevel: number;
  /** Tile movement budget per combat turn — Wizards/Clerics 2,
   *  Fighters 4, Thieves/Rangers 6 in the shipped data. */
  range: number;
  mpSource?: MpSource;
  /** Non-spell abilities the class learns, with their level gates.
   *  Empty for plain classes (Fighter, Thief, Wizard, Cleric); the
   *  hybrid classes (Ranger, Paladin, Alchemist) carry one or more.
   *  Optional so test fixtures and old loaders that don't set it
   *  don't have to thread `[]` through every literal — consumers
   *  treat undefined as the empty list. */
  classAbilities?: ClassAbility[];
}

export interface RaceInfo {
  name: string;
  /** Optional XP override — Humans use 750 instead of the class default. */
  expPerLevel?: number;
}

interface RawClassAbility {
  name?: string;
  description?: string;
  min_level?: number;
}

interface RawClass {
  name?: string;
  hp_per_level?: number;
  mp_per_level?: number;
  exp_per_level?: number;
  range?: number;
  mp_source?: {
    ability?: string;
    abilities?: string[];
    mode?: string;
  } | null;
  class_abilities?: RawClassAbility[];
}

interface RawRaces {
  [key: string]: { exp_per_level?: number } | string;
}

const _classCache = new Map<string, ClassTemplate>();
let _racesCache: Map<string, RaceInfo> | null = null;

function classFromRaw(name: string, raw: RawClass): ClassTemplate {
  const src = raw.mp_source;
  let mpSource: MpSource | undefined;
  if (src) {
    if (src.ability) {
      mpSource = { ability: src.ability as MpSource["ability"] };
    } else if (Array.isArray(src.abilities)) {
      mpSource = {
        abilities: src.abilities as MpSource["abilities"],
        mode: src.mode as MpSource["mode"],
      };
    }
  }
  // Per-ability default min_level is 1 ("known from character creation"),
  // matching the Python game's behaviour where an `abilities` entry
  // without `min_level` is always available. Level-up unlocks key off
  // an explicit min_level above 1.
  const classAbilities: ClassAbility[] = (raw.class_abilities ?? [])
    .map((a) => ({
      name: a.name ?? "",
      description: a.description ?? "",
      minLevel: typeof a.min_level === "number" ? a.min_level : 1,
    }))
    .filter((a) => a.name.length > 0);
  return {
    name: raw.name ?? name,
    hpPerLevel:  raw.hp_per_level  ?? 6,
    mpPerLevel:  raw.mp_per_level  ?? 0,
    expPerLevel: raw.exp_per_level ?? 1000,
    range:       raw.range         ?? 4,
    mpSource,
    classAbilities,
  };
}

/** Fetch one class template (e.g. "Cleric"). Cached after the first call. */
export async function loadClass(name: string): Promise<ClassTemplate> {
  const key = name.toLowerCase();
  const cached = _classCache.get(key);
  if (cached) return cached;
  const url = dataPath(`classes/${key}.json`);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawClass;
  const tpl = classFromRaw(name, raw);
  _classCache.set(key, tpl);
  return tpl;
}

/** Fetch the races map. Cached after the first call. */
export async function loadRaces(url = dataPath("races.json")): Promise<Map<string, RaceInfo>> {
  if (_racesCache) return _racesCache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawRaces;
  const out = new Map<string, RaceInfo>();
  for (const [name, body] of Object.entries(raw)) {
    if (name.startsWith("_") || typeof body !== "object" || body === null) continue;
    out.set(name, {
      name,
      expPerLevel: typeof body.exp_per_level === "number" ? body.exp_per_level : undefined,
    });
  }
  _racesCache = out;
  return out;
}

/** Test-only cache reset. */
export function _clearClassCaches(): void {
  _classCache.clear();
  _racesCache = null;
}
