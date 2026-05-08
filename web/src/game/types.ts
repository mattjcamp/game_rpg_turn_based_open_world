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
  /** Full ability scores carried over from the PartyMember (or
   *  monster spec). Optional because legacy fixtures and some of the
   *  combat tests omit them — combat helpers default each to 10
   *  (modifier +0) when they're missing. Used by spell-damage code so
   *  Magic Arrow can read the caster's INT and Heal can read WIS. */
  strength?: number;
  dexterity?: number;
  constitution?: number;
  intelligence?: number;
  wisdom?: number;
  /** Fallback portrait colour (RGB 0-255) if no sprite is loaded. */
  color: [number, number, number];
  /**
   * Optional path to a 32×32 sprite under `/assets/`. When present the
   * combat scene draws the image; when absent it falls back to the
   * coloured rectangle. Test fixtures omit this freely.
   */
  sprite?: string;
  /**
   * Tile movement budget per turn. Refreshed at the start of every turn
   * by the Combat controller. For party members this comes from the
   * class template's `range`; for monsters from `move_range`.
   */
  baseMoveRange: number;
  /**
   * Position on the arena grid. Initial value is irrelevant — the
   * Combat constructor lays out party and enemies into starting
   * formations and overwrites whatever the caller passed.
   */
  position: { col: number; row: number };
  /**
   * True for undead monsters (skeletons, zombies, liches, …). Mirrors
   * the `undead` flag in monsters.json. Read by Turn Undead so the
   * spell only affects creatures it's supposed to.
   */
  undead?: boolean;
  /** XP awarded to each surviving party member when this enemy dies.
   *  Summed across all defeated enemies on victory and shared with
   *  every alive party member (matches the Python game). */
  xpReward?: number;
  /** Gold this enemy drops on death. Rolled once at spawn so it stays
   *  stable for the encounter; summed across kills on victory. */
  goldReward?: number;
  /**
   * When true, the Combat controller / scene drive this actor through
   * the monster-AI loop instead of the player input UI. Defaults to
   * false for party members and true for enemies. Summoned allies
   * (Animate Dead) live on `side: "party"` but with this flag set so
   * they fight on their own without the player picking actions.
   */
  aiControlled?: boolean;
  /**
   * Multi-tile sprite scale (default 1). Read by CombatScene so a
   * Dragon (`battle_scale: 2`) renders at 2× the normal tile size on
   * the arena grid.
   */
  battleScale?: number;
  /** Spell-casting AI table (Dragon's Fire Breath, Lich's Fireball,
   *  Troll's Self Heal, …). Forwarded from `MonsterSpec` so the AI
   *  loop can roll cast_chance without re-looking-up the catalog. */
  monsterSpells?: import("./data/monsters").MonsterSpell[];
  /** Always-on effects applied each round in `Combat.endTurn` —
   *  regen, fire_resistance, poison_immunity. */
  passives?: import("./data/monsters").MonsterPassive[];
  /** Effects rolled on a successful melee hit — drain HP from victim,
   *  Man Eater "consume" debuff, …. */
  onHitEffects?: import("./data/monsters").MonsterOnHit[];
  /** Bonus tiles after a successful attack — Dragons hit-and-run with
   *  `post_attack_move: 2`. Default 0. */
  postAttackMove?: number;
  /** True for humanoid monsters (Orcs, Goblins, Trolls, Dark Mages…).
   *  Charm-style spells filter on this. */
  humanoid?: boolean;
  /**
   * Active swallow-whole debuff. Set by Man Eater's "consume" on-hit
   * effect when its STR save fails. While set:
   *
   *   - The combatant's `position` is `{-1,-1}` (off the board); the
   *     scene hides their sprite and HP bar.
   *   - On their turn, `Combat.runConsumedAutoTurn()` rolls the STR
   *     save again — pass spits them back out near the consumer, fail
   *     deals `damagePerTurn` damage.
   *   - If the consumer dies, their next turn auto-releases.
   */
  consumed?: {
    damagePerTurn: number;
    saveDc: number;
    consumerId: string;
    originalPosition: { col: number; row: number };
  };
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
