/**
 * Sample party for the combat demo. Stats picked to feel like a level-2
 * D&D-ish party: fighter and barbarian heavy, ranger middling AC, mage low.
 *
 * Later slices will load these from data/party.json (or from save files);
 * for the first slice we keep them inline so the scene starts instantly.
 */

import Phaser from "phaser";
import type { Combatant } from "../types";
import type { Party } from "../world/Party";
import { assetUrl } from "../world/Module";

/** Sprite paths the party-related preloader needs. */
export const PARTY_SPRITES: string[] = [
  assetUrl("/assets/characters/fighter.png"),
  assetUrl("/assets/characters/barbarian.png"),
  assetUrl("/assets/characters/ranger.png"),
  assetUrl("/assets/characters/wizard.png"),
];

/**
 * Distinct sprite paths used by every member in `party` (full
 * roster, not just the active four — sprite loads are cheap, and
 * swapping in a benched member shouldn't pop a "missing texture"
 * rectangle).
 *
 * Used by scenes that render party avatars (Party, Town, Combat)
 * so they can dynamically queue any `member.sprite` that wasn't
 * in the static class-sprite preload list — necessary now that
 * the character creator lets the player pick from npcs/ and
 * monsters/ folders alongside the classic 9 class sprites.
 */
export function partyMemberSpritePaths(party: Party): string[] {
  const seen = new Set<string>();
  for (const m of party.roster) {
    if (m.sprite) seen.add(m.sprite);
  }
  return [...seen];
}

/**
 * Queue every party-member sprite that isn't already in the scene's
 * texture cache, then await the loader to flush. Safe to call when
 * `party` is null (no-op). Returns nothing — when it resolves, the
 * textures are guaranteed to be available for `add.image(path, ...)`.
 *
 * Pass after `loadParty()` resolves and before any code that adds
 * member-sprite images to the scene.
 */
export async function preloadPartyMemberSprites(
  scene: Phaser.Scene,
  party: Party | null | undefined,
): Promise<void> {
  if (!party) return;
  const paths = partyMemberSpritePaths(party);
  let queued = 0;
  for (const path of paths) {
    if (!scene.textures.exists(path)) {
      scene.load.image(path, path);
      queued += 1;
    }
  }
  if (queued === 0) return;
  await new Promise<void>((res) => {
    scene.load.once("complete", () => res());
    scene.load.start();
  });
}

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
