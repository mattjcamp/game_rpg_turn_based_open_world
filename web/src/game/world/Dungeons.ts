/**
 * Module dungeon definitions loader.
 *
 * Reads `modules/<active>/dungeons.json` — the same file the Python
 * game writes from the module editor. Each entry is a dungeon spec
 * the overworld can link to via `link_map: "dungeon:<Name>"`.
 *
 * Web port honours only the procedural mode for now (per the task
 * brief: "we only need procedural"); custom-mode entries are loaded
 * but flagged so the runtime can warn rather than crashing.
 */
import { modulePath } from "./Module";
import type {
  Difficulty,
  DungeonStyle,
  LevelSize,
  TorchDensity,
} from "./Dungeon";

export interface DungeonDef {
  name: string;
  description: string;
  mode: "procedural" | "custom";
  style: DungeonStyle;
  numLevels: number;
  difficulty: Difficulty;
  levelSize: LevelSize;
  torchDensity: TorchDensity;
  lockedDoors: boolean;
}

interface RawDungeon {
  name?: string;
  description?: string;
  mode?: string;
  dungeon_style?: string;
  num_levels?: number;
  difficulty?: string;
  level_size?: string;
  torch_density?: string;
  locked_doors?: string;
}

function fromRaw(raw: RawDungeon): DungeonDef | null {
  if (!raw || typeof raw !== "object" || typeof raw.name !== "string") return null;
  const style: DungeonStyle = (() => {
    const s = raw.dungeon_style ?? "default";
    if (s === "cave" || s === "forest" || s === "ruins") return s;
    return "default";
  })();
  const difficulty: Difficulty = (() => {
    const d = raw.difficulty;
    if (d === "easy" || d === "normal" || d === "hard" || d === "deadly") return d;
    return "normal";
  })();
  const levelSize: LevelSize = (() => {
    const s = raw.level_size;
    if (s === "small" || s === "medium" || s === "large") return s;
    return "medium";
  })();
  const torchDensity: TorchDensity = (() => {
    const t = raw.torch_density;
    if (t === "none" || t === "sparse" || t === "moderate" || t === "abundant") return t;
    return "moderate";
  })();
  const mode = raw.mode === "custom" ? "custom" : "procedural";
  const numLevels = Math.max(1, Math.floor(raw.num_levels ?? 1));
  return {
    name: raw.name,
    description: typeof raw.description === "string" ? raw.description : "",
    mode,
    style,
    numLevels,
    difficulty,
    levelSize,
    torchDensity,
    lockedDoors: raw.locked_doors === "on",
  };
}

let _cache: DungeonDef[] | null = null;

export async function loadDungeons(url = modulePath("dungeons.json")): Promise<DungeonDef[]> {
  if (_cache) return _cache;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const raw = (await res.json()) as RawDungeon[];
  if (!Array.isArray(raw)) throw new Error("dungeons.json is not an array");
  _cache = raw
    .map(fromRaw)
    .filter((d): d is DungeonDef => d !== null);
  return _cache;
}

/** Test-only: clear the cache. */
export function _clearDungeonsCache(): void {
  _cache = null;
}

export function getDungeonByName(defs: DungeonDef[], name: string): DungeonDef | null {
  return defs.find((d) => d.name === name) ?? null;
}
