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
import {
  loadSpawnPoints,
  trySpawnMonster,
  roamStep,
  type SpawnPoint,
  type RoamingMonster,
} from "../world/SpawnPoints";
import {
  loadMonsters,
  loadedMonsterSprites,
  type MonsterSpec,
} from "../data/monsters";
import { TILE_GRASS } from "../world/Tiles";
import { dataPath } from "../world/Module";
import { defaultRng } from "../rng";

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
  /** Loaded spawn-tile catalog keyed by tile id. */
  private spawnPoints: Map<number, SpawnPoint> = new Map();
  /** Live monster catalog — used to resolve spawn-list names + sprites. */
  private monsterCatalog: Map<string, MonsterSpec> = new Map();
  /** Per-roamer-id sprite shown over its current tile. Rebuilt every
   *  step so positions stay in sync with gameState.roamingMonsters. */
  private roamerSprites: Map<string, Phaser.GameObjects.GameObject> = new Map();

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
    this.load.json("tile_defs", dataPath("tile_defs.json"));
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
    // Monster sprites for any roamer that might appear on the map.
    // After loadMonsters() runs once, loadedMonsterSprites() returns
    // the full union; on cold boot we just queue the BUILTIN set.
    for (const path of loadedMonsterSprites()) {
      const key = `monster:${path}`;
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

    // Load spawn data + apply any pending tile destructions BEFORE
    // drawMap. If we did this after, the destroyed spawn would still
    // render with its old id — drawMap creates Phaser GameObjects from
    // the current tile state and they don't auto-update on later
    // setTile() calls. Doing it here means a freshly-destroyed lair
    // shows up as plain grass the moment we return from combat.
    try {
      this.spawnPoints = await loadSpawnPoints();
      this.monsterCatalog = await loadMonsters();
      this.applyPendingSpawnDestructions();
    } catch {
      /* spawn data missing — degrade gracefully */
    }

    this.drawMap();
    this.drawPlayer();
    this.drawHud();
    this.installCamera();
    this.installInput();
    this.refreshHud();
    if (this.dark) this.refreshDarkness();

    // Catalog-driven monster sprite preloads + roamer overlay both
    // run after drawMap because they layer on top of the static map.
    try {
      let queued = 0;
      for (const path of loadedMonsterSprites()) {
        const key = `monster:${path}`;
        if (!this.textures.exists(key)) {
          this.load.image(key, path);
          queued += 1;
        }
      }
      if (queued > 0) this.load.start();
      this.renderRoamers();
    } catch {
      /* spawn data missing — degrade gracefully */
    }

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
        const hasSprite = !!(key && this.textures.exists(key));
        if (hasSprite) {
          this.add.image(x, y, key!).setOrigin(0);
        } else {
          // Fallback: coloured rectangle for tiles without a sprite.
          const def = tileDef(id);
          const colorHex = Phaser.Display.Color.GetColor(...def.color);
          this.add.rectangle(x, y, TILE, TILE, colorHex).setOrigin(0);
        }
        // Spawn tiles get a thematic pulse on top of their sprite so
        // they read as "active lair" without needing a glyph. Other
        // encounter triggers (the rare TILE_ENCOUNTER without an art
        // asset) still get the ✦ marker so the player can spot them.
        if (isEncounterTrigger(id)) {
          if (this.spawnPoints.has(id)) {
            this.spawnSpawnAnimation(id, x, y);
          } else if (!hasSprite) {
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
        // Tick spawn-tile production + roamer pursuit. If a roamer
        // closed to within one tile of the party, jump straight to
        // combat against that creature; otherwise fall through to the
        // normal tile-based encounter check.
        const engaged = this.tickSpawnsAndRoamers();
        this.renderRoamers();
        if (engaged) {
          this.engageRoamer(engaged);
          return;
        }
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
    if (gameState.destroyedSpawns.has(key)) return;
    // If this is a Monster Spawn tile we have data for, hand combat
    // its boss list and ask CombatScene to destroy the tile on
    // victory. Other trigger tiles fall back to the random sample
    // encounter we've used since the demo combat route.
    const sp = this.spawnPoints.get(id);
    const terrainTileId = this.sampleNeighborTerrain(col, row);
    this.cameras.main.fadeOut(220, 0, 0, 0);
    this.cameras.main.once("camerafadeoutcomplete", () => {
      this.scene.start("CombatScene", {
        fromWorld: true,
        triggerKey: key,
        terrainTileId,
        monsterNames: sp && sp.boss_monsters.length > 0 ? sp.boss_monsters : undefined,
        destroySpawnKey: sp ? key : undefined,
      });
    });
  }

  // ── Spawn-tile system ─────────────────────────────────────────────
  //
  // Mirrors the Python OverworldScene's `_spawn_from_spawn_tiles` +
  // roamer pursuit. Each player step runs one pass of:
  //   1. Roll the spawn chance for every nearby spawn tile and try
  //      to drop a fresh roamer.
  //   2. Walk every existing roamer one tile toward the party
  //      (cardinal pursuit).
  //   3. If any roamer is now adjacent to the party, hand off to
  //      combat with that monster's catalog name.

  /**
   * Spawn-tile animation overlay. Mirrors the Python renderer's
   * per-spawn flicker / pulse without recreating the procedural
   * vector art:
   *
   *   - TILE_SPAWN (66, generic / wall_torch art): warm orange
   *     flicker, sin-driven scale + alpha.
   *   - TILE_SPAWN_CAMPFIRE (67): faster, brighter flicker.
   *   - TILE_SPAWN_GRAVEYARD (68): slow eerie green pulse.
   *   - TILE_ENCOUNTER (69, dragon) + TILE 71 (wyvern): hot red glow.
   *
   * Each entry is a small filled circle layered over the sprite with
   * a yoyo tween — Phaser handles the animation loop, so there's no
   * per-frame cost in the scene's update().
   */
  private spawnSpawnAnimation(id: number, x: number, y: number): void {
    let color = 0xff8e3c;     // default warm orange
    let radius = 6;
    let radiusTo = 10;
    let alpha = 0.55;
    let durationMs = 700;
    if (id === 67)      { color = 0xff9a3c; radiusTo = 12; durationMs = 380; }
    else if (id === 68) { color = 0x7be2a8; radius = 8; radiusTo = 14; alpha = 0.4; durationMs = 1100; }
    else if (id === 69) { color = 0xff5040; radius = 8; radiusTo = 14; durationMs = 900; }
    else if (id === 71) { color = 0xffb04a; radius = 8; radiusTo = 14; durationMs = 900; }
    const cx = x + TILE / 2;
    const cy = y + TILE / 2;
    const halo = this.add
      .circle(cx, cy, radius, color, alpha)
      .setBlendMode(Phaser.BlendModes.ADD)
      .setDepth(6);
    this.tweens.add({
      targets: halo,
      radius: radiusTo,
      alpha: Math.max(0.15, alpha - 0.3),
      duration: durationMs,
      yoyo: true,
      repeat: -1,
      ease: "Sine.InOut",
    });
  }

  private renderRoamers(): void {
    // Wipe the previous frame's sprites and redraw from state. Cheap
    // enough for the small numbers of roamers a single map yields.
    for (const o of this.roamerSprites.values()) o.destroy();
    this.roamerSprites.clear();
    for (const m of gameState.roamingMonsters) {
      const x = m.col * TILE + TILE / 2;
      const y = m.row * TILE + TILE / 2;
      const key = m.sprite ? `monster:${m.sprite}` : null;
      let obj: Phaser.GameObjects.GameObject;
      if (key && this.textures.exists(key)) {
        obj = this.add.image(x, y, key).setDepth(8);
      } else {
        // Fallback: small red diamond. Keeps the entity visible even
        // when a sprite isn't ready (cold boot / unknown monster).
        obj = this.add
          .rectangle(x, y, TILE - 8, TILE - 8, 0xb04030, 1)
          .setStrokeStyle(2, 0x1a1a2e)
          .setDepth(8);
      }
      this.roamerSprites.set(m.id, obj);
    }
  }

  /**
   * Apply destruction queued by combat — replace the spawn tile with
   * grass, redraw that tile, and add it to destroyedSpawns so the
   * spawn loop skips it from now on. Called once at scene-create so a
   * spawn destroyed during the previous combat shows up immediately
   * when we return to the overworld.
   */
  private applyPendingSpawnDestructions(): void {
    if (gameState.destroyedSpawns.size === 0) return;
    for (const key of gameState.destroyedSpawns) {
      const [c, r] = key.split(",").map((s) => parseInt(s, 10));
      if (!Number.isFinite(c) || !Number.isFinite(r)) continue;
      // Only rewrite if the underlying tile is still a spawn marker —
      // a normal grass tile is already in the right state.
      const cur = this.tileMap.getTile(c, r);
      if (this.spawnPoints.has(cur)) {
        this.tileMap.setTile(c, r, TILE_GRASS);
      }
    }
  }

  /**
   * Step the spawn / roamer simulation by one tick. Called from
   * tryStep right after a successful party move. Returns the roamer
   * the party is now standing next to (if any) so the caller can
   * fast-path into combat instead of redrawing first.
   */
  private tickSpawnsAndRoamers(): RoamingMonster | null {
    if (this.spawnPoints.size === 0) return null;
    const party = gameState.playerPos;
    const scan = 10;

    // 1. Try to spawn from nearby spawn tiles.
    for (let dr = -scan; dr <= scan; dr++) {
      for (let dc = -scan; dc <= scan; dc++) {
        const c = party.col + dc;
        const r = party.row + dr;
        if (c < 0 || r < 0 || c >= this.tileMap.width || r >= this.tileMap.height) continue;
        const tid = this.tileMap.getTile(c, r);
        const sp = this.spawnPoints.get(tid);
        if (!sp) continue;
        const key = triggerKey(c, r);
        if (gameState.destroyedSpawns.has(key)) continue;
        const newMon = trySpawnMonster({
          spawnTile: { col: c, row: r, tileId: tid },
          point: sp,
          party,
          existing: gameState.roamingMonsters,
          isWalkable: (cc, rr) => this.tileMap.isWalkable(cc, rr),
          rng: defaultRng,
          spriteFor: (n) => this.monsterCatalog.get(n)?.sprite,
        });
        if (newMon) gameState.roamingMonsters.push(newMon);
      }
    }

    // 2. Walk every roamer one cardinal tile toward the party.
    for (const m of gameState.roamingMonsters) {
      const next = roamStep(
        m, party,
        (cc, rr) => this.tileMap.isWalkable(cc, rr),
        // Don't pile two roamers onto the same tile; allow stepping
        // onto the party tile (that's the engagement trigger).
        (cc, rr) => gameState.roamingMonsters.some(
          (o) => o !== m && o.col === cc && o.row === rr,
        ),
      );
      m.col = next.col;
      m.row = next.row;
    }

    // 3. Engagement check — first roamer within Chebyshev 1 wins.
    const hit = gameState.roamingMonsters.find(
      (m) => Math.max(Math.abs(m.col - party.col), Math.abs(m.row - party.row)) <= 1,
    );
    return hit ?? null;
  }

  /** Hand off to combat against a single roaming monster instance. */
  private engageRoamer(m: RoamingMonster): void {
    const terrainTileId = this.sampleNeighborTerrain(m.col, m.row);
    this.cameras.main.fadeOut(220, 0, 0, 0);
    this.cameras.main.once("camerafadeoutcomplete", () => {
      this.scene.start("CombatScene", {
        fromWorld: true,
        // No triggerKey — this isn't a tile-anchored encounter, so
        // we don't want consumedTriggers to mark anything.
        terrainTileId,
        monsterNames: [m.name],
        roamerId: m.id,
      });
    });
  }

  /**
   * Pick the most common walkable, non-trigger tile id in the 8
   * tiles surrounding (col, row). Falls back to the trigger tile's
   * own id when nothing useful is around (very rare — most map tiles
   * are surrounded by terrain).
   */
  private sampleNeighborTerrain(col: number, row: number): number {
    const counts = new Map<number, number>();
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        if (dc === 0 && dr === 0) continue;
        const t = this.tileMap.getTile(col + dc, row + dr);
        if (t < 0 || isEncounterTrigger(t)) continue;
        counts.set(t, (counts.get(t) ?? 0) + 1);
      }
    }
    if (counts.size === 0) return this.tileMap.getTile(col, row);
    let best = -1;
    let bestN = -1;
    for (const [t, n] of counts) {
      if (n > bestN) { best = t; bestN = n; }
    }
    return best;
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
