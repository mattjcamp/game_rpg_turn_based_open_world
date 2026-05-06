/**
 * Shared module-level game state.
 *
 * Phaser scenes live inside a single Phaser.Game instance and need a
 * place to share state across transitions — when CombatScene ends, the
 * party HP changes need to be visible to OverworldScene, and the
 * player's overworld position needs to survive the round-trip.
 *
 * Scene-attached `data` registries work too, but a plain module
 * singleton keeps the contract honest: state is just data, not tied to
 * Phaser, and is testable in pure unit tests if we ever want to.
 *
 * Reset by calling `resetGameState()` (e.g. on "New Game").
 */

import type { Combatant } from "./types";
import { makeSampleParty } from "./data/fighters";

export interface GameState {
  /** Persistent party — HP carries across encounters. */
  party: Combatant[];
  /** Where the player avatar stands on the overworld grid. */
  playerPos: { col: number; row: number };
  /** "col,row" of overworld tiles whose encounter has already been resolved. */
  consumedTriggers: Set<string>;
  /** Set when the player has been wiped — overworld will refuse to step. */
  defeated: boolean;
}

function makeFreshState(): GameState {
  return {
    party: makeSampleParty(),
    // The dragon overworld declares party_start { col: 11, row: 16 }.
    // OverworldScene will overwrite this from the loaded map's
    // party_start once it finishes loading; this default just keeps
    // the type honest on first construction.
    playerPos: { col: 11, row: 16 },
    consumedTriggers: new Set(),
    defeated: false,
  };
}

export const gameState: GameState = makeFreshState();

export function resetGameState(): void {
  const fresh = makeFreshState();
  gameState.party = fresh.party;
  gameState.playerPos = fresh.playerPos;
  gameState.consumedTriggers = fresh.consumedTriggers;
  gameState.defeated = fresh.defeated;
}

export function triggerKey(col: number, row: number): string {
  return `${col},${row}`;
}
