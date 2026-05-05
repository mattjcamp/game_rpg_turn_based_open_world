/**
 * Shared types for the combat layer. Mirrors the relevant subset of the
 * Python Monster / Fighter classes — only the fields combat actually
 * needs. Other gameplay state (terrain, spells, on-hit effects, etc.)
 * will be added as later slices port more behaviour.
 */

export type Side = "party" | "enemies";

export interface DamageRoll {
  dice: number;
  sides: number;
  bonus: number;
}

export interface Combatant {
  /** Stable id for matching across UI and engine state. */
  id: string;
  name: string;
  side: Side;
  maxHp: number;
  hp: number;
  ac: number;
  attackBonus: number;
  damage: DamageRoll;
  /** D&D ability modifier for DEX, used for initiative. */
  dexMod: number;
  /** Visual hint for the placeholder portrait colour (RGB 0-255). */
  color: [number, number, number];
}

/**
 * Result of a single attack action — what the engine returns to the
 * scene so it can animate hit/miss/crit feedback.
 */
export interface AttackResult {
  attackerId: string;
  targetId: string;
  hit: boolean;
  /** Raw d20 roll, before modifiers. */
  roll: number;
  /** d20 + attackBonus. */
  total: number;
  critical: boolean;
  /** Damage dealt; 0 on miss. */
  damage: number;
  /** Was the target reduced to 0 HP by this attack? */
  killed: boolean;
}

export interface InitiativeRoll {
  combatantId: string;
  total: number;
  raw: number;
}
