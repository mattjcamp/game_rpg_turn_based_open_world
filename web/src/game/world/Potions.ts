/**
 * Alchemist potion crafting system.
 *
 * Mirrors the Python game's brew-list flow (`inventory_mixin.py`
 * `_open_brew_list` / `_attempt_brew`): the player picks a recipe from
 * the loaded `data/potions.json`, the party stash is checked for the
 * required reagents, an Alchemist rolls `d20 + INT modifier vs DC`,
 * and on success the crafted item lands in the stash. On failure the
 * reagents are still consumed — bad rolls cost real resources.
 *
 * This module is pure logic. `Potions.ts` knows nothing about
 * Phaser; PartyScene owns the recipe picker UI and the feedback
 * messages.
 */

import { dataPath } from "./Module";
import type { Party, PartyMember } from "./Party";
import { findClass, statMod } from "./PartyActions";
import { addToStash } from "./TownActions";
import type { Item } from "./Items";

/** One brewable recipe. `reagents` is a map of reagent-name → qty. */
export interface Recipe {
  /** Stable key into `data/potions.json`. */
  id: string;
  /** Display name surfaced in the brew list. */
  name: string;
  description: string;
  reagents: Record<string, number>;
  /** d20 + INT mod must be ≥ this to succeed. */
  dc: number;
  /** Item name added to the stash on success — usually matches `name`. */
  resultItem: string;
  /** How many copies of `resultItem` land in the stash per successful
   *  brew. Defaults to 1. */
  resultCount: number;
  /** Designer tag — "restoration", "offensive", "enhancement". Used
   *  by future filters; not surfaced in the v1 picker. */
  category: string;
}

interface RawRecipe {
  name?: string;
  description?: string;
  reagents?: Record<string, number>;
  dc?: number;
  result_item?: string;
  result_count?: number;
  category?: string;
}

interface RawPotionsFile {
  recipes?: Record<string, RawRecipe>;
  reagents?: string[];
}

let _cache: Recipe[] | null = null;

function recipeFromRaw(id: string, raw: RawRecipe): Recipe {
  return {
    id,
    name: raw.name ?? id,
    description: raw.description ?? "",
    reagents: raw.reagents ?? {},
    dc: typeof raw.dc === "number" ? raw.dc : 10,
    resultItem: raw.result_item ?? id,
    resultCount: typeof raw.result_count === "number" ? raw.result_count : 1,
    category: raw.category ?? "",
  };
}

/**
 * Fetch the active module's potions.json and return the parsed
 * recipe list. Cached for the page session so the brew picker can
 * be opened freely without re-fetching. JSON missing / malformed
 * returns an empty list rather than throwing — the brew action then
 * surfaces a "no recipes known" feedback line.
 */
export async function loadPotions(url = dataPath("potions.json")): Promise<Recipe[]> {
  if (_cache) return _cache;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = (await res.json()) as RawPotionsFile;
    const dict = raw.recipes ?? {};
    _cache = Object.entries(dict).map(([id, r]) => recipeFromRaw(id, r));
  } catch {
    _cache = [];
  }
  return _cache;
}

/** Test-only: drop the cached recipe list so a re-fetch hits the
 *  network/mocked fetch again. */
export function _clearPotionsCache(): void {
  _cache = null;
}

// ── Stash inspection / mutation ────────────────────────────────
//
// The reagent helpers honour both shapes the stash carries:
//
//   1. Stacked entry — `{ item: "Moonpetal", charges: 3 }` — three
//      reagents on a single row. Buying / picking up / passive
//      foraging all collapse here for stackable items via
//      `addToStash`.
//   2. Per-entry — `{ item: "Moonpetal" }` — one reagent on a single
//      row. Older code paths (and the herbalism passive's
//      `inventory.push`) write this shape.
//
// `countReagent` and `consumeReagent` walk both transparently so the
// brew engine doesn't care which path put the reagent there.

/** Total count of reagents named `name` across all stash entries. */
export function countReagent(party: Party, name: string): number {
  let total = 0;
  for (const e of party.inventory) {
    if (e.item !== name) continue;
    total += typeof e.charges === "number" ? e.charges : 1;
  }
  return total;
}

/**
 * Remove `qty` reagents named `name` from the stash. Walks entries
 * from end → start so splicing during the loop stays safe; for a
 * stacked entry, decrements its `charges` and drops the row only
 * when it hits zero. Returns true when the full quantity was
 * removed, false when the stash ran short (in which case any
 * already-consumed reagents stay consumed — callers must
 * pre-validate with `countReagent` to avoid partial debits).
 */
export function consumeReagent(party: Party, name: string, qty: number): boolean {
  let remaining = qty;
  for (let i = party.inventory.length - 1; i >= 0 && remaining > 0; i--) {
    const e = party.inventory[i];
    if (e.item !== name) continue;
    if (typeof e.charges === "number") {
      const take = Math.min(remaining, e.charges);
      e.charges -= take;
      remaining -= take;
      if (e.charges <= 0) party.inventory.splice(i, 1);
    } else {
      party.inventory.splice(i, 1);
      remaining--;
    }
  }
  return remaining === 0;
}

/** True iff the party has every reagent the recipe needs in the
 *  required quantity. Used by the picker to dim un-brewable rows. */
export function recipeIsAffordable(party: Party, recipe: Recipe): boolean {
  for (const [name, qty] of Object.entries(recipe.reagents)) {
    if (countReagent(party, name) < qty) return false;
  }
  return true;
}

/**
 * Per-recipe affordability + a missing-reagent list for the picker
 * tooltip. Doesn't mutate the party.
 */
export interface RecipeAvailability {
  affordable: boolean;
  /** Names of reagents the party doesn't have in sufficient quantity.
   *  Empty when `affordable` is true. */
  missing: string[];
}

export function recipeAvailability(party: Party, recipe: Recipe): RecipeAvailability {
  const missing: string[] = [];
  for (const [name, qty] of Object.entries(recipe.reagents)) {
    if (countReagent(party, name) < qty) missing.push(name);
  }
  return { affordable: missing.length === 0, missing };
}

// ── Brew attempt ────────────────────────────────────────────────

export interface BrewResult {
  /** True iff the operation ran — false for hard refusals (no
   *  alchemist, reagents went missing between picker and commit).
   *  Note: a SUCCESSFUL refusal (rolled below DC) still returns
   *  `ok: true` because the brew engine ran to completion — the
   *  attempt just failed the check. Inspect `success` for that. */
  ok: boolean;
  /** True iff the d20 + INT mod hit the DC. Undefined when `ok`
   *  is false (no attempt was made). */
  success?: boolean;
  /** Player-facing feedback. Includes the roll breakdown on a real
   *  attempt so the player can see why a brew failed. */
  message: string;
  /** d20 value (1..20) rolled by the Alchemist. Undefined on
   *  hard-refusal returns. */
  roll?: number;
  /** INT modifier the Alchemist added. */
  intMod?: number;
  /** Recipe that was attempted. */
  recipe?: Recipe;
}

/**
 * Brew one recipe. Mirrors `_attempt_brew` in the Python game:
 *
 *   1. Find an alive Alchemist — refuse otherwise.
 *   2. Re-check the party can afford the reagents (the picker
 *      may have shown the recipe as affordable but a stash entry
 *      could have been consumed by another action in between).
 *   3. Consume the reagents.
 *   4. Roll d20 + INT modifier vs the recipe's DC.
 *   5. On success, add `resultCount` copies of `resultItem` to the
 *      stash. On failure, the reagents are still gone — bad rolls
 *      cost real resources, same as Python.
 *
 * Returns a `BrewResult` the UI can format into a feedback message.
 */
export function attemptBrew(
  party: Party,
  members: PartyMember[],
  recipe: Recipe,
  rng: () => number = Math.random,
  items?: Map<string, Item>,
): BrewResult {
  const alchemist = findClass(members, "Alchemist");
  if (!alchemist) {
    return { ok: false, message: "No Alchemist in the party." };
  }
  // Re-check reagents — picker state can be stale across modes.
  const avail = recipeAvailability(party, recipe);
  if (!avail.affordable) {
    return {
      ok: false,
      recipe,
      message: `Missing reagents: ${avail.missing.join(", ")}.`,
    };
  }
  for (const [name, qty] of Object.entries(recipe.reagents)) {
    consumeReagent(party, name, qty);
  }
  const roll = 1 + Math.floor(rng() * 20);
  const intMod = statMod(alchemist.intelligence);
  const total = roll + intMod;
  const success = total >= recipe.dc;
  if (success) {
    // Honour the items-catalog stacking contract when we can — most
    // brewable potions are flagged stackable in items.json so a
    // second Healing Potion in the stash should merge into the
    // existing row rather than create a duplicate entry. Without
    // the catalog (legacy test fixtures), fall back to a direct
    // push so behaviour is at least safe.
    for (let i = 0; i < recipe.resultCount; i++) {
      if (items) {
        addToStash(party, recipe.resultItem, items);
      } else {
        party.inventory.push({ item: recipe.resultItem });
      }
    }
    return {
      ok: true,
      success: true,
      roll,
      intMod,
      recipe,
      message:
        `${alchemist.name} brews ${recipe.resultItem} — d20=${roll}` +
        `${intMod >= 0 ? "+" : ""}${intMod} vs DC ${recipe.dc}.`,
    };
  }
  return {
    ok: true,
    success: false,
    roll,
    intMod,
    recipe,
    message:
      `${alchemist.name} fumbles ${recipe.name} — d20=${roll}` +
      `${intMod >= 0 ? "+" : ""}${intMod} vs DC ${recipe.dc}. The reagents are ruined.`,
  };
}
