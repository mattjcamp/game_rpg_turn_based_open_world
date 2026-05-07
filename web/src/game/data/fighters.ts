/**
 * Sample party for the combat demo. Stats picked to feel like a level-2
 * D&D-ish party: fighter and barbarian heavy, ranger middling AC, mage low.
 *
 * Later slices will load these from data/party.json (or from save files);
 * for the first slice we keep them inline so the scene starts instantly.
 */

import type { Combatant } from "../types";
import { assetUrl } from "../world/Module";

/** Sprite paths the party-related preloader needs. */
export const PARTY_SPRITES: string[] = [
  assetUrl("/assets/characters/fighter.png"),
  assetUrl("/assets/characters/barbarian.png"),
  assetUrl("/assets/characters/ranger.png"),
  assetUrl("/assets/characters/wizard.png"),
];

export function makeSampleParty(): Combatant[] {
  return [
    {
      id: "kael",
      name: "Kael",
      side: "party",
      maxHp: 22,
      hp: 22,
      ac: 16,
      attackBonus: 5,
      damage: { dice: 1, sides: 8, bonus: 3 }, // longsword + STR
      dexMod: 1,
      color: [180, 60, 60], // ember red
      sprite: assetUrl("/assets/characters/fighter.png"),
      baseMoveRange: 4,
      position: { col: 0, row: 0 }, // overwritten by Combat
    },
    {
      id: "thora",
      name: "Thora",
      side: "party",
      maxHp: 26,
      hp: 26,
      ac: 14,
      attackBonus: 6,
      damage: { dice: 1, sides: 12, bonus: 4 }, // greataxe + STR
      dexMod: 0,
      color: [200, 130, 60], // amber
      sprite: assetUrl("/assets/characters/barbarian.png"),
      baseMoveRange: 3,
      position: { col: 0, row: 0 },
    },
    {
      id: "syl",
      name: "Syl",
      side: "party",
      maxHp: 18,
      hp: 18,
      ac: 14,
      attackBonus: 5,
      damage: { dice: 1, sides: 8, bonus: 3 }, // longbow + DEX
      dexMod: 3,
      color: [80, 160, 100], // forest green
      sprite: assetUrl("/assets/characters/ranger.png"),
      baseMoveRange: 5,
      position: { col: 0, row: 0 },
    },
    {
      id: "miren",
      name: "Miren",
      side: "party",
      maxHp: 14,
      hp: 14,
      ac: 12,
      attackBonus: 4,
      damage: { dice: 1, sides: 6, bonus: 2 }, // staff or fire bolt
      dexMod: 1,
      color: [120, 100, 200], // arcane violet
      sprite: assetUrl("/assets/characters/wizard.png"),
      baseMoveRange: 4,
      position: { col: 0, row: 0 },
    },
  ];
}
