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
  resolveNpcSprite,
  wanderTownNpcs,
  NPC_SPRITE_MANIFEST,
  type Town,
  type NpcDef,
} from "../world/Towns";
import {
  loadCounters,
  type Counter,
  type CounterService,
} from "../world/Counters";
import {
  buyItem,
  buyPriceOf,
  sellItem,
  sellPriceOf,
  performTempleService,
} from "../world/TownActions";
import { loadItems, type Item } from "../world/Items";
import { loadParty } from "../world/Party";
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
  PARTY_LIGHT_RADIUS,
  type LightSource,
} from "../world/Lighting";
import { partyLightRadius, partyLightTint, tickGaladrielsLight } from "../world/PartyActions";
import { decorationFor } from "../world/Decorations";
import { installTileEffects } from "../world/TileEffects";
import { withBase } from "../world/Module";
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
  /** Per-tile tint rectangles for active party-light effects (Infravision /
   *  Galadriel's Light). Drawn above darkness, below the player. */
  private tintRects = new Map<string, Phaser.GameObjects.Rectangle>();
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

  /** Loaded counter catalog (counters.json). */
  private counters: Map<string, Counter> = new Map();
  /** Loaded item catalog — needed for buy/sell prices. */
  private itemCatalog: Map<string, Item> = new Map();

  /** Shop sub-mode state (kind === undefined / regular shop). Tracks
   *  separate cursors for buy and sell so toggling with TAB feels
   *  natural — the player resumes where they were on each side. */
  private shop?: {
    /** Header label, e.g. "Brennan — General Store" or "General Store". */
    title: string;
    counter: Counter;
    mode: "buy" | "sell";
    buyCursor: number;
    sellCursor: number;
    objects: Phaser.GameObjects.GameObject[];
    message: string;
  };

  /** Temple service sub-mode state. */
  private temple?: {
    title: string;
    counter: Counter;
    cursor: number;
    objects: Phaser.GameObjects.GameObject[];
    message: string;
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
    this.tintRects = new Map();
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
    // preload the full character set we ship plus every role + villager
    // sprite the resolver might fall back to. Phaser caches by key,
    // so duplicates across this list are no-ops.
    for (const f of [
      "alchemist", "barbarian", "cleric", "fighter",
      "illusionist", "paladin", "ranger", "thief", "wizard",
    ]) {
      const path = withBase(`/assets/characters/${f}.png`);
      this.load.image(path, path);
    }
    for (const path of NPC_SPRITE_MANIFEST) {
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
    // Counters + items catalogs power the shop / temple service menus.
    // Lazy-loaded; cached after first load. Errors degrade silently
    // (NPCs fall back to dialogue if the data isn't available).
    // Party data is eager-loaded so the very first shop / temple
    // interaction can read gold + roster without the player having
    // to detour through the Party screen first.
    try {
      this.counters = await loadCounters();
      this.itemCatalog = await loadItems();
      if (!gameState.partyData) gameState.partyData = await loadParty();
    } catch {
      /* keep empty maps */
    }

    this.drawMap();
    // Animated tile_properties.effect overlays — see TileEffects.ts.
    installTileEffects(this, this.tileMap, TILE, 7);
    this.drawNpcs();
    this.drawPlayer();
    this.drawHud();
    // When the Party screen is opened on top, this scene is paused.
    // Toggling Infravision / Galadriel's Light there changes the
    // party's effective light radius — so on resume we repaint the
    // darkness to reflect the new state.
    this.events.on(Phaser.Scenes.Events.RESUME, () => {
      if (this.dark) this.refreshDarkness();
    });
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

    // Pre-create one darkness rectangle per cell at depth 9 + a tint
    // rectangle per cell at depth 9.5. Both sit above tiles + NPCs
    // but below the player marker. Per-cell alpha is updated in
    // refreshDarkness; the tint stays invisible until an active
    // party-light effect (Infravision / Galadriel's Light) supplies
    // a colour.
    if (this.dark) {
      for (let row = 0; row < this.town.height; row++) {
        for (let col = 0; col < this.town.width; col++) {
          const d = this.add
            .rectangle(col * TILE, row * TILE, TILE, TILE, 0x000000, 0.85)
            .setOrigin(0)
            .setDepth(9);
          this.darkness.set(`${col},${row}`, d);
          const t = this.add
            .rectangle(col * TILE, row * TILE, TILE, TILE, 0xffffff, 0)
            .setOrigin(0)
            .setDepth(9.5);
          this.tintRects.set(`${col},${row}`, t);
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
    // Active party effects (Infravision, Galadriel's Light) act as a
    // party-carried light source — they bump the radius up from the
    // default 2 tiles to 8/5 respectively, and they also paint a
    // colour tint over visible tiles (red for infrared, pale blue
    // for moonlight). The Python game wires the same predicate via
    // `interior_lighting.party_has_light` and the matching tint via
    // the `TintEffect` enum in `lighting.py`.
    const partyData = gameState.partyData;
    const radius = partyData
      ? partyLightRadius(partyData, PARTY_LIGHT_RADIUS)
      : PARTY_LIGHT_RADIUS;
    const tint = partyData ? partyLightTint(partyData) : null;
    for (let row = 0; row < this.town.height; row++) {
      for (let col = 0; col < this.town.width; col++) {
        const rect = this.darkness.get(`${col},${row}`);
        if (!rect) continue;
        const b = brightnessAt(col, row, this.mapLights, party, radius);
        // Darkness alpha is the inverse of brightness, with a small
        // ambient floor so even fully-lit tiles read as warm rather
        // than 100% transparent. Cap at 0.92 so the player can still
        // make out tile shapes in the gloom.
        const alpha = Math.max(0, Math.min(0.92, (1 - b) * 0.92));
        rect.setFillStyle(0x000000, alpha);
        // Tint layer — coloured rect above the darkness, alpha
        // proportional to brightness so the colour wash fades to
        // nothing at the edge of the party's range. No tint when
        // no effect is equipped (alpha 0).
        const tintRect = this.tintRects.get(`${col},${row}`);
        if (tintRect) {
          if (tint && b > 0) {
            tintRect.setFillStyle(tint.color, b * tint.alphaScale);
          } else {
            tintRect.setFillStyle(0xffffff, 0);
          }
        }
      }
    }
  }

  private drawNpcs(): void {
    for (const npc of this.town.npcs) {
      const x = this.tileX(npc.col);
      const y = this.tileY(npc.row);
      // Sprite resolution chain: explicit sprite → npc_type role →
      // hash-by-name villager. Mirrors the Python renderer so towns
      // populated with copy-paste "fighter.png" entries still come
      // out looking like a varied crowd.
      const path = resolveNpcSprite(npc, (p) => this.textures.exists(p));
      const sprite = this.textures.exists(path)
        ? this.add.image(x, y, path).setDepth(8)
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
      .text(960 - 16, 18, "WASD / arrows / tap to move  ·  Space = wait  ·  tap an NPC to talk", {
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
      // Capture every key we listen for so the browser's default action
      // doesn't fire alongside our handler. This matters most for TAB
      // (which would otherwise move focus to the page header's "← Back"
      // link and let the very next ENTER navigate away from /world —
      // looking exactly like "the game crashed back to the intro
      // screen") but SPACE / ENTER / arrows can also trigger scroll or
      // link activation when focus drifts off the canvas, so we capture
      // the whole set.
      k.addCapture([
        "TAB", "ENTER", "SPACE", "ESC",
        "UP", "DOWN", "LEFT", "RIGHT",
        "W", "A", "S", "D", "P",
      ]);
      const map: Record<string, [number, number]> = {
        W: [0, -1], UP: [0, -1],
        S: [0, 1], DOWN: [0, 1],
        A: [-1, 0], LEFT: [-1, 0],
        D: [1, 0], RIGHT: [1, 0],
      };
      for (const [key, delta] of Object.entries(map)) {
        k.on(`keydown-${key}`, () => this.onMoveKey(key, delta[0], delta[1]));
      }
      k.on("keydown-ENTER", () => this.onConfirmKey());
      k.on("keydown-SPACE", () => this.onConfirmKey());
      k.on("keydown-TAB", () => {
        // TAB toggles the shop's buy/sell mode. No-op outside shop.
        if (this.shop) this.toggleShopMode();
      });
      k.on("keydown-ESC", () => this.onEscape());
      k.on("keydown-P", () => {
        if (this.shop || this.temple) return;
        this.openParty();
      });
    }

    this.input.on("pointerdown", (p: Phaser.Input.Pointer) => {
      // Shop / temple eat ALL background clicks — the menus are
      // keyboard-driven and a misplaced tap shouldn't move the avatar.
      if (this.shop || this.temple) return;
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

  /**
   * Single arrow-key handler that knows about every modal sub-mode.
   * Shop / temple intercept up/down to walk the cursor; movement
   * keys fall through only when no menu is open.
   */
  private onMoveKey(key: string, dc: number, dr: number): void {
    if (this.shop) {
      if (key === "UP" || key === "W")   return this.moveShopCursor(-1);
      if (key === "DOWN" || key === "S") return this.moveShopCursor(1);
      return;
    }
    if (this.temple) {
      if (key === "UP" || key === "W")   return this.moveTempleCursor(-1);
      if (key === "DOWN" || key === "S") return this.moveTempleCursor(1);
      return;
    }
    this.tryStep(dc, dr);
  }

  private onConfirmKey(): void {
    if (this.shop)   return this.confirmShopBuy();
    if (this.temple) return this.confirmTempleService();
    if (this.dialog) return this.advanceDialog();
    // Nothing modal is open — Space skips the party's turn so
    // wandering NPCs and Galadriel/torch timers tick without forcing
    // the player to take a step.
    this.skipTurn();
  }

  /** Single ESC handler — closes whichever modal is active. */
  private onEscape(): void {
    if (this.shop)   return this.closeShop();
    if (this.temple) return this.closeTemple();
    if (this.dialog) return this.closeDialog();
  }

  private npcAt(col: number, row: number): NpcDef | null {
    for (const { def } of this.npcs) {
      if (def.col === col && def.row === row) return def;
    }
    return null;
  }

  private tryStep(dc: number, dr: number): void {
    if (this.busy || this.dialog || this.shop || this.temple) return;
    const nc = this.playerCol + dc;
    const nr = this.playerRow + dr;

    // Walking into an NPC opens their dialog rather than moving.
    const npc = this.npcAt(nc, nr);
    if (npc) {
      this.openDialog(npc);
      return;
    }
    // Walking into a counter tile (General Store / Weapons / Healing /
    // …) opens its shop or service menu — same UI the shopkeep NPCs
    // use, just without the NPC. Falls through to the wall-bump if the
    // counter's catalog isn't loaded.
    const counterKey = this.tileMap.getCounterKey(nc, nr);
    if (counterKey) {
      const counter = this.counters.get(counterKey);
      if (counter) {
        this.openShopAtCounter(counter, counter.name);
        return;
      }
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
        // Burn down a torch step in dark scenes so a 150-step Torch
        // actually expires after 150 movements. We don't tick in lit
        // areas — the player shouldn't be punished for using a torch
        // in a lit overworld town.
        if (this.dark && gameState.partyData && gameState.partyData.torchSteps > 0) {
          gameState.partyData.torchSteps -= 1;
          if (gameState.partyData.torchSteps === 0) {
            // Light just went out — the next refreshDarkness call below
            // sees torchSteps === 0 and snaps the pool away.
          }
        }
        if (gameState.partyData) {
          tickGaladrielsLight(gameState.partyData);
        }
        this.tickNpcWander();
        this.refreshHud();
        this.refreshDarkness();
        this.checkExit(nc, nr);
      },
    });
  }

  /**
   * Skip the player's turn — wandering NPCs still get to step, the
   * Galadriel counter still ticks, and torch steps still burn (only
   * in dark scenes, matching tryStep's rule). Used by the Space-bar
   * shortcut when no dialog/shop/temple is open.
   */
  private skipTurn(): void {
    if (this.busy || this.dialog || this.shop || this.temple) return;
    if (this.dark && gameState.partyData && gameState.partyData.torchSteps > 0) {
      gameState.partyData.torchSteps -= 1;
    }
    if (gameState.partyData) {
      tickGaladrielsLight(gameState.partyData);
    }
    this.tickNpcWander();
    this.refreshHud();
    this.refreshDarkness();
  }

  /**
   * Move every wandering town NPC at most one tile and tween the
   * sprites of any that actually moved. Stationary NPC types stay put.
   */
  private tickNpcWander(): void {
    const defs = this.npcs.map((n) => n.def);
    const moved = wanderTownNpcs(
      defs,
      this.playerCol,
      this.playerRow,
      (c, r) => this.tileMap.isWalkable(c, r),
    );
    if (moved.length === 0) return;
    const movedSet = new Set(moved);
    for (const { def, sprite } of this.npcs) {
      if (!movedSet.has(def)) continue;
      this.tweens.add({
        targets: sprite,
        x: this.tileX(def.col),
        y: this.tileY(def.row),
        duration: 110,
      });
    }
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

  private openParty(): void {
    // Don't open the party screen while a dialog is up — let the
    // player finish the conversation first.
    if (this.dialog) return;
    // Count NPCs in the 8 cells around the player so the Party screen
    // can gate PICKPOCKET on having a target in reach (mirrors
    // inventory_mixin._get_adjacent_npc in the Python game).
    let nearby = 0;
    for (const { def } of this.npcs) {
      const dc = Math.abs(def.col - this.playerCol);
      const dr = Math.abs(def.row - this.playerRow);
      if (dc <= 1 && dr <= 1 && (dc + dr) > 0) nearby += 1;
    }
    this.scene.pause();
    this.scene.launch("PartyScene", {
      from: "TownScene",
      nearbyNpcCount: nearby,
    });
  }

  // ── Dialog ───────────────────────────────────────────────────────

  private openDialog(npc: NpcDef): void {
    if (this.dialog || this.shop || this.temple) return;
    // Role dispatch — mirrors the Python game's _start_dialogue
    // branching. Shopkeeps open the buy/sell UI; priests open the
    // temple service menu. Everyone else (villager, elder, quest_giver,
    // …) falls through to the regular dialogue popup.
    const t = (npc.npcType ?? "").toLowerCase();
    if (t === "shopkeep") {
      void this.openShop(npc);
      return;
    }
    if (t === "priest") {
      void this.openTemple(npc);
      return;
    }
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

  // ── Shop sub-mode ─────────────────────────────────────────────────

  /**
   * Open the buy menu for a shopkeeper. Looks up the shop's catalog
   * by `npc.shopType` (defaults to "general"), then renders a list
   * the player can navigate with up/down + enter to buy. ESC closes.
   *
   * Service counters (e.g. healing) take a different path — those
   * are dispatched to openTemple instead.
   */
  private async openShop(npc: NpcDef): Promise<void> {
    const shopType = npc.shopType ?? "general";
    const counter = this.counters.get(shopType);
    if (!counter) {
      // Falls back to dialogue if we can't resolve the catalog —
      // better than a silent black screen.
      this.openDialogFallback(npc, [
        `${npc.name} is open for business, but the shop hasn't arrived yet.`,
      ]);
      return;
    }
    if (counter.kind === "service") {
      const godSuffix = npc.godName ? ` of ${npc.godName}` : "";
      this.openTempleAtCounter(counter, `${npc.name} — Temple${godSuffix}`);
      return;
    }
    this.openShopAtCounter(counter, `${npc.name} — ${counter.name}`);
  }

  /**
   * Open the shop UI for a bare counter (no NPC). Called from tryStep
   * when the player walks into a counter tile (a shop_type-tagged tile
   * in the General Store, Weapons Shop, etc.). Service counters
   * (healing) dispatch to the temple UI so the same tile can host either.
   */
  private openShopAtCounter(counter: Counter, title: string): void {
    if (counter.kind === "service") {
      this.openTempleAtCounter(counter, title);
      return;
    }
    this.shop = {
      title,
      counter,
      mode: "buy",
      buyCursor: 0,
      sellCursor: 0,
      objects: [],
      message: "",
    };
    this.renderShop();
  }

  private renderShop(): void {
    if (!this.shop) return;
    const shop = this.shop; // local alias keeps TS narrowing in nested closures
    for (const o of shop.objects) o.destroy();
    shop.objects = [];
    const { title, counter, mode, message } = shop;
    const W = 720, H = 420;
    const X = (960 - W) / 2;
    const Y = 80;
    const gold = gameState.partyData?.gold ?? 0;
    const stash = gameState.partyData?.inventory ?? [];
    const buyItems = counter.items;

    const bg = this.add
      .rectangle(X, Y, W, H, 0x161629, 0.98)
      .setOrigin(0).setScrollFactor(0)
      .setStrokeStyle(2, 0xc8553d)
      .setDepth(50);
    shop.objects.push(bg);
    shop.objects.push(this.add
      .text(X + 16, Y + 12, title, {
        fontFamily: "Georgia, serif", fontSize: "18px", color: "#ffd470",
      }).setScrollFactor(0).setDepth(51));
    shop.objects.push(this.add
      .text(X + W - 16, Y + 14, `Party Gold: ${gold}g`, {
        fontFamily: "monospace", fontSize: "14px", color: "#ddc05c",
      }).setOrigin(1, 0).setScrollFactor(0).setDepth(51));

    // Mode tabs — visually highlight whichever side is active.
    const tabY = Y + 40;
    const tabW = 100;
    const buyTabColor  = mode === "buy"  ? "#ffd470" : "#bdb38a";
    const sellTabColor = mode === "sell" ? "#ffd470" : "#bdb38a";
    shop.objects.push(this.add
      .rectangle(X + 16, tabY, tabW, 22,
                 mode === "buy" ? 0x3a2a22 : 0x161629,
                 mode === "buy" ? 1 : 0)
      .setOrigin(0).setStrokeStyle(1, 0xc8553d).setScrollFactor(0).setDepth(51));
    shop.objects.push(this.add
      .text(X + 16 + tabW / 2, tabY + 4, "BUY", {
        fontFamily: "Georgia, serif", fontSize: "14px", color: buyTabColor,
      }).setOrigin(0.5, 0).setScrollFactor(0).setDepth(52));
    shop.objects.push(this.add
      .rectangle(X + 16 + tabW + 4, tabY, tabW, 22,
                 mode === "sell" ? 0x3a2a22 : 0x161629,
                 mode === "sell" ? 1 : 0)
      .setOrigin(0).setStrokeStyle(1, 0xc8553d).setScrollFactor(0).setDepth(51));
    shop.objects.push(this.add
      .text(X + 16 + tabW + 4 + tabW / 2, tabY + 4, "SELL", {
        fontFamily: "Georgia, serif", fontSize: "14px", color: sellTabColor,
      }).setOrigin(0.5, 0).setScrollFactor(0).setDepth(52));

    // Description below the tabs (buy mode only — keeps the sell list
    // tighter when the stash is long).
    if (mode === "buy") {
      shop.objects.push(this.add
        .text(X + 16, Y + 70, counter.description, {
          fontFamily: "Georgia, serif", fontSize: "12px", color: "#bdb38a",
          wordWrap: { width: W - 32 },
        }).setScrollFactor(0).setDepth(51));
    }

    // List body — scrollable window so a 20-item stash doesn't bleed
    // past the panel. Compute scroll-top so the cursor stays visible.
    const listX = X + 16;
    const listY = Y + (mode === "buy" ? 110 : 80);
    const rowH = 22;
    const VISIBLE_ROWS = 11;
    const total = mode === "buy" ? buyItems.length : stash.length;
    const cursor = mode === "buy" ? shop.buyCursor : shop.sellCursor;
    let topRow = 0;
    if (total > VISIBLE_ROWS) {
      const half = Math.floor(VISIBLE_ROWS / 2);
      topRow = Math.max(0, Math.min(total - VISIBLE_ROWS, cursor - half));
    }
    const visibleCount = Math.min(VISIBLE_ROWS, total);

    // Up / down scroll indicators when rows are off-screen.
    if (topRow > 0) {
      shop.objects.push(this.add
        .text(listX + (W - 32) / 2, listY - 12, "▲", {
          fontFamily: "monospace", fontSize: "12px", color: "#bdb38a",
        }).setOrigin(0.5, 0).setScrollFactor(0).setDepth(52));
    }
    if (topRow + visibleCount < total) {
      shop.objects.push(this.add
        .text(listX + (W - 32) / 2, listY + visibleCount * rowH, "▼", {
          fontFamily: "monospace", fontSize: "12px", color: "#bdb38a",
        }).setOrigin(0.5, 0).setScrollFactor(0).setDepth(52));
    }

    if (mode === "buy") {
      for (let i = 0; i < visibleCount; i++) {
        const idx = topRow + i;
        const name = buyItems[idx];
        const price = buyPriceOf(name, this.itemCatalog);
        const rowY = listY + i * rowH;
        const isCursor = idx === shop.buyCursor;
        const bgRow = this.add
          .rectangle(listX, rowY, W - 32, rowH - 2,
                     isCursor ? 0x3a2a22 : 0x161629, isCursor ? 1 : 0)
          .setOrigin(0).setScrollFactor(0).setDepth(51);
        shop.objects.push(bgRow);
        const prefix = isCursor ? "> " : "  ";
        const priceLabel = price > 0
          ? `${price}g${gold < price ? "  — short" : ""}`
          : "—";
        shop.objects.push(this.add
          .text(listX + 8, rowY + 2, `${prefix}${name}`, {
            fontFamily: "Georgia, serif", fontSize: "14px",
            color: isCursor ? "#ffd470" : "#f6efd6",
          }).setScrollFactor(0).setDepth(52));
        shop.objects.push(this.add
          .text(listX + W - 32 - 12, rowY + 2, priceLabel, {
            fontFamily: "monospace", fontSize: "13px",
            color: gold < price && price > 0 ? "#d86a4a" : "#bdb38a",
          }).setOrigin(1, 0).setScrollFactor(0).setDepth(52));
      }
    } else {
      // SELL mode — list entries from the shared stash with their
      // sellPriceOf prices. Items shops won't take get a "—" label
      // and the row is dimmed.
      if (stash.length === 0) {
        shop.objects.push(this.add
          .text(listX + 8, listY + 4, "Your stash is empty.", {
            fontFamily: "Georgia, serif", fontSize: "14px", color: "#bdb38a",
          }).setScrollFactor(0).setDepth(52));
      }
      for (let i = 0; i < visibleCount; i++) {
        const idx = topRow + i;
        const entry = stash[idx];
        const price = sellPriceOf(entry.item, this.itemCatalog);
        const rowY = listY + i * rowH;
        const isCursor = idx === shop.sellCursor;
        const bgRow = this.add
          .rectangle(listX, rowY, W - 32, rowH - 2,
                     isCursor ? 0x3a2a22 : 0x161629, isCursor ? 1 : 0)
          .setOrigin(0).setScrollFactor(0).setDepth(51);
        shop.objects.push(bgRow);
        const prefix = isCursor ? "> " : "  ";
        const priceLabel = price > 0 ? `${price}g` : "—";
        shop.objects.push(this.add
          .text(listX + 8, rowY + 2, `${prefix}${entry.item}`, {
            fontFamily: "Georgia, serif", fontSize: "14px",
            color: isCursor ? "#ffd470"
                 : price > 0 ? "#f6efd6" : "#7e7e7e",
          }).setScrollFactor(0).setDepth(52));
        shop.objects.push(this.add
          .text(listX + W - 32 - 12, rowY + 2, priceLabel, {
            fontFamily: "monospace", fontSize: "13px", color: "#bdb38a",
          }).setOrigin(1, 0).setScrollFactor(0).setDepth(52));
      }
    }

    // Footer message + hint.
    if (message) {
      shop.objects.push(this.add
        .text(X + 16, Y + H - 36, message, {
          fontFamily: "Georgia, serif", fontSize: "13px", color: "#a3d9a5",
        }).setScrollFactor(0).setDepth(51));
    }
    const hint = mode === "buy"
      ? "[↑↓] choose   [Enter] buy   [Tab] sell   [ESC] leave"
      : "[↑↓] choose   [Enter] sell   [Tab] buy   [ESC] leave";
    shop.objects.push(this.add
      .text(X + 16, Y + H - 18, hint, {
        fontFamily: "monospace", fontSize: "12px", color: "#bdb38a",
      }).setScrollFactor(0).setDepth(51));
  }

  /** TAB swaps buy ↔ sell mode. Cursor remembered separately per side. */
  private toggleShopMode(): void {
    if (!this.shop) return;
    this.shop.mode = this.shop.mode === "buy" ? "sell" : "buy";
    this.shop.message = "";
    this.renderShop();
  }

  private moveShopCursor(delta: number): void {
    if (!this.shop) return;
    if (this.shop.mode === "buy") {
      const n = this.shop.counter.items.length;
      if (n === 0) return;
      this.shop.buyCursor = (this.shop.buyCursor + delta + n) % n;
    } else {
      const n = (gameState.partyData?.inventory ?? []).length;
      if (n === 0) return;
      this.shop.sellCursor = (this.shop.sellCursor + delta + n) % n;
    }
    this.renderShop();
  }

  /** Buy or sell, depending on which mode is active. */
  private confirmShopBuy(): void {
    if (!this.shop) return;
    const party = gameState.partyData;
    if (!party) {
      this.shop.message = "Party data isn't loaded.";
      this.renderShop();
      return;
    }
    if (this.shop.mode === "buy") {
      const items = this.shop.counter.items;
      if (items.length === 0) return;
      const itemName = items[this.shop.buyCursor];
      const r = buyItem(party, itemName, this.itemCatalog);
      this.shop.message = r.message;
    } else {
      if (party.inventory.length === 0) {
        this.shop.message = "Nothing in the stash to sell.";
      } else {
        const idx = Math.max(0, Math.min(party.inventory.length - 1, this.shop.sellCursor));
        const r = sellItem(party, idx, this.itemCatalog);
        this.shop.message = r.message;
        // Clamp the cursor in case the stash shrank.
        if (this.shop.sellCursor >= party.inventory.length) {
          this.shop.sellCursor = Math.max(0, party.inventory.length - 1);
        }
      }
    }
    this.renderShop();
  }

  private closeShop(): void {
    if (!this.shop) return;
    for (const o of this.shop.objects) o.destroy();
    this.shop = undefined;
  }

  // ── Temple service sub-mode ───────────────────────────────────────

  /**
   * Open the temple service menu for a priest. Pulls services from
   * counters.json's "healing" entry (heal-all-hp / restore-mp /
   * cure-poisons / raise-dead). Up/down to choose, Enter to buy,
   * ESC to leave.
   */
  private async openTemple(npc: NpcDef, counterOverride?: Counter): Promise<void> {
    const counter = counterOverride ?? this.counters.get("healing");
    if (!counter || counter.kind !== "service" || !counter.services?.length) {
      this.openDialogFallback(npc, [
        `${npc.name} blesses you, but the temple services aren't ready yet.`,
      ]);
      return;
    }
    const godSuffix = npc.godName ? ` of ${npc.godName}` : "";
    this.openTempleAtCounter(counter, `${npc.name} — Temple${godSuffix}`);
  }

  /**
   * Open the temple service UI for a bare counter (no NPC). Same role
   * as openShopAtCounter — used when the player walks into a service-
   * counter tile (e.g. a Healing Counter inside a shrine).
   */
  private openTempleAtCounter(counter: Counter, title: string): void {
    if (counter.kind !== "service" || !counter.services?.length) return;
    this.temple = {
      title,
      counter,
      cursor: 0,
      objects: [],
      message: "",
    };
    this.renderTemple();
  }

  private renderTemple(): void {
    if (!this.temple) return;
    const temple = this.temple; // local alias keeps TS narrowing in nested closures
    for (const o of temple.objects) o.destroy();
    temple.objects = [];
    const { title, counter, cursor, message } = temple;
    const services = counter.services ?? [];
    const W = 640, H = 320;
    const X = (960 - W) / 2;
    const Y = 100;
    const gold = gameState.partyData?.gold ?? 0;

    const bg = this.add
      .rectangle(X, Y, W, H, 0x161629, 0.98)
      .setOrigin(0).setScrollFactor(0)
      .setStrokeStyle(2, 0xc8553d)
      .setDepth(50);
    temple.objects.push(bg);
    temple.objects.push(this.add
      .text(X + 16, Y + 12, title, {
        fontFamily: "Georgia, serif", fontSize: "18px", color: "#ffd470",
      }).setScrollFactor(0).setDepth(51));
    temple.objects.push(this.add
      .text(X + W - 16, Y + 14, `Party Gold: ${gold}g`, {
        fontFamily: "monospace", fontSize: "14px", color: "#ddc05c",
      }).setOrigin(1, 0).setScrollFactor(0).setDepth(51));

    const listX = X + 16;
    const listY = Y + 56;
    const rowH = 48;
    services.forEach((svc, i) => {
      const rowY = listY + i * rowH;
      const isCursor = i === cursor;
      const canAfford = gold >= svc.cost;
      const bgRow = this.add
        .rectangle(listX, rowY, W - 32, rowH - 4,
                   isCursor ? 0x3a2a22 : 0x161629, isCursor ? 1 : 0)
        .setOrigin(0).setScrollFactor(0).setDepth(51);
      temple.objects.push(bgRow);
      const prefix = isCursor ? "> " : "  ";
      temple.objects.push(this.add
        .text(listX + 8, rowY + 4, `${prefix}${svc.name}`, {
          fontFamily: "Georgia, serif", fontSize: "15px",
          color: isCursor ? "#ffd470" : "#f6efd6",
        }).setScrollFactor(0).setDepth(52));
      temple.objects.push(this.add
        .text(listX + W - 32 - 12, rowY + 4, `${svc.cost}g${canAfford ? "" : " — short"}`, {
          fontFamily: "monospace", fontSize: "13px",
          color: canAfford ? "#bdb38a" : "#d86a4a",
        }).setOrigin(1, 0).setScrollFactor(0).setDepth(52));
      temple.objects.push(this.add
        .text(listX + 8, rowY + 22, svc.description, {
          fontFamily: "Georgia, serif", fontSize: "12px", color: "#bdb38a",
          wordWrap: { width: W - 48 },
        }).setScrollFactor(0).setDepth(52));
    });

    if (message) {
      temple.objects.push(this.add
        .text(X + 16, Y + H - 36, message, {
          fontFamily: "Georgia, serif", fontSize: "13px", color: "#a3d9a5",
        }).setScrollFactor(0).setDepth(51));
    }
    temple.objects.push(this.add
      .text(X + 16, Y + H - 18, "[↑↓] choose   [Enter] purchase   [ESC] leave", {
        fontFamily: "monospace", fontSize: "12px", color: "#bdb38a",
      }).setScrollFactor(0).setDepth(51));
  }

  private moveTempleCursor(delta: number): void {
    if (!this.temple) return;
    const n = (this.temple.counter.services ?? []).length;
    if (n === 0) return;
    this.temple.cursor = (this.temple.cursor + delta + n) % n;
    this.renderTemple();
  }

  private confirmTempleService(): void {
    if (!this.temple) return;
    const party = gameState.partyData;
    if (!party) {
      this.temple.message = "Party data isn't loaded.";
      this.renderTemple();
      return;
    }
    const services = this.temple.counter.services ?? [];
    if (services.length === 0) return;
    const svc: CounterService = services[this.temple.cursor];
    const r = performTempleService(party, svc);
    this.temple.message = r.message;
    this.renderTemple();
  }

  private closeTemple(): void {
    if (!this.temple) return;
    for (const o of this.temple.objects) o.destroy();
    this.temple = undefined;
  }

  /**
   * Helper used when role-based dispatch can't open the proper UI
   * (counter data missing, etc.). Falls back to the regular dialogue
   * popup with a single explanatory line.
   */
  private openDialogFallback(npc: NpcDef, lines: string[]): void {
    const stub: NpcDef = { ...npc, dialogue: lines };
    // Bypass the role re-dispatch by going straight to the dialog
    // builder code that openDialog used to inline. Easier to just
    // call openDialog with a temporarily neutered npc_type.
    const neutered: NpcDef = { ...stub, npcType: "villager" };
    this.openDialog(neutered);
  }
}
