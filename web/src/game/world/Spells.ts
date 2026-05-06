/**
 * Spells loader.
 *
 * Mirrors `data/spells.json` from the Python project. The full schema
 * carries combat-only fields (targeting, sfx, hit_sfx, etc.) — we
 * keep them around as opaque so the data round-trips cleanly, but
 * the menu-cast flow only reads a small subset.
 */

import { dataPath } from "./Module";
import type { PartyMember } from "./Party";

export interface SpellEffectValue {
  dice?: string;
  dice_count?: number;
  dice_sides?: number;
  stat_bonus?: string;
  min_damage?: number;
  ac_bonus?: number;
  range_bonus?: number;
  max_target_hp?: number;
  save_dc_stat?: string;
  save_dc_base?: number;
  save_stat?: string;
  hp_amount?: number;
  [key: string]: unknown;
}

export interface Spell {
  id: string;
  name: string;
  description: string;
  allowable_classes: string[];
  casting_type: string;
  /** Minimum caster level when no per-class table is given. */
  min_level: number;
  /** Per-class minimum levels — overrides `min_level` when present. */
  class_min_levels?: Record<string, number>;
  mp_cost: number;
  duration: "instant" | number;
  effect_type: string;
  effect_value?: SpellEffectValue;
  range?: number;
  targeting?: string;
  /** Where the spell may be cast: any of "battle"/"overworld"/"town"/"dungeon". */
  usable_in: string[];
  icon?: string;
}

interface RawSpell {
  id?: string;
  name?: string;
  description?: string;
  allowable_classes?: string[];
  casting_type?: string;
  min_level?: number;
  class_min_levels?: Record<string, number>;
  mp_cost?: number;
  duration?: "instant" | number;
  effect_type?: string;
  effect_value?: SpellEffectValue;
  range?: number;
  targeting?: string;
  usable_in?: string[] | string;
  icon?: string;
}

let _cache: Spell[] | null = null;

export async function loadSpells(url = dataPath("spells.json")): Promise<Spell[]> {
  if (_cache) return _cache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as { spells?: RawSpell[] };
  _cache = (raw.spells ?? []).map((s) => spellFromRaw(s));
  return _cache;
}

export function spellFromRaw(s: RawSpell): Spell {
  const usable = Array.isArray(s.usable_in)
    ? s.usable_in
    : typeof s.usable_in === "string"
      ? [s.usable_in]
      : [];
  return {
    id: s.id ?? "",
    name: s.name ?? "?",
    description: s.description ?? "",
    allowable_classes: s.allowable_classes ?? [],
    casting_type: s.casting_type ?? "",
    min_level: s.min_level ?? 1,
    class_min_levels: s.class_min_levels,
    mp_cost: s.mp_cost ?? 0,
    duration: s.duration ?? "instant",
    effect_type: s.effect_type ?? "",
    effect_value: s.effect_value,
    range: s.range,
    targeting: s.targeting,
    usable_in: usable,
    icon: s.icon,
  };
}

/** Per-class minimum level required to cast — `class_min_levels` wins over `min_level`. */
export function minLevelFor(spell: Spell, klass: string): number {
  const ck = spell.class_min_levels?.[klass];
  if (typeof ck === "number" && Number.isFinite(ck)) return ck;
  return spell.min_level;
}

/**
 * Active members who can cast this spell — must have the class, meet
 * the level threshold, be alive, and have at least `mp_cost` MP.
 */
export function castersFor(spell: Spell, members: PartyMember[]): PartyMember[] {
  return members.filter((m) => {
    if (m.hp <= 0) return false;
    if (!spell.allowable_classes.includes(m.class)) return false;
    if (m.level < minLevelFor(spell, m.class)) return false;
    if (m.maxMp == null || (m.mp ?? 0) < spell.mp_cost) return false;
    return true;
  });
}

/**
 * Spells the player can pick from the Party Inventory's CAST menu —
 * usable outside of combat (the spell has at least one non-"battle"
 * context) and at least one party member can cast it right now.
 */
export function spellsCastableFromMenu(
  spells: Spell[],
  members: PartyMember[],
): Spell[] {
  return spells.filter((s) => {
    if (s.usable_in.length === 0) return false;
    const outsideCombat = s.usable_in.some((c) => c !== "battle");
    if (!outsideCombat) return false;
    return castersFor(s, members).length > 0;
  });
}

/** Test-only cache reset. */
export function _clearSpellsCache(): void {
  _cache = null;
}
