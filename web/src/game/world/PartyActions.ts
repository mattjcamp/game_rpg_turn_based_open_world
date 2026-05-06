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

import type { Party, PartyMember, EquipmentSlots } from "./Party";
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
    // the player's view stays stable.
    member.inventory[itemIndex] = { item: previous };
    writeSlot(member, chosen, inv.item);
    return {
      ok: true,
      message: `${member.name} equips ${inv.item} (replaces ${previous}).`,
    };
  }

  // Empty slot — just move the item.
  member.inventory.splice(itemIndex, 1);
  writeSlot(member, chosen, inv.item);
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
    return {
      ok: true,
      message: `${member.name} equips ${inv.item} as ${SLOT_LABEL[slot]}.`,
    };
  }
  // Swap with the existing occupant.
  member.inventory[itemIndex] = { item: previous };
  writeSlot(member, slot, inv.item);
  return {
    ok: true,
    message: `${member.name} equips ${inv.item} (replaces ${previous}).`,
  };
}

/**
 * Unequip whatever sits in a slot — the item drops into the member's
 * personal inventory. No-op success when the slot is already empty.
 */
export function unequipSlot(
  member: PartyMember,
  slot: EquipSlot,
): ActionResult {
  const current = readSlot(member, slot);
  if (current == null) {
    return { ok: true, message: `${SLOT_LABEL[slot][0].toUpperCase() + SLOT_LABEL[slot].slice(1)} slot is already empty.` };
  }
  writeSlot(member, slot, null);
  member.inventory.push({ item: current });
  return {
    ok: true,
    message: `${member.name} unequips ${current}.`,
  };
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
