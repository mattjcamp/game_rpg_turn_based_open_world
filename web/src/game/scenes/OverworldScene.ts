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
import { Music } from "../audio/Music";
import { Sfx } from "../audio/Sfx";
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
  tileLightBlocker,
  type LightSource,
} from "../world/Lighting";
import { decorationFor } from "../world/Decorations";
import { loadItems, type Item } from "../world/Items";
import { installTileEffects } from "../world/TileEffects";
import {
  advanceClock,
  clockDarknessParams,
  clockFromDate,
} from "../world/GameTime";
import {
  installSceneLog,
  refreshSceneLog,
  LOG_HEIGHT,
  type SceneLogHandle,
} from "../world/SceneLog";
import { partyLightRadius } from "../world/PartyActions";
import { gameState, triggerKey } from "../state";
import { rememberScene } from "../save";
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
import { TILE_GRASS, TILE_PATH, TILE_WATER, TILE_BOAT } from "../world/Tiles";
import { classifyBoatMove } from "../world/Boats";
import { dataPath, loadModuleConfig } from "../world/Module";
import { defaultRng } from "../rng";
import { tickGaladrielsLight } from "../world/PartyActions";
import { activeMembers, loadParty } from "../world/Party";
import {
  loadQuests,
  ensureQuestStates,
  acceptQuest,
  markTurnedIn,
  findQuest,
  applyTurnedInWorldUnlocks,
  applyWorldUnlocks,
  summariseUnlocks,
  type QuestDef,
} from "../world/Quests";
import {
  reachableFrom,
  snapToWalkable,
  tileMapWalk,
} from "../world/InteriorSpawn";
import {
  openQuestDialog as buildQuestDialog,
  closeQuestDialog as destroyQuestDialog,
  flashQuestMessage,
  flashSignMessage,
  openQuestLog,
  openVictoryModal,
  showQuestAcceptedCallout,
  type QuestDialogHandles,
} from "../world/QuestDialog";
import {
  attemptOverworldHerbalism,
  isForageableTile,
} from "../world/Examine";
import {
  attachPulsingGlow,
  QUEST_GIVER_COLOR,
  type PulsingGlowHandle,
} from "../world/GlowEffect";
import { normalizeSpritePath } from "../world/Towns";

const TILE = 32; // matches the source PNGs' native size

/**
 * One-shot gate for the save-resume routing. Set after the first
 * OverworldScene boot of the page session so subsequent legitimate
 * transitions (Town → Overworld via an exit tile, Dungeon →
 * Overworld) don't bounce the player back into whatever scene
 * `gameState.lastScene` happens to remember from its most recent
 * `rememberScene` call. Module-level so it resets on hard reload —
 * which is exactly when we DO want resume to fire again.
 */
let _resumeChecked = false;

export class OverworldScene extends Phaser.Scene {
  private tileMap!: TileMap;
  private player!: Phaser.GameObjects.Image;
  /** Bottom-of-viewport log strip (time + moon phase). The same
   *  helper is wired into TownScene and DungeonScene so every map
   *  scene presents an identical strip in the same screen position. */
  private sceneLog?: SceneLogHandle;
  private busy = false;
  /** Backwards-compat handle — kept around so old code paths that
   *  test `if (this.defeatOverlay)` still work. The new modal lives
   *  in `defeatModalObjects`; this points at the title Text inside
   *  it (or null when the modal isn't up). */
  private defeatOverlay?: Phaser.GameObjects.Text;
  /** Every GameObject that makes up the game-over modal. Populated
   *  by `showDefeat`, destroyed by `dismissDefeatModal`. */
  private defeatModalObjects: Phaser.GameObjects.GameObject[] = [];
  private darkness = new Map<string, Phaser.GameObjects.Rectangle>();
  /** Renamed from `lights` to avoid colliding with Phaser.Scene.lights. */
  private mapLights: LightSource[] = [];
  private dark = false;
  /** Loaded spawn-tile catalog keyed by tile id. */
  private spawnPoints: Map<number, SpawnPoint> = new Map();
  /** Items catalog (loaded once in create) — passed to decorationFor
   *  so tile_properties.item entries render with per-item glyphs. */
  private items: Map<string, Item> = new Map();
  /** Live monster catalog — used to resolve spawn-list names + sprites. */
  private monsterCatalog: Map<string, MonsterSpec> = new Map();
  /** Per-roamer-id sprite shown over its current tile. Rebuilt every
   *  step so positions stay in sync with gameState.roamingMonsters. */
  private roamerSprites: Map<string, Phaser.GameObjects.GameObject> = new Map();
  /** Boat sprites keyed by `${col},${row}` — kept in sync with
   *  gameState.boatPositions. The aboard boat's sprite is the same
   *  object; we just retarget the tween onto it. */
  private boatSprites: Map<string, Phaser.GameObjects.Image> = new Map();
  private boatBobTween?: Phaser.Tweens.Tween;
  /** Module quests loaded from the active module + per-name sprite
   *  Phaser objects for any whose `giverLocation` is "overview". */
  private questDefs: QuestDef[] = [];
  private questGiverSprites: Map<string, Phaser.GameObjects.GameObject> = new Map();
  /** Active quest-acceptance / turn-in overlay (shared helper). */
  private questDialog?: QuestDialogHandles;
  /** Read-only quest-log overlay (Q hotkey). */
  private questLogClose?: () => void;
  /** Halo handles for the on-map quest givers, keyed by quest name
   *  so claiming a quest mid-session can drop the matching glow
   *  alongside the giver sprite. */
  private questGiverGlows: Map<string, PulsingGlowHandle> = new Map();
  /** Runtime position of each overworld quest giver — seeded from
   *  the quest def's `giverCol`/`giverRow` and then mutated by the
   *  per-step wander tick. `homeCol`/`homeRow` is the anchor every
   *  giver stays within `QUEST_GIVER_WANDER_RANGE` Manhattan tiles
   *  of so they don't drift across the map. */
  private questGiverPositions: Map<string, { col: number; row: number; homeCol: number; homeRow: number }> = new Map();

  constructor() {
    super({ key: "OverworldScene" });
  }

  init(): void {
    // Phaser reuses the same scene instance across scene.start calls,
    // so transient state has to be reset here — otherwise a `busy=true`
    // left behind by an arrow-key tween that was interrupted by the
    // fade-into-combat (CombatScene takes over before the tween's
    // onComplete fires) blocks every input on return from combat,
    // leaving the party "frozen". The Maps also dangle stale Phaser
    // objects that get destroyed during scene shutdown — clearing them
    // means create() rebuilds from a clean slate.
    this.busy = false;
    this.dark = false;
    this.mapLights = [];
    this.darkness = new Map();
    this.roamerSprites = new Map();
    this.boatSprites = new Map();
    this.boatBobTween = undefined;
    this.defeatOverlay = undefined;
    this.defeatModalObjects = [];
    this.questGiverSprites = new Map();
    this.questDialog = undefined;
    this.questLogClose = undefined;
    for (const g of this.questGiverGlows.values()) g.destroy();
    this.questGiverGlows = new Map();
    // Don't clear questGiverPositions on init — runtime coords need
    // to survive the scene re-create that happens after every combat
    // / town round-trip, otherwise a wandering giver would teleport
    // back to its home tile every fight.
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
    // Switch to the overworld playlist. No-op when already playing
    // it (e.g. returning from a town or dungeon back to the same
    // area mid-session); a fresh boot triggers a 1.5s crossfade
    // from whatever was playing before.
    Music.playArea("overworld");
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

    // Seed the party's starting position from the map's `party_start`
    // (overview_map.json) on the first overworld boot of this session.
    // Subsequent boots — re-entry from a town, dungeon return, etc. —
    // keep whatever position the player has walked to; the flag stops
    // us re-snapping to the map start every time. The same flag also
    // gates the module-time seed below, so saved games (where the
    // flag is already true at hydration time) skip both seeds and
    // keep their persisted position + clock.
    if (!gameState.partyPosInitialized) {
      if (this.tileMap.partyStart) {
        gameState.playerPos = {
          col: this.tileMap.partyStart.col,
          row: this.tileMap.partyStart.row,
        };
      }
      // Seed the game clock from the module's `settings.start_time`
      // block. `loadModuleConfig` swallows fetch/parse errors and
      // returns an empty config in that case, so missing or malformed
      // module.json leaves the clock at its default epoch (year 1,
      // Jan 1 SUN 12:00 PM) instead of crashing the boot. The Dragon
      // of Dagorn module ships year 10 / June 1 / noon, so a fresh
      // adventure now opens with that calendar reading on the HUD.
      const config = await loadModuleConfig();
      if (config.settings.startTime) {
        gameState.clock = clockFromDate(config.settings.startTime);
      }
      gameState.partyPosInitialized = true;
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
    // Items catalog drives per-icon glyphs on tile_properties.item
    // overlays (drawMap below). A failure here just leaves us with
    // the generic gold-star fallback — every dropped item still
    // renders, just without the type-specific glyph.
    try { this.items = await loadItems(); }
    catch { /* items catalog missing — fall back to ★ */ }

    // Lift any TILE_BOAT cells into gameState.boatPositions and
    // overwrite the underlying data with water — boats are rendered
    // as their own sprite layer so they can move and bob without us
    // having to re-skin the static tile mesh.
    this.extractBoatTiles();

    // Module quests — load and render any "overview" quest givers.
    // Same pattern town quest givers use, just on the overworld layer.
    try {
      this.questDefs = await loadQuests();
      ensureQuestStates(this.questDefs, gameState.moduleQuestStates);
      // Re-apply world-unlock rewards from any turned-in quests so
      // the freshly-loaded JSON tile map matches the player's
      // history. Same idempotent design the Python game uses on
      // save load — the unlocks aren't persisted as a tile diff,
      // they're rederived from the (persisted) `turned_in` quest
      // statuses every time the overworld scene boots.
      applyTurnedInWorldUnlocks(
        this.tileMap,
        this.questDefs,
        gameState.moduleQuestStates,
      );
      // The overworld is the first scene the user lands on, so a
      // freshly-booted session may not have loaded party.json yet —
      // do it now so quest reward delivery has a party to mutate.
      if (!gameState.partyData) {
        try { gameState.partyData = await loadParty(); } catch { /* defer */ }
      }
      // Queue quest-giver sprites — these are filed under /assets/...
      // (the same path translation Towns.ts uses), so the loader
      // queues them as plain image keys. We `await` the loader so
      // the first `renderQuestGivers` call below sees the textures
      // ready; without this the giver shows the gold-rect fallback
      // until the player bounces through a town and back.
      let queued = 0;
      for (const def of this.questDefs) {
        if (def.giverLocation !== "overview") continue;
        const path = normalizeSpritePath(def.giverSprite);
        if (path && !this.textures.exists(path)) {
          this.load.image(path, path);
          queued += 1;
        }
      }
      if (queued > 0) {
        await new Promise<void>((res) => {
          this.load.once("complete", () => res());
          this.load.start();
        });
      }
    } catch {
      this.questDefs = [];
    }

    this.drawMap();
    this.drawBoats();
    // Animated tile_properties.effect overlays — torches flicker, fires
    // dance, smoke rises, fairy lights twinkle. Depth 7 puts them above
    // tiles + decoration glyphs but below darkness (9) and player (10).
    installTileEffects(this, this.tileMap, TILE, 7, this.items);
    this.drawPlayer();
    this.drawHud();
    this.installCamera();
    this.installInput();
    this.refreshHud();
    this.refreshDarkness();
    this.renderQuestGivers();

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

    // Resume routing — only on the FIRST OverworldScene boot of the
    // page session. After that, every legitimate Town/Dungeon → exit
    // tile transition starts OverworldScene fresh, and we must NOT
    // bounce the player back into the scene `lastScene` happens to
    // hold (which is whatever Town/Dungeon they last visited).
    if (!_resumeChecked) {
      _resumeChecked = true;
      const snap = gameState.lastScene;
      if (snap && snap.key !== "OverworldScene") {
        this.scene.start(snap.key, snap.payload);
        return;
      }
    }
    rememberScene({ key: "OverworldScene", payload: {} });
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
      // Pass the items catalog so a `tile_properties.item` field
      // resolves to its per-icon glyph (torch flame, potion phial,
      // sword, …) rather than the generic gold star.
      const spec = decorationFor(entry, this.items);
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
    // Always create the per-tile darkness mesh — it sits invisible
    // (alpha=0) under broad daylight and gets repainted whenever the
    // map is interior-dark or the clock rolls into dawn/dusk/night.
    for (let row = 0; row < this.tileMap.height; row++) {
      for (let col = 0; col < this.tileMap.width; col++) {
        const r = this.add
          .rectangle(col * TILE, row * TILE, TILE, TILE, 0x000000, 0)
          .setOrigin(0)
          .setDepth(9);
        this.darkness.set(`${col},${row}`, r);
      }
    }
  }

  /**
   * Repaint the per-tile darkness overlay. Three sources can darken
   * the world:
   *   1. Interior maps with baked light_source tiles ("this.dark") —
   *      pitch-black outside soft pools around each light + party.
   *   2. The game clock at dawn/dusk/night — colour-tinted wash.
   *   3. Daytime with no interior darkness — all tiles cleared to
   *      alpha=0 (broad daylight).
   * The two sources can co-exist (e.g. a town interior at night), in
   * which case interior darkness wins because the clock can't punch
   * light into a windowless room.
   */
  private refreshDarkness(): void {
    const party = gameState.playerPos;
    const clockParams = clockDarknessParams(gameState.clock);
    const partyR = gameState.partyData
      ? partyLightRadius(gameState.partyData, 2)
      : 2;
    // LOS blocker for the overworld tile map. Built once per refresh
    // so the closure is shared across the W*H * lights iteration.
    const blocks = tileLightBlocker(this.tileMap);
    for (let row = 0; row < this.tileMap.height; row++) {
      for (let col = 0; col < this.tileMap.width; col++) {
        const rect = this.darkness.get(`${col},${row}`);
        if (!rect) continue;
        if (this.dark) {
          // Interior darkness — same logic as before, with LOS so
          // walls / locked doors don't pass light through.
          const b = brightnessAt(col, row, this.mapLights, party, undefined, blocks);
          rect.setFillStyle(0x000000, Math.max(0, Math.min(0.92, (1 - b) * 0.92)));
          continue;
        }
        if (!clockParams) {
          rect.setFillStyle(0x000000, 0);
          continue;
        }
        if (clockParams.maxAlpha < 0.5) {
          // Dawn / dusk — uniform colour wash, no party-light pool.
          rect.setFillStyle(clockParams.tint, clockParams.maxAlpha);
          continue;
        }
        // Night — full black except pools around the party AND
        // every map-defined light (spawn-tile campfires, fairy
        // lights, etc.). Previously this passed [] for the lights
        // array, so the player had no way to navigate by torchlight
        // even in tile patches the map clearly marks as lit. LOS
        // blocker keeps light pools from leaking through walls.
        const b = brightnessAt(col, row, this.mapLights, party, partyR, blocks);
        const alpha = Math.max(0, Math.min(1, (1 - b) * clockParams.maxAlpha));
        rect.setFillStyle(clockParams.tint, alpha);
      }
    }
  }

  private drawPlayer(): void {
    const { col, row } = gameState.playerPos;
    const x = col * TILE + TILE / 2;
    const y = row * TILE + TILE / 2;
    this.player = this.add.image(x, y, "player").setDepth(10);
    // While the party is aboard a boat, the boat sprite IS the
    // marker — hide the avatar so the two don't visually overlap.
    if (gameState.onBoat) {
      this.player.setVisible(false);
      this.startBoatBobTween();
    }
  }

  /**
   * Move all TILE_BOAT cells in the freshly-loaded map into the
   * shared `gameState.boatPositions` set, replacing the underlying
   * tile data with TILE_WATER. Boats render as their own animated
   * sprite layer (`drawBoats`) so they can sail without us having to
   * mutate the static tile sprite mesh on every step.
   *
   * Idempotent across scene restarts: returning from combat re-loads
   * the map JSON (which still has TILE_BOAT in its source data), but
   * `gameState.boatPositions` already remembers the live runtime
   * positions, so we honour those instead of resetting to the JSON
   * baseline.
   */
  private extractBoatTiles(): void {
    const seenPositions = new Set<string>();
    for (let r = 0; r < this.tileMap.height; r++) {
      for (let c = 0; c < this.tileMap.width; c++) {
        if (this.tileMap.getTile(c, r) === TILE_BOAT) {
          this.tileMap.setTile(c, r, TILE_WATER);
          seenPositions.add(`${c},${r}`);
        }
      }
    }
    if (gameState.boatPositions.size === 0) {
      // First entry into this scene this session — seed from the JSON.
      gameState.boatPositions = seenPositions;
      return;
    }
    // Already populated (returning from combat or town): also force
    // every gameState boat tile to water so a freshly-loaded TILE_BOAT
    // at a position the boat already moved away from doesn't double up.
    for (const key of gameState.boatPositions) {
      const [c, r] = key.split(",").map((s) => parseInt(s, 10));
      if (Number.isFinite(c) && Number.isFinite(r)) {
        this.tileMap.setTile(c, r, TILE_WATER);
      }
    }
  }

  /**
   * Render every boat in `gameState.boatPositions` as a Phaser image
   * at depth 8 (above tiles, below the player). Called once per scene
   * create after `drawMap`. Sailing/disembarking re-keys this map
   * without going through here again.
   */
  private drawBoats(): void {
    const key = tileSpriteKey(TILE_BOAT);
    if (!key || !this.textures.exists(key)) return;
    for (const k of gameState.boatPositions) {
      const [c, r] = k.split(",").map((s) => parseInt(s, 10));
      if (!Number.isFinite(c) || !Number.isFinite(r)) continue;
      const img = this.add
        .image(c * TILE + TILE / 2, r * TILE + TILE / 2, key)
        .setDepth(8);
      this.boatSprites.set(k, img);
    }
  }

  /**
   * Start (or replace) the bob tween on the boat sprite the party is
   * currently riding. The tween yoyos the sprite ±1px vertically every
   * 350 ms — the same cadence the Python game uses in
   * `OverworldState.update`.
   */
  private startBoatBobTween(): void {
    this.stopBoatBobTween();
    const key = `${gameState.playerPos.col},${gameState.playerPos.row}`;
    const sprite = this.boatSprites.get(key);
    if (!sprite) return;
    this.boatBobTween = this.tweens.add({
      targets: sprite,
      y: sprite.y - 2,
      duration: 350,
      yoyo: true,
      repeat: -1,
      ease: "Sine.InOut",
    });
  }

  private stopBoatBobTween(): void {
    if (this.boatBobTween) {
      this.boatBobTween.stop();
      this.boatBobTween = undefined;
    }
  }

  private installCamera(): void {
    // Bounds extended downward by LOG_HEIGHT so the camera always
    // has headroom to scroll the bottom row of tiles above the log
    // strip. Without this, when the party stands on the bottom row
    // of a tall map the camera clamps and the player marker hides
    // behind the strip pinned at the viewport's bottom edge.
    this.cameras.main.setBounds(
      0,
      0,
      this.tileMap.width * TILE,
      this.tileMap.height * TILE + LOG_HEIGHT
    );
    this.cameras.main.startFollow(this.player, true, 0.2, 0.2);
  }

  private drawHud(): void {
    // Single shared log strip at the bottom of the viewport. The
    // pre-existing top-bar HUD (party HP, tile coords, controls hint)
    // was retired in favour of one consistent log surface across all
    // map scenes — the player gets a predictable place to read time
    // + moon phase whether they're standing on the overworld, in a
    // town, or deep in a dungeon. Future iterations will surface
    // step-driven log lines into this same strip.
    this.sceneLog = installSceneLog(this);
  }

  private refreshHud(): void {
    if (this.sceneLog) {
      refreshSceneLog(this.sceneLog, gameState.clock, gameState.partyData);
    }
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
      // SPACE — skip this turn. The party stays put but spawn / roamer
      // / Galadriel timers all tick, so the player can wait out a
      // monster or burn down a buffed effect deliberately.
      k.on("keydown-SPACE", () => this.skipTurn());
      // 'E' zooms into the local Examine view of the current tile —
      // forageable items, a Ranger/Alchemist INT save for reagents.
      k.on("keydown-E", () => this.openExamine());
      // 'P' opens the party screen as an overlay. We pause this scene
      // so its keyboard handlers don't fire while the overlay is up.
      k.on("keydown-P", () => {
        if (this.questDialog) return;
        this.openParty();
      });
      // Quest dialog choices — Y / Enter / Space accept (or claim),
      // N / Escape decline.
      k.on("keydown-Y", () => {
        if (this.questDialog) this.confirmOverworldQuestDialog();
      });
      k.on("keydown-N", () => {
        if (this.questDialog) this.closeOverworldQuestDialog();
      });
      k.on("keydown-ENTER", () => {
        if (this.questDialog) this.confirmOverworldQuestDialog();
      });
      k.on("keydown-ESC", () => {
        if (this.questDialog) this.closeOverworldQuestDialog();
        else if (this.questLogClose) this.toggleOverworldQuestLog();
      });
      k.on("keydown-Q", () => {
        if (this.questDialog) return;
        this.toggleOverworldQuestLog();
      });
    }

    this.input.on("pointerdown", (p: Phaser.Input.Pointer) => {
      // Quest dialog eats clicks — choices are keyboard-driven.
      if (this.questDialog) return;
      const world = this.cameras.main.getWorldPoint(p.x, p.y);
      const col = Math.floor(world.x / TILE);
      const row = Math.floor(world.y / TILE);
      // Tap on an adjacent quest giver opens the quest dialog.
      const dc = col - gameState.playerPos.col;
      const dr = row - gameState.playerPos.row;
      if (Math.max(Math.abs(dc), Math.abs(dr)) <= 1) {
        const giver = this.questGiverAt(col, row);
        if (giver) { this.openOverworldQuestDialog(giver); return; }
      }
      if (Math.abs(dc) + Math.abs(dr) !== 1) return;
      this.tryStep(dc, dr);
    });
  }

  /**
   * Skip the party's turn. Runs the same end-of-turn bookkeeping a
   * successful step does — Galadriel's Light tick, spawn/roamer
   * advance, encounter check — without moving the avatar.
   */
  private skipTurn(): void {
    if (this.busy || gameState.defeated) return;
    advanceClock(gameState.clock);
    if (gameState.partyData) {
      tickGaladrielsLight(gameState.partyData);
    }
    this.refreshHud();
    this.refreshDarkness();
    this.tickQuestGiverWander();
    const engaged = this.tickSpawnsAndRoamers();
    this.renderRoamers();
    if (engaged) {
      this.engageRoamer(engaged);
      return;
    }
    const { col, row } = gameState.playerPos;
    this.checkEncounter(col, row);
  }

  /** Shared "bumped a wall" shake — used by tryStep and the boat
   *  handler when they can't actually move. */
  private bumpShake(dc: number, dr: number): void {
    const target = gameState.onBoat
      ? this.boatSprites.get(`${gameState.playerPos.col},${gameState.playerPos.row}`) ?? this.player
      : this.player;
    this.busy = true;
    this.tweens.add({
      targets: target,
      x: target.x + dc * 4,
      y: target.y + dr * 4,
      duration: 60,
      yoyo: true,
      onComplete: () => (this.busy = false),
    });
  }

  /**
   * Apply a board / sail / disembark outcome from `classifyBoatMove`.
   * Updates `gameState.onBoat` + `boatPositions`, retargets the boat
   * sprite, hides/shows the player, restarts the bob tween — and runs
   * the same end-of-turn pipeline a regular step would (clock tick,
   * encounter check, etc.).
   */
  private applyBoatMove(
    kind: "board" | "sail" | "disembark",
    fromCol: number, fromRow: number,
    toCol: number, toRow: number,
  ): void {
    this.busy = true;
    const tileX = (c: number) => c * TILE + TILE / 2;
    const tileY = (r: number) => r * TILE + TILE / 2;
    const fromKey = `${fromCol},${fromRow}`;
    const toKey = `${toCol},${toRow}`;

    if (kind === "board") {
      // Hide the player avatar; the boat sprite is the marker now.
      this.player.setVisible(false);
      gameState.onBoat = true;
      gameState.playerPos = { col: toCol, row: toRow };
      this.player.x = tileX(toCol);
      this.player.y = tileY(toRow);
      this.startBoatBobTween();
    } else if (kind === "sail") {
      // Move the boat sprite from its old tile to the new one and
      // re-key the lookup map so future hit-tests find it there.
      const sprite = this.boatSprites.get(fromKey);
      if (sprite) {
        this.boatSprites.delete(fromKey);
        this.boatSprites.set(toKey, sprite);
        // Stop the bob tween before tweening the position so the two
        // tweens don't fight over `y`.
        this.stopBoatBobTween();
        this.tweens.add({
          targets: sprite,
          x: tileX(toCol),
          y: tileY(toRow),
          duration: 110,
          onComplete: () => this.startBoatBobTween(),
        });
      }
      gameState.boatPositions.delete(fromKey);
      gameState.boatPositions.add(toKey);
      gameState.playerPos = { col: toCol, row: toRow };
      this.player.x = tileX(toCol);
      this.player.y = tileY(toRow);
    } else {
      // disembark — boat stays where it is, party steps off.
      this.stopBoatBobTween();
      gameState.onBoat = false;
      gameState.playerPos = { col: toCol, row: toRow };
      this.player.setVisible(true);
      this.player.x = tileX(toCol);
      this.player.y = tileY(toRow);
    }

    // Mirror the end-of-turn pipeline tryStep runs after a normal move.
    advanceClock(gameState.clock);
    if (gameState.partyData) tickGaladrielsLight(gameState.partyData);
    this.refreshHud();
    this.refreshDarkness();
    this.busy = false;
    if (this.checkLink(toCol, toRow)) return;
    const engaged = this.tickSpawnsAndRoamers();
    this.renderRoamers();
    if (engaged) {
      this.engageRoamer(engaged);
      return;
    }
    this.checkEncounter(toCol, toRow);
  }

  private tryStep(dc: number, dr: number): void {
    if (this.busy || gameState.defeated) return;
    if (this.questDialog) return;
    const fromCol = gameState.playerPos.col;
    const fromRow = gameState.playerPos.row;
    const nc = fromCol + dc;
    const nr = fromRow + dr;
    // Bumping into a quest giver opens their dialog instead of moving.
    const giver = this.questGiverAt(nc, nr);
    if (giver) {
      this.bumpShake(dc, dr);
      this.openOverworldQuestDialog(giver);
      return;
    }

    // Boat-aware classification first — handles boarding, sailing, and
    // disembarking. Returns "passthrough" if the move has nothing to do
    // with boats and we should fall through to normal walking.
    const boatMove = classifyBoatMove(
      this.tileMap,
      { onBoat: gameState.onBoat, boatPositions: gameState.boatPositions },
      fromCol, fromRow, nc, nr,
    );
    if (boatMove.kind === "blocked") {
      this.bumpShake(dc, dr);
      return;
    }
    if (boatMove.kind === "board" || boatMove.kind === "sail" || boatMove.kind === "disembark") {
      this.applyBoatMove(boatMove.kind, fromCol, fromRow, nc, nr);
      return;
    }

    if (!this.tileMap.isWalkable(nc, nr)) {
      this.bumpShake(dc, dr);
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
        advanceClock(gameState.clock);
        if (gameState.partyData) {
          tickGaladrielsLight(gameState.partyData);
        }
        // Passive herbalism — every Ranger / Alchemist gets an INT
        // saving throw against DC 20 on each overworld step over a
        // forageable tile (grass / forest / sand / path). On a
        // success a reagent lands in the stash and a "Name found
        // Moonpetal!" label floats up from the party, mirroring the
        // sign-read float so the cue feels like part of the world
        // rather than a HUD pop.
        this.runHerbalismStep(nc, nr);
        this.refreshHud();
        this.refreshDarkness();
        this.tickQuestGiverWander();
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
    if (link.kind === "dungeon") {
      this.cameras.main.fadeOut(220, 0, 0, 0);
      this.cameras.main.once("camerafadeoutcomplete", () => {
        this.scene.start("DungeonScene", {
          dungeonName: link.name,
          overworldCol: col,
          overworldRow: row,
        });
      });
      return true;
    }
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
    // Outdoor encounters use a flat path-tile background so the
    // characters and monsters stay readable. The previous behaviour
    // sampled the dominant nearby terrain, which produced busy
    // tree-checkered or mountain-checkered arenas (notably for forest
    // / mountain triggers) where sprites blended into the floor.
    // Future work can theme combat backdrops more carefully; for
    // now the simple path fill matches what the user can clearly read.
    const terrainTileId = TILE_PATH;
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
   * Roll the per-step Herbalism passive for any Ranger / Alchemist
   * in the active party. Skipped on non-forageable tiles (water,
   * mountain, town/dungeon entrances) so the player doesn't pluck
   * Moonpetals out of stone. Each successful find drops a reagent
   * in the stash and floats a "Name found Reagent" label above the
   * party — same visual treatment a sign read uses, so the cue
   * lives in the world layer rather than the HUD strip.
   *
   * Multiple herbalists firing in the same step are stacked
   * vertically (16 px apart) so the labels don't collide.
   */
  private runHerbalismStep(col: number, row: number): void {
    if (!gameState.partyData) return;
    const tileId = this.tileMap.getTile(col, row);
    if (!isForageableTile(tileId)) return;
    const members = activeMembers(gameState.partyData);
    const finds = attemptOverworldHerbalism(
      gameState.partyData,
      members,
      defaultRng,
      this.items,
    );
    if (finds.length === 0) return;
    const playerX = col * TILE + TILE / 2;
    const playerY = row * TILE + TILE / 2;
    finds.forEach((find, i) => {
      flashSignMessage(
        this,
        `${find.member} found ${find.reagent}`,
        playerX,
        playerY - i * 16,
      );
    });
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
    //    While the party is aboard a boat, only sea creatures can
    //    initiate contact: a land monster on the shore can't board
    //    the boat. Mirrors `OverworldState._check_monster_contact`
    //    in the Python game (`src/states/overworld.py:1493`).
    const hit = gameState.roamingMonsters.find((m) => {
      if (Math.max(Math.abs(m.col - party.col), Math.abs(m.row - party.row)) > 1) return false;
      if (gameState.onBoat) {
        const terrain = this.monsterCatalog.get(m.name)?.terrain ?? "land";
        if (terrain !== "sea") return false;
      }
      return true;
    });
    return hit ?? null;
  }

  /** Hand off to combat against a single roaming monster instance. */
  private engageRoamer(m: RoamingMonster): void {
    // Same rationale as `checkEncounter` — a single flat path-tile
    // arena reads cleaner than the sampled-terrain mosaic.
    const terrainTileId = TILE_PATH;
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

  private openParty(): void {
    if (gameState.defeated) return;
    this.scene.pause();
    this.scene.launch("PartyScene", { from: "OverworldScene" });
  }

  /**
   * Zoom into the Examine scene for the tile under the party. Refuses
   * to fire while aboard a boat — the party can't forage from a
   * deck, same constraint the Python game enforces by binding E only
   * to walking-on-foot moves.
   */
  private openExamine(): void {
    if (gameState.defeated || gameState.onBoat) return;
    const { col, row } = gameState.playerPos;
    const tileId = this.tileMap.getTile(col, row);
    this.cameras.main.fadeOut(180, 0, 0, 0);
    this.cameras.main.once("camerafadeoutcomplete", () => {
      this.scene.start("ExamineScene", { col, row, tileId });
    });
  }

  /**
   * Game-over modal — shown when CombatScene returns with the
   * party fully wiped (`gameState.defeated`). Replaces the older
   * "Defeated. Reload the page to start over." static text with two
   * actionable buttons:
   *
   *   - **Return to Game** — soft revive. The party stands back up
   *     at full HP on the same overworld tile, the defeated flag
   *     clears, and the modal goes away. Treats the wipe as a
   *     "you blacked out and woke up here" moment rather than a
   *     hard end-game. Cheaper than a full save reload, and the
   *     rolling save's been overwritten with `defeated=true`
   *     anyway so loading it would just restore the same dead
   *     state — soft revive is the only useful "continue" path.
   *
   *   - **Start New Game** — wipes the rolling save + stored
   *     roster (via `startFreshSession`) and routes the page to
   *     `/new-game`, the same intro the title-screen "Start New
   *     Game" button uses. The user re-creates their party from
   *     scratch.
   *
   * Idempotent — calling twice is a no-op while the modal is up.
   */
  private showDefeat(): void {
    if (this.defeatOverlay) return;

    const W = 480;
    const H = 240;
    const X = (960 - W) / 2;
    const Y = (720 - H) / 2;
    const track = (obj: Phaser.GameObjects.GameObject): void => {
      this.defeatModalObjects.push(obj);
    };
    // Dim veil over the whole screen so the modal reads as modal.
    track(
      this.add
        .rectangle(0, 0, 960, 720, 0x000000, 0.78)
        .setOrigin(0)
        .setScrollFactor(0)
        .setDepth(95),
    );
    // Frame.
    track(
      this.add
        .rectangle(X, Y, W, H, 0x161629, 0.97)
        .setOrigin(0)
        .setStrokeStyle(3, 0xc8553d)
        .setScrollFactor(0)
        .setDepth(96),
    );
    // Title — also tracked as `defeatOverlay` for backwards-compat
    // with the "is the modal up?" idempotency guard.
    const title = this.add
      .text(480, Y + 36, "YOUR PARTY HAS FALLEN", {
        fontFamily: "Georgia, serif",
        fontSize: "26px",
        color: "#ff6b6b",
        align: "center",
        stroke: "#1a1a2e",
        strokeThickness: 5,
      })
      .setOrigin(0.5)
      .setScrollFactor(0)
      .setDepth(97);
    track(title);
    this.defeatOverlay = title;
    track(
      this.add
        .text(480, Y + 78, "Pick up where you fell, or begin again.", {
          fontFamily: "Georgia, serif",
          fontSize: "14px",
          color: "#dcc69a",
          align: "center",
        })
        .setOrigin(0.5)
        .setScrollFactor(0)
        .setDepth(97),
    );
    // Buttons — clickable rounded rectangles with centred labels.
    this.makeDefeatButton(
      X + 24, Y + 120, W - 48, 44,
      "Return to Game",
      "[Enter]",
      () => this.continueAfterDefeat(),
    );
    this.makeDefeatButton(
      X + 24, Y + 174, W - 48, 44,
      "Start New Game",
      "[Esc]",
      () => this.restartAfterDefeat(),
    );
    // Keyboard shortcuts — match what the buttons advertise.
    const k = this.input.keyboard;
    if (k) {
      const onEnter = (): void => {
        if (this.defeatOverlay) this.continueAfterDefeat();
      };
      const onEsc = (): void => {
        if (this.defeatOverlay) this.restartAfterDefeat();
      };
      k.once("keydown-ENTER", onEnter);
      k.once("keydown-SPACE", onEnter);
      k.once("keydown-ESC", onEsc);
    }
  }

  /** Build one game-over button at (x, y, w, h) with `label` + a
   *  small grey hotkey hint on the right edge. Tracks every
   *  GameObject it creates on `defeatModalObjects` so dismissal
   *  cleans up cleanly. */
  private makeDefeatButton(
    x: number, y: number, w: number, h: number,
    label: string, hotkey: string,
    onClick: () => void,
  ): void {
    const track = (obj: Phaser.GameObjects.GameObject): void => {
      this.defeatModalObjects.push(obj);
    };
    const bg = this.add
      .rectangle(x, y, w, h, 0x2a1f24, 1)
      .setOrigin(0)
      .setStrokeStyle(2, 0xc8553d)
      .setScrollFactor(0)
      .setDepth(97)
      .setInteractive({ useHandCursor: true });
    bg.on("pointerover", () => bg.setFillStyle(0x3a2b30, 1));
    bg.on("pointerout",  () => bg.setFillStyle(0x2a1f24, 1));
    bg.on("pointerdown", () => onClick());
    track(bg);
    track(
      this.add
        .text(x + w / 2, y + h / 2, label, {
          fontFamily: "Georgia, serif",
          fontSize: "18px",
          color: "#f6efd6",
        })
        .setOrigin(0.5)
        .setScrollFactor(0)
        .setDepth(98),
    );
    track(
      this.add
        .text(x + w - 12, y + h / 2, hotkey, {
          fontFamily: "monospace",
          fontSize: "11px",
          color: "#bdb38a",
        })
        .setOrigin(1, 0.5)
        .setScrollFactor(0)
        .setDepth(98),
    );
  }

  /** "Return to Game" handler — soft revive at the current tile. */
  private continueAfterDefeat(): void {
    if (!this.defeatOverlay) return;
    const party = gameState.partyData;
    if (party) {
      // Stand the active four back up at full HP / MP. We don't
      // touch the wider roster — players who'd benched a member
      // before the fight won't see them magically revived.
      for (const idx of party.activeParty) {
        const m = party.roster[idx];
        if (!m) continue;
        m.hp = m.maxHp;
        if (typeof m.maxMp === "number") m.mp = m.maxMp;
      }
    }
    gameState.defeated = false;
    // Persist the revived state so a refresh now resumes here, not
    // back to the wiped party.
    void import("../save").then(({ save }) => save());
    this.dismissDefeatModal();
  }

  /** "Start New Game" handler — full reset + route to /new-game. */
  private restartAfterDefeat(): void {
    if (!this.defeatOverlay) return;
    void import("../save").then(({ startFreshSession }) => {
      startFreshSession();
      // We're inside a Phaser scene, not a React component, so
      // useRouter isn't available. window.location.href is the
      // simplest reliable way to navigate; Next handles the route
      // change and re-mounts the title flow.
      if (typeof window !== "undefined") {
        window.location.href = "/new-game";
      }
    });
  }

  /** Tear down every GameObject the modal created and clear the
   *  idempotency guard so a future defeat can re-show. */
  private dismissDefeatModal(): void {
    for (const obj of this.defeatModalObjects) obj?.destroy();
    this.defeatModalObjects = [];
    this.defeatOverlay = undefined;
  }

  // ── Module quest givers (overworld) ─────────────────────────────

  /** Render every quest-giver NPC anchored to the overworld map.
   *  Sprites at depth 8 — above the tile mesh and decorations, below
   *  the darkness overlay and player marker. Re-runs when called by
   *  scene re-create; dictionary tracks sprites by quest name so we
   *  can despawn turned-in givers without scanning. */
  private renderQuestGivers(): void {
    for (const obj of this.questGiverSprites.values()) obj.destroy();
    this.questGiverSprites.clear();
    for (const g of this.questGiverGlows.values()) g.destroy();
    this.questGiverGlows = new Map();
    for (const def of this.questDefs) {
      if (def.giverLocation !== "overview") continue;
      const state = gameState.moduleQuestStates.get(def.name);
      if (state?.status === "turned_in") continue;
      // Seed runtime position on first sight of this giver. Subsequent
      // re-renders (after combat / town visits) honour the position
      // the wander tick last left them at.
      let pos = this.questGiverPositions.get(def.name);
      if (!pos) {
        // Snap unwalkable / unreachable authored coords to the nearest
        // tile the player can actually reach. Without this, an author
        // typo (giver placed on a Water tile, or inside a walled-off
        // shrine) leaves the NPC clipping through scenery and the
        // bump-to-talk flow can't engage them.
        const reachable = reachableFrom(
          tileMapWalk(this.tileMap),
          gameState.playerPos.col,
          gameState.playerPos.row,
        );
        const snapped = snapToWalkable(
          tileMapWalk(this.tileMap),
          def.giverCol,
          def.giverRow,
          {
            reachable,
            occupied: [...this.questGiverPositions.values()].map(
              (p) => [p.col, p.row] as const,
            ),
          },
        );
        pos = {
          col: snapped.col, row: snapped.row,
          homeCol: snapped.col, homeRow: snapped.row,
        };
        this.questGiverPositions.set(def.name, pos);
      }
      const path = normalizeSpritePath(def.giverSprite);
      const x = pos.col * TILE + TILE / 2;
      const y = pos.row * TILE + TILE / 2;
      let obj: Phaser.GameObjects.GameObject;
      if (path && this.textures.exists(path)) {
        obj = this.add.image(x, y, path).setDepth(8);
      } else {
        // Fallback: small gold diamond so the giver is still visible
        // even when the sprite hasn't loaded.
        obj = this.add
          .rectangle(x, y, TILE - 8, TILE - 8, 0xffd470, 1)
          .setStrokeStyle(2, 0x1a1a2e)
          .setDepth(8);
      }
      this.questGiverSprites.set(def.name, obj);

      // Soft pulsing halo so the giver reads as a quest hook in a
      // crowd. Tracked per-quest so the claim path can despawn it
      // alongside the giver sprite.
      const sprite = obj as Phaser.GameObjects.Image | Phaser.GameObjects.Rectangle;
      const glow = attachPulsingGlow(this, () => sprite.x, () => sprite.y, {
        color: QUEST_GIVER_COLOR,
        intensity: 0.35,
        depth: 7,
      });
      this.questGiverGlows.set(def.name, glow);
    }
  }

  /** How far an overworld quest giver may roam from its anchor.
   *  Manhattan distance, mirrors the town NPC default of 3. */
  private static readonly QUEST_GIVER_WANDER_RANGE = 3;
  /** Per-step probability a giver actually attempts a step. Lower
   *  than the town NPC rate so the realm-scale overworld doesn't
   *  feel manic. */
  private static readonly QUEST_GIVER_STEP_CHANCE = 0.5;

  /**
   * Step every overworld quest giver at most one tile per player
   * step. Wandering is anchored: each giver stays within
   * `QUEST_GIVER_WANDER_RANGE` Manhattan tiles of its home (the
   * `giver_col`/`giver_row` from quests.json) so they don't drift
   * across the realm. Skips the move when there's no walkable
   * candidate or the destination collides with another giver / the
   * party.
   */
  private tickQuestGiverWander(): void {
    if (this.questGiverPositions.size === 0) return;
    const occupied = new Set<string>();
    for (const p of this.questGiverPositions.values()) occupied.add(`${p.col},${p.row}`);
    occupied.add(`${gameState.playerPos.col},${gameState.playerPos.row}`);
    const dirs: Array<[number, number]> = [[0, -1], [0, 1], [-1, 0], [1, 0]];
    for (const [questName, pos] of this.questGiverPositions) {
      // Skip movement for any giver whose quest has been turned in —
      // the sprite and glow have been despawned already, but their
      // position entry can hang around until the scene reboots.
      const sprite = this.questGiverSprites.get(questName);
      if (!sprite) continue;
      if (Math.random() >= OverworldScene.QUEST_GIVER_STEP_CHANCE) continue;

      occupied.delete(`${pos.col},${pos.row}`);
      // Shuffle directions and pick the first valid step.
      const shuffled = [...dirs];
      for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        const t = shuffled[i]; shuffled[i] = shuffled[j]; shuffled[j] = t;
      }
      let stepped = false;
      for (const [dc, dr] of shuffled) {
        const nc = pos.col + dc;
        const nr = pos.row + dr;
        if (!this.tileMap.inBounds(nc, nr)) continue;
        if (!this.tileMap.isWalkable(nc, nr)) continue;
        if (occupied.has(`${nc},${nr}`)) continue;
        // Honour the wander leash so givers don't drift far from home.
        const dist = Math.abs(nc - pos.homeCol) + Math.abs(nr - pos.homeRow);
        if (dist > OverworldScene.QUEST_GIVER_WANDER_RANGE) continue;
        pos.col = nc;
        pos.row = nr;
        stepped = true;
        break;
      }
      occupied.add(`${pos.col},${pos.row}`);
      if (!stepped) continue;
      const targetX = pos.col * TILE + TILE / 2;
      const targetY = pos.row * TILE + TILE / 2;
      this.tweens.add({ targets: sprite, x: targetX, y: targetY, duration: 200 });
    }
  }

  /** Find a quest-giver NPC at (col, row), if any. Used by the
   *  pointer / step handlers to detect tap-to-talk and adjacent-step
   *  interactions. Honours the giver's wander position rather than
   *  the static `def.giverCol`/`Row` so the bump check tracks them. */
  private questGiverAt(col: number, row: number): QuestDef | null {
    for (const def of this.questDefs) {
      if (def.giverLocation !== "overview") continue;
      const state = gameState.moduleQuestStates.get(def.name);
      if (state?.status === "turned_in") continue;
      const pos = this.questGiverPositions.get(def.name) ?? { col: def.giverCol, row: def.giverRow };
      if (pos.col === col && pos.row === row) return def;
    }
    return null;
  }

  /** Open the quest-giver overlay for a quest. Called from the tap
   *  handler when the player clicks an adjacent giver, or from the
   *  arrow-key bump path when they walk into one. */
  private openOverworldQuestDialog(def: QuestDef): void {
    if (this.questDialog) return;
    const state = gameState.moduleQuestStates.get(def.name);
    if (!state) return;
    const handles = buildQuestDialog(this, {
      npcName: def.giverNpc,
      questName: def.name,
      defs: this.questDefs,
      state,
    });
    if (handles) this.questDialog = handles;
  }

  private confirmOverworldQuestDialog(): void {
    if (!this.questDialog) return;
    const { questName, mode } = this.questDialog;
    if (mode === "available") {
      const accepted = acceptQuest(gameState.moduleQuestStates, questName);
      this.closeOverworldQuestDialog();
      // Mirror TownScene's accept beat — same callout helper, same
      // SFX, so the player sees the same "QUEST ACCEPTED" treatment
      // whether they triggered it from a town NPC or an overworld
      // quest giver.
      if (accepted) {
        const def = findQuest(this.questDefs, questName);
        showQuestAcceptedCallout(this, {
          questName,
          firstStep: def?.steps[0]?.description,
        });
        Sfx.play("chirp");
      }
      return;
    }
    if (mode === "completed") {
      this.claimOverworldQuestReward(questName);
      return;
    }
    this.closeOverworldQuestDialog();
  }

  private closeOverworldQuestDialog(): void {
    destroyQuestDialog(this.questDialog);
    this.questDialog = undefined;
  }

  /** Same reward delivery as TownScene.claimQuestReward. Updates HUD
   *  + quest sprite layer so the giver despawns on final claim. */
  private claimOverworldQuestReward(questName: string): void {
    const def = findQuest(this.questDefs, questName);
    if (!def || !gameState.partyData) {
      this.closeOverworldQuestDialog();
      return;
    }
    const party = gameState.partyData;
    if (def.rewardGold > 0) party.gold = (party.gold ?? 0) + def.rewardGold;
    if (def.rewardXp > 0) {
      const alive = activeMembers(party).filter((m) => m.hp > 0);
      const recipients = alive.length > 0 ? alive : activeMembers(party);
      const share = Math.floor(def.rewardXp / Math.max(1, recipients.length));
      for (const m of recipients) m.exp = (m.exp ?? 0) + share;
    }
    for (const item of def.rewardItems) party.inventory.push({ item });
    // World-unlock rewards (e.g. a Bridge tile dropped at quest end).
    // Apply to the live tile map so the data is correct immediately;
    // the visible redraw lands on the next OverworldScene boot via
    // `applyTurnedInWorldUnlocks`, which is the natural lifecycle
    // for the rare overworld-claim case (most quests turn in inside
    // a town and the player walks out into a fresh draw). The
    // per-cell sprite cache `drawMap` builds isn't keyed by coord
    // today, so an in-place repaint would need a wider refactor we
    // can defer until a quest ships with `giver_location: "overview"`
    // and a world-unlock reward.
    const applied = applyWorldUnlocks(this.tileMap, def.rewardWorldUnlocks);
    const unlockSummary = summariseUnlocks(applied);
    markTurnedIn(gameState.moduleQuestStates, questName);
    this.closeOverworldQuestDialog();
    // Despawn the giver sprite now that the quest is turned in.
    const sprite = this.questGiverSprites.get(questName);
    if (sprite) { sprite.destroy(); this.questGiverSprites.delete(questName); }
    const glow = this.questGiverGlows.get(questName);
    if (glow) { glow.destroy(); this.questGiverGlows.delete(questName); }
    if (def.isFinalQuest) {
      openVictoryModal(this, def.victoryText);
    } else {
      const baseMsg = `Quest "${def.name}" complete!`;
      flashQuestMessage(
        this,
        unlockSummary ? `${baseMsg} ${unlockSummary}` : baseMsg,
      );
    }
    this.refreshHud();
  }

  private toggleOverworldQuestLog(): void {
    if (this.questLogClose) {
      this.questLogClose();
      this.questLogClose = undefined;
      return;
    }
    this.questLogClose = openQuestLog(this, this.questDefs, gameState.moduleQuestStates);
  }
}
