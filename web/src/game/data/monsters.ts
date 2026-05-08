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
  /** "land" (default) or "sea". Sea creatures can attack the party
   *  while they're aboard a boat; land creatures cannot. Mirrors the
   *  Python `monsters.json` `terrain` field. */
  terrain?: "land" | "sea";
  /** Multi-tile sprite scale. Default 1 (32×32). 2 → 64×64 — used by
   *  Dragons and Man Eaters so a boss reads as a boss on the grid. */
  battleScale?: number;
  /** Spell-casting AI table. Each entry has a `cast_chance` (0-100)
   *  the engine rolls against on the monster's turn; the first
   *  passing spell with a valid target gets cast. */
  monsterSpells?: MonsterSpell[];
  /** Always-on effects — regen amount, fire/poison resistance, etc. */
  passives?: MonsterPassive[];
  /** Triggered effects on a successful melee hit: drain HP back into
   *  the attacker, "consume" debuff that ticks damage each turn, … */
  onHitEffects?: MonsterOnHit[];
  /** Extra tiles of movement granted after a successful attack —
   *  Dragons hit-and-run with `post_attack_move: 2`. Default 0. */
  postAttackMove?: number;
  /** Whether the creature is humanoid. Used by spells that target
   *  only humanoids (Charm in the Python game). */
  humanoid?: boolean;
  /** "easy" / "moderate" / "hard" / "deadly" / "boss" — flavour tag
   *  carried for HUD labels and possibly future scaling. */
  difficulty?: string;
}

export type MonsterSpellType =
  | "breath_fire"
  | "magic_dart"
  | "magic_arrow"
  | "fireball"
  | "lightning_bolt"
  | "sleep"
  | "curse"
  | "poison"
  | "heal_self"
  | "heal_ally";

export interface MonsterSpell {
  type: MonsterSpellType;
  name: string;
  /** 0-100 chance to attempt the cast on the monster's turn. */
  castChance: number;
  /** Tile range — used both to pick targets and to gate the cast. */
  range?: number;
  damageDice?: number;
  damageSides?: number;
  damageBonus?: number;
  healDice?: number;
  healSides?: number;
  healBonus?: number;
  saveDc?: number;
  duration?: number;
  /** Sleep-style spells refuse targets above this HP threshold. */
  maxTargetHp?: number;
  acPenalty?: number;
  attackPenalty?: number;
  damagePerTurn?: number;
}

export type MonsterPassive =
  | { type: "regen"; amount: number }
  | { type: "fire_resistance" }
  | { type: "poison_immunity" };

export type MonsterOnHit =
  | { type: "drain"; chance: number; amount: number }
  | { type: "consume"; chance: number; damagePerTurn: number; saveDc: number };

interface RawMonsterSpell {
  type?: string;
  name?: string;
  cast_chance?: number;
  range?: number;
  damage_dice?: number;
  damage_sides?: number;
  damage_bonus?: number;
  heal_dice?: number;
  heal_sides?: number;
  heal_bonus?: number;
  save_dc?: number;
  duration?: number;
  max_target_hp?: number;
  ac_penalty?: number;
  attack_penalty?: number;
  damage_per_turn?: number;
}

interface RawMonsterPassive {
  type?: string;
  amount?: number;
}

interface RawMonsterOnHit {
  type?: string;
  chance?: number;
  amount?: number;
  damage_per_turn?: number;
  save_dc?: number;
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
  terrain?: string;
  battle_scale?: number;
  spells?: RawMonsterSpell[] | null;
  passives?: RawMonsterPassive[] | null;
  on_hit_effects?: RawMonsterOnHit[] | null;
  post_attack_move?: number;
  humanoid?: boolean;
  difficulty?: string;
}

const KNOWN_SPELL_TYPES: ReadonlySet<string> = new Set([
  "breath_fire", "magic_dart", "magic_arrow", "fireball",
  "lightning_bolt", "sleep", "curse", "poison",
  "heal_self", "heal_ally",
]);

function spellFromRaw(s: RawMonsterSpell): MonsterSpell | null {
  if (!s.type || !KNOWN_SPELL_TYPES.has(s.type)) return null;
  return {
    type: s.type as MonsterSpellType,
    name: s.name ?? s.type,
    castChance: typeof s.cast_chance === "number" ? s.cast_chance : 0,
    range: s.range,
    damageDice: s.damage_dice,
    damageSides: s.damage_sides,
    damageBonus: s.damage_bonus,
    healDice: s.heal_dice,
    healSides: s.heal_sides,
    healBonus: s.heal_bonus,
    saveDc: s.save_dc,
    duration: s.duration,
    maxTargetHp: s.max_target_hp,
    acPenalty: s.ac_penalty,
    attackPenalty: s.attack_penalty,
    damagePerTurn: s.damage_per_turn,
  };
}

function passiveFromRaw(p: RawMonsterPassive): MonsterPassive | null {
  if (p.type === "regen") {
    return { type: "regen", amount: typeof p.amount === "number" ? p.amount : 1 };
  }
  if (p.type === "fire_resistance")  return { type: "fire_resistance" };
  if (p.type === "poison_immunity")  return { type: "poison_immunity" };
  return null;
}

function onHitFromRaw(h: RawMonsterOnHit): MonsterOnHit | null {
  if (h.type === "drain") {
    return {
      type: "drain",
      chance: typeof h.chance === "number" ? h.chance : 0,
      amount: typeof h.amount === "number" ? h.amount : 0,
    };
  }
  if (h.type === "consume") {
    return {
      type: "consume",
      chance: typeof h.chance === "number" ? h.chance : 0,
      damagePerTurn: typeof h.damage_per_turn === "number" ? h.damage_per_turn : 1,
      saveDc: typeof h.save_dc === "number" ? h.save_dc : 12,
    };
  }
  return null;
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
    terrain: raw.terrain === "sea" ? "sea" : "land",
    battleScale: typeof raw.battle_scale === "number" ? raw.battle_scale : 1,
    monsterSpells: Array.isArray(raw.spells)
      ? raw.spells.map(spellFromRaw).filter((x): x is MonsterSpell => x !== null)
      : undefined,
    passives: Array.isArray(raw.passives)
      ? raw.passives.map(passiveFromRaw).filter((x): x is MonsterPassive => x !== null)
      : undefined,
    onHitEffects: Array.isArray(raw.on_hit_effects)
      ? raw.on_hit_effects.map(onHitFromRaw).filter((x): x is MonsterOnHit => x !== null)
      : undefined,
    postAttackMove: typeof raw.post_attack_move === "number" ? raw.post_attack_move : 0,
    humanoid: !!raw.humanoid,
    difficulty: raw.difficulty,
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
    battleScale: spec.battleScale,
    monsterSpells: spec.monsterSpells,
    passives: spec.passives,
    onHitEffects: spec.onHitEffects,
    postAttackMove: spec.postAttackMove,
    humanoid: spec.humanoid,
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
