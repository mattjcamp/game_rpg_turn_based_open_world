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
import { makeClock, type GameClock } from "./world/GameTime";
import type { ExamineLayout } from "./world/Examine";

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
  /** True once OverworldScene has seeded `playerPos` from the loaded
   *  map's `party_start` for this session. Subsequent scene re-entries
   *  preserve whatever position the player has walked to (we don't
   *  re-snap to the map start every time the overworld boots). Reset
   *  by `resetGameState()` so a New Game pulls the latest map start. */
  partyPosInitialized: boolean;
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
  /** Game world clock — minutes elapsed since epoch (Sun Jan 1, 12 PM).
   *  Each overworld/town move advances 5 minutes. Drives the time-of-day
   *  darkness overlay and the moon-phase HUD readout. */
  clock: GameClock;
  /** True while the party is sitting on a boat. Land monsters can't
   *  contact the party while this is set; only sea creatures engage. */
  onBoat: boolean;
  /** Live overworld boat positions, keyed by `${col},${row}`. Seeded
   *  from any TILE_BOAT cells in the source map on first load and
   *  mutated as boats sail / are disembarked. Persists across scene
   *  restarts so a boat the party left at a far shore is still there
   *  when they walk back. */
  boatPositions: Set<string>;
  /** Cached Examine state per overworld tile, keyed by `${col},${row}`.
   *  Each entry holds the obstacle layout, ground items, and
   *  reagents-searched flag for one zoomed-in area. Persists across
   *  scene transitions so a tile the party left items on still has
   *  them when they come back. */
  examineLayouts: Map<string, ExamineLayout>;
}

function makeFreshState(): GameState {
  return {
    party: makeSampleParty(),
    partyData: null,
    // OverworldScene seeds this from the loaded map's `party_start`
    // on the first scene boot of the session. The hardcoded fallback
    // here just keeps the type honest before the map has loaded —
    // by the time anything actually renders, `partyPosInitialized`
    // will be true and `playerPos` will reflect the map data.
    playerPos: { col: 0, row: 0 },
    partyPosInitialized: false,
    consumedTriggers: new Set(),
    destroyedSpawns: new Set(),
    roamingMonsters: [],
    defeated: false,
    clock: makeClock(),
    onBoat: false,
    boatPositions: new Set(),
    examineLayouts: new Map(),
  };
}

export const gameState: GameState = makeFreshState();

export function resetGameState(): void {
  const fresh = makeFreshState();
  gameState.party = fresh.party;
  gameState.partyData = fresh.partyData;
  gameState.playerPos = fresh.playerPos;
  gameState.partyPosInitialized = fresh.partyPosInitialized;
  gameState.consumedTriggers = fresh.consumedTriggers;
  gameState.destroyedSpawns = fresh.destroyedSpawns;
  gameState.roamingMonsters = fresh.roamingMonsters;
  gameState.defeated = fresh.defeated;
  gameState.clock = fresh.clock;
  gameState.onBoat = fresh.onBoat;
  gameState.boatPositions = fresh.boatPositions;
  gameState.examineLayouts = fresh.examineLayouts;
}

export function triggerKey(col: number, row: number): string {
  return `${col},${row}`;
}
