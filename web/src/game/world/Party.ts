/**
 * Party state — roster, active members, gold, shared inventory.
 *
 * Mirrors the Python project's `data/party.json` format directly so a
 * round-trip through the module editor stays loss-less. Loaded via
 * `loadParty()` once on first access and then held in `gameState`
 * (state.ts) so HP/gold/inventory edits survive scene transitions.
 */

import { dataPath } from "./Module";
import { normalizeSpritePath } from "./Towns";

export interface EquipmentSlots {
  rightHand: string | null;
  leftHand: string | null;
  body: string | null;
  head: string | null;
}

export interface InventoryItem {
  item: string;
  /** Charges remaining for stacked / consumable items. Absent for gear. */
  charges?: number;
  /**
   * Current remaining durability for worn gear. Absent means the item
   * has never been used (start at the catalog max when equipped) or is
   * indestructible. The field travels with the entry so two copies of
   * the same item in the stash can wear independently — exactly like
   * the Python game's per-entry durability dict.
   */
  durability?: number;
}

export interface PartyMember {
  name: string;
  /** Class name, capitalised as the source data writes it (Fighter, Wizard…). */
  class: string;
  race: string;
  gender: string;
  hp: number;
  /** Starting/maximum HP — derived from `hp` at load time. */
  maxHp: number;
  /** Mana points (casters only). */
  mp?: number;
  maxMp?: number;
  strength: number;
  dexterity: number;
  /** Constitution — drives HP gain on level-up via `con_mod`.
   *  Defaults to 10 (no bonus) when the source data omits the field
   *  so legacy save files still load. */
  constitution: number;
  intelligence: number;
  wisdom: number;
  level: number;
  /** Cumulative experience points across the member's life. Used by
   *  the leveling system to decide when level-ups fire — see
   *  Leveling.ts. Mirrors the Python `Fighter.exp` field. */
  exp: number;
  equipped: EquipmentSlots;
  /**
   * Per-slot remaining durability for the items currently equipped.
   * `null` means the slot's item is indestructible (or there's nothing
   * equipped). When an item is unequipped, its current value moves
   * onto the receiving InventoryItem.durability so wear isn't lost.
   */
  equippedDurability: {
    right_hand: number | null;
    left_hand: number | null;
    body: number | null;
    head: number | null;
  };
  inventory: InventoryItem[];
  /** Resolved /assets/... path. Source path is normalised on load. */
  sprite: string;
}

export interface Party {
  startPosition: { col: number; row: number };
  gold: number;
  /** Full roster — characters available to swap in/out of the active party. */
  roster: PartyMember[];
  /** Indices into `roster` of the four members currently adventuring. */
  activeParty: number[];
  /** Up to 4 named effects active on the party (Detect Traps, Infravision…). */
  partyEffects: Record<string, string | null>;
  /** Stash — items shared across the party. */
  inventory: InventoryItem[];
  /** Remaining steps the currently-burning torch lights for. Increased
   *  by `consumeTorch`; decremented one per move in dark scenes. Mirrors the
   *  Python game's `DungeonState.torch_steps` but kept on the party so
   *  it survives transitions in this port. */
  torchSteps: number;
  /** Remaining steps before Galadriel's Light burns out. Set when the
   *  effect is equipped (from effects.json `duration`) and decremented
   *  once per move in any scene. When it hits zero, the effect is
   *  cleared from its slot — matches the Python game's
   *  `party.galadriels_light_steps`. */
  galadrielsLightSteps: number;
}

interface RawEquipped {
  right_hand?: string | null;
  left_hand?: string | null;
  body?: string | null;
  head?: string | null;
}

interface RawMember {
  name?: string;
  class?: string;
  race?: string;
  gender?: string;
  hp?: number;
  mp?: number;
  strength?: number;
  dexterity?: number;
  constitution?: number;
  intelligence?: number;
  wisdom?: number;
  level?: number;
  exp?: number;
  equipped?: RawEquipped;
  inventory?: InventoryItem[];
  sprite?: string;
}

interface RawParty {
  start_position?: { col?: number; row?: number };
  gold?: number;
  roster?: RawMember[];
  active_party?: number[];
  party_effects?: Record<string, string | null>;
  inventory?: InventoryItem[];
  torch_steps?: number;
  galadriels_light_steps?: number;
}

/**
 * If the source sprite path doesn't resolve to one of the character
 * PNGs we ship, fall back to a class-based default. e.g. a Fighter
 * with sprite `src/assets/game/npcs/shopkeep.png` (placeholder data
 * in the source) lands on `/assets/characters/fighter.png` instead.
 */
/** Folders under /public/assets/ whose PNGs the character creator
 *  exposes as avatar choices. Anything under one of these directories
 *  is accepted by `spriteForMember` and round-trips through
 *  localStorage, party.json, etc. without being squashed back to a
 *  class default. */
const HUMANOID_SPRITE_PREFIXES = [
  "/assets/characters/",
  "/assets/npcs/",
  "/assets/monsters/",
] as const;

export function spriteForMember(rawSprite: string | undefined, klass: string): string {
  const norm = normalizeSpritePath(rawSprite ?? "");
  // Accept any humanoid sprite the player picked in the creator.
  // We can't filesystem-check the file at runtime, but a valid
  // /assets/<folder>/<name>.png path is honoured as-is — broken
  // paths show a 404 in the network tab rather than silently
  // resetting the avatar.
  if (HUMANOID_SPRITE_PREFIXES.some((p) => norm.startsWith(p)) && norm.endsWith(".png")) {
    return norm;
  }
  // Otherwise fall back to /assets/characters/<class>.png.
  const fallback = `/assets/characters/${klass.toLowerCase()}.png`;
  return fallback;
}

export function memberFromRaw(raw: RawMember): PartyMember {
  const klass = raw.class ?? "Fighter";
  const hp = raw.hp ?? 0;
  return {
    name: raw.name ?? "?",
    class: klass,
    race: raw.race ?? "?",
    gender: raw.gender ?? "?",
    hp,
    maxHp: hp,
    mp: raw.mp,
    maxMp: raw.mp,
    strength: raw.strength ?? 10,
    dexterity: raw.dexterity ?? 10,
    constitution: raw.constitution ?? 10,
    intelligence: raw.intelligence ?? 10,
    wisdom: raw.wisdom ?? 10,
    level: raw.level ?? 1,
    exp: raw.exp ?? 0,
    equipped: {
      rightHand: raw.equipped?.right_hand ?? null,
      leftHand: raw.equipped?.left_hand ?? null,
      body: raw.equipped?.body ?? null,
      head: raw.equipped?.head ?? null,
    },
    // Durability trackers default to "uninitialised" — the first time
    // an item is equipped (or use_durability runs against it) the
    // helper seeds it from the catalog max. Mirrors the Python game's
    // lazy initialisation in equipped_durability.
    equippedDurability: {
      right_hand: null,
      left_hand: null,
      body: null,
      head: null,
    },
    inventory: raw.inventory ?? [],
    sprite: spriteForMember(raw.sprite, klass),
  };
}

export function partyFromRaw(raw: RawParty): Party {
  return {
    startPosition: {
      col: raw.start_position?.col ?? 0,
      row: raw.start_position?.row ?? 0,
    },
    gold: raw.gold ?? 0,
    roster: (raw.roster ?? []).map(memberFromRaw),
    activeParty: raw.active_party ?? [0, 1, 2, 3],
    partyEffects: raw.party_effects ?? {
      effect_1: null, effect_2: null, effect_3: null, effect_4: null,
    },
    inventory: raw.inventory ?? [],
    torchSteps: raw.torch_steps ?? 0,
    galadrielsLightSteps: raw.galadriels_light_steps ?? 0,
  };
}

/**
 * Inverse of `partyFromRaw` — turn a runtime Party back into the
 * snake-cased shape `data/party.json` uses, ready for JSON.stringify.
 * Used by the form-party screen to persist edits to localStorage so
 * roster changes survive a page reload.
 */
export function partyToRaw(p: Party): RawParty {
  return {
    start_position: { col: p.startPosition.col, row: p.startPosition.row },
    gold: p.gold,
    roster: p.roster.map((m) => ({
      name: m.name,
      class: m.class,
      race: m.race,
      gender: m.gender,
      hp: m.hp,
      mp: m.mp,
      strength: m.strength,
      dexterity: m.dexterity,
      constitution: m.constitution,
      intelligence: m.intelligence,
      wisdom: m.wisdom,
      level: m.level,
      exp: m.exp,
      equipped: {
        right_hand: m.equipped.rightHand ?? null,
        left_hand:  m.equipped.leftHand  ?? null,
        body:       m.equipped.body      ?? null,
        head:       m.equipped.head      ?? null,
      },
      inventory: m.inventory,
      sprite: m.sprite,
    })),
    active_party: p.activeParty,
    party_effects: p.partyEffects,
    inventory: p.inventory,
    torch_steps: p.torchSteps,
    galadriels_light_steps: p.galadrielsLightSteps,
  };
}

const STORAGE_KEY = "realm-of-shadow.roster.v1";

/**
 * Read a roster previously saved via the formation screen. Returns
 * null when nothing's been saved yet (or when running outside a
 * browser — Next's static export pre-renders pages on the server). */
export function loadStoredRoster(): Party | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return partyFromRaw(JSON.parse(raw) as RawParty);
  } catch {
    return null;
  }
}

/** Persist the current roster (and active-party selection) to
 *  localStorage so subsequent loads see the player's edits. */
export function saveStoredRoster(p: Party): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(partyToRaw(p)));
  } catch {
    /* quota / storage disabled — degrade silently */
  }
}

/** Drop any stored roster — used by the "Reset roster" button. */
export function clearStoredRoster(): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.removeItem(STORAGE_KEY); } catch { /* noop */ }
  _partyCache = null;
}

let _partyCache: Party | null = null;

/**
 * Resolve the current party. Order of preference:
 *   1. In-memory cache (set on first call this session).
 *   2. localStorage (the formation screen's edits).
 *   3. The bundled `/data/party.json` seed.
 *
 * Subsequent calls reuse the cached value so combat doesn't re-fetch
 * mid-session. Use `_clearPartyCache()` between scene boots if a
 * fresh load is needed (e.g. the formation screen just saved).
 */
export async function loadParty(url = dataPath("party.json")): Promise<Party> {
  if (_partyCache) return _partyCache;
  const stored = loadStoredRoster();
  if (stored) {
    _partyCache = stored;
    return _partyCache;
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawParty;
  _partyCache = partyFromRaw(raw);
  return _partyCache;
}

/** Return the four active PartyMember objects (in active_party order). */
export function activeMembers(p: Party): PartyMember[] {
  return p.activeParty
    .map((i) => p.roster[i])
    .filter((m): m is PartyMember => Boolean(m));
}

/** Test-only cache reset. */
export function _clearPartyCache(): void {
  _partyCache = null;
}
