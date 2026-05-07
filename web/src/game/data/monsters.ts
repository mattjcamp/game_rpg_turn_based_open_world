/**
 * Monster catalog — loads `data/monsters.json` once and exposes a
 * `makeMonsterByName(name)` helper that combat / overworld spawning
 * use to instantiate fresh enemies.
 *
 * The Python game ships a few dozen entries (everything from Giant
 * Rat through Dragon, Wyvern, Lich, Dark Mage) — keeping the runtime
 * data-driven means designer additions to monsters.json land in the
 * web port without code changes.
 *
 * A small built-in fallback set covers the four monsters used by the
 * legacy `makeSampleEncounter` so existing tests / the demo combat
 * route keep working before / without the loader being initialised.
 */

import type { Combatant } from "../types";
import { assetUrl, dataPath, BASE_PATH } from "../world/Module";

export interface MonsterSpec {
  name: string;
  hp: number;
  ac: number;
  attackBonus: number;
  damage: { dice: number; sides: number; bonus: number };
  dexMod: number;
  color: [number, number, number];
  /** /assets/... path the Phaser preloader can pull. */
  sprite: string;
  baseMoveRange: number;
  undead?: boolean;
  /** Flat XP awarded on kill (Python: monsters.json `xp_reward`). */
  xpReward?: number;
  /** Inclusive bounds for the gold roll on death (Python:
   *  `gold_min` / `gold_max`); rolled per spawn in makeMonsterByName. */
  goldMin?: number;
  goldMax?: number;
}

interface RawMonster {
  hp?: number;
  ac?: number;
  attack_bonus?: number;
  damage_dice?: number;
  damage_sides?: number;
  damage_bonus?: number;
  color?: [number, number, number] | number[];
  tile?: string;
  move_range?: number;
  undead?: boolean;
  xp_reward?: number;
  gold_min?: number;
  gold_max?: number;
}

/**
 * Built-in fallbacks — keep the demo encounter playable before the
 * JSON catalog is loaded (and serve as defaults for monsters that
 * happen to be missing from monsters.json).
 */
const BUILTIN: Record<string, MonsterSpec> = {
  "Giant Rat": {
    name: "Giant Rat", hp: 8, ac: 12, attackBonus: 2,
    damage: { dice: 1, sides: 4, bonus: 0 }, dexMod: 2,
    color: [140, 100, 80], sprite: assetUrl("/assets/monsters/giant_rat.png"),
    baseMoveRange: 5,
  },
  Goblin: {
    name: "Goblin", hp: 6, ac: 11, attackBonus: 2,
    damage: { dice: 1, sides: 4, bonus: 0 }, dexMod: 2,
    color: [100, 160, 60], sprite: assetUrl("/assets/monsters/goblin.png"),
    baseMoveRange: 4,
  },
  Skeleton: {
    name: "Skeleton", hp: 12, ac: 13, attackBonus: 3,
    damage: { dice: 1, sides: 6, bonus: 1 }, dexMod: 1,
    color: [220, 220, 200], sprite: assetUrl("/assets/monsters/skeleton.png"),
    baseMoveRange: 3, undead: true,
  },
  Orc: {
    name: "Orc", hp: 18, ac: 13, attackBonus: 4,
    damage: { dice: 1, sides: 8, bonus: 2 }, dexMod: 0,
    color: [80, 130, 70], sprite: assetUrl("/assets/monsters/orc.png"),
    baseMoveRange: 3,
  },
};

let _catalog: Map<string, MonsterSpec> | null = null;

/**
 * Normalise a monsters.json `tile` field into a `/assets/...` path:
 *   - "game/monsters/skeleton.png" → "/assets/monsters/skeleton.png"
 *   - "monsters/lich"              → "/assets/monsters/lich.png"
 *   - "/assets/foo.png"            → unchanged
 *
 * Mirrors the same path-rewriting we do for character sprites.
 */
function spritePathFromTile(tile: string | undefined): string {
  if (!tile) return "";
  // Already a runtime URL (with the active base prefix already applied) — leave alone.
  if (BASE_PATH && tile.startsWith(`${BASE_PATH}/assets/`)) return tile;
  if (!BASE_PATH && tile.startsWith("/assets/")) return tile;
  // Otherwise normalise the catalog form ("game/monsters/x" or
  // "monsters/x") and prefix with the deploy base.
  let p = tile.replace(/^\/+/, "").replace(/^assets\//, "");
  p = p.replace(/^game\//, "");                  // strip "game/" prefix
  if (!/\.[a-z]+$/i.test(p)) p = `${p}.png`;     // add .png if missing
  return assetUrl(p);
}

/** Convert one raw monster entry into the typed MonsterSpec. */
export function specFromRaw(name: string, raw: RawMonster): MonsterSpec {
  const color: [number, number, number] = Array.isArray(raw.color) && raw.color.length >= 3
    ? [Number(raw.color[0]), Number(raw.color[1]), Number(raw.color[2])]
    : [180, 80, 80];
  return {
    name,
    hp:           raw.hp ?? 10,
    ac:           raw.ac ?? 11,
    attackBonus:  raw.attack_bonus ?? 2,
    damage: {
      dice:  raw.damage_dice  ?? 1,
      sides: raw.damage_sides ?? 6,
      bonus: raw.damage_bonus ?? 0,
    },
    dexMod: 0,
    color,
    sprite: spritePathFromTile(raw.tile),
    baseMoveRange: raw.move_range ?? 3,
    undead: !!raw.undead,
    xpReward: raw.xp_reward,
    goldMin: raw.gold_min,
    goldMax: raw.gold_max,
  };
}

export async function loadMonsters(
  url = dataPath("monsters.json"),
): Promise<Map<string, MonsterSpec>> {
  if (_catalog) return _catalog;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as { monsters?: Record<string, RawMonster> };
  const m = new Map<string, MonsterSpec>();
  // Seed builtins first so they're always available, then let the
  // catalog override them with the live data.
  for (const [k, v] of Object.entries(BUILTIN)) m.set(k, v);
  for (const [name, body] of Object.entries(raw.monsters ?? {})) {
    m.set(name, specFromRaw(name, body));
  }
  _catalog = m;
  return _catalog;
}

/** Test-only escape hatch. */
export function _clearMonstersCache(): void {
  _catalog = null;
}

/**
 * Build a fresh Combatant for combat / overworld roaming. Works
 * against the loaded catalog — falls back to the small BUILTIN set
 * (and a generic "?" stub) when an unknown name is requested, so the
 * caller never crashes on missing data.
 */
export function makeMonsterByName(name: string, idSuffix = ""): Combatant {
  const spec = (_catalog && _catalog.get(name))
    ?? BUILTIN[name]
    ?? {
      name, hp: 10, ac: 11, attackBonus: 2,
      damage: { dice: 1, sides: 6, bonus: 0 }, dexMod: 0,
      color: [180, 80, 80] as [number, number, number],
      sprite: "/assets/monsters/goblin.png", baseMoveRange: 3,
    };
  // Roll gold per-spawn so two Goblins in the same fight may carry
  // different purses (matches the Python game). Inclusive on both ends.
  const goldMin = spec.goldMin ?? 0;
  const goldMax = spec.goldMax ?? goldMin;
  const goldReward = goldMax > goldMin
    ? goldMin + Math.floor(Math.random() * (goldMax - goldMin + 1))
    : goldMin;
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
    xpReward: spec.xpReward,
    goldReward,
  };
}

/** Sprite paths the preloader needs — spans the BUILTIN set plus the
 *  loaded catalog (best-effort; if the loader hasn't run yet we just
 *  ship the builtins). The CombatScene preloader still works at the
 *  union of party + every monster name we know so spawn-list creatures
 *  appear instantly when combat opens. */
export const MONSTER_SPRITES: string[] = (() => {
  const set = new Set<string>();
  for (const s of Object.values(BUILTIN)) if (s.sprite) set.add(s.sprite);
  return [...set];
})();

/** Sprites for every monster currently in the loaded catalog. */
export function loadedMonsterSprites(): string[] {
  if (!_catalog) return MONSTER_SPRITES;
  const set = new Set<string>(MONSTER_SPRITES);
  for (const s of _catalog.values()) if (s.sprite) set.add(s.sprite);
  return [...set];
}

export function makeSampleEncounter(): Combatant[] {
  return [
    makeMonsterByName("Goblin", "-1"),
    makeMonsterByName("Goblin", "-2"),
    makeMonsterByName("Skeleton"),
  ];
}
