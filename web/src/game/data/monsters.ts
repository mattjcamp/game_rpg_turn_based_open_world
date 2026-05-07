/**
 * Tiny sample of monsters for the combat demo, lifted from
 * data/monsters.json in the Python project. Field names map directly
 * (hp, ac, attack_bonus, damage_dice/sides/bonus, color).
 *
 * Later slices will read the full monsters.json through a loader; for
 * now we ship four hand-picked entries inline so we have something
 * playable without solving the cross-directory data import yet.
 */

import type { Combatant } from "../types";

interface MonsterSpec {
  name: string;
  hp: number;
  ac: number;
  attackBonus: number;
  damage: { dice: number; sides: number; bonus: number };
  dexMod: number;
  color: [number, number, number];
  sprite: string;
  /** Tiles per turn. Mirrors `move_range` in the Python data files. */
  baseMoveRange: number;
  /** Mirrors monsters.json's `undead` flag — only undead are affected
   *  by Turn Undead and Holy Water. */
  undead?: boolean;
}

const SPECS: Record<string, MonsterSpec> = {
  "Giant Rat": {
    name: "Giant Rat",
    hp: 8,
    ac: 12,
    attackBonus: 2,
    damage: { dice: 1, sides: 4, bonus: 0 },
    dexMod: 2,
    color: [140, 100, 80],
    sprite: "/assets/monsters/giant_rat.png",
    baseMoveRange: 5,
  },
  Goblin: {
    name: "Goblin",
    hp: 6,
    ac: 11,
    attackBonus: 2,
    damage: { dice: 1, sides: 4, bonus: 0 },
    dexMod: 2,
    color: [100, 160, 60],
    sprite: "/assets/monsters/goblin.png",
    baseMoveRange: 4,
  },
  Skeleton: {
    name: "Skeleton",
    hp: 12,
    ac: 13,
    attackBonus: 3,
    damage: { dice: 1, sides: 6, bonus: 1 },
    dexMod: 1,
    color: [220, 220, 200],
    sprite: "/assets/monsters/skeleton.png",
    baseMoveRange: 3,
    undead: true,
  },
  Orc: {
    name: "Orc",
    hp: 18,
    ac: 13,
    attackBonus: 4,
    damage: { dice: 1, sides: 8, bonus: 2 },
    dexMod: 0,
    color: [80, 130, 70],
    sprite: "/assets/monsters/orc.png",
    baseMoveRange: 3,
  },
};

export function makeMonster(name: keyof typeof SPECS, idSuffix = ""): Combatant {
  const spec = SPECS[name];
  return {
    id: `${name.toLowerCase().replace(/\s+/g, "-")}${idSuffix}`,
    name: spec.name,
    side: "enemies",
    maxHp: spec.hp,
    hp: spec.hp,
    ac: spec.ac,
    attackBonus: spec.attackBonus,
    damage: spec.damage,
    dexMod: spec.dexMod,
    color: spec.color,
    sprite: spec.sprite,
    baseMoveRange: spec.baseMoveRange,
    position: { col: 0, row: 0 }, // overwritten by Combat
    undead: spec.undead,
  };
}

/** Build a sample encounter — three monsters appropriate for a level-2 party. */
export function makeSampleEncounter(): Combatant[] {
  return [
    makeMonster("Goblin", "-1"),
    makeMonster("Goblin", "-2"),
    makeMonster("Skeleton"),
  ];
}

/** Sprite paths the monster preloader needs. Includes every monster we ship. */
export const MONSTER_SPRITES: string[] = Object.values(SPECS).map((s) => s.sprite);
