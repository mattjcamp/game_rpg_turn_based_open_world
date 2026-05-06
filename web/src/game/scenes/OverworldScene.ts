/**
 * Overworld Phaser scene.
 *
 * Loads the bundled overworld JSON, renders every tile as a coloured
 * rectangle, places the party avatar on the player's saved position,
 * and steps it tile-by-tile in response to keyboard / pointer input.
 * The camera follows the avatar with a soft lerp and is clamped to
 * the map bounds.
 *
 * Stepping onto an encounter trigger tile (campfire / graveyard /
 * monster spawn / explicit encounter) hands off to CombatScene with
 * the trigger's coordinates so it can be marked consumed on victory.
 */

import Phaser from "phaser";
import { TileMap, loadTileMap } from "../world/TileMap";
import {
  tileDef,
  isEncounterTrigger,
  spriteManifest,
  tileSpriteKey,
  populateRuntimeDefs,
} from "../world/Tiles";
import {
  collectLightSources,
  brightnessAt,
  mapIsDark,
  type LightSource,
} from "../world/Lighting";
import { decorationFor } from "../world/Decorations";
import { gameState, triggerKey } from "../state";
import type { Combatant } from "../types";

const TILE = 32; // matches the source PNGs' native size
const HUD_HEIGHT = 56;

export class OverworldScene extends Phaser.Scene {
  private tileMap!: TileMap;
  private player!: Phaser.GameObjects.Image;
  private status!: Phaser.GameObjects.Text;
  private hpSummary!: Phaser.GameObjects.Text;
  private hint!: Phaser.GameObjects.Text;
  private busy = false;
  private defeatOverlay?: Phaser.GameObjects.Text;
  private darkness = new Map<string, Phaser.GameObjects.Rectangle>();
  /** Renamed from `lights` to avoid colliding with Phaser.Scene.lights. */
  private mapLights: LightSource[] = [];
  private dark = false;

  constructor() {
    super({ key: "OverworldScene" });
  }

  preload(): void {
    // Crisp pixels, no smoothing — these are 32×32 tile graphics.
    this.textures.on("addtexture", (key: string) => {
      const tex = this.textures.get(key);
      if (tex) tex.setFilter(Phaser.Textures.FilterMode.NEAREST);
    });

    // Two-phase load: tile_defs.json arrives first via Phaser's loader,
    // then the listener adds every tile sprite that tile_defs declares.
    // Phaser keeps the loader running while new files are queued during
    // preload, so the scene's create() runs only after ALL tile sprites
    // (hardcoded + runtime) have finished loading.
    this.load.json("tile_defs", "/data/tile_defs.json");
    this.load.once("filecomplete-json-tile_defs", () => {
      const raw = this.cache.json.get("tile_defs");
      if (raw) populateRuntimeDefs(raw);
      // spriteManifest() now returns hardcoded + runtime tiles. Phaser
      // dedupes by key, so no harm if a key was already queued.
      for (const { key, path } of spriteManifest()) {
        this.load.image(key, path);
      }
    });
    // Also enqueue the hardcoded set immediately so the player marker
    // and overworld basics start loading without waiting on JSON.
    for (const { key, path } of spriteManifest()) {
      this.load.image(key, path);
    }
  }

  async create(): Promise<void> {
    this.cameras.main.setBackgroundColor("#0f0f1a");
    try {
      this.tileMap = await loadTileMap();
    } catch (err) {
      this.add.text(
        20, 20,
        `Failed to load overworld: ${(err as Error).message}`,
        { color: "#ff6b6b", fontFamily: "monospace", fontSize: "16px" }
      );
      return;
    }

    this.mapLights = collectLightSources(this.tileMap);
    this.dark = mapIsDark(this.mapLights);
    this.drawMap();
    this.drawPlayer();
    this.drawHud();
    this.installCamera();
    this.installInput();
    this.refreshHud();
    if (this.dark) this.refreshDarkness();

    if (gameState.defeated) this.showDefeat();
  }

  // ── Static rendering ─────────────────────────────────────────────

  private drawMap(): void {
    // 60×30 = 1800 tiles. Sprite Images cull off-screen for free, so
    // this is a one-time scene-create cost.
    for (let row = 0; row < this.tileMap.height; row++) {
      for (let col = 0; col < this.tileMap.width; col++) {
        const id = this.tileMap.getTile(col, row);
        const x = col * TILE;
        const y = row * TILE;
        const key = tileSpriteKey(id);
        if (key && this.textures.exists(key)) {
          this.add.image(x, y, key).setOrigin(0);
        } else {
          // Fallback: coloured rectangle for tiles without a sprite
          // (currently the spawn / encounter markers).
          const def = tileDef(id);
          const colorHex = Phaser.Display.Color.GetColor(...def.color);
          this.add.rectangle(x, y, TILE, TILE, colorHex).setOrigin(0);
        }
        // Trigger glyph drawn on top regardless of base style so the
        // player can spot encounters at a glance.
        if (isEncounterTrigger(id)) {
          this.add
            .text(x + TILE / 2, y + TILE / 2, "✦", {
              fontFamily: "Georgia, serif",
              fontSize: "18px",
              color: "#ffd470",
              stroke: "#1a1a2e",
              strokeThickness: 3,
            })
            .setOrigin(0.5);
        }
      }
    }
    // Decoration glyphs (rising_smoke at the dragon's lair, fairy
    // lights along certain paths, etc.) drawn from tile_properties.
    for (const [key, entry] of Object.entries(this.tileMap.tileProperties)) {
      const spec = decorationFor(entry);
      if (!spec) continue;
      const [c, r] = key.split(",").map((s) => parseInt(s, 10));
      if (!Number.isFinite(c) || !Number.isFinite(r)) continue;
      this.add
        .text(c * TILE + TILE / 2, r * TILE + TILE / 2, spec.glyph, {
          fontFamily: "Georgia, serif",
          fontSize: "20px",
          color: spec.color,
          stroke: spec.stroke ?? "#1a1a2e",
          strokeThickness: 3,
        })
        .setOrigin(0.5)
        .setDepth(7);
    }
    if (this.dark) {
      for (let row = 0; row < this.tileMap.height; row++) {
        for (let col = 0; col < this.tileMap.width; col++) {
          const r = this.add
            .rectangle(col * TILE, row * TILE, TILE, TILE, 0x000000, 0.85)
            .setOrigin(0)
            .setDepth(9);
          this.darkness.set(`${col},${row}`, r);
        }
      }
    }
  }

  private refreshDarkness(): void {
    if (!this.dark) return;
    const party = gameState.playerPos;
    for (let row = 0; row < this.tileMap.height; row++) {
      for (let col = 0; col < this.tileMap.width; col++) {
        const rect = this.darkness.get(`${col},${row}`);
        if (!rect) continue;
        const b = brightnessAt(col, row, this.mapLights, party);
        const alpha = Math.max(0, Math.min(0.92, (1 - b) * 0.92));
        rect.setFillStyle(0x000000, alpha);
      }
    }
  }

  private drawPlayer(): void {
    const { col, row } = gameState.playerPos;
    const x = col * TILE + TILE / 2;
    const y = row * TILE + TILE / 2;
    this.player = this.add.image(x, y, "player").setDepth(10);
  }

  private installCamera(): void {
    // Bounds extended upward by HUD_HEIGHT so the camera always has
    // headroom to scroll the world strictly below the HUD bar. Without
    // this, when the player stands at row 0 the camera clamps scrollY
    // to 0 and the top tiles render under the HUD.
    this.cameras.main.setBounds(
      0,
      -HUD_HEIGHT,
      this.tileMap.width * TILE,
      this.tileMap.height * TILE + HUD_HEIGHT
    );
    this.cameras.main.startFollow(this.player, true, 0.2, 0.2);
  }

  private drawHud(): void {
    // HUD bar pinned to the top of the viewport with setScrollFactor(0).
    const bar = this.add
      .rectangle(0, 0, 960, HUD_HEIGHT, 0x161629, 0.92)
      .setOrigin(0)
      .setScrollFactor(0)
      .setStrokeStyle(1, 0x2a2a3a);
    void bar;

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
      .text(960 - 16, 18, "WASD / arrows / tap to move  ·  ✦ = encounter", {
        fontFamily: "monospace",
        fontSize: "12px",
        color: "#bdb38a",
      })
      .setOrigin(1, 0)
      .setScrollFactor(0);
  }

  private refreshHud(): void {
    const { col, row } = gameState.playerPos;
    const tileName = tileDef(this.tileMap.getTile(col, row)).name;
    this.status.setText(`(${col}, ${row})  ·  ${tileName}`);
    const partyText = gameState.party
      .map((c: Combatant) => `${c.name} ${c.hp}/${c.maxHp}`)
      .join("   ");
    this.hpSummary.setText(partyText);
  }

  // ── Input ────────────────────────────────────────────────────────

  private installInput(): void {
    const k = this.input.keyboard;
    if (k) {
      const map: Record<string, [number, number]> = {
        W: [0, -1], UP: [0, -1],
        S: [0, 1], DOWN: [0, 1],
        A: [-1, 0], LEFT: [-1, 0],
        D: [1, 0], RIGHT: [1, 0],
      };
      for (const [key, delta] of Object.entries(map)) {
        k.on(`keydown-${key}`, () => this.tryStep(delta[0], delta[1]));
      }
      // 'P' opens the party screen as an overlay. We pause this scene
      // so its keyboard handlers don't fire while the overlay is up.
      k.on("keydown-P", () => this.openParty());
    }

    this.input.on("pointerdown", (p: Phaser.Input.Pointer) => {
      const world = this.cameras.main.getWorldPoint(p.x, p.y);
      const col = Math.floor(world.x / TILE);
      const row = Math.floor(world.y / TILE);
      const dc = col - gameState.playerPos.col;
      const dr = row - gameState.playerPos.row;
      if (Math.abs(dc) + Math.abs(dr) !== 1) return;
      this.tryStep(dc, dr);
    });
  }

  private tryStep(dc: number, dr: number): void {
    if (this.busy || gameState.defeated) return;
    const nc = gameState.playerPos.col + dc;
    const nr = gameState.playerPos.row + dr;
    if (!this.tileMap.isWalkable(nc, nr)) {
      // Quick shake to acknowledge the attempted move.
      this.busy = true;
      this.tweens.add({
        targets: this.player,
        x: this.player.x + dc * 4,
        y: this.player.y + dr * 4,
        duration: 60,
        yoyo: true,
        onComplete: () => (this.busy = false),
      });
      return;
    }

    gameState.playerPos = { col: nc, row: nr };
    this.busy = true;
    const targetX = nc * TILE + TILE / 2;
    const targetY = nr * TILE + TILE / 2;
    this.tweens.add({
      targets: this.player,
      x: targetX,
      y: targetY,
      duration: 110,
      onComplete: () => {
        this.busy = false;
        this.refreshHud();
        this.refreshDarkness();
        // Town/dungeon links take priority over encounter triggers.
        // (In the dragon module they're on different tiles anyway.)
        if (this.checkLink(nc, nr)) return;
        this.checkEncounter(nc, nr);
      },
    });
  }

  private checkLink(col: number, row: number): boolean {
    const link = this.tileMap.getTileLink(col, row);
    if (!link) return false;
    if (link.kind === "town") {
      this.cameras.main.fadeOut(220, 0, 0, 0);
      this.cameras.main.once("camerafadeoutcomplete", () => {
        this.scene.start("TownScene", {
          townName: link.name,
          entryCol: link.x ?? 0,
          entryRow: link.y ?? 0,
          returnCol: col,
          returnRow: row,
        });
      });
      return true;
    }
    if (link.kind === "building") {
      // Buildings live in their own JSON. We re-prefix the name with
      // "building:" so TownScene knows to dispatch through the
      // Buildings loader instead of the Towns one. `link.name` may be
      // either "<Name>" (default to first space) or "<Name>:<Space>".
      this.cameras.main.fadeOut(220, 0, 0, 0);
      this.cameras.main.once("camerafadeoutcomplete", () => {
        this.scene.start("TownScene", {
          townName: `building:${link.name}`,
          entryCol: link.x ?? 0,
          entryRow: link.y ?? 0,
          returnCol: col,
          returnRow: row,
        });
      });
      return true;
    }
    // Other link kinds (dungeon) aren't wired up yet — let the
    // encounter check fire instead so play continues normally.
    return false;
  }

  private checkEncounter(col: number, row: number): void {
    const id = this.tileMap.getTile(col, row);
    if (!isEncounterTrigger(id)) return;
    const key = triggerKey(col, row);
    if (gameState.consumedTriggers.has(key)) return;
    // Hand off to CombatScene with metadata it can use to mark the
    // trigger consumed on victory.
    this.cameras.main.fadeOut(220, 0, 0, 0);
    this.cameras.main.once("camerafadeoutcomplete", () => {
      this.scene.start("CombatScene", {
        fromWorld: true,
        triggerKey: key,
      });
    });
  }

  private openParty(): void {
    if (gameState.defeated) return;
    this.scene.pause();
    this.scene.launch("PartyScene", { from: "OverworldScene" });
  }

  private showDefeat(): void {
    if (this.defeatOverlay) return;
    this.defeatOverlay = this.add
      .text(480, 360, "Defeated.\nReload the page to start over.", {
        fontFamily: "Georgia, serif",
        fontSize: "32px",
        color: "#ff6b6b",
        align: "center",
        stroke: "#1a1a2e",
        strokeThickness: 6,
      })
      .setOrigin(0.5)
      .setScrollFactor(0);
  }
}
