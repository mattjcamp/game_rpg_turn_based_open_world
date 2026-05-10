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
import { Music } from "../audio/Music";
import { gameState } from "../state";
import { rememberScene } from "../save";
import {
  tileDef,
  loadTileDefs,
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
  loadQuests,
  ensureQuestStates,
  creditKills,
  creditCollect,
  activeCollectStepFor,
  activeKillStepsForLocation,
  rosterFor,
  type QuestDef,
} from "../world/Quests";
import {
  flashQuestMessage,
  openQuestLog,
  showStepCompleteCallout,
} from "../world/QuestDialog";
import {
  attachPulsingGlow,
  QUEST_ITEM_COLOR,
  QUEST_MONSTER_COLOR,
  type PulsingGlowHandle,
} from "../world/GlowEffect";
import {
  generateDungeon,
  dungeonSeed,
  styleFloorTile,
  placeQuestKillMonsters,
  cleanupCompletedQuestMonsters,
  TILE_STAIRS,
  TILE_STAIRS_DOWN,
  TILE_CHEST,
  TILE_TRAP,
  TILE_ARTIFACT,
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
  partyLightTint,
  tickGaladrielsLight,
  consumeTorch,
} from "../world/PartyActions";
import {
  advanceClock,
} from "../world/GameTime";
import { brightnessAt, type LightSource } from "../world/Lighting";
import { roamStep } from "../world/SpawnPoints";
import {
  loadMonsters,
  loadedMonsterSprites,
  type MonsterSpec,
} from "../data/monsters";

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
  private monsterCatalog: Map<string, MonsterSpec> = new Map();
  /** Module quests — loaded in create() so kill / collect credit can
   *  resolve which active quest a defeated encounter or picked-up
   *  artifact belongs to. */
  private questDefs: QuestDef[] = [];
  /** Quest log overlay close handle (Q hotkey). */
  private questLogClose?: () => void;
  /** Pulsing-glow overlays per quest-artifact tile. Keyed by
   *  "col,row" so we can dispose the glow when the player picks up
   *  the artifact (which restores the floor underneath). */
  private artifactGlows: Map<string, PulsingGlowHandle> = new Map();
  /** Pulsing gold halos per quest-spawned monster on the active
   *  floor. Keyed by monster id so each one can be torn down when
   *  the monster is engaged or the floor changes. */
  private questMonsterGlows: Map<string, PulsingGlowHandle> = new Map();

  // Phaser objects
  private tileSprites: Phaser.GameObjects.GameObject[][] = [];
  private decorSprites: Map<string, Phaser.GameObjects.GameObject> = new Map();
  private monsterSprites: Map<string, Phaser.GameObjects.GameObject> = new Map();
  private darknessRects: Map<string, Phaser.GameObjects.Rectangle> = new Map();
  /** Coloured tint layer above darkness — picks up the party-carried
   *  light's hue (warm orange for torches, pale blue for Galadriel's,
   *  red for Infravision) and washes lit cells with it. Mirrors the
   *  same pair of rectangles TownScene maintains for interior darkness. */
  private tintRects: Map<string, Phaser.GameObjects.Rectangle> = new Map();
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
    this.tintRects = new Map();
    this.busy = false;
    this.message = undefined;
    this.messageTimer = undefined;
    for (const h of this.artifactGlows.values()) h.destroy();
    this.artifactGlows = new Map();
    for (const h of this.questMonsterGlows.values()) h.destroy();
    this.questMonsterGlows = new Map();
    this.questLogClose = undefined;
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
    // Monster sprites — loadMonsters() may not have run yet on a cold
    // boot (e.g. /world is the first scene the user loads and they
    // step into a dungeon before any combat). The BUILTIN set ships
    // here regardless; the post-loadMonsters() pass in create() picks
    // up the rest.
    for (const path of loadedMonsterSprites()) {
      this.load.image(`monster:${path}`, path);
    }
  }

  async create(): Promise<void> {
    this.cameras.main.setBackgroundColor("#0c0c14");
    // Crossfade into the dungeon playlist. Re-entry from a combat
    // encounter inside the dungeon is a no-op (we're already on
    // the dungeon track when we left); fresh entries from the
    // overworld trigger the standard 1.5s crossfade.
    Music.playArea("dungeon");

    // Re-entry from combat hits a Phaser texture cache where the
    // runtime tile defs may already be populated (OverworldScene
    // loaded them on first boot) but the `filecomplete-json-tile_defs`
    // listener in our preload doesn't re-fire because the JSON is
    // cached. `loadTileDefs()` has its own module-level dedupe so
    // calling it here is a cheap idempotent guarantee that
    // `tileDef(id).flags` is populated — which the lighting model
    // depends on for wall-torch radiance.
    try { await loadTileDefs(); } catch { /* tile_defs absent — leave fallback colours */ }

    // Only load from disk when no live party is in memory yet —
    // matches the guard the other world scenes use. Calling
    // `loadParty()` unconditionally here used to hand back the
    // stale module cache and silently overwrite the player's live
    // inventory (gold, bought weapons, quest items, …) with seed
    // party.json data, manifesting as "my stash reset to five
    // rocks the moment I entered the cave."
    if (!gameState.partyData) {
      try {
        gameState.partyData = await loadParty();
      } catch {
        /* couldn't load — leave null; this.partyData stays null too */
      }
    }
    this.partyData = gameState.partyData;

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

    // Load the monster catalog and queue any sprites the BUILTIN
    // pre-pass missed. Phaser dedupes loader keys, so a sprite already
    // in the texture cache is a free no-op.
    try {
      this.monsterCatalog = await loadMonsters();
      let queued = 0;
      for (const path of loadedMonsterSprites()) {
        const k = `monster:${path}`;
        if (!this.textures.exists(k)) {
          this.load.image(k, path);
          queued += 1;
        }
      }
      if (queued > 0) this.load.start();
    } catch {
      this.monsterCatalog = new Map();
    }

    // Quest definitions. Failure here is non-fatal — kill/collect
    // credit just won't fire, but the dungeon is still playable.
    try {
      this.questDefs = await loadQuests();
      ensureQuestStates(this.questDefs, gameState.moduleQuestStates);
    } catch {
      this.questDefs = [];
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
    // Place quest collect artifact(s) on the deepest floor if an
    // active quest's collect step targets this dungeon. Idempotent:
    // re-entries skip placement when an artifact for the same step
    // is already recorded on the level.
    this.placeQuestArtifactsIfNeeded();
    // Place quest-required kill encounters (goblin warbands, the
    // ambush boss, etc.) into the appropriate floors. Top-up only:
    // re-entries don't respawn already-killed monsters.
    this.spawnQuestKillMonstersIfNeeded();

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

    // Auto-light a torch BEFORE the first darkness pass so the initial
    // render shows the right party-light radius. Mirrors the Python
    // `DungeonState.enter` flow. Returning from combat skips this so
    // we don't burn a fresh torch on top of an already-active one or
    // double-fire the entry message.
    const isFreshEntry = !dpos || (dpos.col === this.level.entryCol && dpos.row === this.level.entryRow && dpos.level === 0);
    let entryTorchMsg = "";
    if (isFreshEntry) entryTorchMsg = this.tryAutoLightTorch();

    this.refreshDarkness();
    this.refreshHud();

    if (isFreshEntry) {
      this.showMessage(`You enter ${this.level.name}. ${entryTorchMsg}`, 2400);
    }

    // Credit any quest kill steps satisfied by the combat the party
    // just returned from. The encounter table is the source of truth
    // for "monster X is in encounter Y's roster"; both `creditKills`
    // and the dungeon scene share the same loaded copy.
    if (
      gameState.pendingKilledMonsters.length > 0 &&
      this.encounterTable &&
      this.questDefs.length > 0
    ) {
      const result = creditKills(
        this.questDefs,
        gameState.moduleQuestStates,
        this.encounterTable,
        gameState.pendingKilledMonsters,
        gameState.combatLocation,
      );
      // One callout per step that just completed. Progress messages
      // (n/N kills) still go to the console; the centered banner is
      // reserved for transitions the player needs to notice.
      for (const c of result.callouts) {
        showStepCompleteCallout(this, {
          questName: c.questName,
          description: c.description,
          questComplete: c.questComplete,
        });
      }
      for (const m of result.messages) console.log("[quest]", m);
    }
    gameState.pendingKilledMonsters = [];

    // Save snapshot — closing the tab inside the dungeon resumes
    // back into this same dungeon on next launch. The payload
    // is the same init shape the scene started with.
    rememberScene({
      key: "DungeonScene",
      payload: {
        dungeonName: this.dungeonName,
        overworldCol: this.overworldCol,
        overworldRow: this.overworldRow,
      },
    });
  }

  /**
   * Attempt to auto-light a torch from the party's stash on dungeon
   * entry. Returns a short status string for the entry-message line.
   * Skipped when the party already has Galadriel's Light, Infravision,
   * or an active torch — no point burning a fresh torch on top of a
   * working light source.
   */
  private tryAutoLightTorch(): string {
    if (!this.partyData) return "";
    if (this.partyData.torchSteps > 0) return "Torch lit.";
    // partyHasEffect imports are heavy; use the same fields
    // partyLightRadius would peek at via a cheap check.
    const radius = partyLightRadius(this.partyData, 0);
    if (radius >= 5) return "";  // Galadriel's Light or Infravision already up.
    const result = consumeTorch(this.partyData);
    return result.ok ? "Torch lit." : "No torch equipped — it's dark.";
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
    // Tear down quest-monster glows from the previous floor — the
    // sprites are gone, the halos shouldn't outlive them.
    for (const g of this.questMonsterGlows.values()) g.destroy();
    this.questMonsterGlows.clear();
    for (const r of this.darknessRects.values()) r.destroy();
    this.darknessRects.clear();
    for (const r of this.tintRects.values()) r.destroy();
    this.tintRects.clear();

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
    // Quest-artifact halos — cyan glow over every TILE_ARTIFACT on
    // this floor. Disposed when the player picks an artifact up.
    this.spawnArtifactGlows();
    // Per-cell darkness overlay (depth 9 — above monsters, below player)
    // plus a tint pass at depth 9.5 that washes lit cells with the
    // party-light colour (warm/blue/red). Both meshes always exist;
    // refreshDarkness sets per-cell alphas every step.
    for (let row = 0; row < this.level.height; row++) {
      for (let col = 0; col < this.level.width; col++) {
        const d = this.add
          .rectangle(col * TILE, row * TILE, TILE, TILE, 0x000000, 1)
          .setOrigin(0)
          .setDepth(9);
        this.darknessRects.set(`${col},${row}`, d);
        const t = this.add
          .rectangle(col * TILE, row * TILE, TILE, TILE, 0xffffff, 0)
          .setOrigin(0)
          .setDepth(9.5);
        this.tintRects.set(`${col},${row}`, t);
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
    const spec = this.monsterCatalog.get(m.name);
    const key = spec?.sprite ? `monster:${spec.sprite}` : null;
    let obj: Phaser.GameObjects.GameObject;
    if (key && this.textures.exists(key)) {
      obj = this.add.image(x, y, key).setDepth(7);
    } else {
      // Fallback: small red diamond, same shape OverworldScene falls
      // back to when the catalog or sprite isn't ready.
      obj = this.add
        .rectangle(x, y, TILE - 8, TILE - 8, 0xb04030, 1)
        .setStrokeStyle(2, 0x1a1a2e)
        .setDepth(7);
    }
    this.monsterSprites.set(m.id, obj);
    // Quest-spawned monsters get a soft gold halo so the player can
    // see at a glance which sprites credit a quest. Same colour /
    // intensity TownScene uses for interior quest targets.
    if (m.questName) {
      const sprite = obj as Phaser.GameObjects.Image | Phaser.GameObjects.Rectangle;
      const glow = attachPulsingGlow(
        this,
        () => sprite.x,
        () => sprite.y,
        { color: QUEST_MONSTER_COLOR, intensity: 0.5, depth: 6 },
      );
      this.questMonsterGlows.set(m.id, glow);
    }
  }

  private drawPlayer(): void {
    const dp = gameState.dungeonPos!;
    const x = dp.col * TILE + TILE / 2;
    const y = dp.row * TILE + TILE / 2;
    // Destroy any pre-existing avatar so floor changes don't leave a
    // phantom party sprite parked on the previous floor's stairs.
    if (this.player) {
      this.player.destroy();
    }
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
   *   - currently lit (party light OR a wall torch in range): alpha
   *     scales with brightness so the cell is bright at the source
   *     and fades toward the edge of the lit pool. Lit cells are
   *     also added to `exploredTiles` so they stay revealed once the
   *     party walks past — fog-of-war history.
   *   - previously seen but not lit now: dim (alpha 0.55).
   *   - never seen: pitch black (alpha 1).
   *
   * Fog-of-war is driven by light, not by a fixed step radius — that's
   * what makes a wall torch reveal the corridor it sits in the moment
   * the party walks into the torch's pool, exactly the way the Python
   * dungeon renderer does it.
   */
  private refreshDarkness(): void {
    const dp = gameState.dungeonPos!;
    const partyR = this.partyData ? partyLightRadius(this.partyData, 2) : 2;
    const tint = this.partyData ? partyLightTint(this.partyData) : null;
    // Wall-torch radiance contribution from tile_defs.flags.light_source
    // and the party-carried light pool are independent: the dungeon
    // owns its torches (driven by `torch_density`), and the party adds
    // their own pool on top. Both go through `brightnessAt`, which
    // takes the brighter of the two contributions per cell.
    const lights = this.collectLights();
    // Dungeon-flavoured LOS blocker. Walls / closed doors / non-
    // walkable cells block; tiles flagged `transparent` (water,
    // glass, etc.) pass light through. Mirrors `tileLightBlocker`
    // for TileMap, but reads the dungeon level's tile array + per-
    // cell `tileProperties.walkable` overrides instead of going
    // through TileMap.
    const lvl = this.level;
    const blocks = (col: number, row: number): boolean => {
      if (col < 0 || row < 0 || col >= lvl.width || row >= lvl.height) return true;
      const props = lvl.tileProperties[`${col},${row}`];
      if (props && typeof props.walkable === "boolean") return !props.walkable;
      const def = tileDef(lvl.tiles[row][col]);
      if (def.flags?.transparent) return false;
      return !def.walkable;
    };
    for (let row = 0; row < this.level.height; row++) {
      for (let col = 0; col < this.level.width; col++) {
        const rect = this.darknessRects.get(`${col},${row}`);
        const tintRect = this.tintRects.get(`${col},${row}`);
        if (!rect || !tintRect) continue;
        // ── Combined brightness ──
        const b = brightnessAt(col, row, lights, { col: dp.col, row: dp.row }, partyR, blocks);
        // ── Party-only brightness (drives the tint wash) ──
        // The tint is a property of what the PARTY carries, so we don't
        // want a wall torch to look red just because the party has
        // Infravision — the wash should only paint cells the party's
        // light actually reaches. Compute partyB by passing an empty
        // lights array (still LOS-gated so the wash doesn't bleed
        // through walls either).
        const partyB = brightnessAt(col, row, [], { col: dp.col, row: dp.row }, partyR, blocks);
        if (b > 0) {
          this.level.exploredTiles.add(`${col},${row}`);
          rect.setFillStyle(0x000000, Math.max(0, Math.min(0.92, (1 - b) * 0.92)));
        } else if (this.level.exploredTiles.has(`${col},${row}`)) {
          rect.setFillStyle(0x000000, SEEN_DIM);
        } else {
          rect.setFillStyle(0x000000, 1);
        }
        // Tint wash: only on cells the party's own light reaches, and
        // only when an effect that should colour the world is active
        // (Torch / Galadriel's / Infravision). Outside the party pool
        // the wash is fully transparent so wall-torch-lit cells keep
        // their natural look.
        if (tint && partyB > 0) {
          tintRect.setFillStyle(tint.color, partyB * tint.alphaScale);
        } else {
          tintRect.setFillStyle(0xffffff, 0);
        }
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
      // Party screen overlay — pause this scene so movement keys don't
      // fire while the inventory is up. PartyScene resumes us on close.
      if (ev.key === "p" || ev.key === "P") { this.openParty(); return; }
      // Q toggles the read-only quest log overlay.
      if (ev.key === "q" || ev.key === "Q") { this.toggleQuestLog(); return; }
      if (this.busy) return;
      if (ev.key === "Escape") {
        if (this.questLogClose) { this.toggleQuestLog(); return; }
        this.handleEscape();
        return;
      }
      if (this.questLogClose) return;  // log overlay swallows movement
      const dir = directionForKey(ev.key);
      if (dir) this.tryMove(dir.dc, dir.dr);
    });
  }

  private toggleQuestLog(): void {
    if (this.questLogClose) {
      this.questLogClose();
      this.questLogClose = undefined;
      return;
    }
    this.questLogClose = openQuestLog(this, this.questDefs, gameState.moduleQuestStates);
  }

  private openParty(): void {
    if (gameState.defeated) return;
    this.scene.pause();
    this.scene.launch("PartyScene", { from: "DungeonScene" });
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
    // Burn down a torch step — dungeons are always dark, so unlike the
    // overworld/town we tick unconditionally. When the counter hits
    // zero the next refreshDarkness sees torchSteps === 0 and snaps
    // the party-light pool away, making the dungeon go dark again.
    if (this.partyData && this.partyData.torchSteps > 0) {
      this.partyData.torchSteps -= 1;
      if (this.partyData.torchSteps === 0) {
        this.showMessage("Your torch burns out.", 1800);
      }
    }
    if (this.partyData) tickGaladrielsLight(this.partyData);
    this.busy = true;
    this.tweens.add({
      targets: this.player,
      x: nc * TILE + TILE / 2,
      y: nr * TILE + TILE / 2,
      duration: 110,
      onComplete: () => {
        this.busy = false;
        // Step every dungeon monster and redraw the sprite layer
        // BEFORE the standing-tile handler runs. If a monster moved
        // adjacent to the party, we engage immediately and skip the
        // chest/trap/stairs prompt — same precedence the Python game
        // uses (`_check_monster_contact` runs in the move handler
        // ahead of pickup logic).
        this.tickDungeonMonsters();
        this.redrawMonsters();
        const contact = this.checkMonsterContact();
        if (contact) {
          this.refreshDarkness();
          this.refreshHud();
          this.engageMonster(contact);
          return;
        }
        this.refreshDarkness();
        this.refreshHud();
        this.handleStandingTile();
      },
    });
  }

  /**
   * Move every monster on the current floor one tile. Monsters that
   * can see the party (Chebyshev <= 6) pursue via cardinal step that
   * minimises distance; the rest wander randomly with a small "stay
   * put" bias so the floor isn't a hive of constant motion.
   *
   * Mirrors `DungeonState._move_monsters` in `src/states/dungeon.py`.
   * Skips the line-of-sight check the Python version does — we'll
   * add it once the dungeon scene grows a wall-occlusion ray helper.
   */
  private tickDungeonMonsters(): void {
    const dp = gameState.dungeonPos!;
    const party = { col: dp.col, row: dp.row };
    const occupied = new Set<string>();
    for (const m of this.level.monsters) occupied.add(`${m.col},${m.row}`);
    occupied.add(`${party.col},${party.row}`);
    for (const m of this.level.monsters) {
      occupied.delete(`${m.col},${m.row}`);
      const dist = Math.max(Math.abs(m.col - party.col), Math.abs(m.row - party.row));
      let next: { col: number; row: number } = { col: m.col, row: m.row };
      if (dist <= 6) {
        next = roamStep(
          m,
          party,
          (c, r) => this.isWalkable(c, r),
          (c, r) => occupied.has(`${c},${r}`),
        );
      } else {
        // Random wander — 30% stay still, otherwise pick the first
        // walkable cardinal direction from a shuffled list.
        if (Math.random() >= 0.3) {
          const dirs: Array<[number, number]> = [[0, -1], [0, 1], [-1, 0], [1, 0]];
          for (let i = dirs.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            const t = dirs[i]; dirs[i] = dirs[j]; dirs[j] = t;
          }
          for (const [dc, dr] of dirs) {
            const nc = m.col + dc, nr = m.row + dr;
            if (nc < 0 || nc >= this.level.width || nr < 0 || nr >= this.level.height) continue;
            if (!this.isWalkable(nc, nr)) continue;
            if (occupied.has(`${nc},${nr}`)) continue;
            next = { col: nc, row: nr };
            break;
          }
        }
      }
      m.col = next.col;
      m.row = next.row;
      occupied.add(`${m.col},${m.row}`);
    }
  }

  private redrawMonsters(): void {
    for (const obj of this.monsterSprites.values()) obj.destroy();
    this.monsterSprites.clear();
    // Glows are recreated by drawMonster — tear down the old ones
    // first so we don't stack two halos on the same sprite (or
    // leave one behind for a monster that wandered off-floor).
    for (const g of this.questMonsterGlows.values()) g.destroy();
    this.questMonsterGlows.clear();
    for (const m of this.level.monsters) this.drawMonster(m);
  }

  /** First monster within Chebyshev 1 of the party, or null. */
  private checkMonsterContact(): DungeonMonster | null {
    const dp = gameState.dungeonPos!;
    for (const m of this.level.monsters) {
      const d = Math.max(Math.abs(m.col - dp.col), Math.abs(m.row - dp.row));
      if (d <= 1) return m;
    }
    return null;
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
    if (id === TILE_ARTIFACT) {
      this.pickUpArtifact(dp.col, dp.row);
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

  // ── Quest collect artifacts ─────────────────────────────────────

  /**
   * Walk the active collect quests; for any whose `spawn_location`
   * names this dungeon, paint a TILE_ARTIFACT on the deepest floor
   * (the boss/treasure floor of any multi-level dungeon — Floor N for
   * N levels, Floor 0 for single-level dungeons). Idempotent — skips
   * if the same step already has an artifact recorded on the level.
   *
   * Honors the optional `spawn_col` / `spawn_row` overrides on the
   * step. When the override coords aren't walkable or are off-map,
   * falls back to a deterministic search of walkable floor cells.
   */
  private placeQuestArtifactsIfNeeded(): void {
    if (this.questDefs.length === 0) return;
    const target = `dungeon:${this.dungeonName}`;
    const placement = activeCollectStepFor(
      this.questDefs,
      gameState.moduleQuestStates,
      target,
    );
    if (!placement) return;
    // Drop artifacts on the deepest floor — that's where the Python
    // game places quest artifacts (`place_artifact` flag in the
    // generator's last-floor branch).
    const lvl = this.levels[this.levels.length - 1];
    // Skip if this exact step already has an artifact on the level.
    for (const meta of Object.values(lvl.questArtifacts)) {
      if (meta.questName === placement.questName && meta.stepIdx === placement.stepIdx) {
        return;
      }
    }
    const pos = this.pickArtifactPos(lvl, placement.step.spawnCol, placement.step.spawnRow);
    if (!pos) {
      console.warn(`[quest] Could not place artifact for "${placement.questName}" — no walkable cell.`);
      return;
    }
    lvl.tiles[pos.row][pos.col] = TILE_ARTIFACT;
    lvl.questArtifacts[`${pos.col},${pos.row}`] = {
      questName: placement.questName,
      stepIdx: placement.stepIdx,
      itemName: placement.step.collectItem,
    };
  }

  /**
   * Top up dungeon-floor monster lists with the encounters every
   * active kill step demands. Mirrors the artifact placement above:
   * idempotent, only adds the missing copies on re-entry, no-op
   * when the encounter table didn't load.
   *
   * Without this pass, quests like "Goblins in the Hill" couldn't
   * complete — the procedural generator only places random
   * encounters from the level's encounter band, so the specific
   * "Wolves and Goblins" warbands the quest demands never appeared
   * unless the random roll happened to pick them.
   */
  private spawnQuestKillMonstersIfNeeded(): void {
    if (this.questDefs.length === 0) return;
    const target = `dungeon:${this.dungeonName}`;
    const steps = activeKillStepsForLocation(
      this.questDefs,
      gameState.moduleQuestStates,
      target,
    );
    // Build the active-step set FIRST. This drives both the cleanup
    // sweep below (which runs unconditionally) and the spawn pass
    // (only if there are rows to place).
    const activeStepKeys = new Set(
      steps.map((s) => `${s.questName}|${s.stepIdx}`),
    );
    // ── Sweep stale quest monsters from completed/turned-in steps ──
    //
    // Runs even when `steps` is empty — that's the case where the
    // player has completed every step of every quest targeting this
    // dungeon, and any quest monsters still in the cached level are
    // pure leftovers (a 4th wolf from an over-spawn, an orphaned boss
    // from a different distribution rule, or just a stale spawn from
    // a step that's now done). Without this sweep the player would
    // walk back into the dungeon and see glowing encounters from
    // quests that are already turned in.
    cleanupCompletedQuestMonsters(this.levels, activeStepKeys);

    // Nothing to place if nothing's active or the encounters file
    // didn't load — but the cleanup above still fired.
    if (steps.length === 0) return;
    if (!this.encounterTable) return;
    // Convert the quest-side rows into the placement helper's input
    // shape, looking up the encounter template for each step.
    const rows: import("../world/Dungeon").QuestKillSpawnRow[] = [];
    for (const s of steps) {
      const tmpl = rosterFor(this.encounterTable, s.step.encounter);
      if (!tmpl || tmpl.monsters.length === 0) continue;
      rows.push({
        questName: s.questName,
        stepIdx: s.stepIdx,
        remaining: s.remaining,
        template: {
          name: tmpl.name,
          monsters: tmpl.monsters,
          monsterPartyTile: tmpl.monsterPartyTile,
        },
      });
    }
    if (rows.length === 0) return;
    placeQuestKillMonsters(
      this.levels,
      rows,
      (col, row, levelIdx) => this.isWalkableOnLevel(col, row, levelIdx),
    );
  }

  /** Walkability check for an arbitrary floor (not just the current
   *  one) — the quest spawn pass needs to evaluate floors the player
   *  hasn't entered yet. Mirrors `isWalkable` but scoped to a
   *  passed-in level. */
  private isWalkableOnLevel(col: number, row: number, levelIdx: number): boolean {
    const lvl = this.levels[levelIdx];
    if (!lvl) return false;
    if (col < 0 || row < 0 || col >= lvl.width || row >= lvl.height) return false;
    const props = lvl.tileProperties[`${col},${row}`];
    if (props && typeof props.walkable === "boolean") return props.walkable;
    const id = lvl.tiles[row][col];
    return tileDef(id).walkable;
  }

  /** Attach a cyan pulsing halo over every artifact tile on the
   *  current floor. Called from `drawLevel` after the tile pass so
   *  the glow tracks the (static) cell. Disposed on pickup. */
  private spawnArtifactGlows(): void {
    for (const h of this.artifactGlows.values()) h.destroy();
    this.artifactGlows = new Map();
    for (const k of Object.keys(this.level.questArtifacts)) {
      const [c, r] = k.split(",").map((s) => parseInt(s, 10));
      if (!Number.isFinite(c) || !Number.isFinite(r)) continue;
      // Sanity: only glow if the tile is still TILE_ARTIFACT — a
      // partially-saved level might have stale entries.
      if (this.level.tiles[r][c] !== TILE_ARTIFACT) continue;
      const x = c * TILE + TILE / 2;
      const y = r * TILE + TILE / 2;
      this.artifactGlows.set(
        k,
        attachPulsingGlow(this, () => x, () => y, {
          color: QUEST_ITEM_COLOR,
          intensity: 1.0,
          depth: 7,
        }),
      );
    }
  }

  /** Resolve an artifact spawn cell. Honors explicit override coords
   *  when both are non-negative AND the cell is walkable; otherwise
   *  scans the level for the first walkable floor tile that isn't a
   *  stair / chest / trap (those tiles already have meaning). */
  private pickArtifactPos(
    lvl: DungeonLevel,
    overrideCol?: number,
    overrideRow?: number,
  ): { col: number; row: number } | null {
    if (typeof overrideCol === "number" && typeof overrideRow === "number"
        && overrideCol >= 0 && overrideRow >= 0
        && overrideCol < lvl.width && overrideRow < lvl.height) {
      const props = lvl.tileProperties[`${overrideCol},${overrideRow}`];
      const id = lvl.tiles[overrideRow][overrideCol];
      const def = tileDef(id);
      const walkable = props && typeof props.walkable === "boolean" ? props.walkable : def.walkable;
      if (walkable) return { col: overrideCol, row: overrideRow };
    }
    const floor = styleFloorTile(lvl.style);
    for (let r = 0; r < lvl.height; r++) {
      for (let c = 0; c < lvl.width; c++) {
        if (lvl.tiles[r][c] === floor) return { col: c, row: r };
      }
    }
    return null;
  }

  /**
   * Credit the active collect step the artifact at (col, row) belongs
   * to, surface a flash banner, and replace the tile with the level's
   * native floor so the cell blends back into the map.
   */
  private pickUpArtifact(col: number, row: number): void {
    const k = `${col},${row}`;
    const meta = this.level.questArtifacts[k];
    if (!meta) {
      // Stray artifact tile — show a generic pickup line and clear it.
      this.showMessage("You pick up a relic.", 2000);
    } else {
      const result = creditCollect(
        this.questDefs,
        gameState.moduleQuestStates,
        meta.questName,
        meta.stepIdx,
        meta.itemName,
      );
      if (gameState.partyData) {
        gameState.partyData.inventory.push({ item: meta.itemName });
      }
      // Promote the pickup to a centered step-complete banner —
      // mirrors the Python game's "STEP COMPLETE" / "QUEST COMPLETE"
      // callout. Falls back to a small flash when the credit didn't
      // produce a callout (defensive — a stale meta entry).
      if (result.callout) {
        showStepCompleteCallout(this, {
          questName: result.callout.questName,
          description: result.callout.description,
          questComplete: result.callout.questComplete,
        });
      } else {
        flashQuestMessage(this, result.message);
      }
      delete this.level.questArtifacts[k];
    }
    // Drop the cyan glow that was tracking this cell.
    const glow = this.artifactGlows.get(k);
    if (glow) { glow.destroy(); this.artifactGlows.delete(k); }
    const floor = styleFloorTile(this.level.style);
    this.level.tiles[row][col] = floor;
    this.replaceTileSprite(col, row);
    this.refreshHud();
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
    // Stamp the combat location BEFORE the scene transition so the
    // post-combat creditKills pass knows whether a step's
    // `spawn_location` matches. Use the dungeon name (no floor) —
    // `locationMatches` strips trailing " - Floor N" from either side.
    gameState.combatLocation = `dungeon:${this.dungeonName}`;
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
