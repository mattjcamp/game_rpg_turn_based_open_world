/**
 * Party-wide effects (Detect Traps, Infravision, Galadriel's Light…).
 *
 * Effects come from `data/effects.json` and have requirements that
 * gate which effects the current party can equip. The Python game
 * supports three requirement forms:
 *
 *   - `{ class: "Thief", min_level: 1 }`    — a member of that class
 *     at or above the level
 *   - `{ race:  "Dwarf" }`                  — any member of the race
 *   - `{ any_of: [<req>, <req>, …] }`       — at least one match
 *
 * Plus an `item_granted: true` flag for effects that only become
 * available once the party owns a specific item (we treat these as
 * unavailable for now — item-granted activation comes later).
 */

import { dataPath } from "./Module";
import type { PartyMember } from "./Party";

export interface Requirement {
  class?: string;
  min_level?: number;
  race?: string;
  any_of?: Requirement[];
}

export interface Effect {
  id: string;
  name: string;
  description: string;
  duration: "permanent" | number;
  requirements?: Requirement;
  item_granted?: boolean;
}

interface RawEffect {
  id?: string;
  name?: string;
  description?: string;
  duration?: "permanent" | number;
  requirements?: Requirement;
  item_granted?: boolean;
}

let _cache: Effect[] | null = null;

export async function loadEffects(url = dataPath("effects.json")): Promise<Effect[]> {
  if (_cache) return _cache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as { effects?: RawEffect[] };
  _cache = (raw.effects ?? []).map((e) => ({
    id: e.id ?? "",
    name: e.name ?? "?",
    description: e.description ?? "",
    duration: e.duration ?? "permanent",
    requirements: e.requirements,
    item_granted: e.item_granted,
  }));
  return _cache;
}

/**
 * Does the active party (or any single member) meet a single
 * requirement clause? Recurses into `any_of`.
 */
function meetsClause(req: Requirement, members: PartyMember[]): boolean {
  if (req.any_of && req.any_of.length > 0) {
    return req.any_of.some((sub) => meetsClause(sub, members));
  }
  if (req.class) {
    const min = req.min_level ?? 1;
    return members.some(
      (m) => m.class.toLowerCase() === req.class!.toLowerCase() && m.level >= min
    );
  }
  if (req.race) {
    return members.some((m) => m.race.toLowerCase() === req.race!.toLowerCase());
  }
  return false;
}

/**
 * Whether the party can equip this effect. Item-granted effects are
 * gated by item ownership, which we don't model yet — return false
 * so the UI can render them dim with an explanatory hint.
 */
export function canEquip(effect: Effect, members: PartyMember[]): boolean {
  if (effect.item_granted) return false;
  if (!effect.requirements) return true;
  return meetsClause(effect.requirements, members);
}

/** Test-only cache reset. */
export function _clearEffectsCache(): void {
  _cache = null;
}
