/**
 * Status-effect / buff state for combat.
 *
 * Mirrors the Python game's `bless_buffs` / `curse_buffs` /
 * `range_buffs` dicts at a slightly higher level: a single per-
 * combatant list of {kind, value, turnsLeft, source}. The combat
 * engine sums matching kinds at attack time and ticks every entry
 * down at the end of each round, expiring with a log line.
 *
 * Mechanical kinds shipped today:
 *   - attack_bonus   — added to the d20 hit roll (Bless +2)
 *   - ac_bonus       — added to the combatant's AC (Shield +1)
 *   - attack_penalty — subtracted from the d20 hit roll (Curse -2)
 *   - ac_penalty     — subtracted from the combatant's AC (Curse -2)
 *   - range_bonus    — added to baseMoveRange (Long Shanks +4)
 *
 * The full Python game also has skip_turn (Sleep) and side-flip
 * (Charm) status effects; they need turn-loop changes that are
 * separate from the numerical buffs covered here.
 */

export type BuffKind =
  | "attack_bonus"
  | "ac_bonus"
  | "attack_penalty"
  | "ac_penalty"
  | "range_bonus";

export interface Buff {
  kind: BuffKind;
  value: number;
  /** Decrements each round; the buff expires when this hits 0. */
  turnsLeft: number;
  /** Spell name — e.g. "Bless" — used for "X's blessing fades." log. */
  source: string;
}

/** Sum every buff of `kind` on a combatant's list. */
export function sumBuff(buffs: Buff[] | undefined, kind: BuffKind): number {
  if (!buffs) return 0;
  let total = 0;
  for (const b of buffs) {
    if (b.kind === kind) total += b.value;
  }
  return total;
}

/**
 * Decrement turnsLeft on every buff in `buffs`. Returns the buffs
 * that expired this tick (caller logs them). Mutates the list in
 * place — expired entries are removed.
 */
export function tickBuffs(buffs: Buff[]): Buff[] {
  const expired: Buff[] = [];
  for (let i = buffs.length - 1; i >= 0; i--) {
    const b = buffs[i];
    b.turnsLeft -= 1;
    if (b.turnsLeft <= 0) {
      expired.push(b);
      buffs.splice(i, 1);
    }
  }
  return expired;
}

/** Per-source flavour line for the round-end expire log. */
export function describeExpire(name: string, source: string): string {
  const tag = source.toLowerCase();
  if (tag === "bless")        return `${name}'s blessing fades.`;
  if (tag === "curse")        return `${name}'s curse lifts.`;
  if (tag === "shield")       return `${name}'s magical shield fades.`;
  if (tag === "long shanks")  return `${name}'s hastened legs slow.`;
  return `${name}'s ${source} ends.`;
}
