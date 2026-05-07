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
import type { Party } from "./world/Party";
import type { RoamingMonster } from "./world/SpawnPoints";

export interface GameState {
  /** Combat-layer party — slim Combatant[] used by CombatScene only.
   *  HP changes here are written back through to `partyData` after
   *  combat ends. Kept as a separate handle while the combat engine
   *  runs against this narrower shape. */
  party: Combatant[];
  /**
   * Full Party payload from `/data/party.json` — roster, active
   * indices, gold, shared inventory, party effects. Loaded lazily by
   * the first scene that needs it (PartyScene) and held here so
   * subsequent opens are instant and edits survive transitions.
   */
  partyData: Party | null;
  /** Where the player avatar stands on the overworld grid. */
  playerPos: { col: number; row: number };
  /** "col,row" of overworld tiles whose encounter has already been resolved. */
  consumedTriggers: Set<string>;
  /**
   * "col,row" of Monster Spawn tiles the party has wiped out — these
   * tiles render as plain grass and never spawn another monster.
   * Survives the lifetime of the session, just like consumedTriggers.
   */
  destroyedSpawns: Set<string>;
  /**
   * Live monsters wandering the overworld. Each entry was produced by
   * a spawn tile and pursues the party one step at a time. Combat
   * removes the engaged entry on victory.
   */
  roamingMonsters: RoamingMonster[];
  /** Set when the player has been wiped — overworld will refuse to step. */
  defeated: boolean;
}

function makeFreshState(): GameState {
  return {
    party: makeSampleParty(),
    partyData: null,
    // The dragon overworld declares party_start { col: 11, row: 16 }.
    // OverworldScene will overwrite this from the loaded map's
    // party_start once it finishes loading; this default just keeps
    // the type honest on first construction.
    playerPos: { col: 11, row: 16 },
    consumedTriggers: new Set(),
    destroyedSpawns: new Set(),
    roamingMonsters: [],
    defeated: false,
  };
}

export const gameState: GameState = makeFreshState();

export function resetGameState(): void {
  const fresh = makeFreshState();
  gameState.party = fresh.party;
  gameState.partyData = fresh.partyData;
  gameState.playerPos = fresh.playerPos;
  gameState.consumedTriggers = fresh.consumedTriggers;
  gameState.destroyedSpawns = fresh.destroyedSpawns;
  gameState.roamingMonsters = fresh.roamingMonsters;
  gameState.defeated = fresh.defeated;
}

export function triggerKey(col: number, row: number): string {
  return `${col},${row}`;
}
