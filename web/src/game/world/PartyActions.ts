/**
 * Pure logic for the Party screen's action handlers.
 *
 * Each helper takes the live Party state (mutates in place — that's
 * the simplest contract for a single-player save), and returns a
 * `{ ok, message }` pair so the scene can show a feedback line.
 *
 * Keeping these out of the scene class means we can unit-test them
 * without spinning up Phaser, and reuse them from anywhere a non-UI
 * caller wants the same effect (e.g., a future save/load layer).
 */

import type { Party, PartyMember, EquipmentSlots, InventoryItem } from "./Party";
import type { Effect } from "./Effects";
import { canEquip } from "./Effects";
import type { Spell } from "./Spells";
import { castersFor } from "./Spells";
import type { Item, EquipSlot } from "./Items";

// ── Slot name bridge ───────────────────────────────────────────────
// items.json uses snake_case ("right_hand"); EquipmentSlots uses
// camelCase ("rightHand"). Centralise the mapping here so callers
// don't have to think about it.

const SLOT_TO_FIELD: Record<EquipSlot, keyof EquipmentSlots> = {
  right_hand: "rightHand",
  left_hand:  "leftHand",
  body:       "body",
  head:       "head",
};

const SLOT_LABEL: Record<EquipSlot, string> = {
  right_hand: "weapon",
  left_hand:  "offhand",
  body:       "body armor",
  head:       "helmet",
};

/** Read the item name in a slot (camelCase field). */
function readSlot(member: PartyMember, slot: EquipSlot): string | null {
  return member.equipped[SLOT_TO_FIELD[slot]];
}

/** Write the slot in a way the EquipmentSlots type accepts. */
function writeSlot(member: PartyMember, slot: EquipSlot, value: string | null): void {
  member.equipped[SLOT_TO_FIELD[slot]] = value;
}

export interface ActionResult {
  ok: boolean;
  message: string;
}

// ── Party composition helpers ──────────────────────────────────────
// Used to gate the conditional ability rows (BREW / PICKPOCKET /
// TINKER) on the Party Inventory screen.

/** True iff at least one alive member belongs to the given class. */
export function hasClass(members: PartyMember[], klass: string): boolean {
  const k = klass.toLowerCase();
  return members.some((m) => m.hp > 0 && m.class.toLowerCase() === k);
}

/** True iff at least one alive member belongs to the given race. */
export function hasRace(members: PartyMember[], race: string): boolean {
  const r = race.toLowerCase();
  return members.some((m) => m.hp > 0 && m.race.toLowerCase() === r);
}

/** Find the first alive member matching a class (case-insensitive). */
export function findClass(
  members: PartyMember[], klass: string,
): PartyMember | null {
  const k = klass.toLowerCase();
  return members.find((m) => m.hp > 0 && m.class.toLowerCase() === k) ?? null;
}

/** Find the first alive member matching a race (case-insensitive). */
export function findRace(
  members: PartyMember[], race: string,
): PartyMember | null {
  const r = race.toLowerCase();
  return members.find((m) => m.hp > 0 && m.race.toLowerCase() === r) ?? null;
}

// ── Active-effect predicates / lighting boosts ─────────────────────

/** True when the party currently has the named effect equipped. */
export function partyHasEffect(party: Party, effectId: string): boolean {
  for (const v of Object.values(party.partyEffects)) {
    if (v === effectId) return true;
  }
  return false;
}

/**
 * The party's effective light radius (in tiles) for the lighting
 * overlay. Mirrors the Python game's "party has light" predicate
 * (`interior_lighting.party_has_light`) — Infravision and
 * Galadriel's Light each act as a light source carried by the
 * party. Returns the larger of the boost and the supplied default.
 *
 * Numbers picked to roughly match the look of the pygame version:
 *   - Infravision: 8 tiles (effectively floods a small interior)
 *   - Galadriel's Light: 5 tiles (warm, more local pool)
 *   - default: whatever the caller passed in
 */
export function partyLightRadius(party: Party, defaultRadius: number): number {
  if (partyHasEffect(party, "infravision")) return Math.max(defaultRadius, 8);
  if (partyHasEffect(party, "galadriels_light")) return Math.max(defaultRadius, 5);
  return defaultRadius;
}

/**
 * Post-processing tint for the party light. Mirrors the pygame
 * tints: Infravision shifts the visible area to red ("infrared"),
 * Galadriel's Light to a cool, washed-out blue ("moonlight").
 *
 * Returns the colour and an alpha scaling factor — callers multiply
 * the scale by the per-cell brightness so the tint fades with the
 * party light's range. Returns null when no tinting effect is
 * equipped.
 */
export interface PartyTint {
  color: number;
  alphaScale: number;
}
export function partyLightTint(party: Party): PartyTint | null {
  // Infravision wins when both are equipped — same precedence the
  // Python renderer uses (`if has_infravision and not has_equipped_light`).
  if (partyHasEffect(party, "infravision")) {
    return { color: 0xc02020, alphaScale: 0.55 };
  }
  if (partyHasEffect(party, "galadriels_light")) {
    return { color: 0x9bb6e0, alphaScale: 0.45 };
  }
  return null;
}

// ── Effects ────────────────────────────────────────────────────────

/**
 * Assign an effect into the first empty `effect_N` slot of the party.
 *
 * Fails if the party can't equip it (requirements unmet) or if every
 * slot is already filled.
 */
export function assignEffectToParty(
  party: Party,
  effect: Effect,
  members: PartyMember[],
): ActionResult {
  if (!canEquip(effect, members)) {
    return { ok: false, message: `Cannot assign ${effect.name} — requirements not met.` };
  }
  // Already equipped? Treat as success no-op.
  for (const v of Object.values(party.partyEffects)) {
    if (v === effect.id) {
      return { ok: true, message: `${effect.name} is already active.` };
    }
  }
  // First null slot wins.
  const slots = Object.keys(party.partyEffects).sort();
  for (const slot of slots) {
    if (party.partyEffects[slot] == null) {
      party.partyEffects[slot] = effect.id;
      return { ok: true, message: `${effect.name} active.` };
    }
  }
  return { ok: false, message: "All four effect slots are full." };
}

/**
 * Remove an effect from whatever slot holds it. No-op success when
 * the effect isn't currently equipped.
 */
export function removeEffectFromParty(
  party: Party,
  effect: Effect,
): ActionResult {
  for (const slot of Object.keys(party.partyEffects)) {
    if (party.partyEffects[slot] === effect.id) {
      party.partyEffects[slot] = null;
      return { ok: true, message: `${effect.name} dispelled.` };
    }
  }
  return { ok: true, message: `${effect.name} was not active.` };
}

// ── Stash ↔ personal inventory ─────────────────────────────────────

/**
 * Move one item from the shared stash into a member's personal
 * inventory. The stash is indexed because items can repeat — by
 * index we always remove the right one without needing unique ids.
 */
export function giveStashItemTo(
  party: Party,
  stashIndex: number,
  memberIndex: number,
): ActionResult {
  if (stashIndex < 0 || stashIndex >= party.inventory.length) {
    return { ok: false, message: "Item not found in stash." };
  }
  const member = party.roster[party.activeParty[memberIndex] ?? -1];
  if (!member) return { ok: false, message: "No active member in that slot." };
  const item = party.inventory[stashIndex];
  party.inventory.splice(stashIndex, 1);
  member.inventory.push(item);
  return { ok: true, message: `Gave ${item.item} to ${member.name}.` };
}

/**
 * Move an item from a member's personal inventory back into the
 * shared stash. Inverse of giveStashItemTo — handy for the future
 * "Return to Stash" action menu the Python game has.
 */
export function returnItemToStash(
  party: Party,
  memberIndex: number,
  itemIndex: number,
): ActionResult {
  const member = party.roster[party.activeParty[memberIndex] ?? -1];
  if (!member) return { ok: false, message: "No active member in that slot." };
  if (itemIndex < 0 || itemIndex >= member.inventory.length) {
    return { ok: false, message: "Item not found." };
  }
  const item = member.inventory[itemIndex];
  member.inventory.splice(itemIndex, 1);
  party.inventory.push(item);
  return { ok: true, message: `${item.item} returned to stash.` };
}

// ── Durability ─────────────────────────────────────────────────────
//
// Mirrors the Python game's per-slot durability tracker
// (`equipped_durability`) plus the per-inventory-entry durability
// field. Items in items.json carry a `durability` value that's the
// MAX uses; `0` (or missing) means indestructible. When an item is
// equipped, the slot tracker holds the *current* value; when it's
// unequipped or swapped, that value rides along with the item back
// into the inventory entry so wear travels with the object.

/**
 * Look up an item's max durability from the catalog. Returns `null`
 * when the item is indestructible (no durability set, or 0) or when
 * the catalog doesn't recognise the item.
 */
export function getItemMaxDurability(
  itemName: string,
  items: Map<string, Item>,
): number | null {
  const def = items.get(itemName);
  if (!def) return null;
  const dur = def.durability ?? 0;
  return dur > 0 ? dur : null;
}

/** True if the catalog flags the item as indestructible. */
export function isIndestructible(
  itemName: string,
  items: Map<string, Item>,
): boolean {
  return getItemMaxDurability(itemName, items) == null;
}

/**
 * Outcome of decrementing the wear on a slot's equipped item.
 *   - `kind: "ok"` — durability ticked down; item is still usable.
 *   - `kind: "broke"` — durability hit zero; the slot has been cleared
 *     and the item is destroyed (no inventory return).
 *   - `kind: "indestructible"` — nothing to do.
 *   - `kind: "empty"` — slot is empty / item not in catalog.
 */
export type DurabilityResult =
  | { kind: "ok"; current: number; max: number }
  | { kind: "broke"; itemName: string }
  | { kind: "indestructible" }
  | { kind: "empty" };

/**
 * Decrement durability for the item in `slot` by one. Initialises the
 * tracker to max on first use (the Python game does the same lazy
 * seed). When durability reaches zero the slot is cleared and the
 * item is removed from play.
 */
export function useEquippedDurability(
  member: PartyMember,
  slot: EquipSlot,
  items: Map<string, Item>,
): DurabilityResult {
  const itemName = readSlot(member, slot);
  if (!itemName) return { kind: "empty" };
  const max = getItemMaxDurability(itemName, items);
  if (max == null) return { kind: "indestructible" };
  let current = member.equippedDurability[slot];
  if (current == null) current = max;
  if (current > max) current = max;     // editor-changed-max guard
  current -= 1;
  if (current <= 0) {
    // Snap the slot — the item shatters out of existence.
    writeSlot(member, slot, null);
    member.equippedDurability[slot] = null;
    return { kind: "broke", itemName };
  }
  member.equippedDurability[slot] = current;
  return { kind: "ok", current, max };
}

/**
 * Read the current/max durability pair for an equipped slot. Returns
 * `null` for indestructible items, empty slots, or unknown items.
 * Used by the inspect/examine popup to render the progress bar.
 */
export function getSlotDurability(
  member: PartyMember,
  slot: EquipSlot,
  items: Map<string, Item>,
): { current: number; max: number } | null {
  const itemName = readSlot(member, slot);
  if (!itemName) return null;
  const max = getItemMaxDurability(itemName, items);
  if (max == null) return null;
  let current = member.equippedDurability[slot];
  if (current == null) current = max;
  if (current > max) current = max;
  return { current, max };
}

/**
 * Move an inventory entry's wear into the slot tracker on equip.
 * Indestructible items get `null`; destructible items use the entry's
 * stored value (or seed to max when this is the first use).
 */
function seedSlotFromEntry(
  member: PartyMember,
  slot: EquipSlot,
  itemName: string,
  itemDur: number | undefined,
  items: Map<string, Item>,
): void {
  const max = getItemMaxDurability(itemName, items);
  if (max == null) {
    member.equippedDurability[slot] = null;
    return;
  }
  if (typeof itemDur === "number") {
    member.equippedDurability[slot] = Math.max(0, Math.min(max, itemDur));
  } else {
    member.equippedDurability[slot] = max;
  }
}

/**
 * Build an InventoryItem entry for an item being unequipped (or
 * displaced by a swap), copying the slot's current durability across
 * so wear isn't lost.
 */
function entryForSlot(
  member: PartyMember,
  slot: EquipSlot,
  itemName: string,
  items: Map<string, Item>,
): InventoryItem {
  const max = getItemMaxDurability(itemName, items);
  if (max == null) return { item: itemName };
  const cur = member.equippedDurability[slot];
  if (cur == null) return { item: itemName };
  return { item: itemName, durability: cur };
}

// ── Equip / unequip ────────────────────────────────────────────────

/**
 * Equip an item from the member's personal inventory.
 *
 * Logic:
 *   - The Items table tells us which slots accept the item, in
 *     priority order (weapons usually list right_hand, then
 *     left_hand). Pick the first empty matching slot. If every
 *     accepting slot is full, swap with the first one — its current
 *     occupant goes back into personal inventory.
 *   - Items the catalog flags as `character_can_equip: false`
 *     (consumables, keys, herbs) refuse with a polite message so the
 *     UI can still show feedback.
 *   - Items not in the catalog get a no-slot default — also refused
 *     so we don't accidentally treat unknown items as gear.
 */
export function equipItemFromInventory(
  member: PartyMember,
  itemIndex: number,
  items: Map<string, Item>,
): ActionResult {
  if (itemIndex < 0 || itemIndex >= member.inventory.length) {
    return { ok: false, message: "Item not found in personal inventory." };
  }
  const inv = member.inventory[itemIndex];
  const def = items.get(inv.item);
  if (!def) {
    return { ok: false, message: `Don't know how to equip ${inv.item}.` };
  }
  if (!def.characterCanEquip || def.slots.length === 0) {
    return { ok: false, message: `${inv.item} cannot be equipped.` };
  }

  // First empty matching slot wins.
  let chosen: EquipSlot | null = null;
  for (const s of def.slots) {
    if (readSlot(member, s) == null) { chosen = s; break; }
  }

  if (chosen == null) {
    // All matching slots full — swap with the FIRST listed slot.
    chosen = def.slots[0];
    const previous = readSlot(member, chosen)!;
    // Move displaced item back into inventory at the same index so
    // the player's view stays stable. Carry its current durability
    // across so the swapped-out item doesn't reset to full wear.
    const displaced = entryForSlot(member, chosen, previous, items);
    member.inventory[itemIndex] = displaced;
    writeSlot(member, chosen, inv.item);
    seedSlotFromEntry(member, chosen, inv.item, inv.durability, items);
    return {
      ok: true,
      message: `${member.name} equips ${inv.item} (replaces ${previous}).`,
    };
  }

  // Empty slot — just move the item.
  member.inventory.splice(itemIndex, 1);
  writeSlot(member, chosen, inv.item);
  seedSlotFromEntry(member, chosen, inv.item, inv.durability, items);
  return {
    ok: true,
    message: `${member.name} equips ${inv.item} as ${SLOT_LABEL[chosen]}.`,
  };
}

/**
 * Equip an item into an explicitly-chosen slot.
 *
 * Used when an item can land in multiple slots (a dagger in either
 * hand, a versatile weapon vs. an offhand) and the player has picked
 * which one they want. The slot must be one of the item catalog's
 * accepting slots — otherwise we refuse so the UI can't sneak an
 * invalid pairing past us (e.g. equipping body armor in head).
 *
 * Behaviour matches `equipItemFromInventory` for the swap case: if
 * the chosen slot is occupied, the displaced item slides into the
 * inventory at the same index so the player's view stays stable.
 */
export function equipItemIntoSlot(
  member: PartyMember,
  itemIndex: number,
  slot: EquipSlot,
  items: Map<string, Item>,
): ActionResult {
  if (itemIndex < 0 || itemIndex >= member.inventory.length) {
    return { ok: false, message: "Item not found in personal inventory." };
  }
  const inv = member.inventory[itemIndex];
  const def = items.get(inv.item);
  if (!def) {
    return { ok: false, message: `Don't know how to equip ${inv.item}.` };
  }
  if (!def.characterCanEquip || def.slots.length === 0) {
    return { ok: false, message: `${inv.item} cannot be equipped.` };
  }
  if (!def.slots.includes(slot)) {
    return {
      ok: false,
      message: `${inv.item} cannot be equipped as ${SLOT_LABEL[slot]}.`,
    };
  }
  const previous = readSlot(member, slot);
  if (previous == null) {
    member.inventory.splice(itemIndex, 1);
    writeSlot(member, slot, inv.item);
    seedSlotFromEntry(member, slot, inv.item, inv.durability, items);
    return {
      ok: true,
      message: `${member.name} equips ${inv.item} as ${SLOT_LABEL[slot]}.`,
    };
  }
  // Swap with the existing occupant. The displaced item carries its
  // current durability into the inventory entry; the new item picks
  // up whatever wear was stored on its inventory entry.
  const displaced = entryForSlot(member, slot, previous, items);
  member.inventory[itemIndex] = displaced;
  writeSlot(member, slot, inv.item);
  seedSlotFromEntry(member, slot, inv.item, inv.durability, items);
  return {
    ok: true,
    message: `${member.name} equips ${inv.item} (replaces ${previous}).`,
  };
}

/**
 * Unequip whatever sits in a slot — the item drops into the member's
 * personal inventory. No-op success when the slot is already empty.
 *
 * `items` is optional so legacy callers keep working, but passing it
 * is strongly recommended: with the catalog we can move the slot's
 * current durability onto the new InventoryItem entry, preserving wear
 * across the unequip → equip cycle just like the Python game.
 */
export function unequipSlot(
  member: PartyMember,
  slot: EquipSlot,
  items?: Map<string, Item>,
): ActionResult {
  const current = readSlot(member, slot);
  if (current == null) {
    return { ok: true, message: `${SLOT_LABEL[slot][0].toUpperCase() + SLOT_LABEL[slot].slice(1)} slot is already empty.` };
  }
  const entry: InventoryItem = items
    ? entryForSlot(member, slot, current, items)
    : { item: current };
  writeSlot(member, slot, null);
  member.equippedDurability[slot] = null;
  member.inventory.push(entry);
  return {
    ok: true,
    message: `${member.name} unequips ${current}.`,
  };
}

// ── Race / class abilities (BREW / PICKPOCKET / TINKER) ────────────
//
// These three rows live between CAST SPELL and SHARED STASH on the
// Party Inventory screen, conditional on the right party member
// being present:
//   BREW POTIONS — when an Alchemist is in the party (class).
//   PICKPOCKET   — when a Halfling is in the party (race).
//   TINKER       — when a Gnome is in the party (race).
//
// V1 implementation: each press picks a random item from a small
// table and adds it to the shared stash. Once-per-day gating, the
// in-town adjacent-NPC requirement for pickpocket, and the bigger
// dice/skill-check workflow can layer on later — these stubs just
// surface the actions and prove the gating works.

/**
 * Pick one element from a weight × value list. `[weight, value][]`.
 */
function pickWeighted<T>(
  table: ReadonlyArray<readonly [number, T]>,
  rng: () => number = Math.random,
): T {
  const total = table.reduce((s, [w]) => s + w, 0);
  let roll = rng() * total;
  for (const [w, v] of table) {
    roll -= w;
    if (roll <= 0) return v;
  }
  return table[table.length - 1][1];
}

/** Mirror of `_PICKPOCKET_LOOT` in the Python inventory_mixin. */
const PICKPOCKET_LOOT: ReadonlyArray<readonly [number, string]> = [
  [25, "Gold"],            // special-cased below — adds gold instead of an item
  [20, "Healing Herb"],
  [12, "Torch"],
  [10, "Arrows"],
  [10, "Antidote"],
  [8,  "Lockpick"],
  [5,  "Dagger"],
  [4,  "Mana Potion"],
  [3,  "Stones"],
  [2,  "Smoke Bomb"],
  [1,  "Holy Water"],
];

/**
 * A Halfling tries to pickpocket. Picks a random reward from the
 * loot table, adding either gold or an item to the shared stash.
 * Returns a feedback line.
 *
 * The Python game gates this on an adjacent NPC + a DEX skill check;
 * we elide both for the menu-cast version (the screen has no notion
 * of which NPC is adjacent today). A later slice can wire in the
 * scene-context to do the proper check.
 */
export function pickpocket(
  party: Party,
  members: PartyMember[],
  rng: () => number = Math.random,
): ActionResult {
  const halfling = findRace(members, "Halfling");
  if (!halfling) {
    return { ok: false, message: "No Halfling in the party." };
  }
  const reward = pickWeighted(PICKPOCKET_LOOT, rng);
  if (reward === "Gold") {
    const amount = 3 + Math.floor(rng() * 13); // 3–15 inclusive
    party.gold += amount;
    return { ok: true, message: `${halfling.name} pilfers ${amount} gold.` };
  }
  party.inventory.push({ item: reward });
  return { ok: true, message: `${halfling.name} swipes a ${reward}.` };
}

/** Small set of recipes an Alchemist can brew on the fly. */
const BREW_RECIPES: ReadonlyArray<readonly [number, string]> = [
  [40, "Healing Potion"],
  [25, "Mana Potion"],
  [15, "Antidote"],
  [10, "Elixir of Strength"],
  [10, "Elixir of Warding"],
];

/**
 * An Alchemist brews a random potion. Drops it in the shared stash.
 */
export function brewPotion(
  party: Party,
  members: PartyMember[],
  rng: () => number = Math.random,
): ActionResult {
  const alchemist = findClass(members, "Alchemist");
  if (!alchemist) {
    return { ok: false, message: "No Alchemist in the party." };
  }
  const item = pickWeighted(BREW_RECIPES, rng);
  party.inventory.push({ item });
  return { ok: true, message: `${alchemist.name} brews a ${item}.` };
}

/** Items a Gnome can tinker together. */
const TINKER_RECIPES: ReadonlyArray<readonly [number, string]> = [
  [30, "Lockpick"],
  [25, "Torch"],
  [20, "Arrows"],
  [15, "Bolts"],
  [10, "Camping Supplies"],
];

/** A Gnome tinkers a random utility item into existence. */
export function tinker(
  party: Party,
  members: PartyMember[],
  rng: () => number = Math.random,
): ActionResult {
  const gnome = findRace(members, "Gnome");
  if (!gnome) {
    return { ok: false, message: "No Gnome in the party." };
  }
  const item = pickWeighted(TINKER_RECIPES, rng);
  party.inventory.push({ item });
  return { ok: true, message: `${gnome.name} tinkers up a ${item}.` };
}

// ── Spell casting (menu / out-of-combat) ───────────────────────────

/**
 * Roll an XdY dice expression. Pure — accepts an injected RNG so
 * tests can pin down outcomes.
 */
export function rollDice(
  count: number, sides: number, rng: () => number = Math.random,
): number {
  let total = 0;
  for (let i = 0; i < Math.max(0, count); i++) {
    total += 1 + Math.floor(rng() * Math.max(1, sides));
  }
  return total;
}

/** Statistical D&D-style modifier from a stat (10 = +0, 18 = +4). */
export function statMod(stat: number): number {
  return Math.floor((stat - 10) / 2);
}

/**
 * The amount a heal spell heals on the target. Honours either the
 * `dice` string in `effect_value` or a static `hp_amount`. Falls
 * back to a sensible default when the data omits both.
 */
export function rollHeal(
  spell: Spell, caster: PartyMember, rng: () => number = Math.random,
): number {
  const ev = spell.effect_value ?? {};
  if (typeof ev.hp_amount === "number") return ev.hp_amount;
  let dice = 0;
  if (typeof ev.dice_count === "number" && typeof ev.dice_sides === "number") {
    dice = rollDice(ev.dice_count, ev.dice_sides, rng);
  } else if (typeof ev.dice === "string") {
    const m = /^(\d+)d(\d+)$/.exec(ev.dice);
    if (m) dice = rollDice(parseInt(m[1], 10), parseInt(m[2], 10), rng);
  } else {
    // Sensible defaults when the source data omits a roll: 1d8 for
    // heal, 2d8 for major_heal, 3d8 for mass_heal-per-target.
    const defaults: Record<string, [number, number]> = {
      heal:        [1, 8],
      major_heal:  [2, 8],
      mass_heal:   [1, 6],
    };
    const def = defaults[spell.effect_type];
    if (def) dice = rollDice(def[0], def[1], rng);
  }
  // WIS adds to clerical heals.
  const bonus = ev.stat_bonus === "wisdom" ? statMod(caster.wisdom) : 0;
  return Math.max(1, dice + bonus);
}

/**
 * Cast a single-target heal. Picks the best caster automatically
 * (highest level among those with enough MP). Returns the message
 * that should bubble up to the player.
 */
export function castHealOnTarget(
  party: Party,
  members: PartyMember[],
  spell: Spell,
  targetIndex: number,
  rng: () => number = Math.random,
): ActionResult {
  const target = members[targetIndex];
  if (!target) return { ok: false, message: "No such target." };
  if (target.hp <= 0) {
    return { ok: false, message: `${target.name} is dead and cannot be healed.` };
  }
  const possible = castersFor(spell, members);
  if (possible.length === 0) {
    return { ok: false, message: "No one in the party can cast that spell." };
  }
  // Prefer the highest-level caster; tie-break by who has the most MP.
  possible.sort(
    (a, b) => b.level - a.level || (b.mp ?? 0) - (a.mp ?? 0)
  );
  const caster = possible[0];
  caster.mp = (caster.mp ?? 0) - spell.mp_cost;
  const before = target.hp;
  const amount = rollHeal(spell, caster, rng);
  target.hp = Math.min(target.maxHp, target.hp + amount);
  const healed = target.hp - before;
  void party;
  return {
    ok: true,
    message: `${caster.name} casts ${spell.name} on ${target.name} — heals ${healed} HP.`,
  };
}

/**
 * Cast a mass heal — one party member spends MP, every alive ally
 * is healed. Returns a single summary message.
 */
export function castMassHeal(
  party: Party,
  members: PartyMember[],
  spell: Spell,
  rng: () => number = Math.random,
): ActionResult {
  const possible = castersFor(spell, members);
  if (possible.length === 0) {
    return { ok: false, message: "No one in the party can cast that spell." };
  }
  possible.sort(
    (a, b) => b.level - a.level || (b.mp ?? 0) - (a.mp ?? 0)
  );
  const caster = possible[0];
  caster.mp = (caster.mp ?? 0) - spell.mp_cost;
  let total = 0;
  for (const m of members) {
    if (m.hp <= 0) continue;
    const before = m.hp;
    const amount = rollHeal(spell, caster, rng);
    m.hp = Math.min(m.maxHp, m.hp + amount);
    total += m.hp - before;
  }
  void party;
  return {
    ok: true,
    message: `${caster.name} casts ${spell.name} — party heals ${total} HP total.`,
  };
}

/**
 * Targeting kind for menu-cast spells. UI uses this to know whether
 * to prompt for a target via 1-4 or to cast immediately.
 */
export type MenuCastKind = "self" | "single-ally" | "mass" | "unsupported";

/**
 * Classify a spell for the Party-screen cast flow. Based on its
 * `effect_type` and `targeting`. Anything we haven't wired returns
 * "unsupported" so the UI can show a polite "no effect here" line.
 */
export function classifyMenuCast(spell: Spell): MenuCastKind {
  if (spell.effect_type === "mass_heal") return "mass";
  if (spell.effect_type === "heal" || spell.effect_type === "major_heal") {
    return "single-ally";
  }
  // Other utility spells (knock, magic_light, etc.) need world-state
  // hooks (unlock door, light tile) we haven't built yet.
  return "unsupported";
}
