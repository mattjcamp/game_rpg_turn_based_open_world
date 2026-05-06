/**
 * Town & interior Phaser scene.
 *
 * Reads either a top-level town or a "Town/Interior" building from
 * `data/towns.json`, renders its tile grid, places the party and the
 * map's NPCs, supports WASD/tap movement, tap-on-NPC opens a dialog
 * box, and stepping on a linked tile fades to the next scene.
 *
 * Three link kinds are honoured on exit:
 *   - "overworld"  → OverworldScene (return to world map)
 *   - "town"       → TownScene with the named town
 *   - "interior"   → TownScene with a "Town/Interior" path
 *
 * Rendering note: town tiles are drawn as either sprites (when a
 * tile_def has a `sprite`) or coloured rectangles. Pixel-perfect
 * interior art is a future slice — the gameplay loop here doesn't
 * need it.
 *
 * Init data:
 *   { townName, entryCol, entryRow, returnCol, returnRow }
 *     - townName: town name OR "Town/Interior" path into towns.json.
 *       The field is named `townName` for backwards compatibility with
 *       OverworldScene; treat it as a generic mapPath.
 *     - entryCol/entryRow: where to drop the player (from the source
 *       tile's link_x/link_y)
 *     - returnCol/returnRow: where to put the player on the *previous*
 *       map when they leave through an "overworld"/"town" link without
 *       its own link_x/link_y (rare — the editor usually sets them).
 */

import Phaser from "phaser";
import {
  loadTowns,
  resolveTownOrInterior,
  tileMapForTown,
  type Town,
  type NpcDef,
} from "../world/Towns";
import {
  loadBuildings,
  getBuildingSpace,
  parseBuildingPath,
} from "../world/Buildings";
import { TileMap } from "../world/TileMap";
import {
  tileDef,
  loadTileDefs,
  PLAYER_SPRITE,
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
import { gameState } from "../state";

const TILE = 32;
const HUD_HEIGHT = 56;

interface TownSceneData {
  townName: string;
  entryCol: number;
  entryRow: number;
  returnCol: number;
  returnRow: number;
}

export class TownScene extends Phaser.Scene {
  private town!: Town;
  private tileMap!: TileMap;
  private player!: Phaser.GameObjects.Image;
  private playerCol = 0;
  private playerRow = 0;
  private npcs: Array<{ def: NpcDef; sprite: Phaser.GameObjects.Image }> = [];
  private busy = false;
  private status!: Phaser.GameObjects.Text;
  private hpSummary!: Phaser.GameObjects.Text;
  private hint!: Phaser.GameObjects.Text;
  /** Set of darkness rectangles drawn one per tile, indexed by `${col},${row}`. */
  private darkness = new Map<string, Phaser.GameObjects.Rectangle>();
  /** Light sources collected once per scene from map + tile_defs.
   *  Named `mapLights` to avoid colliding with Phaser.Scene's built-in
   *  `lights: LightsManager`. */
  private mapLights: LightSource[] = [];
  /** Whether the current map renders with darkness — set by collectLightSources. */
  private dark = false;

  // Init context
  private townName = "";
  private entryCol = 0;
  private entryRow = 0;
  private returnCol = 0;
  private returnRow = 0;

  // Dialog state
  private dialog?: {
    bg: Phaser.GameObjects.Rectangle;
    nameText: Phaser.GameObjects.Text;
    bodyText: Phaser.GameObjects.Text;
    advanceHint: Phaser.GameObjects.Text;
    npc: NpcDef;
    lineIdx: number;
  };

  constructor() {
    super({ key: "TownScene" });
  }

  init(data?: TownSceneData): void {
    this.townName = data?.townName ?? "";
    this.entryCol = data?.entryCol ?? 0;
    this.entryRow = data?.entryRow ?? 0;
    this.returnCol = data?.returnCol ?? gameState.playerPos.col;
    this.returnRow = data?.returnRow ?? gameState.playerPos.row;
    // Reset transient handles so a re-entered scene starts clean.
    this.busy = false;
    this.npcs = [];
    this.dialog = undefined;
    this.darkness = new Map();
    this.mapLights = [];
    this.dark = false;
  }

  preload(): void {
    this.textures.on("addtexture", (key: string) => {
      const tex = this.textures.get(key);
      if (tex) tex.setFilter(Phaser.Textures.FilterMode.NEAREST);
    });

    // Two-phase load: pull tile_defs.json via Phaser's loader, then
    // enqueue every tile sprite declared in it once the JSON arrives.
    // Phaser keeps preload going for any files added inside this
    // listener, so create() only fires once the full sprite set
    // (overworld + town + dungeon tiles) is in cache.
    this.load.json("tile_defs", "/data/tile_defs.json");
    this.load.once("filecomplete-json-tile_defs", () => {
      const raw = this.cache.json.get("tile_defs");
      if (raw) populateRuntimeDefs(raw);
      for (const { key, path } of spriteManifest()) {
        this.load.image(key, path);
      }
    });

    // Hardcoded tile sprites + player marker can start loading now,
    // they don't depend on the JSON.
    for (const { key, path } of spriteManifest()) {
      this.load.image(key, path);
    }
    this.load.image(PLAYER_SPRITE, PLAYER_SPRITE);

    // We don't yet know which NPC sprites the chosen town uses, so
    // preload the full character set we ship. Phaser caches by key —
    // duplicates are no-ops.
    for (const f of [
      "alchemist", "barbarian", "cleric", "fighter",
      "illusionist", "paladin", "ranger", "wizard",
    ]) {
      const path = `/assets/characters/${f}.png`;
      this.load.image(path, path);
    }
  }

  async create(): Promise<void> {
    this.cameras.main.setBackgroundColor("#0f0f1a");
    this.cameras.main.fadeIn(220, 0, 0, 0);

    try {
      // tile_defs.json is small and idempotent to reload (the cache
      // in Tiles.ts dedupes inserts). We always await it before
      // building the map so isWalkable() resolves correctly for
      // town-only tile ids.
      await loadTileDefs();
      // Three accepted path forms, dispatched in this order:
      //   "building:<name>[:<space>]" → buildings.json
      //   "<town>/<interior>"          → towns.json (interior)
      //   "<town>"                     → towns.json (top-level)
      // Buildings live in their own JSON so we resolve them first.
      const buildingRef = parseBuildingPath(this.townName);
      let found: Town | null = null;
      if (buildingRef) {
        const buildings = await loadBuildings();
        const ref = buildingRef.space
          ? `${buildingRef.building}:${buildingRef.space}`
          : buildingRef.building;
        found = getBuildingSpace(buildings, ref);
      } else {
        const towns = await loadTowns();
        found = resolveTownOrInterior(towns, this.townName);
      }
      if (!found) {
        this.add.text(
          20, 20,
          `Map not found: ${this.townName}`,
          { color: "#ff6b6b", fontFamily: "monospace", fontSize: "16px" }
        );
        return;
      }
      this.town = found;
    } catch (err) {
      this.add.text(
        20, 20,
        `Failed to load town: ${(err as Error).message}`,
        { color: "#ff6b6b", fontFamily: "monospace", fontSize: "16px" }
      );
      return;
    }

    this.tileMap = tileMapForTown(this.town);
    this.mapLights = collectLightSources(this.tileMap);
    // Lighting policy:
    //   * Outdoor towns (top-level entries in towns.json) inherit the
    //     overworld's day/night lighting, which today is always bright.
    //   * Interiors (nested under a town via "Town/Building" path) and
    //     building spaces (any "building:..." path) are always dark
    //     with light pools — the Python game's INTERIOR_DARKNESS mode.
    const isIndoor =
      this.townName.startsWith("building:") || this.townName.includes("/");
    this.dark = isIndoor && mapIsDark(this.mapLights);
    this.drawMap();
    this.drawNpcs();
    this.drawPlayer();
    this.drawHud();
    this.installCamera();
    this.installInput();
    this.refreshHud();
    if (this.dark) this.refreshDarkness();
  }

  // ── Coordinate helpers ───────────────────────────────────────────

  private tileX(col: number): number {
    return col * TILE + TILE / 2;
  }
  private tileY(row: number): number {
    return row * TILE + TILE / 2;
  }

  // ── Static rendering ─────────────────────────────────────────────

  private drawMap(): void {
    // 25×25 = 625 tiles for Plainstown. Phaser handles this load fine
    // as a one-time scene-create cost. The camera culls off-screen
    // images automatically.
    for (let row = 0; row < this.town.height; row++) {
      for (let col = 0; col < this.town.width; col++) {
        const id = this.tileMap.getTile(col, row);
        const x = col * TILE;
        const y = row * TILE;
        const key = tileSpriteKey(id);
        if (key && this.textures.exists(key)) {
          this.add.image(x, y, key).setOrigin(0);
        } else {
          // Fallback: coloured rectangle for tile ids we don't ship a
          // sprite for. This still happens for void / unrecognised ids.
          const def = tileDef(id);
          const colorHex = Phaser.Display.Color.GetColor(...def.color);
          this.add.rectangle(x, y, TILE, TILE, colorHex).setOrigin(0);
        }
      }
    }
    // Decoration glyphs (fire / fairy_light / item) drawn over their
    // tile so authors can mark hearths, magical lights, and ground
    // items in tile_properties without shipping a sprite per kind.
    // Depth 7 puts them under the player but above tiles & NPCs.
    for (const [key, entry] of Object.entries(this.tileMap.tileProperties)) {
      const spec = decorationFor(entry);
      if (!spec) continue;
      const [c, r] = key.split(",").map((s) => parseInt(s, 10));
      if (!Number.isFinite(c) || !Number.isFinite(r)) continue;
      this.add
        .text(this.tileX(c), this.tileY(r), spec.glyph, {
          fontFamily: "Georgia, serif",
          fontSize: "20px",
          color: spec.color,
          stroke: spec.stroke ?? "#1a1a2e",
          strokeThickness: 3,
        })
        .setOrigin(0.5)
        .setDepth(7);
    }

    // Pre-create one darkness rectangle per cell at depth 9 so it
    // sits above tiles + NPCs but below the player marker. Visibility
    // alpha is set per-frame in refreshDarkness().
    if (this.dark) {
      for (let row = 0; row < this.town.height; row++) {
        for (let col = 0; col < this.town.width; col++) {
          const r = this.add
            .rectangle(col * TILE, row * TILE, TILE, TILE, 0x000000, 0.85)
            .setOrigin(0)
            .setDepth(9);
          this.darkness.set(`${col},${row}`, r);
        }
      }
    }
  }

  /**
   * Update each darkness rectangle's alpha based on the brightness at
   * its tile. Called every time the player moves so the party's light
   * pool tracks them across the map.
   */
  private refreshDarkness(): void {
    if (!this.dark) return;
    const party = { col: this.playerCol, row: this.playerRow };
    for (let row = 0; row < this.town.height; row++) {
      for (let col = 0; col < this.town.width; col++) {
        const rect = this.darkness.get(`${col},${row}`);
        if (!rect) continue;
        const b = brightnessAt(col, row, this.mapLights, party);
        // Darkness alpha is the inverse of brightness, with a small
        // ambient floor so even fully-lit tiles read as warm rather
        // than 100% transparent. Cap at 0.92 so the player can still
        // make out tile shapes in the gloom.
        const alpha = Math.max(0, Math.min(0.92, (1 - b) * 0.92));
        rect.setFillStyle(0x000000, alpha);
      }
    }
  }

  private drawNpcs(): void {
    for (const npc of this.town.npcs) {
      const x = this.tileX(npc.col);
      const y = this.tileY(npc.row);
      // npc.sprite is already a normalised /assets/... path. Fall back
      // to a coloured rectangle if the texture didn't get preloaded
      // (unrecognised character sprite).
      const sprite = npc.sprite && this.textures.exists(npc.sprite)
        ? this.add.image(x, y, npc.sprite).setDepth(8)
        : (this.add
            .rectangle(x, y, TILE - 4, TILE - 4, 0xc8a060)
            .setStrokeStyle(2, 0x1a1a2e) as unknown as Phaser.GameObjects.Image);
      sprite.setInteractive({ useHandCursor: true });
      sprite.on(
        "pointerdown",
        (
          _p: Phaser.Input.Pointer,
          _x: number,
          _y: number,
          evt: Phaser.Types.Input.EventData
        ) => {
          evt.stopPropagation?.();
          this.openDialog(npc);
        }
      );
      this.npcs.push({ def: npc, sprite });
    }
  }

  private drawPlayer(): void {
    this.playerCol = this.entryCol;
    this.playerRow = this.entryRow;
    this.player = this.add
      .image(this.tileX(this.playerCol), this.tileY(this.playerRow), PLAYER_SPRITE)
      .setDepth(10);
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
      .text(960 - 16, 18, "WASD / arrows / tap to move  ·  tap an NPC to talk", {
        fontFamily: "monospace",
        fontSize: "12px",
        color: "#bdb38a",
      })
      .setOrigin(1, 0)
      .setScrollFactor(0);
  }

  private refreshHud(): void {
    const tileName = tileDef(this.tileMap.getTile(this.playerCol, this.playerRow)).name;
    this.status.setText(`${this.town.name}  ·  (${this.playerCol}, ${this.playerRow})  ·  ${tileName}`);
    const partyText = gameState.party
      .map((c) => `${c.name} ${c.hp}/${c.maxHp}`)
      .join("   ");
    this.hpSummary.setText(partyText);
  }

  private installCamera(): void {
    // Bounds extended upward by HUD_HEIGHT so the camera always has
    // headroom to scroll the world strictly below the HUD bar. Without
    // this, when the player stands at row 0 the camera clamps scrollY
    // to 0 and the top tiles render under the HUD (and the player
    // marker disappears behind party HP text).
    this.cameras.main.setBounds(
      0,
      -HUD_HEIGHT,
      this.town.width * TILE,
      this.town.height * TILE + HUD_HEIGHT
    );
    this.cameras.main.startFollow(this.player, true, 0.2, 0.2);
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
      k.on("keydown-ESC", () => this.closeDialog());
    }

    this.input.on("pointerdown", (p: Phaser.Input.Pointer) => {
      // If a dialog is open, ANY background click advances it.
      if (this.dialog) {
        this.advanceDialog();
        return;
      }
      const world = this.cameras.main.getWorldPoint(p.x, p.y);
      const col = Math.floor(world.x / TILE);
      const row = Math.floor(world.y / TILE);
      const dc = col - this.playerCol;
      const dr = row - this.playerRow;
      if (Math.abs(dc) + Math.abs(dr) !== 1) return;
      this.tryStep(dc, dr);
    });
  }

  private npcAt(col: number, row: number): NpcDef | null {
    for (const { def } of this.npcs) {
      if (def.col === col && def.row === row) return def;
    }
    return null;
  }

  private tryStep(dc: number, dr: number): void {
    if (this.busy || this.dialog) return;
    const nc = this.playerCol + dc;
    const nr = this.playerRow + dr;

    // Walking into an NPC opens their dialog rather than moving.
    const npc = this.npcAt(nc, nr);
    if (npc) {
      this.openDialog(npc);
      return;
    }
    if (!this.tileMap.isWalkable(nc, nr)) {
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

    this.playerCol = nc;
    this.playerRow = nr;
    this.busy = true;
    this.tweens.add({
      targets: this.player,
      x: this.tileX(nc),
      y: this.tileY(nr),
      duration: 110,
      onComplete: () => {
        this.busy = false;
        this.refreshHud();
        this.refreshDarkness();
        this.checkExit(nc, nr);
      },
    });
  }

  private checkExit(col: number, row: number): void {
    const link = this.tileMap.getTileLink(col, row);
    if (!link) return;

    if (link.kind === "overworld") {
      // Use the link's link_x/link_y if present, else the return coords
      // we were handed when the scene was launched.
      const back = {
        col: link.x ?? this.returnCol,
        row: link.y ?? this.returnRow,
      };
      gameState.playerPos = back;
      this.cameras.main.fadeOut(220, 0, 0, 0);
      this.cameras.main.once("camerafadeoutcomplete", () => {
        this.scene.start("OverworldScene");
      });
      return;
    }

    if (link.kind === "town" || link.kind === "interior") {
      // For both link kinds, we re-enter TownScene with the new map
      // path. Interior paths are stored as "Town/Building"; town links
      // are bare names. The link's link_x/link_y is where to spawn
      // inside the destination map (the editor sets this to the door
      // tile).
      //
      // Return coords = the tile we're leaving on. If the player walks
      // back through the same door we'll land where we came from.
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
      return;
    }

    if (link.kind === "building") {
      // Same re-entry pattern, but TileMap.getTileLink stripped the
      // "building:" prefix on parse. We add it back here so TownScene
      // dispatches to the buildings loader instead of towns.
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
      return;
    }
    // Other link kinds (dungeon, etc) are not yet implemented — fall
    // through silently and let the player keep walking.
  }

  // ── Dialog ───────────────────────────────────────────────────────

  private openDialog(npc: NpcDef): void {
    if (this.dialog) return;
    if (npc.dialogue.length === 0) return;
    const W = 640;
    const H = 140;
    const X = (960 - W) / 2;
    const Y = 720 - H - 32;
    const bg = this.add
      .rectangle(X, Y, W, H, 0x161629, 0.96)
      .setOrigin(0)
      .setStrokeStyle(2, 0xc8553d)
      .setScrollFactor(0)
      .setDepth(50);
    const nameText = this.add
      .text(X + 16, Y + 12, `${npc.name} — ${npc.npcType}`, {
        fontFamily: "Georgia, serif",
        fontSize: "16px",
        color: "#ffd470",
      })
      .setScrollFactor(0)
      .setDepth(51);
    const bodyText = this.add
      .text(X + 16, Y + 38, "", {
        fontFamily: "Georgia, serif",
        fontSize: "15px",
        color: "#f6efd6",
        wordWrap: { width: W - 32 },
      })
      .setScrollFactor(0)
      .setDepth(51);
    const advanceHint = this.add
      .text(X + W - 16, Y + H - 18, "", {
        fontFamily: "monospace",
        fontSize: "11px",
        color: "#bdb38a",
      })
      .setOrigin(1, 0)
      .setScrollFactor(0)
      .setDepth(51);
    this.dialog = { bg, nameText, bodyText, advanceHint, npc, lineIdx: 0 };
    this.renderDialogLine();
  }

  private renderDialogLine(): void {
    if (!this.dialog) return;
    const { bodyText, advanceHint, npc, lineIdx } = this.dialog;
    const total = npc.dialogue.length;
    bodyText.setText(npc.dialogue[lineIdx] ?? "");
    advanceHint.setText(
      lineIdx < total - 1
        ? `[${lineIdx + 1}/${total}] tap to continue`
        : `[${lineIdx + 1}/${total}] tap to close`
    );
  }

  private advanceDialog(): void {
    if (!this.dialog) return;
    const total = this.dialog.npc.dialogue.length;
    if (this.dialog.lineIdx < total - 1) {
      this.dialog.lineIdx += 1;
      this.renderDialogLine();
    } else {
      this.closeDialog();
    }
  }

  private closeDialog(): void {
    if (!this.dialog) return;
    const { bg, nameText, bodyText, advanceHint } = this.dialog;
    bg.destroy();
    nameText.destroy();
    bodyText.destroy();
    advanceHint.destroy();
    this.dialog = undefined;
  }
}
