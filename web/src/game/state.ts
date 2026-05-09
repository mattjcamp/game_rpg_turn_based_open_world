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
import type { DungeonLevel } from "./world/Dungeon";
import type { QuestState } from "./world/Quests";
import type { LastSceneSnapshot } from "./save";

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
  /**
   * Cached dungeon levels per overworld entrance, keyed by `${col},${row}`.
   * Each entry is a list of `DungeonLevel` (one per floor) — generated
   * once on first entry and reused on every re-visit so explored tiles,
   * opened chests, triggered traps, and remaining monsters all persist.
   * The "generate dungeons one time" requirement maps onto a cache miss
   * triggering generation, and a hit returning the same mutable level
   * objects the previous visit walked through. */
  dungeonCache: Map<string, DungeonLevel[]>;
  /**
   * In-dungeon position (overworld entry, current floor, party tile).
   * Set when the party enters a dungeon and read by DungeonScene on
   * boot so a return-from-combat replays the previous tile rather than
   * snapping to the entry stairs. Cleared on `_exitDungeon`.
   */
  dungeonPos: {
    overworldCol: number;
    overworldRow: number;
    level: number;
    col: number;
    row: number;
  } | null;
  /**
   * Per-quest progress, keyed by quest name. Initialized lazily by
   * the first scene that loads `quests.json` (TownScene / OverworldScene)
   * via `ensureQuestStates`. Persists across scene transitions so a
   * quest accepted in one town stays active when the party walks out.
   * The map is mutated in place by `Quests.creditKills` and
   * `Quests.creditCollect`. */
  moduleQuestStates: Map<string, QuestState>;
  /**
   * Location string passed to `creditKills` so kill credit only fires
   * when the combat location matches a step's `spawn_location`. Set by
   * the scene that triggered combat:
   *   - DungeonScene: `dungeon:<name>` (or `dungeon:<name> - Floor N`
   *     for multi-level dungeons).
   *   - TownScene:    `town:<name>` (when town interior combat lands).
   *   - OverworldScene: `overview`.
   * Cleared on dungeon exit / town exit so a stale value can't credit
   * the wrong fight.
   */
  combatLocation: string;
  /**
   * Names of monsters defeated in the most recent combat. Populated
   * by CombatScene's victory branch and read by the scene that
   * launched combat (DungeonScene right now) to credit quest kill
   * steps via `Quests.creditKills`. Cleared after credit so a single
   * fight credits steps once.
   */
  pendingKilledMonsters: string[];
  /**
   * Quest monsters placed in town interiors / building spaces. Keyed
   * by the full path the player enters with (e.g.
   * `"Plainstown/General Shop Interior"`). Populated lazily on first
   * entry to an interior whose active quests have kill steps targeting
   * it. Survives town/interior re-entries so positions + remaining-
   * count persist mid-quest. Mirrors the Python game's
   * `quest_interior_monsters` dict.
   */
  interiorMonsters: Map<string, InteriorMonster[]>;
  /**
   * Per-shop-instance inventory, keyed by `${townName}|${shopType}`.
   * Each value is the list of item names currently in stock at that
   * counter. Seeded lazily from `counters.json` on first visit, then
   * mutated by buy (item removed) and sell (item appended). Persists
   * across scene transitions and the rolling save so a sold-out shop
   * stays sold out, and items the party offloaded earlier remain on
   * the shelf when they return.
   */
  shopInventories: Map<string, string[]>;
  /**
   * NPCs the party has already pickpocketed this run. Each entry is
   * a stable per-NPC key composed via `npcKey()` below — typically
   * `"<sceneKey>|<npcName>|<homeCol>,<homeRow>"`. The home position
   * disambiguates NPCs that share a name (every village has an
   * "Innkeeper"); the scene key disambiguates across towns and
   * building interiors.
   *
   * The Halfling pickpocket action refuses when every nearby NPC's
   * key is already in this Set, mirroring the design rule that a
   * given NPC can only be lifted from once per run.
   */
  pickpocketedNpcs: Set<string>;
  /**
   * The active scene + its init payload — written by each scene's
   * create() and read by the resume path on "Return to Game" so the
   * player lands back in whichever map they were on. Null until any
   * scene boots for the first time (which it does within ~1s of the
   * world page loading). */
  lastScene: LastSceneSnapshot | null;
}

/**
 * Compose a stable per-NPC key for the pickpocket gate. Combines
 * the scene path (town name, "building:Foo:Space", or "overview")
 * with the NPC's name and home anchor so two villagers named
 * "Villager" in the same town are still distinct, and the same
 * villager wandering around their tile range still resolves to one
 * key (their home position never changes).
 */
export function npcKey(
  sceneKey: string,
  npcName: string,
  homeCol: number,
  homeRow: number,
): string {
  return `${sceneKey}|${npcName}|${homeCol},${homeRow}`;
}

export interface InteriorMonster {
  /** Stable id — used to remove this entry on combat victory. */
  id: string;
  col: number;
  row: number;
  /** Catalog name (sprite + stats lookup). The first roster entry
   *  doubles as the on-map sprite, matching the overworld-roamer
   *  convention. */
  name: string;
  /** Encounter roster handed to CombatScene. */
  encounterNames: string[];
  /** Encounter template name — needed by `creditKills` so the right
   *  quest step gets credited when this monster is defeated. */
  encounterName: string;
  /** Quest this monster was placed for. Lets the spawn pass tell
   *  "already placed for this step" apart from "this is for some
   *  other step", so accepting a quest *after* first entering the
   *  interior still tops up the population correctly. */
  questName: string;
  /** Index of the kill step inside the quest definition. Combined
   *  with `questName`, this is the per-step identity used to decide
   *  whether more monsters need spawning on re-entry. */
  stepIdx: number;
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
    dungeonCache: new Map(),
    dungeonPos: null,
    moduleQuestStates: new Map(),
    combatLocation: "",
    pendingKilledMonsters: [],
    interiorMonsters: new Map(),
    shopInventories: new Map(),
    pickpocketedNpcs: new Set(),
    lastScene: null,
  };
}

export const gameState: GameState = makeFreshState();

// Live-debug hook — exposes the singleton on window so the browser
// console / Claude-in-Chrome MCP can inspect quest progress, party
// data, dungeon cache, etc. without going through a scene.
if (typeof window !== "undefined") {
  (window as unknown as { __gameState?: GameState }).__gameState = gameState;
}

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
  gameState.dungeonCache = fresh.dungeonCache;
  gameState.dungeonPos = fresh.dungeonPos;
  gameState.moduleQuestStates = fresh.moduleQuestStates;
  gameState.combatLocation = fresh.combatLocation;
  gameState.pendingKilledMonsters = fresh.pendingKilledMonsters;
  gameState.interiorMonsters = fresh.interiorMonsters;
  gameState.shopInventories = fresh.shopInventories;
  gameState.pickpocketedNpcs = fresh.pickpocketedNpcs;
  gameState.lastScene = fresh.lastScene;
}

export function triggerKey(col: number, row: number): string {
  return `${col},${row}`;
}
