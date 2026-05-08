/**
 * Dungeon Phaser scene.
 *
 * Renders one floor of a procedurally generated dungeon, walks the
 * party tile-by-tile, and dispatches to CombatScene on monster
 * contact. Mirrors the relevant subset of `src/states/dungeon.py`:
 *
 *   - Cached generation: dungeons are generated once on first entry
 *     and reused on every re-visit (the cache lives on `gameState`).
 *   - Multi-level: stairs-down descend; stairs-up ascend (or exit to
 *     the overworld on floor 0 / on a tile recorded in the level's
 *     `overworldExits` set).
 *   - Chests: gold + a basic random pickup, then the chest tile is
 *     replaced with the level's native floor tile.
 *   - Traps: random alive party member takes 3–8 damage; trap tile
 *     is replaced with floor.
 *   - Locked doors: render and block movement. Pick-lock UX waits
 *     for the Lock port to mature.
 *   - Wall torches + party-radius lighting via `Lighting.ts`.
 *   - Fog of war: tiles not yet seen render black.
 *
 * Exit data on the way back to the overworld is the same shape that
 * OverworldScene's tilemap already understands — `gameState.playerPos`
 * is left at the dungeon entrance tile.
 */

import Phaser from "phaser";
import { gameState } from "../state";
import {
  tileDef,
  PLAYER_SPRITE,
  spriteManifest,
  tileSpriteKey,
  populateRuntimeDefs,
} from "../world/Tiles";
import { dataPath } from "../world/Module";
import {
  loadDungeons,
  getDungeonByName,
  type DungeonDef,
} from "../world/Dungeons";
import {
  loadEncounters,
  type EncounterTemplate,
} from "../world/Encounters";
import {
  generateDungeon,
  dungeonSeed,
  styleFloorTile,
  TILE_STAIRS,
  TILE_STAIRS_DOWN,
  TILE_CHEST,
  TILE_TRAP,
  type DungeonLevel,
  type DungeonMonster,
} from "../world/Dungeon";
import {
  TILE_FOREST_ARCHWAY_UP,
  TILE_FOREST_ARCHWAY_DOWN,
  TILE_LOCKED_DOOR,
} from "../world/Tiles";
import {
  loadParty,
  activeMembers,
  type Party,
} from "../world/Party";
import {
  partyLightRadius,
  tickGaladrielsLight,
} from "../world/PartyActions";
import {
  advanceClock,
} from "../world/GameTime";
import { brightnessAt, type LightSource } from "../world/Lighting";

const TILE = 32;
const HUD_HEIGHT = 56;

// Visual-tier thresholds for the fog-of-war fade. Cells the party has
// stepped into render at the brightness their lighting computation
// gives them; cells they've seen but aren't lighting up now render
// dimmed; never-seen cells render fully black so the unexplored
// portion of the level stays a mystery.
const SEEN_DIM = 0.55;

interface DungeonSceneData {
  /** Display name from dungeons.json — keys into the cache. */
  dungeonName: string;
  /** Overworld tile this dungeon hangs off of. */
  overworldCol: number;
  overworldRow: number;
}

const _ASCEND_TILES: ReadonlySet<number> = new Set([TILE_STAIRS, TILE_FOREST_ARCHWAY_UP]);
const _DESCEND_TILES: ReadonlySet<number> = new Set([TILE_STAIRS_DOWN, TILE_FOREST_ARCHWAY_DOWN]);

export class DungeonScene extends Phaser.Scene {
  private dungeonName = "";
  private overworldCol = 0;
  private overworldRow = 0;
  private levels: DungeonLevel[] = [];
  private currentLevel = 0;
  private level!: DungeonLevel;
  private partyData: Party | null = null;
  private encounterTable: Record<string, EncounterTemplate[]> | null = null;
  private dungeonDef: DungeonDef | null = null;

  // Phaser objects
  private tileSprites: Phaser.GameObjects.GameObject[][] = [];
  private decorSprites: Map<string, Phaser.GameObjects.GameObject> = new Map();
  private monsterSprites: Map<string, Phaser.GameObjects.GameObject> = new Map();
  private darknessRects: Map<string, Phaser.GameObjects.Rectangle> = new Map();
  private player!: Phaser.GameObjects.Image;
  private status!: Phaser.GameObjects.Text;
  private hpSummary!: Phaser.GameObjects.Text;
  private hint!: Phaser.GameObjects.Text;
  private message?: Phaser.GameObjects.Text;
  private messageTimer?: Phaser.Time.TimerEvent;

  private busy = false;

  constructor() {
    super({ key: "DungeonScene" });
  }

  init(data?: DungeonSceneData): void {
    this.dungeonName = data?.dungeonName ?? "";
    this.overworldCol = data?.overworldCol ?? 0;
    this.overworldRow = data?.overworldRow ?? 0;
    this.levels = [];
    this.currentLevel = 0;
    this.tileSprites = [];
    this.decorSprites = new Map();
    this.monsterSprites = new Map();
    this.darknessRects = new Map();
    this.busy = false;
    this.message = undefined;
    this.messageTimer = undefined;
  }

  preload(): void {
    this.textures.on("addtexture", (key: string) => {
      const tex = this.textures.get(key);
      if (tex) tex.setFilter(Phaser.Textures.FilterMode.NEAREST);
    });
    // Two-phase load mirrors OverworldScene/TownScene: tile_defs.json
    // first so the runtime def table is populated, then sprites for
    // every declared tile id.
    this.load.json("tile_defs", dataPath("tile_defs.json"));
    this.load.once("filecomplete-json-tile_defs", () => {
      const raw = this.cache.json.get("tile_defs");
      if (raw) populateRuntimeDefs(raw);
      for (const { key, path } of spriteManifest()) {
        this.load.image(key, path);
      }
    });
    for (const { key, path } of spriteManifest()) {
      this.load.image(key, path);
    }
    this.load.image("player", PLAYER_SPRITE);
  }

  async create(): Promise<void> {
    this.cameras.main.setBackgroundColor("#0c0c14");

    try {
      this.partyData = await loadParty();
      gameState.partyData = this.partyData;
    } catch {
      this.partyData = gameState.partyData;
    }

    try {
      const defs = await loadDungeons();
      this.dungeonDef = getDungeonByName(defs, this.dungeonName);
    } catch (err) {
      this.fatal(`Failed to load dungeons.json: ${(err as Error).message}`);
      return;
    }
    if (!this.dungeonDef) {
      this.fatal(`Dungeon "${this.dungeonName}" not found in dungeons.json`);
      return;
    }
    if (this.dungeonDef.mode !== "procedural") {
      this.fatal(`Dungeon "${this.dungeonName}" is in custom mode — only procedural is supported.`);
      return;
    }

    try {
      this.encounterTable = await loadEncounters();
    } catch {
      this.encounterTable = null;
    }

    // Cache lookup (the "generate once" guarantee). Miss → generate
    // a fresh multi-level dungeon and store it; hit → reuse the
    // mutable level objects so explored tiles, opened chests, etc.,
    // all carry over.
    const key = `${this.overworldCol},${this.overworldRow}`;
    let cached = gameState.dungeonCache.get(key);
    if (!cached) {
      cached = generateDungeon({
        name: this.dungeonDef.name,
        style: this.dungeonDef.style,
        numLevels: this.dungeonDef.numLevels,
        difficulty: this.dungeonDef.difficulty,
        levelSize: this.dungeonDef.levelSize,
        torchDensity: this.dungeonDef.torchDensity,
        lockedDoors: this.dungeonDef.lockedDoors,
        seedBase: dungeonSeed(this.dungeonDef.name, this.overworldCol, this.overworldRow),
        encounters: this.encounterTable ?? undefined,
      });
      gameState.dungeonCache.set(key, cached);
    }
    this.levels = cached;

    // Resolve player position. If gameState.dungeonPos belongs to this
    // entrance, replay it (return-from-combat / re-enter). Otherwise
    // a fresh entry — drop on floor 0 entry stairs.
    const dpos = gameState.dungeonPos;
    if (dpos && dpos.overworldCol === this.overworldCol && dpos.overworldRow === this.overworldRow) {
      this.currentLevel = Math.max(0, Math.min(this.levels.length - 1, dpos.level));
      this.level = this.levels[this.currentLevel];
    } else {
      this.currentLevel = 0;
      this.level = this.levels[0];
      gameState.dungeonPos = {
        overworldCol: this.overworldCol,
        overworldRow: this.overworldRow,
        level: 0,
        col: this.level.entryCol,
        row: this.level.entryRow,
      };
    }

    this.markExplored(gameState.dungeonPos!.col, gameState.dungeonPos!.row);
    this.drawLevel();
    this.drawPlayer();
    this.drawHud();
    this.installCamera();
    this.installInput();
    this.refreshDarkness();
    this.refreshHud();

    // Show entry message on a fresh entry (not on combat-return).
    if (!dpos || dpos.level !== this.currentLevel) {
      this.showMessage(`You enter ${this.level.name}.`, 1800);
    }
  }

  // ── Rendering ───────────────────────────────────────────────────

  private drawLevel(): void {
    // Clear any stale objects from a previous floor.
    for (const row of this.tileSprites) for (const obj of row) obj.destroy();
    this.tileSprites = [];
    for (const obj of this.decorSprites.values()) obj.destroy();
    this.decorSprites.clear();
    for (const obj of this.monsterSprites.values()) obj.destroy();
    this.monsterSprites.clear();
    for (const r of this.darknessRects.values()) r.destroy();
    this.darknessRects.clear();

    for (let row = 0; row < this.level.height; row++) {
      const rowSprites: Phaser.GameObjects.GameObject[] = [];
      for (let col = 0; col < this.level.width; col++) {
        rowSprites.push(this.drawTile(col, row));
      }
      this.tileSprites.push(rowSprites);
    }
    // Decoration overlay (puddles, moss, torches) at depth 6 — above
    // tiles, below player + darkness.
    for (const [k, tid] of Object.entries(this.level.decorations)) {
      const [c, r] = k.split(",").map((s) => parseInt(s, 10));
      if (!Number.isFinite(c) || !Number.isFinite(r)) continue;
      const key = tileSpriteKey(tid);
      const x = c * TILE;
      const y = r * TILE;
      let obj: Phaser.GameObjects.GameObject;
      if (key && this.textures.exists(key)) {
        obj = this.add.image(x, y, key).setOrigin(0).setDepth(6);
      } else {
        const def = tileDef(tid);
        obj = this.add
          .rectangle(x, y, TILE, TILE, Phaser.Display.Color.GetColor(...def.color), 0.5)
          .setOrigin(0)
          .setDepth(6);
      }
      this.decorSprites.set(k, obj);
    }
    // Monster sprites: a simple placeholder glyph until monster
    // catalog sprites are wired into the dungeon scene.
    for (const m of this.level.monsters) {
      this.drawMonster(m);
    }
    // Per-cell darkness overlay (depth 9 — above monsters, below player).
    for (let row = 0; row < this.level.height; row++) {
      for (let col = 0; col < this.level.width; col++) {
        const r = this.add
          .rectangle(col * TILE, row * TILE, TILE, TILE, 0x000000, 1)
          .setOrigin(0)
          .setDepth(9);
        this.darknessRects.set(`${col},${row}`, r);
      }
    }
  }

  private drawTile(col: number, row: number): Phaser.GameObjects.GameObject {
    const id = this.level.tiles[row][col];
    const x = col * TILE;
    const y = row * TILE;
    const key = tileSpriteKey(id);
    if (key && this.textures.exists(key)) {
      return this.add.image(x, y, key).setOrigin(0).setDepth(0);
    }
    const def = tileDef(id);
    return this.add
      .rectangle(x, y, TILE, TILE, Phaser.Display.Color.GetColor(...def.color))
      .setOrigin(0)
      .setDepth(0);
  }

  private drawMonster(m: DungeonMonster): void {
    const x = m.col * TILE + TILE / 2;
    const y = m.row * TILE + TILE / 2;
    const obj = this.add
      .text(x, y, "✦", {
        fontFamily: "Georgia, serif",
        fontSize: "20px",
        color: "#ff6b6b",
        stroke: "#1a1a2e",
        strokeThickness: 3,
      })
      .setOrigin(0.5)
      .setDepth(7);
    this.monsterSprites.set(m.id, obj);
  }

  private drawPlayer(): void {
    const dp = gameState.dungeonPos!;
    const x = dp.col * TILE + TILE / 2;
    const y = dp.row * TILE + TILE / 2;
    if (this.textures.exists("player")) {
      this.player = this.add.image(x, y, "player").setDepth(10);
    } else {
      // Fallback shouldn't ever fire — preload always queues the marker.
      this.player = this.add
        .text(x, y, "@", {
          fontFamily: "Georgia, serif",
          fontSize: "22px",
          color: "#f6efd6",
        })
        .setOrigin(0.5)
        .setDepth(10) as unknown as Phaser.GameObjects.Image;
    }
  }

  private drawHud(): void {
    this.add
      .rectangle(0, 0, 960, HUD_HEIGHT, 0x161629, 0.92)
      .setOrigin(0)
      .setScrollFactor(0)
      .setStrokeStyle(1, 0x2a2a3a);
    this.status = this.add
      .text(16, 12, "", {
        fontFamily: "Georgia, serif",
        fontSize: "16px",
        color: "#f6efd6",
      })
      .setScrollFactor(0);
    this.hpSummary = this.add
      .text(16, 32, "", {
        fontFamily: "monospace",
        fontSize: "12px",
        color: "#bdb38a",
      })
      .setScrollFactor(0);
    this.hint = this.add
      .text(960 - 16, 12, "WASD / arrows · ESC on stairs to leave", {
        fontFamily: "monospace",
        fontSize: "12px",
        color: "#bdb38a",
      })
      .setOrigin(1, 0)
      .setScrollFactor(0);
  }

  private installCamera(): void {
    this.cameras.main.setBounds(
      0,
      -HUD_HEIGHT,
      this.level.width * TILE,
      this.level.height * TILE + HUD_HEIGHT,
    );
    this.cameras.main.startFollow(this.player, true, 0.2, 0.2);
  }

  private refreshHud(): void {
    const total = this.levels.length;
    const depth = this.currentLevel + 1;
    const floorLabel = total > 1 ? `  ·  Floor ${depth}/${total}` : "";
    this.status.setText(`${this.dungeonName}${floorLabel}`);
    if (this.partyData) {
      const members = activeMembers(this.partyData);
      const summary = members
        .map((m) => `${m.name} ${Math.max(0, m.hp)}/${m.maxHp}`)
        .join("  ·  ");
      this.hpSummary.setText(summary);
    }
  }

  /**
   * Repaint the per-tile darkness overlay. Three states per cell:
   *   - never seen: pitch black (alpha 1).
   *   - seen but not lit now: dim (alpha 0.55).
   *   - currently lit by party / wall torch: alpha = 1 - brightness.
   */
  private refreshDarkness(): void {
    const dp = gameState.dungeonPos!;
    const partyR = this.partyData ? partyLightRadius(this.partyData, 2) : 2;
    const lights = this.collectLights();
    for (let row = 0; row < this.level.height; row++) {
      for (let col = 0; col < this.level.width; col++) {
        const rect = this.darknessRects.get(`${col},${row}`);
        if (!rect) continue;
        const seen = this.level.exploredTiles.has(`${col},${row}`);
        if (!seen) {
          rect.setFillStyle(0x000000, 1);
          continue;
        }
        const b = brightnessAt(col, row, lights, { col: dp.col, row: dp.row }, partyR);
        if (b <= 0) {
          rect.setFillStyle(0x000000, SEEN_DIM);
          continue;
        }
        rect.setFillStyle(0x000000, Math.max(0, Math.min(0.92, (1 - b) * 0.92)));
      }
    }
  }

  private collectLights(): LightSource[] {
    const out: LightSource[] = [];
    for (const [k, tid] of Object.entries(this.level.decorations)) {
      const def = tileDef(tid);
      if (!def.flags?.light_source) continue;
      const [c, r] = k.split(",").map((s) => parseInt(s, 10));
      if (!Number.isFinite(c) || !Number.isFinite(r)) continue;
      out.push({ col: c, row: r, radius: def.flags.light_radius ?? 3 });
    }
    return out;
  }

  // ── Movement & input ────────────────────────────────────────────

  private installInput(): void {
    this.input.keyboard?.on("keydown", (ev: KeyboardEvent) => {
      if (this.busy) return;
      if (ev.key === "Escape") { this.handleEscape(); return; }
      const dir = directionForKey(ev.key);
      if (dir) this.tryMove(dir.dc, dir.dr);
    });
  }

  private tryMove(dc: number, dr: number): void {
    const dp = gameState.dungeonPos!;
    const nc = dp.col + dc;
    const nr = dp.row + dr;
    if (nc < 0 || nc >= this.level.width || nr < 0 || nr >= this.level.height) return;
    if (!this.isWalkable(nc, nr)) {
      const t = this.level.tiles[nr][nc];
      if (t === TILE_LOCKED_DOOR) {
        this.showMessage("The door is locked.", 1500);
      }
      return;
    }
    // Engagement check — if a monster sits on the destination tile,
    // bump-into-fight (parallels the Python "step onto monster"
    // engagement model).
    const monster = this.level.monsters.find((m) => m.col === nc && m.row === nr);
    if (monster) {
      this.engageMonster(monster);
      return;
    }
    dp.col = nc;
    dp.row = nr;
    this.markExplored(nc, nr);
    advanceClock(gameState.clock);
    if (this.partyData) tickGaladrielsLight(this.partyData);
    this.busy = true;
    this.tweens.add({
      targets: this.player,
      x: nc * TILE + TILE / 2,
      y: nr * TILE + TILE / 2,
      duration: 110,
      onComplete: () => {
        this.busy = false;
        this.refreshDarkness();
        this.refreshHud();
        this.handleStandingTile();
      },
    });
  }

  /**
   * Walkability for a dungeon tile. Per-cell `tileProperties.walkable`
   * (forest tree-walls) wins; otherwise defer to `tileDef(id).walkable`.
   */
  private isWalkable(col: number, row: number): boolean {
    const props = this.level.tileProperties[`${col},${row}`];
    if (props && typeof props.walkable === "boolean") return props.walkable;
    const id = this.level.tiles[row][col];
    return tileDef(id).walkable;
  }

  private markExplored(col: number, row: number): void {
    // Mark the tile and its 8 neighbours so the seen-but-dim ring
    // around the party fills in as they walk.
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        const c = col + dc, r = row + dr;
        if (c < 0 || c >= this.level.width || r < 0 || r >= this.level.height) continue;
        this.level.exploredTiles.add(`${c},${r}`);
      }
    }
  }

  /**
   * Handle pickup / interaction on the tile the party just stepped
   * onto. Mirrors the "tile_id == TILE_*" ladder in Python's
   * dungeon.py:1654.
   */
  private handleStandingTile(): void {
    const dp = gameState.dungeonPos!;
    const id = this.level.tiles[dp.row][dp.col];
    if (id === TILE_CHEST) {
      const k = `${dp.col},${dp.row}`;
      if (!this.level.openedChests.has(k)) {
        this.level.openedChests.add(k);
        this.openChest(dp.col, dp.row);
      }
      return;
    }
    if (id === TILE_TRAP) {
      const k = `${dp.col},${dp.row}`;
      if (!this.level.triggeredTraps.has(k)) {
        this.level.triggeredTraps.add(k);
        this.triggerTrap(dp.col, dp.row);
      }
      return;
    }
    if (_ASCEND_TILES.has(id)) {
      const k = `${dp.col},${dp.row}`;
      if (this.level.overworldExits.has(k)) {
        this.showMessage("Exit to the surface! Press ESC to leave.", 2000);
      } else if (this.currentLevel > 0) {
        this.showMessage("Stairs up! Press ESC to ascend.", 1800);
      } else {
        this.showMessage("Stairs up! Press ESC to leave.", 1800);
      }
      return;
    }
    if (_DESCEND_TILES.has(id)) {
      if (this.currentLevel < this.levels.length - 1) {
        this.showMessage("Stairs leading down... press ESC to descend.", 1800);
      }
      return;
    }
  }

  private openChest(col: number, row: number): void {
    const gold = 5 + Math.floor(Math.random() * 26);
    if (this.partyData) this.partyData.gold = (this.partyData.gold ?? 0) + gold;
    // Replace the chest tile with the level's native floor so the cell
    // blends back into the surrounding map.
    const floor = styleFloorTile(this.level.style);
    this.level.tiles[row][col] = floor;
    this.replaceTileSprite(col, row);
    this.showMessage(`The party found a chest with ${gold} gold!`, 2200);
    this.refreshHud();
  }

  private triggerTrap(col: number, row: number): void {
    if (this.partyData) {
      const alive = activeMembers(this.partyData).filter((m) => m.hp > 0);
      if (alive.length > 0) {
        const victim = alive[Math.floor(Math.random() * alive.length)];
        const damage = 3 + Math.floor(Math.random() * 6);
        victim.hp = Math.max(0, victim.hp - damage);
        this.showMessage(`Trap! ${victim.name} takes ${damage} damage!`, 2000);
      }
    }
    const floor = styleFloorTile(this.level.style);
    this.level.tiles[row][col] = floor;
    this.replaceTileSprite(col, row);
    this.refreshHud();
  }

  private replaceTileSprite(col: number, row: number): void {
    const old = this.tileSprites[row][col];
    if (old) old.destroy();
    this.tileSprites[row][col] = this.drawTile(col, row);
  }

  // ── Stairs / exit ───────────────────────────────────────────────

  private handleEscape(): void {
    const dp = gameState.dungeonPos!;
    const id = this.level.tiles[dp.row][dp.col];
    const k = `${dp.col},${dp.row}`;
    if (_ASCEND_TILES.has(id)) {
      if (this.level.overworldExits.has(k)) { this.exitToOverworld(); return; }
      if (this.currentLevel > 0) { this.ascend(); return; }
      this.exitToOverworld();
      return;
    }
    if (_DESCEND_TILES.has(id)) {
      if (this.currentLevel < this.levels.length - 1) { this.descend(); return; }
      // Bottom floor descent stairs are inert — same as the Python
      // game's "stairs leading down…" feedback.
      this.showMessage("Stairs leading down...", 1500);
      return;
    }
    this.showMessage("Find the exit to escape!", 1500);
  }

  private ascend(): void {
    if (this.currentLevel <= 0) return;
    this.currentLevel -= 1;
    this.level = this.levels[this.currentLevel];
    // Drop the party on the descent stair of the level above (where
    // they came from). Falls back to the entry stair if the descent
    // stair can't be located — should only happen on a malformed
    // generation, but the fallback keeps the player on a walkable
    // tile rather than embedded in stone.
    const stair = this.findDescendStair();
    const dp = gameState.dungeonPos!;
    if (stair) { dp.col = stair.col; dp.row = stair.row; }
    else { dp.col = this.level.entryCol; dp.row = this.level.entryRow; }
    dp.level = this.currentLevel;
    this.markExplored(dp.col, dp.row);
    this.drawLevel();
    this.drawPlayer();
    this.cameras.main.setBounds(
      0,
      -HUD_HEIGHT,
      this.level.width * TILE,
      this.level.height * TILE + HUD_HEIGHT,
    );
    this.cameras.main.startFollow(this.player, true, 0.2, 0.2);
    this.refreshDarkness();
    this.refreshHud();
    this.showMessage(`You ascend... (Floor ${this.currentLevel + 1}/${this.levels.length})`, 1800);
  }

  private descend(): void {
    if (this.currentLevel >= this.levels.length - 1) return;
    this.currentLevel += 1;
    this.level = this.levels[this.currentLevel];
    const dp = gameState.dungeonPos!;
    dp.col = this.level.entryCol;
    dp.row = this.level.entryRow;
    dp.level = this.currentLevel;
    this.markExplored(dp.col, dp.row);
    this.drawLevel();
    this.drawPlayer();
    this.cameras.main.setBounds(
      0,
      -HUD_HEIGHT,
      this.level.width * TILE,
      this.level.height * TILE + HUD_HEIGHT,
    );
    this.cameras.main.startFollow(this.player, true, 0.2, 0.2);
    this.refreshDarkness();
    this.refreshHud();
    this.showMessage(`You descend... (Floor ${this.currentLevel + 1}/${this.levels.length})`, 1800);
  }

  private findDescendStair(): { col: number; row: number } | null {
    for (let r = 0; r < this.level.height; r++) {
      for (let c = 0; c < this.level.width; c++) {
        if (_DESCEND_TILES.has(this.level.tiles[r][c])) return { col: c, row: r };
      }
    }
    return null;
  }

  /**
   * Leave the dungeon back to the overworld. Dungeon state stays in
   * the cache so a future re-entry preserves explored tiles + opened
   * chests; only the in-dungeon position pointer is cleared so the
   * next entry to a *different* dungeon doesn't replay these coords.
   *
   * The overworld dungeon tile is left as-is — clearing it is a quest-
   * completion concern (Python's `_place_portal` flow) and quests
   * aren't ported yet.
   */
  private exitToOverworld(): void {
    gameState.playerPos = { col: this.overworldCol, row: this.overworldRow };
    gameState.dungeonPos = null;
    this.cameras.main.fadeOut(220, 0, 0, 0);
    this.cameras.main.once("camerafadeoutcomplete", () => {
      this.scene.start("OverworldScene");
    });
  }

  // ── Combat handoff ──────────────────────────────────────────────

  private engageMonster(m: DungeonMonster): void {
    // Don't actually move into the monster's tile — the player stays
    // on their current cell while combat resolves. This matches the
    // Python game's bump-into-fight behaviour.
    const terrainTileId = styleFloorTile(this.level.style);
    this.cameras.main.fadeOut(220, 0, 0, 0);
    this.cameras.main.once("camerafadeoutcomplete", () => {
      this.scene.start("CombatScene", {
        fromWorld: true,
        terrainTileId,
        monsterNames: m.encounterNames,
        dungeonMonsterId: m.id,
        returnSceneKey: "DungeonScene",
        returnPayload: {
          dungeonName: this.dungeonName,
          overworldCol: this.overworldCol,
          overworldRow: this.overworldRow,
        },
      });
    });
  }

  // ── UI helpers ──────────────────────────────────────────────────

  private showMessage(text: string, durationMs: number): void {
    if (this.message) this.message.destroy();
    if (this.messageTimer) this.messageTimer.remove();
    this.message = this.add
      .text(480, 720 - 24, text, {
        fontFamily: "Georgia, serif",
        fontSize: "16px",
        color: "#ffd470",
        backgroundColor: "#161629",
        padding: { x: 12, y: 6 },
      })
      .setOrigin(0.5, 1)
      .setScrollFactor(0)
      .setDepth(11);
    this.messageTimer = this.time.delayedCall(durationMs, () => {
      this.message?.destroy();
      this.message = undefined;
    });
  }

  private fatal(msg: string): void {
    this.add
      .text(480, 360, msg, {
        fontFamily: "Georgia, serif",
        fontSize: "18px",
        color: "#ff6b6b",
        align: "center",
      })
      .setOrigin(0.5)
      .setScrollFactor(0);
  }
}

function directionForKey(key: string): { dc: number; dr: number } | null {
  switch (key) {
    case "ArrowLeft":
    case "a":
    case "A":
      return { dc: -1, dr: 0 };
    case "ArrowRight":
    case "d":
    case "D":
      return { dc: 1, dr: 0 };
    case "ArrowUp":
    case "w":
    case "W":
      return { dc: 0, dr: -1 };
    case "ArrowDown":
    case "s":
    case "S":
      return { dc: 0, dr: 1 };
    default:
      return null;
  }
}
