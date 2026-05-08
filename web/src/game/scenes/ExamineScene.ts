/**
 * Examine scene — zoomed-in 12×14 area view of the current overworld
 * tile. Port of `src/states/examine.py`.
 *
 * Triggered when the player presses E on the overworld. Rangers and
 * Alchemists in the active party get a one-time INT save to discover
 * a free reagent on first visit, plus their presence doubles the
 * weight of `_reagent_` rolls in the random ground-loot table. Layouts
 * are cached in `gameState.examineLayouts` so re-entering a tile shows
 * the same scene the party left behind.
 */

import Phaser from "phaser";
import { gameState } from "../state";
import { activeMembers } from "../world/Party";
import { dataPath } from "../world/Module";
import {
  tileDef,
  tileSpriteKey,
  PLAYER_SPRITE,
  populateRuntimeDefs,
  spriteManifest,
} from "../world/Tiles";
import {
  EXAMINE_COLS, EXAMINE_ROWS, EXAMINE_START_COL, EXAMINE_START_ROW,
  generateExamineLayout, attemptHerbalistDiscovery, hasHerbalist,
  themeForExamine, floorTileFor, edgeTileFor,
  type ExamineLayout, type ObstacleKind,
} from "../world/Examine";

const TILE = 32;
const GRID_X = 64;
const GRID_Y = 80;

interface ExamineSceneData {
  /** Overworld column the party is standing on. */
  col: number;
  /** Overworld row the party is standing on. */
  row: number;
  /** Underlying overworld tile id at (col, row) — used to theme the
   *  area and pick the obstacle/loot profile. */
  tileId: number;
}

export class ExamineScene extends Phaser.Scene {
  private layout!: ExamineLayout;
  private overworldCol = 0;
  private overworldRow = 0;

  private playerCol = EXAMINE_START_COL;
  private playerRow = EXAMINE_START_ROW;
  private player!: Phaser.GameObjects.Image;

  private obstacleSprites = new Map<string, Phaser.GameObjects.Graphics>();
  private itemSprites = new Map<string, Phaser.GameObjects.Text>();
  private pickupText!: Phaser.GameObjects.Text;
  private busy = false;
  private msgClearTimer?: Phaser.Time.TimerEvent;

  constructor() {
    super({ key: "ExamineScene" });
  }

  init(data?: ExamineSceneData): void {
    this.overworldCol = data?.col ?? 0;
    this.overworldRow = data?.row ?? 0;
    this.playerCol = EXAMINE_START_COL;
    this.playerRow = EXAMINE_START_ROW;
    this.busy = false;
    this.obstacleSprites = new Map();
    this.itemSprites = new Map();
    const tileName = tileDef(data?.tileId ?? 0).name;
    const key = `${this.overworldCol},${this.overworldRow}`;

    let cached = gameState.examineLayouts.get(key);
    let firstVisit = false;
    if (!cached) {
      const members = gameState.partyData ? activeMembers(gameState.partyData) : [];
      cached = generateExamineLayout(
        data?.tileId ?? 0, tileName, members, Math.random,
      );
      gameState.examineLayouts.set(key, cached);
      firstVisit = true;
    }
    this.layout = cached;
    this._firstVisit = firstVisit;
  }

  /** Set in init(); read in create() to decide whether to run the
   *  herbalist INT-save discovery + show its message. */
  private _firstVisit = false;

  preload(): void {
    this.textures.on("addtexture", (k: string) => {
      const tex = this.textures.get(k);
      if (tex) tex.setFilter(Phaser.Textures.FilterMode.NEAREST);
    });
    // Phaser dedupes by key, so re-queueing sprites that another
    // scene already loaded is a no-op. We still queue them all so
    // ExamineScene works as a cold boot too.
    if (!this.textures.exists(PLAYER_SPRITE)) {
      this.load.image(PLAYER_SPRITE, PLAYER_SPRITE);
    }
    this.load.json("tile_defs_examine", dataPath("tile_defs.json"));
    this.load.once("filecomplete-json-tile_defs_examine", () => {
      const raw = this.cache.json.get("tile_defs_examine");
      if (raw) populateRuntimeDefs(raw);
      // Now that the runtime tile defs are populated, enqueue every
      // sprite the manifest describes — TownScene uses the same
      // pattern. We need at minimum grass / forest / sand / path /
      // mountain so the themed examine grid can paint real tiles.
      for (const { key, path } of spriteManifest()) {
        if (!this.textures.exists(key)) this.load.image(key, path);
      }
    });
    // Pre-queue what the hardcoded DEFS table can already see — gets
    // grass + forest + the rest of the overworld set into cache
    // before the JSON arrives.
    for (const { key, path } of spriteManifest()) {
      if (!this.textures.exists(key)) this.load.image(key, path);
    }
  }

  create(): void {
    this.cameras.main.setBackgroundColor("#0a0a14");
    this.drawGrid();
    this.drawObstacles();
    this.drawItems();
    this.drawPlayer();
    this.drawPanel();
    this.installInput();

    // First-visit herbalist INT save — same trigger window as Python.
    if (this._firstVisit && gameState.partyData) {
      const members = activeMembers(gameState.partyData);
      if (hasHerbalist(members) && !this.layout.reagentsSearched) {
        const found = attemptHerbalistDiscovery(
          gameState.partyData, members, Math.random,
        );
        this.layout.reagentsSearched = true;
        if (found.length > 0) {
          const lines = found.map((f) => `${f.member} discovered ${f.reagent}`);
          this.showMessage(`${lines.join(" · ")}!`, 4000);
        }
      }
    } else if (this.layout.reagentsSearched
               && gameState.partyData
               && hasHerbalist(activeMembers(gameState.partyData))) {
      this.showMessage(
        "The party already combed this area for reagents.", 3000,
      );
    }
  }

  // ── Static rendering ─────────────────────────────────────────────

  private drawGrid(): void {
    const theme = themeForExamine(this.layout.tileType);
    for (let r = 0; r < EXAMINE_ROWS; r++) {
      for (let c = 0; c < EXAMINE_COLS; c++) {
        const x = GRID_X + c * TILE;
        const y = GRID_Y + r * TILE;
        const isEdge = (c === 0 || c === EXAMINE_COLS - 1
                        || r === 0 || r === EXAMINE_ROWS - 1);
        const tileId = isEdge
          ? edgeTileFor(this.layout.tileType)
          : floorTileFor(this.layout.tileType, c, r);
        const key = tileSpriteKey(tileId);
        if (key && this.textures.exists(key)) {
          this.add.image(x, y, key).setOrigin(0);
        } else {
          // Fallback: themed colour rectangle if the sprite isn't in
          // cache (offline run, missing asset, etc.).
          const fill = isEdge ? theme.edge : theme.floor;
          this.add.rectangle(x, y, TILE, TILE, fill).setOrigin(0);
        }
      }
    }
    // Outer frame so the grid reads as a discrete area, not a torn
    // viewport edge.
    this.add
      .rectangle(GRID_X, GRID_Y, EXAMINE_COLS * TILE, EXAMINE_ROWS * TILE)
      .setOrigin(0)
      .setStrokeStyle(2, 0x1a1a2e)
      .setFillStyle(0x000000, 0);
  }

  private drawObstacles(): void {
    const theme = themeForExamine(this.layout.tileType);
    for (const [key, kind] of this.layout.obstacles) {
      const [c, r] = key.split(",").map(Number);
      const cx = GRID_X + c * TILE + TILE / 2;
      const cy = GRID_Y + r * TILE + TILE / 2;
      const g = this.add.graphics().setDepth(2);
      this.paintObstacle(g, kind, cx, cy, theme.obstacle);
      this.obstacleSprites.set(key, g);
    }
  }

  /** Procedural obstacle painter — bushes, trees, and rocks all use
   *  the same palette but different silhouettes. */
  private paintObstacle(
    g: Phaser.GameObjects.Graphics,
    kind: ObstacleKind,
    cx: number, cy: number,
    color: number,
  ): void {
    g.clear();
    if (kind === "tree") {
      // Trunk + canopy
      g.fillStyle(0x553a1a, 1);
      g.fillRect(cx - 2, cy + 2, 4, 8);
      g.fillStyle(color, 1);
      g.fillCircle(cx,     cy - 4, 8);
      g.fillCircle(cx - 6, cy + 1, 6);
      g.fillCircle(cx + 6, cy + 1, 6);
    } else if (kind === "bush") {
      g.fillStyle(color, 1);
      g.fillCircle(cx,     cy + 2, 7);
      g.fillCircle(cx - 5, cy + 4, 5);
      g.fillCircle(cx + 5, cy + 4, 5);
    } else {
      // rock
      g.fillStyle(color, 1);
      g.fillCircle(cx, cy + 2, 8);
      g.fillStyle(0xffffff, 0.18);
      g.fillCircle(cx - 2, cy - 1, 3);
    }
  }

  private drawItems(): void {
    for (const [key] of this.layout.groundItems) {
      this.drawItemAt(key);
    }
  }

  private drawItemAt(key: string): void {
    const [c, r] = key.split(",").map(Number);
    const cx = GRID_X + c * TILE + TILE / 2;
    const cy = GRID_Y + r * TILE + TILE / 2;
    const star = this.add
      .text(cx, cy, "★", {
        fontFamily: "Georgia, serif",
        fontSize: "20px",
        color: "#ffd470",
        stroke: "#1a1a2e",
        strokeThickness: 3,
      })
      .setOrigin(0.5)
      .setDepth(3);
    this.itemSprites.set(key, star);
  }

  private drawPlayer(): void {
    const x = GRID_X + this.playerCol * TILE + TILE / 2;
    const y = GRID_Y + this.playerRow * TILE + TILE / 2;
    this.player = this.add.image(x, y, PLAYER_SPRITE).setDepth(10);
  }

  private drawPanel(): void {
    const px = GRID_X + EXAMINE_COLS * TILE + 24;
    let py = GRID_Y;
    const tileNameSurf = this.add
      .text(px, py, `Examining: ${this.layout.tileName}`, {
        fontFamily: "Georgia, serif",
        fontSize: "18px",
        color: "#f6efd6",
      });
    py += tileNameSurf.height + 12;
    this.add.rectangle(px, py, 220, 1, 0x3c3c64).setOrigin(0);
    py += 12;
    for (const line of [
      "Arrow keys / WASD: Move",
      "Step on ★ to pick up",
      "E or Esc: Return",
    ]) {
      this.add.text(px, py, line, {
        fontFamily: "monospace",
        fontSize: "12px",
        color: "#bdb38a",
      });
      py += 18;
    }
    this.pickupText = this.add
      .text(px, py + 14, "", {
        fontFamily: "monospace",
        fontSize: "13px",
        color: "#ffd470",
        wordWrap: { width: 220 },
      });
  }

  // ── Input + movement ─────────────────────────────────────────────

  private installInput(): void {
    const k = this.input.keyboard;
    if (!k) return;
    k.addCapture(["W", "A", "S", "D", "UP", "DOWN", "LEFT", "RIGHT", "E", "ESC"]);
    const map: Record<string, [number, number]> = {
      W: [0, -1], UP: [0, -1],
      S: [0, 1],  DOWN: [0, 1],
      A: [-1, 0], LEFT: [-1, 0],
      D: [1, 0],  RIGHT: [1, 0],
    };
    for (const [key, delta] of Object.entries(map)) {
      k.on(`keydown-${key}`, () => this.tryMove(delta[0], delta[1]));
    }
    k.on("keydown-E", () => this.exit());
    k.on("keydown-ESC", () => this.exit());
  }

  private tryMove(dc: number, dr: number): void {
    if (this.busy) return;
    const nc = this.playerCol + dc;
    const nr = this.playerRow + dr;
    // Interior bounds — exclude the outer ring.
    if (nc < 1 || nc > EXAMINE_COLS - 2) return;
    if (nr < 1 || nr > EXAMINE_ROWS - 2) return;
    const key = `${nc},${nr}`;
    if (this.layout.obstacles.has(key)) return;
    this.playerCol = nc;
    this.playerRow = nr;
    this.busy = true;
    this.tweens.add({
      targets: this.player,
      x: GRID_X + nc * TILE + TILE / 2,
      y: GRID_Y + nr * TILE + TILE / 2,
      duration: 90,
      onComplete: () => {
        this.busy = false;
        this.tryPickup();
      },
    });
  }

  private tryPickup(): void {
    const key = `${this.playerCol},${this.playerRow}`;
    const loot = this.layout.groundItems.get(key);
    if (!loot) return;
    this.layout.groundItems.delete(key);
    if (gameState.partyData) {
      gameState.partyData.inventory.push({ item: loot.item });
    }
    const sprite = this.itemSprites.get(key);
    sprite?.destroy();
    this.itemSprites.delete(key);
    this.showMessage(`Picked up ${loot.item}!`, 2000);
  }

  private showMessage(text: string, durationMs: number): void {
    this.pickupText.setText(text);
    if (this.msgClearTimer) {
      this.msgClearTimer.remove(false);
    }
    this.msgClearTimer = this.time.delayedCall(durationMs, () => {
      this.pickupText.setText("");
    });
  }

  private exit(): void {
    // Layout already lives in gameState.examineLayouts (we kept a
    // reference at init time and have been mutating it in place).
    this.cameras.main.fadeOut(180, 0, 0, 0);
    this.cameras.main.once("camerafadeoutcomplete", () => {
      this.scene.start("OverworldScene");
    });
  }
}
