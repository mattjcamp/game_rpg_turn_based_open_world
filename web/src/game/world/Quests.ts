/**
 * Module quest data + state.
 *
 * Mirrors the relevant subset of `src/quest_manager.py` from the
 * Python project — same status lifecycle, same kill/collect step
 * semantics, same location-matching rules. Quest definitions are
 * loaded from the active module's `quests.json`; per-quest progress
 * lives on `gameState.moduleQuestStates`.
 *
 * **Status lifecycle.**
 *   `available` → `active` (player accepted the quest)
 *                 → `completed` (every step's progress flag is true)
 *                                → `turned_in` (rewards claimed; terminal)
 *
 * **Step kinds.** v1 supports two:
 *   - `"kill"` — defeat the named encounter (from encounters.json)
 *               at `spawn_location`, `target_count` times.
 *   - `"collect"` — pick up `collect_item` at `spawn_location`.
 *
 * **Location matching** (`locationMatches`) accepts:
 *   - empty step location → any combat location credits
 *   - `"overview"` / `"Overview Map"` → overworld combat
 *   - exact case-insensitive match for `"town:X"`, `"interior:X/Y"`,
 *     `"space:X/Y"`, `"building:X"`
 *   - `"dungeon:X"` → matches `"dungeon:X"` and `"dungeon:X - Floor N"`
 *   - `"building:X"` → also matches `"space:X/Y"` for any sub-space
 *
 * v1 explicitly does NOT implement quest-tag verification (the Python
 * "this monster must be the quest's specific spawn" rule). That's a
 * fix-up to preserve the cinematic boss moment in localized steps;
 * for v1 a roster name + location match is the user-facing
 * simplification called out in the port plan.
 */

import { modulePath } from "./Module";
import { sampleEncounter, type EncounterTemplate } from "./Encounters";
import { tileDef } from "./Tiles";
import type { TileMap } from "./TileMap";

export type QuestStatus = "available" | "active" | "completed" | "turned_in";
export type QuestStepKind = "kill" | "collect";

// ── World-unlock rewards ──────────────────────────────────────────
//
// A quest can declare a list of overworld tile mutations that fire
// when the quest is turned in — used in modules like Dragon of
// Dagorn to drop a Bridge across an impassable river once the
// Stolen Sealstone quest is delivered. The Python implementation
// lives in `src/module_editor_quest.py:apply_world_unlocks`; this
// is a faithful port.
//
// `kind` is preserved as a designer hint so the quest editor can
// re-open the right tile picker on a round-trip; at runtime the
// two kinds are identical (a single `set_tile`):
//   - "add_tile"        — paint any overworld tile id
//   - "remove_obstacle" — paint a passable tile (subset of add_tile)
//
// Out-of-bounds entries and ones missing required ints are skipped
// silently rather than crashing on a malformed quests.json.
export type WorldUnlockKind = "add_tile" | "remove_obstacle" | "";

export interface WorldUnlock {
  kind: WorldUnlockKind;
  col: number;
  row: number;
  tile: number;
}

/** Triple returned by `applyWorldUnlocks` — used by the reward-summary
 *  line so the player sees "World changed: Bridge at (5,13)" when a
 *  quest's world-unlock op completes. */
export type AppliedUnlock = readonly [col: number, row: number, tile: number];

export interface QuestStep {
  description: string;
  stepType: QuestStepKind;
  /** For kill steps — encounter name (encounters.json key). */
  encounter: string;
  /** For collect steps — display name of the artifact item. */
  collectItem: string;
  /** "yes" / "no" — when "yes", a guardian roster entry joins the
   *  artifact's encounter (v1 simplification: not a separate fight). */
  hasGuardian: boolean;
  /** Encounter name for the guardian (when hasGuardian). */
  guardianEncounter: string;
  /** Where this step plays out — `"dungeon:X"`, `"town:X"`,
   *  `"interior:X/Y"`, `"building:X"`, `"space:X/Y"`, `"overview"`,
   *  or empty (any location credits). */
  spawnLocation: string;
  /** How many encounter clearings (kill) or items (collect) to credit
   *  the step. Most steps are 1; some kill steps are 3. */
  targetCount: number;
  /** Optional pinned spawn coords for the artifact (collect steps). */
  spawnCol?: number;
  spawnRow?: number;
}

export interface QuestDef {
  name: string;
  description: string;
  giverNpc: string;
  /** Path under /assets/ (or a Python-style absolute path that the
   *  asset resolver will translate). Empty falls back to the role
   *  default in `resolveNpcSprite`. */
  giverSprite: string;
  giverLocation: string;
  giverDialogue: string;
  giverCol: number;
  giverRow: number;
  rewardXp: number;
  rewardGold: number;
  rewardItems: string[];
  /**
   * Overworld tile mutations applied on turn-in. Most quests carry an
   * empty list. Mirrors the Python `reward_world_unlocks` field —
   * the data is a list (not a singleton) so authors can hand-edit a
   * multi-tile unlock (e.g. a 2-wide bridge) by adding entries.
   */
  rewardWorldUnlocks: WorldUnlock[];
  isFinalQuest: boolean;
  victoryText: string;
  steps: QuestStep[];
}

export interface QuestState {
  status: QuestStatus;
  /** One bool per step in the original definition. Auto-extended on
   *  load if the JSON gained extra steps after the save was written
   *  (matches the Python guard against mismatched step_progress). */
  stepProgress: boolean[];
  /** Per-kill-step counter so multi-target steps (e.g. "Wolves and
   *  Goblins ×3") report progress and complete on the right roll. */
  stepKills: Record<number, number>;
  /** Per-collect-step flag — true once the guardian protecting a
   *  collect step's artifact has been defeated. The interior /
   *  building-space spawn pass reads this to avoid re-spawning the
   *  guardian on every re-entry, which would otherwise leave the
   *  player in an endless-encounter loop the moment they killed the
   *  Cursed Battalion and walked back into the Abandoned Building.
   *  Indices not in the map default to "guardian still alive". */
  guardianDefeated: Record<number, boolean>;
}

interface RawQuestStep {
  description?: string;
  step_type?: string;
  encounter?: string;
  collect_item?: string;
  has_guardian?: string | boolean;
  guardian_encounter?: string;
  spawn_location?: string;
  target?: string;
  target_count?: number;
  optional?: string;
  spawn_col?: number | string;
  spawn_row?: number | string;
}

interface RawWorldUnlock {
  kind?: string;
  col?: number | string;
  row?: number | string;
  tile?: number | string;
}

interface RawQuest {
  name?: string;
  description?: string;
  giver_npc?: string;
  giver_sprite?: string;
  giver_location?: string;
  giver_dialogue?: string;
  giver_col?: number;
  giver_row?: number;
  reward_xp?: number;
  reward_gold?: number;
  reward_items?: string[];
  reward_world_unlocks?: RawWorldUnlock[];
  is_final_quest?: boolean;
  victory_text?: string;
  steps?: RawQuestStep[];
}

function coerceInt(v: unknown): number | undefined {
  if (typeof v === "number" && Number.isFinite(v)) return Math.floor(v);
  if (typeof v === "string" && v.trim().length > 0) {
    const n = parseInt(v, 10);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

function stepFromRaw(raw: RawQuestStep): QuestStep | null {
  const stepType = raw.step_type === "collect" ? "collect" : "kill";
  return {
    description: raw.description ?? "",
    stepType,
    encounter: raw.encounter ?? "",
    collectItem: raw.collect_item ?? "",
    hasGuardian: raw.has_guardian === "yes" || raw.has_guardian === true,
    guardianEncounter: raw.guardian_encounter ?? "",
    spawnLocation: raw.spawn_location ?? "",
    targetCount: Math.max(1, raw.target_count ?? 1),
    spawnCol: coerceInt(raw.spawn_col),
    spawnRow: coerceInt(raw.spawn_row),
  };
}

function unlockFromRaw(raw: RawWorldUnlock): WorldUnlock | null {
  if (!raw || typeof raw !== "object") return null;
  const c = coerceInt(raw.col);
  const r = coerceInt(raw.row);
  const t = coerceInt(raw.tile);
  if (c === undefined || r === undefined || t === undefined) return null;
  // Accept anything the editor might have written for `kind`, but only
  // round-trip the two values the editor surfaces; anything else
  // (including the empty string) collapses to "add_tile" so a hand-
  // edited entry without a kind still applies cleanly at runtime.
  let kind: WorldUnlockKind = "add_tile";
  if (raw.kind === "remove_obstacle") kind = "remove_obstacle";
  else if (raw.kind === "add_tile" || raw.kind === undefined || raw.kind === "") {
    kind = "add_tile";
  } else {
    // Unknown kinds still apply — preserve the string the editor wrote
    // so a future round-trip doesn't lose data, but TS narrows it to
    // the empty-string branch of the union for callers.
    kind = "";
  }
  return { kind, col: c, row: r, tile: t };
}

function fromRaw(raw: RawQuest): QuestDef | null {
  if (!raw || typeof raw !== "object" || typeof raw.name !== "string") return null;
  const steps = (raw.steps ?? [])
    .map(stepFromRaw)
    .filter((s): s is QuestStep => s !== null);
  const rewardWorldUnlocks = Array.isArray(raw.reward_world_unlocks)
    ? raw.reward_world_unlocks
        .map(unlockFromRaw)
        .filter((u): u is WorldUnlock => u !== null)
    : [];
  return {
    name: raw.name,
    description: raw.description ?? "",
    giverNpc: raw.giver_npc ?? raw.name,
    giverSprite: raw.giver_sprite ?? "",
    giverLocation: raw.giver_location ?? "",
    giverDialogue: raw.giver_dialogue ?? "",
    giverCol: raw.giver_col ?? 0,
    giverRow: raw.giver_row ?? 0,
    rewardXp: raw.reward_xp ?? 0,
    rewardGold: raw.reward_gold ?? 0,
    rewardItems: Array.isArray(raw.reward_items)
      ? raw.reward_items.filter((s): s is string => typeof s === "string")
      : [],
    rewardWorldUnlocks,
    isFinalQuest: raw.is_final_quest === true,
    victoryText: raw.victory_text ?? "",
    steps,
  };
}

let _cache: QuestDef[] | null = null;

export async function loadQuests(url = modulePath("quests.json")): Promise<QuestDef[]> {
  if (_cache) return _cache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawQuest[];
  if (!Array.isArray(raw)) throw new Error("quests.json is not an array");
  _cache = raw
    .map(fromRaw)
    .filter((q): q is QuestDef => q !== null);
  return _cache;
}

/** Test-only: clear the cache. */
export function _clearQuestsCache(): void {
  _cache = null;
}

export function findQuest(defs: QuestDef[], name: string): QuestDef | null {
  return defs.find((q) => q.name === name) ?? null;
}

/** Bring the quest-state map up to date with the loaded definitions.
 *  Adds a fresh `available` entry for any quest the state hasn't seen
 *  yet, and pads `stepProgress` if the JSON gained steps since the
 *  state was last written. Idempotent — safe to call on every scene
 *  boot. */
export function ensureQuestStates(
  defs: QuestDef[],
  states: Map<string, QuestState>,
): void {
  for (const def of defs) {
    let state = states.get(def.name);
    if (!state) {
      state = {
        status: "available",
        stepProgress: def.steps.map(() => false),
        stepKills: {},
        guardianDefeated: {},
      };
      states.set(def.name, state);
      continue;
    }
    while (state.stepProgress.length < def.steps.length) {
      state.stepProgress.push(false);
    }
    // Saves written before the guardian-defeated tracking landed
    // arrive without the field — patch it in so the spawn pass can
    // read it without an undefined-property guard everywhere.
    if (!state.guardianDefeated) state.guardianDefeated = {};
  }
}

// ── Location matching ───────────────────────────────────────────

/**
 * Strip a trailing " - Floor N" from a `dungeon:` location so a step
 * targeting `"dungeon:Crypt"` credits combat on any floor.
 */
const FLOOR_SUFFIX = /\s*-\s*floor\s+\d+$/i;

/**
 * Returns true when a combat-location string satisfies a step's
 * spawn_location. Mirrors `_location_matches` in quest_manager.py.
 */
export function locationMatches(stepLocation: string, combatLocation: string): boolean {
  if (!stepLocation) return true;
  if (stepLocation === "overview" || stepLocation === "Overview Map") {
    return combatLocation === "overview" || combatLocation === "overworld" || combatLocation === "";
  }
  if (!combatLocation) return false;
  const sl = stepLocation.toLowerCase();
  const cl = combatLocation.toLowerCase();
  if (sl === cl) return true;
  if (sl.startsWith("building:")) {
    const bld = sl.slice("building:".length);
    if (cl.startsWith("space:") && cl.slice("space:".length).startsWith(bld + "/")) return true;
  }
  if (sl.startsWith("dungeon:")) {
    const base = sl.slice("dungeon:".length);
    if (cl.startsWith("dungeon:")) {
      const clBase = cl.slice("dungeon:".length).replace(FLOOR_SUFFIX, "");
      if (clBase === base) return true;
    }
  }
  return false;
}

// ── Monster-name normalisation ─────────────────────────────────

/**
 * Build the variant set the Python quest manager builds: original,
 * lowercase, snake_case, Title Case, lowercase-with-spaces. A roster
 * monster matches a killed monster if their variant sets intersect.
 */
function nameVariants(name: string): Set<string> {
  if (!name) return new Set();
  const out = new Set<string>();
  out.add(name);
  out.add(name.toLowerCase());
  out.add(name.replace(/\s+/g, "_").toLowerCase());
  // Title Case on the spaced form
  const spaced = name.replace(/_/g, " ");
  out.add(spaced.replace(/\b\w/g, (c) => c.toUpperCase()));
  out.add(spaced.toLowerCase());
  return out;
}

function variantsOverlap(a: Set<string>, b: Set<string>): boolean {
  for (const v of a) if (b.has(v)) return true;
  return false;
}

// ── Step credit ────────────────────────────────────────────────

export interface QuestStepCallout {
  questName: string;
  description: string;
  /** True when this credit completed the entire quest. */
  questComplete: boolean;
}

export interface KillCreditResult {
  /** Player-facing summary lines, one per progress event. */
  messages: string[];
  /** Quests that crossed into `completed` on this credit. */
  newlyCompleted: string[];
  /** Step-completion callouts to surface as banners. One per step
   *  that flipped from incomplete → done in this credit pass. */
  callouts: QuestStepCallout[];
}

/**
 * Credit any kill steps satisfied by the names of monsters killed in
 * a single combat at `combatLocation`. Mutates the relevant quest
 * states in place.
 *
 * `encounters` is the loaded encounters.json table — we look up each
 * step's `encounter` name to get its roster, then test whether any
 * killed monster name is in that roster (variant-fuzzy match).
 */
export function creditKills(
  defs: QuestDef[],
  states: Map<string, QuestState>,
  encounters: Record<string, EncounterTemplate[]>,
  killedNames: string[],
  combatLocation: string,
): KillCreditResult {
  const messages: string[] = [];
  const newlyCompleted: string[] = [];
  const callouts: QuestStepCallout[] = [];
  if (killedNames.length === 0) return { messages, newlyCompleted, callouts };

  const killedVariants = new Set<string>();
  for (const n of killedNames) for (const v of nameVariants(n)) killedVariants.add(v);

  // Flat map of encounter name → roster (across all areas).
  const rosterByName = new Map<string, string[]>();
  for (const list of Object.values(encounters)) {
    for (const e of list) {
      if (!rosterByName.has(e.name)) rosterByName.set(e.name, e.monsters);
    }
  }

  for (const def of defs) {
    const state = states.get(def.name);
    if (!state || state.status !== "active") continue;
    let stepCompleted = false;

    for (let i = 0; i < def.steps.length; i++) {
      const step = def.steps[i];
      if (state.stepProgress[i]) continue;
      if (step.stepType !== "kill") continue;
      if (!step.encounter) continue;
      if (!locationMatches(step.spawnLocation, combatLocation)) continue;
      const roster = rosterByName.get(step.encounter);
      if (!roster) continue;
      let rosterHit = false;
      for (const m of roster) {
        if (variantsOverlap(nameVariants(m), killedVariants)) { rosterHit = true; break; }
      }
      if (!rosterHit) continue;

      const prev = state.stepKills[i] ?? 0;
      const now = prev + 1;
      state.stepKills[i] = now;
      if (now >= step.targetCount) {
        state.stepProgress[i] = true;
        stepCompleted = true;
        messages.push(`Quest "${def.name}": ${step.description} — Complete!`);
        const willCompleteQuest = state.stepProgress.every((p) => p);
        callouts.push({
          questName: def.name,
          description: step.description,
          questComplete: willCompleteQuest,
        });
      } else {
        messages.push(`${step.encounter} defeated! (${now}/${step.targetCount})`);
      }
    }

    if (stepCompleted && state.stepProgress.every((p) => p)) {
      // status was "active" at the loop guard above; TS narrows it
      // here, so we can flip directly without re-checking.
      state.status = "completed";
      newlyCompleted.push(def.name);
      messages.push("All steps done! Return to the quest giver for your reward.");
    }
  }
  return { messages, newlyCompleted, callouts };
}

export interface CollectCreditResult {
  message: string;
  /** True when this credit completed the quest. */
  questNowCompleted: boolean;
  /** Banner payload for the credited step. Null only when the
   *  quest / step weren't found (the message becomes a generic
   *  pickup line in that case). */
  callout: QuestStepCallout | null;
}

/**
 * Credit a single collect step. Returns a UI message and a flag for
 * whether the quest just transitioned to `completed`. The caller is
 * responsible for removing the artifact from the world (mirrors the
 * Python `collect_quest_item` contract).
 */
export function creditCollect(
  defs: QuestDef[],
  states: Map<string, QuestState>,
  questName: string,
  stepIdx: number,
  itemName: string,
): CollectCreditResult {
  const def = findQuest(defs, questName);
  const state = states.get(questName);
  if (!def || !state) return { message: `Found ${itemName}!`, questNowCompleted: false, callout: null };
  if (stepIdx < 0 || stepIdx >= state.stepProgress.length) {
    return { message: `Found ${itemName}!`, questNowCompleted: false, callout: null };
  }
  state.stepProgress[stepIdx] = true;
  const stepDesc = def.steps[stepIdx]?.description ?? `Step ${stepIdx + 1}`;
  const allDone = state.stepProgress.every((p) => p);
  if (allDone && state.status === "active") {
    state.status = "completed";
    return {
      message: `Collected ${itemName}! Quest "${def.name}" complete — return to ${def.giverNpc}.`,
      questNowCompleted: true,
      callout: { questName: def.name, description: stepDesc, questComplete: true },
    };
  }
  return {
    message: `Collected ${itemName}! (${stepDesc})`,
    questNowCompleted: false,
    callout: { questName: def.name, description: stepDesc, questComplete: false },
  };
}

/**
 * Find the active quest + step that wants its `collect_item` placed
 * at the given `dungeonName`. Used by the dungeon generator to know
 * whether to paint a TILE_ARTIFACT and where.
 *
 * Returns the first match — modules are authored such that one
 * dungeon hosts at most one collect step at a time.
 */
export function activeCollectStepFor(
  defs: QuestDef[],
  states: Map<string, QuestState>,
  combatLocation: string,
): { questName: string; stepIdx: number; step: QuestStep } | null {
  for (const def of defs) {
    const state = states.get(def.name);
    if (!state || state.status !== "active") continue;
    for (let i = 0; i < def.steps.length; i++) {
      const step = def.steps[i];
      if (step.stepType !== "collect") continue;
      if (state.stepProgress[i]) continue;
      if (!locationMatches(step.spawnLocation, combatLocation)) continue;
      return { questName: def.name, stepIdx: i, step };
    }
  }
  return null;
}

/**
 * Every active collect step whose `spawn_location` resolves to the
 * given `combatLocation` (per `locationMatches`). Companion to
 * `activeKillStepsForLocation` — TownScene calls this when entering a
 * building space (or interior) to figure out which artifacts to drop
 * on the floor. A single space hosts at most one collect step in v1,
 * but we return a list so a future module that pins two artifacts to
 * the same room (e.g. the binding-rite + the keystone) doesn't lose
 * one silently.
 */
export function activeCollectStepsForLocation(
  defs: QuestDef[],
  states: Map<string, QuestState>,
  combatLocation: string,
): Array<{ questName: string; stepIdx: number; step: QuestStep }> {
  const out: Array<{ questName: string; stepIdx: number; step: QuestStep }> = [];
  for (const def of defs) {
    const state = states.get(def.name);
    if (!state || state.status !== "active") continue;
    for (let i = 0; i < def.steps.length; i++) {
      const step = def.steps[i];
      if (step.stepType !== "collect") continue;
      if (state.stepProgress[i]) continue;
      if (!locationMatches(step.spawnLocation, combatLocation)) continue;
      out.push({ questName: def.name, stepIdx: i, step });
    }
  }
  return out;
}

/**
 * Every active kill step whose `spawn_location` resolves to the given
 * `combatLocation` (per `locationMatches`). Used by TownScene on
 * interior entry to figure out which encounters to spawn — and how
 * many copies of each — so a player who accepted "Rat Problem" sees
 * the rats actually appear in the shop floor.
 */
export function activeKillStepsForLocation(
  defs: QuestDef[],
  states: Map<string, QuestState>,
  combatLocation: string,
): Array<{ questName: string; stepIdx: number; step: QuestStep; remaining: number }> {
  const out: Array<{ questName: string; stepIdx: number; step: QuestStep; remaining: number }> = [];
  for (const def of defs) {
    const state = states.get(def.name);
    if (!state || state.status !== "active") continue;
    for (let i = 0; i < def.steps.length; i++) {
      const step = def.steps[i];
      if (step.stepType !== "kill") continue;
      if (state.stepProgress[i]) continue;
      if (!step.encounter) continue;
      if (!locationMatches(step.spawnLocation, combatLocation)) continue;
      const done = state.stepKills[i] ?? 0;
      const remaining = Math.max(0, step.targetCount - done);
      if (remaining <= 0) continue;
      out.push({ questName: def.name, stepIdx: i, step, remaining });
    }
  }
  return out;
}

// ── Acceptance / turn-in ───────────────────────────────────────

export function acceptQuest(states: Map<string, QuestState>, questName: string): boolean {
  const state = states.get(questName);
  if (!state || state.status !== "available") return false;
  state.status = "active";
  return true;
}

export function markTurnedIn(states: Map<string, QuestState>, questName: string): boolean {
  const state = states.get(questName);
  if (!state || state.status !== "completed") return false;
  state.status = "turned_in";
  return true;
}

// ── World-unlock application ───────────────────────────────────

/**
 * Display name for a tile id — falls back to "Tile <id>" when the
 * runtime def table doesn't recognise it. Mirrors the Python
 * `world_unlock_tile_name` so reward summary text reads identically
 * across the two ports ("World changed: Bridge at (5,13)").
 */
export function worldUnlockTileName(tileId: number): string {
  const name = tileDef(tileId).name;
  return name && name !== "Unknown" ? name : `Tile ${tileId}`;
}

/**
 * Apply a list of world-unlock ops to *tileMap* in place. Returns
 * the entries that actually landed — useful for the reward summary
 * the turn-in dialog shows. Bad / out-of-bounds entries are skipped
 * silently so a malformed quests.json never crashes a run.
 *
 * Mirrors `apply_world_unlocks` in `src/module_editor_quest.py`.
 */
export function applyWorldUnlocks(
  tileMap: TileMap | null | undefined,
  unlocks: readonly WorldUnlock[] | null | undefined,
): AppliedUnlock[] {
  const applied: AppliedUnlock[] = [];
  if (!tileMap || !unlocks || unlocks.length === 0) return applied;
  for (const op of unlocks) {
    if (!op || typeof op !== "object") continue;
    const c = op.col;
    const r = op.row;
    const t = op.tile;
    if (!Number.isFinite(c) || !Number.isFinite(r) || !Number.isFinite(t)) continue;
    if (c < 0 || c >= tileMap.width || r < 0 || r >= tileMap.height) continue;
    tileMap.setTile(c, r, t);
    applied.push([c, r, t]);
  }
  return applied;
}

/**
 * Re-apply every turned-in quest's world unlocks to the overworld
 * tile map. Called by OverworldScene after `loadTileMap()` so the
 * reward survives the natural "fetch fresh JSON on every scene
 * boot" lifecycle of the web port — same idempotent design the
 * Python game's save/load path uses (see
 * `_apply_turned_in_world_unlocks` in `src/save_load.py`).
 *
 * Returns the flat list of applied triples in the order they were
 * walked, mainly for tests and the resume-time reward log.
 */
export function applyTurnedInWorldUnlocks(
  tileMap: TileMap | null | undefined,
  defs: QuestDef[],
  states: Map<string, QuestState>,
): AppliedUnlock[] {
  const applied: AppliedUnlock[] = [];
  if (!tileMap) return applied;
  for (const def of defs) {
    if (def.rewardWorldUnlocks.length === 0) continue;
    const state = states.get(def.name);
    if (!state || state.status !== "turned_in") continue;
    for (const a of applyWorldUnlocks(tileMap, def.rewardWorldUnlocks)) {
      applied.push(a);
    }
  }
  return applied;
}

/**
 * Build a short description of an applied world-unlock list — used
 * by the turn-in reward summary line. Single-tile unlocks name the
 * tile and coords ("Bridge at (5,13)"); multi-tile unlocks roll up
 * to a count to keep the dialog from overflowing.
 */
export function summariseUnlocks(applied: readonly AppliedUnlock[]): string {
  if (applied.length === 0) return "";
  if (applied.length === 1) {
    const [c, r, t] = applied[0];
    return `World changed: ${worldUnlockTileName(t)} at (${c},${r})`;
  }
  return `World changed: ${applied.length} tiles updated`;
}

// ── Misc helpers ────────────────────────────────────────────────

/**
 * Build a short adventurer's-note line listing the dungeons referenced
 * by a quest's steps + a hint when a guardian fight is coming. Empty
 * string when the quest doesn't go into any dungeon.
 *
 * Mirrors `build_quest_location_hint` in quest_manager.py.
 */
export function locationHint(def: QuestDef): string {
  const dungeons: string[] = [];
  let hasGuardian = false;
  for (const step of def.steps) {
    if (step.spawnLocation.startsWith("dungeon:")) {
      const name = step.spawnLocation.slice("dungeon:".length).trim();
      if (name && !dungeons.includes(name)) dungeons.push(name);
    }
    if (step.hasGuardian) hasGuardian = true;
  }
  if (dungeons.length === 0) return "";
  let line: string;
  if (dungeons.length === 1) {
    line = `[Adventurer's Note: This quest will take you into the ${dungeons[0]} dungeon — tread carefully.]`;
  } else {
    const head = dungeons.slice(0, -1).join(", ");
    const tail = dungeons[dungeons.length - 1];
    line = `[Adventurer's Note: This quest will take you into the following dungeons: ${head} and ${tail}.]`;
  }
  if (hasGuardian) {
    line = line.slice(0, -1) + " A powerful guardian is said to watch over what you seek.]";
  }
  return line;
}

/** Sample roster for a kill step's encounter — surfaces the monster
 *  catalog so the dungeon scene's combat dispatch builds the right
 *  encounter rather than rolling a random one. Returns null if the
 *  encounter name isn't found. */
export function rosterFor(
  encounters: Record<string, EncounterTemplate[]>,
  encounterName: string,
): EncounterTemplate | null {
  for (const list of Object.values(encounters)) {
    for (const e of list) if (e.name === encounterName) return e;
  }
  return null;
}

// Re-export a small typed alias for the sampler so consumers don't
// need to reach into Encounters.ts directly.
export { sampleEncounter };
