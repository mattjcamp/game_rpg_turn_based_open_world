/**
 * Single-slot rolling save for the running session.
 *
 * Stores the live `gameState` in localStorage so the player can close
 * the tab mid-quest and pick up exactly where they left off via the
 * "Return to Game" button on the landing page.
 *
 * Three jobs:
 *   - `save()`     — write current `gameState` to localStorage.
 *   - `load()`     — hydrate `gameState` from localStorage (returns
 *                    true on success, false when there's nothing to
 *                    load or the payload is malformed).
 *   - `clearSave()` — drop the save (called when the player picks
 *                    "Start New Game", which restarts cleanly).
 *
 * **Why a hand-rolled (de)serialiser?** `JSON.stringify` strips
 * `Map`s and `Set`s — the game state is full of them
 * (`dungeonCache`, `interiorMonsters`, `consumedTriggers`, …). The
 * helpers below convert those to JSON-friendly arrays on save and
 * back on load.
 *
 * **What's saved.** Everything on `gameState` that affects gameplay
 * — party roster (HP, MP, equipment, inventory, gold, XP), party
 * position, the procedural-dungeon cache (rooms, monsters, opened
 * chests, fog of war), interior quest monsters, quest progress,
 * boats, examine layouts, the clock, and the last-active scene
 * (so resume routes back into the dungeon / town the player was
 * in). Roamer monsters and pending combat-killed lists are saved
 * too so a save mid-overworld-fight still resolves cleanly.
 *
 * **What's NOT saved.** Phaser-internal state (sprites, tweens,
 * camera) — those rebuild on scene boot. `partyData = null` is
 * never written back; if the saved payload has it, we deserialise
 * fresh, otherwise the loader sees null and the next scene-boot
 * will lazy-load from the roster cache.
 */
import { gameState, resetGameState, type GameState, type InteriorMonster } from "./state";
import type { DungeonLevel, DungeonMonster } from "./world/Dungeon";
import type { QuestState } from "./world/Quests";
import type { Party } from "./world/Party";
import type { ExamineLayout } from "./world/Examine";
import type { RoamingMonster } from "./world/SpawnPoints";
import type { GameClock } from "./world/GameTime";
import type { Combatant } from "./types";

const STORAGE_KEY = "realm-of-shadow.save.v1";

export type LastSceneKey = "OverworldScene" | "TownScene" | "DungeonScene";

export interface LastSceneSnapshot {
  key: LastSceneKey;
  /** Init-data payload to hand the scene on resume. Shape varies
   *  per-scene; the schemas live in each scene's `init()`. We treat
   *  this as opaque JSON since the only consumer is the matching
   *  scene's init handler. */
  payload: Record<string, unknown>;
}

interface RawSave {
  v: 1;
  party: Party | null;
  playerPos: { col: number; row: number };
  partyPosInitialized: boolean;
  consumedTriggers: string[];
  destroyedSpawns: string[];
  roamingMonsters: RoamingMonster[];
  defeated: boolean;
  clock: GameClock;
  onBoat: boolean;
  boatPositions: string[];
  examineLayouts: Array<[string, ExamineLayout]>;
  dungeonCache: Array<[string, RawDungeonLevel[]]>;
  dungeonPos: GameState["dungeonPos"];
  moduleQuestStates: Array<[string, QuestState]>;
  combatLocation: string;
  pendingKilledMonsters: string[];
  interiorMonsters: Array<[string, InteriorMonster[]]>;
  party_combat: Combatant[];
  lastScene: LastSceneSnapshot | null;
}

/** Per-floor dungeon shape with Sets converted to arrays for JSON. */
interface RawDungeonLevel {
  name: string;
  width: number;
  height: number;
  tiles: number[][];
  decorations: Record<string, number>;
  tileProperties: Record<string, { walkable?: boolean }>;
  entryCol: number;
  entryRow: number;
  style: DungeonLevel["style"];
  monsters: DungeonMonster[];
  openedChests: string[];
  triggeredTraps: string[];
  exploredTiles: string[];
  overworldExits: string[];
  questArtifacts: DungeonLevel["questArtifacts"];
}

function dungeonLevelToRaw(lvl: DungeonLevel): RawDungeonLevel {
  return {
    name: lvl.name,
    width: lvl.width,
    height: lvl.height,
    tiles: lvl.tiles,
    decorations: lvl.decorations,
    tileProperties: lvl.tileProperties,
    entryCol: lvl.entryCol,
    entryRow: lvl.entryRow,
    style: lvl.style,
    monsters: lvl.monsters,
    openedChests: [...lvl.openedChests],
    triggeredTraps: [...lvl.triggeredTraps],
    exploredTiles: [...lvl.exploredTiles],
    overworldExits: [...lvl.overworldExits],
    questArtifacts: lvl.questArtifacts,
  };
}

function dungeonLevelFromRaw(raw: RawDungeonLevel): DungeonLevel {
  return {
    name: raw.name,
    width: raw.width,
    height: raw.height,
    tiles: raw.tiles,
    decorations: raw.decorations ?? {},
    tileProperties: raw.tileProperties ?? {},
    entryCol: raw.entryCol,
    entryRow: raw.entryRow,
    style: raw.style ?? "default",
    monsters: raw.monsters ?? [],
    openedChests: new Set(raw.openedChests ?? []),
    triggeredTraps: new Set(raw.triggeredTraps ?? []),
    exploredTiles: new Set(raw.exploredTiles ?? []),
    overworldExits: new Set(raw.overworldExits ?? []),
    questArtifacts: raw.questArtifacts ?? {},
  };
}

function toRaw(s: GameState): RawSave {
  return {
    v: 1,
    party: s.partyData,
    playerPos: s.playerPos,
    partyPosInitialized: s.partyPosInitialized,
    consumedTriggers: [...s.consumedTriggers],
    destroyedSpawns: [...s.destroyedSpawns],
    roamingMonsters: s.roamingMonsters,
    defeated: s.defeated,
    clock: s.clock,
    onBoat: s.onBoat,
    boatPositions: [...s.boatPositions],
    examineLayouts: [...s.examineLayouts.entries()],
    dungeonCache: [...s.dungeonCache.entries()].map(
      ([key, levels]) => [key, levels.map(dungeonLevelToRaw)],
    ),
    dungeonPos: s.dungeonPos,
    moduleQuestStates: [...s.moduleQuestStates.entries()],
    combatLocation: s.combatLocation,
    pendingKilledMonsters: [...s.pendingKilledMonsters],
    interiorMonsters: [...s.interiorMonsters.entries()],
    party_combat: s.party,
    lastScene: s.lastScene ?? null,
  };
}

function fromRaw(raw: RawSave, target: GameState): void {
  target.partyData = raw.party ?? null;
  target.playerPos = raw.playerPos ?? { col: 0, row: 0 };
  target.partyPosInitialized = !!raw.partyPosInitialized;
  target.consumedTriggers = new Set(raw.consumedTriggers ?? []);
  target.destroyedSpawns = new Set(raw.destroyedSpawns ?? []);
  target.roamingMonsters = raw.roamingMonsters ?? [];
  target.defeated = !!raw.defeated;
  target.clock = raw.clock;
  target.onBoat = !!raw.onBoat;
  target.boatPositions = new Set(raw.boatPositions ?? []);
  target.examineLayouts = new Map(raw.examineLayouts ?? []);
  target.dungeonCache = new Map(
    (raw.dungeonCache ?? []).map(
      ([key, levels]) => [key, levels.map(dungeonLevelFromRaw)] as const,
    ),
  );
  target.dungeonPos = raw.dungeonPos ?? null;
  target.moduleQuestStates = new Map(raw.moduleQuestStates ?? []);
  target.combatLocation = raw.combatLocation ?? "";
  target.pendingKilledMonsters = raw.pendingKilledMonsters ?? [];
  target.interiorMonsters = new Map(raw.interiorMonsters ?? []);
  target.party = raw.party_combat ?? [];
  target.lastScene = raw.lastScene ?? null;
}

/**
 * Persist `gameState` to localStorage. Errors (quota, private mode)
 * are swallowed — saving is best-effort and shouldn't crash gameplay
 * on a tab where storage is unavailable.
 */
export function save(): void {
  if (typeof window === "undefined") return;
  try {
    const raw = toRaw(gameState);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(raw));
  } catch {
    /* private mode / quota — swallow */
  }
}

/**
 * Hydrate `gameState` from localStorage. Returns true when a save
 * existed and was applied. Mismatched-version or malformed payloads
 * fall through to false (the caller can show "Start New Game" only).
 */
export function load(): boolean {
  if (typeof window === "undefined") return false;
  let raw: RawSave | null = null;
  try {
    const text = window.localStorage.getItem(STORAGE_KEY);
    if (!text) return false;
    const parsed = JSON.parse(text) as RawSave;
    if (parsed?.v !== 1) return false;
    raw = parsed;
  } catch {
    return false;
  }
  if (!raw) return false;
  fromRaw(raw, gameState);
  return true;
}

/** Drop the save slot. Called by "Start New Game" so the player
 *  doesn't accidentally inherit a previous run's quest state. */
export function clearSave(): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.removeItem(STORAGE_KEY); } catch { /* noop */ }
}

/** Cheap check used by the landing page to decide whether to render
 *  the "Return to Game" button. */
export function hasSave(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const text = window.localStorage.getItem(STORAGE_KEY);
    if (!text) return false;
    const parsed = JSON.parse(text) as { v?: number };
    return parsed?.v === 1;
  } catch {
    return false;
  }
}

/**
 * Stamp the active scene + its init payload onto `gameState.lastScene`
 * and persist. Each scene's `create()` calls this once it's up — the
 * payload is whatever the scene's own `init()` would need to re-enter
 * cleanly. Resume reads this and routes back into the same scene.
 */
export function rememberScene(snapshot: LastSceneSnapshot): void {
  gameState.lastScene = snapshot;
  save();
}

/**
 * Convenience: clear the save AND reset gameState. Used by "Start
 * New Game" so the next world boot is genuinely fresh.
 */
export function startFreshSession(): void {
  clearSave();
  resetGameState();
}
