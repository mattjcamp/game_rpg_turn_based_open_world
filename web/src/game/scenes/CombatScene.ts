/**
 * Tactical combat scene.
 *
 *   ┌─ Top status bar ──────────────────────────────────────────┐
 *   │  BATTLE                                                   │
 *   ├─ Arena (left) ─────────────┬─ Right HUD ──────────────────┤
 *   │  18×21 grid of terrain     │ PARTY                        │
 *   │  tiles matching the        │ ┌──┐ Gimli   ▓▓▓ 20/20       │
 *   │  encounter location.       │ │  │                          │
 *   │  Party at the bottom,      │ ├──┤ Merry   ▓▓▓ 20/20       │
 *   │  enemies at the top.       │ │…│                          │
 *   │                            │ ├──┤ Gandolf ▓▓▓ 20/20  ▓▓ MP│
 *   │                            │ │…│                          │
 *   │                            │ ├──┤ Selina  ▓▓▓ 20/20  ▓▓ MP│
 *   │                            │ │…│                          │
 *   │                            │ -- Gimli'S TURN --            │
 *   │                            │ > Attack                      │
 *   │                            │   End Turn                    │
 *   │                            │   Flee                        │
 *   │                            │   Throw    (coming soon)      │
 *   │                            │   Defend   (coming soon)      │
 *   ├────────────────────────────┴───────────────────────────────┤
 *   │ Battle log (full-width — last ~7 lines, dice + mods)       │
 *   └────────────────────────────────────────────────────────────┘
 *
 * Movement uses arrow keys / WASD or tap-to-step (cardinal only).
 * The action menu uses UP/DOWN/Enter and works on top of the action
 * buttons we already had (End Turn, Flee, Attack via bump).
 */

import Phaser from "phaser";
import { Combat, isAiControlled } from "../combat/Combat";
import {
  ARENA_COLS,
  ARENA_ROWS,
  isWall,
  DIR_DELTAS,
  type Direction,
} from "../combat/Arena";
import { makeSampleParty, PARTY_SPRITES } from "../data/fighters";
import {
  makeSampleEncounter,
  makeMonsterByName,
  loadMonsters,
  loadedMonsterSprites,
  MONSTER_SPRITES,
} from "../data/monsters";
import { gameState } from "../state";
import { tileSpriteKey, populateRuntimeDefs, spriteManifest } from "../world/Tiles";
import { assetUrl, dataPath } from "../world/Module";
import { loadItems, type Item } from "../world/Items";
import { loadSpells, type Spell } from "../world/Spells";
import { loadParty } from "../world/Party";
import { loadClass, loadRaces, type ClassTemplate } from "../world/Classes";
import { awardXp, type LevelUpEvent } from "../world/Leveling";
import { defaultRng } from "../rng";
import {
  resolveThrow,
  isThrowable,
  isRanged,
  maxRangeFor,
  spellIsCombatCastable,
  classifyCombatCast,
  describeStatusCast,
  resolveDamageSpell,
  resolveHealSpell,
  resolveTurnUndead,
  makeSummonedSkeleton,
  traceDirectionalRay,
} from "../combat/CombatActions";
import { combatantsFromParty, syncCombatHpBack, abilityMod } from "../combat/CombatBridge";
import { useEquippedDurability } from "../world/PartyActions";
import {
  flashTarget,
  castGlow,
  projectileLine,
  lightningZigzag,
  radialBurst,
  healingSparkles,
  glowAura,
  screenShake,
  floatingX,
  shatterEffect,
  magicDart,
  magicArrow,
  VFX_COLOURS,
} from "../combat/Vfx";
import { Sfx } from "../audio/Sfx";
import type { Combatant, AttackResult } from "../types";
import type { PartyMember } from "../world/Party";

interface CombatSceneData {
  /** True when launched from the overworld; false for the /combat demo. */
  fromWorld?: boolean;
  /** The "col,row" key of the trigger tile that started this fight. */
  triggerKey?: string;
  /**
   * Terrain tile id whose sprite should fill the arena floor. When
   * present, every non-wall tile renders that sprite; falls back to
   * a coloured rectangle otherwise.
   */
  terrainTileId?: number;
  /**
   * When set, build the encounter from these catalog names instead
   * of the random sample. Used by Monster Spawn boss fights and
   * roamer engagements so the player faces the right creatures.
   */
  monsterNames?: string[];
  /**
   * "col,row" of the Monster Spawn tile that triggered this fight.
   * On victory, OverworldScene will rewrite that tile to grass and
   * mark it as destroyed so it never spawns again.
   */
  destroySpawnKey?: string;
  /**
   * Id of the roaming monster the party engaged. On victory the
   * overworld removes it from gameState.roamingMonsters.
   */
  roamerId?: string;
}

// ── Layout (canvas is 960×720) ────────────────────────────────────
// TILE matches the rest of the engine (overworld + town interiors)
// so monster / character sprites — which ship as native 32×32 PNGs
// — render at their native size, not stretched.
const TILE = 32;
const HEADER_H = 32;
const ARENA_X = 12;
const ARENA_Y = HEADER_H + 8;             // 40
const ARENA_W = ARENA_COLS * TILE;        // 18 × 32 = 576
const ARENA_H = ARENA_ROWS * TILE;        // 16 × 32 = 512
const HUD_X = ARENA_X + ARENA_W + 12;     // 600
const HUD_W = 960 - HUD_X - 12;           // 348
const HUD_Y = ARENA_Y;
const HUD_H = ARENA_H;
const LOG_X = 12;
const LOG_Y = ARENA_Y + ARENA_H + 8;      // 560
const LOG_W = 960 - 24;                   // 936
const LOG_H = 720 - LOG_Y - 12;           // 148

// ── Web-app theme palette (matches PartyScene + TownScene) ────────
const C = {
  bgFull:    0x0c0c14,
  panel:     0x161629,
  panelEdge: 0x2a2a3a,
  accent:    0xc8553d,
  gold:      0xffd470,
  body:      0xf6efd6,
  dim:       0xbdb38a,
  faint:     0x6f6960,
  hpFull:    0x6acf6a,
  hpLow:     0xd14a4a,
  mp:        0x7aa6ff,
  cursor:    0xc8553d,
  moveHint:  0x44648a,
  selectBg:  0x2a1f24,
} as const;

const hex = (n: number) => "#" + n.toString(16).padStart(6, "0");
const FONT_TITLE = (color: number = C.gold) => ({ fontFamily: "Georgia, serif", fontSize: "20px", color: hex(color) });
const FONT_HEAD  = (color: number = C.gold) => ({ fontFamily: "Georgia, serif", fontSize: "16px", color: hex(color) });
const FONT_BODY  = (color: number = C.body) => ({ fontFamily: "Georgia, serif", fontSize: "14px", color: hex(color) });
const FONT_MONO  = (color: number = C.dim)  => ({ fontFamily: "monospace",     fontSize: "12px", color: hex(color) });

/** Action menu — what the active party member can do this turn.
 *  No "Flee" — once battle is joined, the party fights to win or
 *  loses (matches the Python game's combat loop). */
type ActionId = "attack" | "range" | "throw" | "cast" | "end";

interface ActionEntry {
  id: ActionId;
  label: string;
}

const PARTY_ACTIONS: ActionEntry[] = [
  { id: "attack", label: "Attack"          },
  { id: "range",  label: "Range"           },
  { id: "throw",  label: "Throw"           },
  { id: "cast",   label: "Cast"            },
  { id: "end",    label: "End Turn  [SPACE]" },
];

/**
 * Sub-modes the scene can be in:
 *   - default:        action menu has focus, arrows move the avatar
 *   - pick-throw:     player is choosing which item to throw
 *   - pick-spell:     player is choosing which spell to cast
 *   - pick-target:    player is choosing the enemy/ally for the staged
 *                     action (numbered 1..N on the arena)
 */
type SceneMode =
  | "default" | "pick-throw" | "pick-spell" | "pick-target" | "pick-tile"
  /** Magic Dart-style spells: player presses an arrow key to fire
   *  along that cardinal direction up to the spell's range. */
  | "pick-direction";

/** What to do once a target is picked. */
type PendingAction =
  | { kind: "throw"; item: Item }
  | { kind: "range"; weapon: Item }
  | { kind: "cast"; spell: Spell }
  /** Tile-targeted spell — resolution branches by effect_type. */
  | { kind: "tile"; spell: Spell }
  /** Directional spell — resolution waits on an arrow-key press. */
  | { kind: "direction"; spell: Spell };

export class CombatScene extends Phaser.Scene {
  private combat!: Combat;
  private fromWorld = false;
  private triggerKey: string | null = null;
  private terrainTileId: number | null = null;
  /** Catalog names for this fight; null falls back to makeSampleEncounter. */
  private monsterNames: string[] | null = null;
  /** "col,row" of a Monster Spawn tile to destroy on victory. */
  private destroySpawnKey: string | null = null;
  /** Roaming monster id to remove from gameState.roamingMonsters on victory. */
  private roamerId: string | null = null;

  private bodies = new Map<string, Phaser.GameObjects.Image | Phaser.GameObjects.Rectangle>();
  private selRings = new Map<string, Phaser.GameObjects.Rectangle>();
  private moveHintRects: Phaser.GameObjects.Rectangle[] = [];
  /** Per-party-member card UI, kept so we can refresh in place. The MP
   *  fields are absent for non-casters (Fighter / Thief / etc.). */
  private partyCards = new Map<string, {
    hpBar: Phaser.GameObjects.Rectangle;
    hpText: Phaser.GameObjects.Text;
    mpBar?: Phaser.GameObjects.Rectangle;
    mpText?: Phaser.GameObjects.Text;
    /** Inner-fill width when the bar is full — used to scale by HP/MP %. */
    fullBarW: number;
  }>();
  /** Floating HP bar above each enemy's body sprite. Position is
   *  re-synced from the body during move / bump tweens via onUpdate. */
  private monsterHpBars = new Map<string, {
    bg: Phaser.GameObjects.Rectangle;
    bar: Phaser.GameObjects.Rectangle;
    fullW: number;
    /** Pixels above the body sprite centre to anchor the bar. */
    offsetY: number;
  }>();

  private logText!: Phaser.GameObjects.Text;
  private turnText!: Phaser.GameObjects.Text;
  private movePointsText!: Phaser.GameObjects.Text;
  private actionTexts: Phaser.GameObjects.Text[] = [];
  private actionRowHandles: Phaser.GameObjects.Rectangle[] = [];
  private actionCursor = 0;

  // Sub-mode + picker state
  private mode: SceneMode = "default";
  private pendingAction: PendingAction | null = null;
  /** Items the user can pick to throw — populated when entering pick-throw mode. */
  private throwOptions: Array<{ item: Item; source: "personal" | "stash"; index: number }> = [];
  private spellOptions: Spell[] = [];
  /** Shared cursor for the scrollable pickers (pick-throw / pick-spell).
   *  Index into the corresponding options array. */
  private pickerCursor = 0;
  /** Per-target arena badges shown during pick-target mode. */
  private targetBadges: Phaser.GameObjects.Text[] = [];
  /** Pick-tile state — current cursor position on the arena. */
  private tileCursorPos = { col: 0, row: 0 };
  /** Phaser objects rendered for the tile cursor + AOE preview.
   *  Cleared on every cursor move and on mode exit. */
  private tileCursorObjects: Phaser.GameObjects.GameObject[] = [];
  /** Items + Spells data, loaded lazily. */
  private items: Map<string, Item> = new Map();
  private spells: Spell[] = [];
  /** Picker overlay objects (cleared on mode transition). */
  private pickerObjects: Phaser.GameObjects.GameObject[] = [];

  private busy = false;
  private ended = false;
  private overlayText?: Phaser.GameObjects.Text;

  constructor() {
    super({ key: "CombatScene" });
  }

  init(data?: CombatSceneData): void {
    this.fromWorld = !!data?.fromWorld;
    this.triggerKey = data?.triggerKey ?? null;
    this.terrainTileId = data?.terrainTileId ?? null;
    this.monsterNames = data?.monsterNames && data.monsterNames.length > 0
      ? [...data.monsterNames] : null;
    this.destroySpawnKey = data?.destroySpawnKey ?? null;
    this.roamerId = data?.roamerId ?? null;
    this.busy = false;
    this.ended = false;
    this.actionCursor = 0;
    this.bodies.clear();
    this.selRings.clear();
    this.moveHintRects.length = 0;
    this.partyCards.clear();
    this.monsterHpBars.clear();
    this.actionTexts.length = 0;
    this.actionRowHandles.length = 0;
    this.mode = "default";
    this.pendingAction = null;
    this.throwOptions = [];
    this.spellOptions = [];
    this.pickerCursor = 0;
    this.targetBadges = [];
    this.pickerObjects = [];
    this.tileCursorPos = { col: 0, row: 0 };
    this.tileCursorObjects = [];
  }

  preload(): void {
    for (const path of [...PARTY_SPRITES, ...MONSTER_SPRITES]) {
      this.load.image(path, path);
    }
    // The active party (when launched from the world) is built from
    // data/party.json, so we don't know which class sprites we'll
    // need until create() runs. Preload the whole shipped set so any
    // PartyMember.sprite path resolves immediately when drawn.
    for (const f of [
      "alchemist", "barbarian", "cleric", "fighter",
      "illusionist", "paladin", "ranger", "thief", "wizard",
    ]) {
      const path = assetUrl(`/assets/characters/${f}.png`);
      this.load.image(path, path);
    }
    // Tile sprites for the arena floor — load the full tile manifest
    // so we can render whatever terrain the encounter sat on.
    this.textures.on("addtexture", (key: string) => {
      const tex = this.textures.get(key);
      if (tex) tex.setFilter(Phaser.Textures.FilterMode.NEAREST);
    });
    this.load.json("tile_defs_combat", dataPath("tile_defs.json"));
    this.load.once("filecomplete-json-tile_defs_combat", () => {
      const raw = this.cache.json.get("tile_defs_combat");
      if (raw) populateRuntimeDefs(raw);
      for (const { key, path } of spriteManifest()) {
        this.load.image(key, path);
      }
    });
  }

  async create(): Promise<void> {
    // Items + spells back the action sub-menus and the
    // party-bridge's stat derivation, so load them up-front before
    // we build Combat.
    try {
      this.items = await loadItems();
      this.spells = await loadSpells();
      // Make sure partyData is loaded too — the world scenes load it
      // lazily but combat may be entered before any party screen has
      // been opened.
      if (!gameState.partyData) gameState.partyData = await loadParty();
      // Spawn-tile fights use catalog names; warm the loader so
      // makeMonsterByName resolves stats / sprites correctly.
      await loadMonsters();
      // Make sure every monster sprite the catalog knows about is
      // queued — spawn lists can include creatures we didn't preload
      // in the static manifest.
      let queued = 0;
      for (const path of loadedMonsterSprites()) {
        if (!this.textures.exists(path)) {
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
    } catch (err) {
      // Combat is still playable with melee only; just skip the
      // data-driven rows. But surface the failure — a silent swallow
      // here used to leave Range / Throw / Cast permanently disabled
      // on the second battle with no signal to the player or developer.
      console.error("CombatScene: data load failed (Range/Throw/Cast may be disabled)", err);
    }
    if (this.items.size === 0) {
      console.warn("CombatScene: items catalog is empty — Range / Throw will be disabled");
    }
    if (this.spells.length === 0) {
      console.warn("CombatScene: spells catalog is empty — Cast will be disabled");
    }
    if (this.fromWorld && !gameState.partyData) {
      console.warn("CombatScene: gameState.partyData missing — Range / Throw / Cast will be disabled");
    }

    // Use the real roster when launched from the world. The /combat
    // demo route still uses the hand-built sample party so it's
    // self-contained for testing.
    let party: Combatant[];
    if (this.fromWorld && gameState.partyData) {
      party = combatantsFromParty(gameState.partyData, this.items);
    } else {
      party = makeSampleParty();
    }
    // Boss list / single-roamer name vs the legacy random sample.
    const enemies = this.monsterNames
      ? this.monsterNames.map((n, i) => makeMonsterByName(n, `-${i}`))
      : makeSampleEncounter();
    this.combat = new Combat(party, enemies);
    this.cameras.main.setBackgroundColor("#0c0c14");
    this.cameras.main.fadeIn(220, 0, 0, 0);

    this.drawHeader();
    this.drawArena();
    this.drawHud();
    this.drawLog();
    this.drawCombatants();
    this.installInput();

    this.refreshAll();
    // Encounter stinger — play once the scene has rendered.
    Sfx.play("encounter");
    // If an enemy won initiative the encounter opens on their turn —
    // hand control straight to the AI loop. Without this the screen
    // freezes on "GOBLIN'S TURN" with the action menu dimmed because
    // the player can't act and nothing schedules the monster turn.
    this.kickOffCurrentTurn();
  }

  /**
   * If the current actor is on the enemy side, schedule the monster
   * AI loop after a short pause. Used both at scene-create (in case
   * an enemy won initiative) and after every endTurn so consecutive
   * enemy turns chain cleanly.
   */
  private kickOffCurrentTurn(): void {
    if (this.combat.isOver || this.ended) return;
    if (isAiControlled(this.combat.current)) {
      this.busy = true;
      this.time.delayedCall(450, () => void this.runMonsterTurn());
    }
  }

  // ── Static panels ───────────────────────────────────────────────

  private panel(x: number, y: number, w: number, h: number, alpha = 0.96): void {
    this.add
      .rectangle(x, y, w, h, C.panel, alpha)
      .setOrigin(0)
      .setStrokeStyle(2, C.panelEdge);
  }

  private drawHeader(): void {
    this.panel(0, 0, 960, HEADER_H);
    this.add.text(960 / 2, 6, "BATTLE", FONT_TITLE()).setOrigin(0.5, 0);
  }

  private drawArena(): void {
    this.panel(ARENA_X - 4, ARENA_Y - 4, ARENA_W + 8, ARENA_H + 8);
    const terrainKey = this.terrainTileId != null
      ? tileSpriteKey(this.terrainTileId)
      : null;

    for (let row = 0; row < ARENA_ROWS; row++) {
      for (let col = 0; col < ARENA_COLS; col++) {
        const x = ARENA_X + col * TILE;
        const y = ARENA_Y + row * TILE;
        const wall = isWall(col, row);
        if (wall) {
          // Trees / boulders for the wall ring — simple dark fill so
          // the arena border reads as "edge of the world" without
          // overcomplicating the tile shop.
          this.add
            .rectangle(x, y, TILE, TILE, 0x14140f, 1)
            .setOrigin(0)
            .setStrokeStyle(1, 0x1a1a2a);
          continue;
        }
        // Open floor — terrain sprite if available, otherwise a
        // moody dark green that reads as "field" without leaning on
        // U3 styling. Tile sprites are native 32×32 so we don't
        // force-resize.
        if (terrainKey && this.textures.exists(terrainKey)) {
          this.add.image(x, y, terrainKey).setOrigin(0);
        } else {
          this.add
            .rectangle(x, y, TILE, TILE, 0x14241a, 1)
            .setOrigin(0)
            .setStrokeStyle(1, 0x1a2a20);
        }
        // Per-tile click target for cardinal-step movement / attack.
        const hit = this.add
          .rectangle(x, y, TILE, TILE, 0xffffff, 0)
          .setOrigin(0)
          .setInteractive({ useHandCursor: false });
        hit.on("pointerdown", () => this.onTileClicked(col, row));
      }
    }
  }

  private drawHud(): void {
    this.panel(HUD_X, HUD_Y, HUD_W, HUD_H);
    let cy = HUD_Y + 12;

    // PARTY header + mini cards
    this.add.text(HUD_X + 14, cy, "PARTY", FONT_HEAD());
    cy += 24;
    const cardH = 60;
    const cardW = HUD_W - 24;
    const partySide = this.combat.combatants.filter((c) => c.side === "party");
    for (const c of partySide) {
      this.drawPartyCard(c, HUD_X + 12, cy, cardW, cardH);
      cy += cardH + 4;
    }

    cy += 8;
    this.add
      .rectangle(HUD_X + 12, cy, HUD_W - 24, 1, C.panelEdge)
      .setOrigin(0);
    cy += 10;

    // -- Name'S TURN --
    this.turnText = this.add.text(HUD_X + 14, cy, "", FONT_HEAD()).setOrigin(0, 0);
    cy += 22;
    this.movePointsText = this.add.text(HUD_X + 14, cy, "", FONT_MONO()).setOrigin(0, 0);
    cy += 24;

    // Action menu
    for (let i = 0; i < PARTY_ACTIONS.length; i++) {
      const a = PARTY_ACTIONS[i];
      const ry = cy + i * 22;
      const handle = this.add
        .rectangle(HUD_X + 12, ry, HUD_W - 24, 22, C.selectBg, 0)
        .setOrigin(0)
        .setInteractive({ useHandCursor: true });
      handle.on("pointerdown", () => {
        // refreshActionMenu has the canonical enable check — re-use
        // it by setting cursor + activating; activate() bails if the
        // row is disabled at that moment.
        this.actionCursor = i;
        this.activateAction();
      });
      const t = this.add.text(HUD_X + 24, ry + 2, "", FONT_BODY());
      this.actionRowHandles.push(handle);
      this.actionTexts.push(t);
    }
  }

  private drawPartyCard(
    c: Combatant, x: number, y: number, w: number, h: number,
  ): void {
    this.add
      .rectangle(x, y, w, h, 0x1c1c2a, 1)
      .setOrigin(0)
      .setStrokeStyle(1, C.panelEdge);
    // Avatar
    const avatar = 44;
    if (c.sprite && this.textures.exists(c.sprite)) {
      const img = this.add.image(x + 8, y + 8, c.sprite).setOrigin(0);
      img.setDisplaySize(avatar, avatar);
    } else {
      const colorHex = Phaser.Display.Color.GetColor(...c.color);
      this.add.rectangle(x + 8, y + 8, avatar, avatar, colorHex).setOrigin(0);
    }
    const tx = x + avatar + 16;
    this.add.text(tx, y + 4, c.name, FONT_BODY());

    // HP bar (always present). Inner fill width = barW - 2 to leave a
    // 1px panel-edge frame on either side. Stored as fullBarW so
    // refreshHp can recompute from %.
    const barW = w - (tx - x) - 12;
    const fullBarW = barW - 2;
    const hpBarY = y + 22;
    this.add.rectangle(tx, hpBarY, barW, 8, 0x1c1c2a, 1).setOrigin(0)
      .setStrokeStyle(1, C.panelEdge);
    const hpBar = this.add
      .rectangle(tx + 1, hpBarY + 1, fullBarW, 6, C.hpFull, 1)
      .setOrigin(0);
    const hpText = this.add
      .text(tx + barW - 2, hpBarY - 14, `${c.hp}/${c.maxHp}`,
            FONT_MONO(C.dim))
      .setOrigin(1, 0);

    // MP bar — drawn only for casters (members with maxMp set). Combat
    // doesn't carry MP on Combatant; we read the live PartyMember.
    let mpBar: Phaser.GameObjects.Rectangle | undefined;
    let mpText: Phaser.GameObjects.Text | undefined;
    const member = this.memberByCombatantId(c.id);
    if (member && member.maxMp != null) {
      const mpBarY = y + 44;
      this.add.rectangle(tx, mpBarY, barW, 8, 0x1c1c2a, 1).setOrigin(0)
        .setStrokeStyle(1, C.panelEdge);
      mpBar = this.add
        .rectangle(tx + 1, mpBarY + 1, fullBarW, 6, C.mp, 1)
        .setOrigin(0);
      mpText = this.add
        .text(tx + barW - 2, mpBarY - 14, `${member.mp ?? 0}/${member.maxMp}`,
              FONT_MONO(C.dim))
        .setOrigin(1, 0);
    }

    this.partyCards.set(c.id, { hpBar, hpText, mpBar, mpText, fullBarW });
  }

  private drawLog(): void {
    this.panel(LOG_X, LOG_Y, LOG_W, LOG_H);
    this.logText = this.add.text(LOG_X + 14, LOG_Y + 10, "", {
      fontFamily: "monospace",
      fontSize: "12px",
      color: hex(C.body),
      lineSpacing: 2,
      wordWrap: { width: LOG_W - 28, useAdvancedWrap: true },
    });
  }

  // ── Combatants ───────────────────────────────────────────────────

  private tileX(col: number): number { return ARENA_X + col * TILE + TILE / 2; }
  private tileY(row: number): number { return ARENA_Y + row * TILE + TILE / 2; }

  private drawCombatants(): void {
    for (const c of this.combat.combatants) {
      const x = this.tileX(c.position.col);
      const y = this.tileY(c.position.row);
      const ring = this.add
        .rectangle(x, y, TILE, TILE, C.cursor, 0)
        .setStrokeStyle(2, C.cursor)
        .setVisible(false);
      this.selRings.set(c.id, ring);
      let body: Phaser.GameObjects.Image | Phaser.GameObjects.Rectangle;
      if (c.sprite && this.textures.exists(c.sprite)) {
        // Sprites are native 32×32 — render unscaled so transparency
        // holds and the pixel art stays crisp.
        body = this.add.image(x, y, c.sprite);
      } else {
        const colorHex = Phaser.Display.Color.GetColor(...c.color);
        body = this.add
          .rectangle(x, y, TILE - 4, TILE - 4, colorHex)
          .setStrokeStyle(2, 0x0a0a14);
      }
      this.bodies.set(c.id, body);

      // Floating HP bar above each enemy. The party gets full HP/MP
      // cards in the HUD, so we keep the arena uncluttered for them.
      if (c.side === "enemies") {
        const fullW = 26;
        const offsetY = 20;
        const bg = this.add
          .rectangle(x, y - offsetY, 30, 5, 0x10101a, 0.85)
          .setOrigin(0.5, 0.5)
          .setStrokeStyle(1, C.panelEdge)
          .setDepth(15);
        const bar = this.add
          .rectangle(x - fullW / 2, y - offsetY, fullW, 3, C.hpFull, 1)
          .setOrigin(0, 0.5)
          .setDepth(16);
        this.monsterHpBars.set(c.id, { bg, bar, fullW, offsetY });
      }
    }
  }

  // ── Input ────────────────────────────────────────────────────────

  private installInput(): void {
    const k = this.input.keyboard;
    if (!k) return;
    const stepMap: Record<string, Direction> = {
      W: "n", A: "w", S: "s", D: "e",
      UP: "n", DOWN: "s", LEFT: "w", RIGHT: "e",
    };
    Object.entries(stepMap).forEach(([key, dir]) => {
      k.on(`keydown-${key}`, () => this.onArrowKey(key, dir));
    });
    k.on("keydown-ENTER", () => this.activateAction());
    // SPACE is a quick "end turn" shortcut from the main action menu —
    // skips having to navigate the cursor down to "End Turn". Inside
    // any picker sub-mode it still activates the cursored row, so the
    // keyboard flow there isn't disrupted.
    k.on("keydown-SPACE", () => this.onSpacePressed());
    k.on("keydown-ESC",   () => this.cancelSubMode());
    // Number keys 1..9 dispatch through pick-throw / pick-spell /
    // pick-target sub-modes. We register a handler per digit since
    // Phaser keys are individual.
    for (let i = 1; i <= 9; i++) {
      k.on(`keydown-${["ONE","TWO","THREE","FOUR","FIVE","SIX","SEVEN","EIGHT","NINE"][i-1]}`, () => this.onDigit(i));
    }
  }

  /** ESC backs out of any sub-mode, or does nothing in default mode. */
  private cancelSubMode(): void {
    if (this.mode === "default") return;
    this.mode = "default";
    this.pendingAction = null;
    this.throwOptions = [];
    this.spellOptions = [];
    this.pickerCursor = 0;
    this.clearPicker();
    this.clearTargetBadges();
    this.clearTileCursor();
    this.refreshAll();
  }

  /**
   * Number-key dispatch — meaning depends on current sub-mode.
   *
   * In the scrollable pickers (pick-throw / pick-spell), 1-9 picks
   * the Nth row of the *visible window* (relative to scroll), not
   * the Nth absolute index. This keeps the shortcut consistent with
   * what the player sees on screen.
   */
  private onDigit(n: number): void {
    if (this.mode === "pick-throw" || this.mode === "pick-spell") {
      const total =
        this.mode === "pick-throw" ? this.throwOptions.length :
        this.spellOptions.length;
      if (total === 0) return;
      const visibleMax = 12;
      const visibleCount = Math.min(visibleMax, total);
      const half = Math.floor(visibleCount / 2);
      const topRow = Math.max(0, Math.min(total - visibleCount, this.pickerCursor - half));
      const absIndex = topRow + (n - 1);
      if (absIndex < 0 || absIndex >= total) return;
      this.pickerCursor = absIndex;
      this.activateAction();
      return;
    }
    if (this.mode === "pick-target") {
      const targets = this.currentTargetList();
      const target = targets[n - 1];
      if (target) this.resolveTarget(target);
      return;
    }
  }

  /**
   * Arrow-key dispatch — when the action cursor is sitting on a menu
   * row, UP/DOWN walks the menu. Otherwise (for WASD or any time the
   * cursor isn't in the menu), the keys move the active fighter.
   *
   * The "is the menu focused?" rule is implicit: UP and DOWN always
   * walk the menu when it's the player's turn (since vertical
   * movement on the arena is also UP/DOWN — disambiguated by holding
   * shift in a future slice; for V1 the menu wins).
   *
   * To keep movement available, only WASD steps the avatar; arrow
   * keys navigate the menu.
   */
  private onArrowKey(key: string, dir: Direction): void {
    if (!this.canTakePlayerInput()) return;
    // In a scrollable picker UP/DOWN walks the picker cursor — not
    // the avatar.
    if (this.mode === "pick-throw" || this.mode === "pick-spell") {
      if (key === "UP")   return this.movePickerCursor(-1);
      if (key === "DOWN") return this.movePickerCursor(1);
      return; // ignore left/right in pickers
    }
    // In tile-pick mode all four arrows nudge the reticle.
    if (this.mode === "pick-tile") {
      if (key === "UP")    return this.moveTileCursor(0, -1);
      if (key === "DOWN")  return this.moveTileCursor(0, 1);
      if (key === "LEFT")  return this.moveTileCursor(-1, 0);
      if (key === "RIGHT") return this.moveTileCursor(1, 0);
      // WASD fall through to the same handler.
      if (dir === "n") return this.moveTileCursor(0, -1);
      if (dir === "s") return this.moveTileCursor(0, 1);
      if (dir === "w") return this.moveTileCursor(-1, 0);
      if (dir === "e") return this.moveTileCursor(1, 0);
      return;
    }
    // Direction-pick mode: ANY of the four arrows fires the spell.
    if (this.mode === "pick-direction") {
      void this.fireDirectionalSpell(dir);
      return;
    }
    if (key === "UP")    return this.moveActionCursor(-1);
    if (key === "DOWN")  return this.moveActionCursor(1);
    if (key === "LEFT" || key === "RIGHT") return;
    void this.tryPlayerStep(dir);
  }

  /** Move the picker cursor through the active option list. Re-renders
   *  the picker so the highlight + scroll window update. */
  private movePickerCursor(delta: number): void {
    const total =
      this.mode === "pick-throw" ? this.throwOptions.length :
      this.mode === "pick-spell" ? this.spellOptions.length : 0;
    if (total === 0) return;
    this.pickerCursor = (this.pickerCursor + delta + total) % total;
    if (this.mode === "pick-throw") this.refreshThrowPicker();
    else if (this.mode === "pick-spell") this.refreshSpellPicker();
  }

  private moveActionCursor(delta: number): void {
    if (this.mode !== "default") return;
    const member = this.memberForCurrent();
    const canThrow = !!member && this.partyHasThrowable();
    const canCast =
      !!member && member.maxMp != null &&
      this.spells.some(
        (s) =>
          spellIsCombatCastable(s, member.class) &&
          (member.mp ?? 0) >= s.mp_cost
      );
    const equippedWeapon =
      member && member.equipped.rightHand
        ? this.items.get(member.equipped.rightHand) ?? null
        : null;
    const canRange = !!equippedWeapon && isRanged(equippedWeapon);
    const enabledIdx = PARTY_ACTIONS
      .map((a, i) => {
        if (a.id === "range" && !canRange) return -1;
        if (a.id === "throw" && !canThrow) return -1;
        if (a.id === "cast"  && !canCast)  return -1;
        return i;
      })
      .filter((i) => i >= 0);
    if (enabledIdx.length === 0) return;
    let cur = enabledIdx.indexOf(this.actionCursor);
    if (cur < 0) cur = 0;
    const next = (cur + delta + enabledIdx.length) % enabledIdx.length;
    this.actionCursor = enabledIdx[next];
    this.refreshActionMenu();
  }

  /**
   * SPACE is a shortcut for "end this character's turn" from the main
   * action menu — saves the player navigating the cursor down to End
   * Turn. Inside any picker sub-mode (throw, spell, tile, target) it
   * falls through to `activateAction` so the cursor's row still fires,
   * preserving the existing keyboard ergonomics there.
   */
  private onSpacePressed(): void {
    if (!this.canTakePlayerInput()) return;
    if (this.mode === "default") {
      this.onEndTurnClicked();
      return;
    }
    this.activateAction();
  }

  private activateAction(): void {
    if (!this.canTakePlayerInput()) return;
    // Enter inside a scrollable picker activates the cursored row.
    if (this.mode === "pick-throw") {
      const opt = this.throwOptions[this.pickerCursor];
      if (!opt) return;
      this.startTargetingFor({ kind: "throw", item: opt.item }, "enemies");
      this.consumeThrowItem(opt);
      return;
    }
    if (this.mode === "pick-spell") {
      const spell = this.spellOptions[this.pickerCursor];
      if (!spell) return;
      this.dispatchSpell(spell);
      return;
    }
    if (this.mode === "pick-tile") {
      void this.resolveTileSpell();
      return;
    }
    if (this.mode !== "default") return; // other sub-modes use number keys
    const a = PARTY_ACTIONS[this.actionCursor];
    if (!a) return;
    if (a.id === "attack") {
      const me = this.combat.current;
      const dirs: Direction[] = ["n", "s", "e", "w"];
      const offsets: Record<Direction, [number, number]> = {
        n: [0, -1], s: [0, 1], e: [1, 0], w: [-1, 0],
      };
      for (const d of dirs) {
        const [dc, dr] = offsets[d];
        const occ = this.combat.combatantAt(me.position.col + dc, me.position.row + dr);
        if (occ && occ.side !== me.side && occ.hp > 0) {
          void this.tryPlayerStep(d);
          return;
        }
      }
      this.combat.log.push(`${me.name} has no adjacent enemy to attack.`);
      this.refreshLog();
      return;
    }
    if (a.id === "range") return this.startRangeAttack();
    if (a.id === "throw") return this.openThrowPicker();
    if (a.id === "cast")  return this.openSpellPicker();
    if (a.id === "end")   return this.onEndTurnClicked();
  }

  /**
   * Begin a ranged attack with the currently equipped weapon —
   * skip the item picker (the weapon is already chosen) and go
   * straight to target select. Only valid enemies within the
   * weapon's `maxRangeFor` distance get badges.
   */
  private startRangeAttack(): void {
    const member = this.memberForCurrent();
    if (!member) return;
    const weaponName = member.equipped.rightHand;
    if (!weaponName) {
      this.combat.log.push(`${this.combat.current.name} has no weapon equipped.`);
      this.refreshLog();
      return;
    }
    const weapon = this.items.get(weaponName);
    if (!weapon || !isRanged(weapon)) {
      this.combat.log.push(`${this.combat.current.name}'s ${weaponName} is not a ranged weapon.`);
      this.refreshLog();
      return;
    }
    this.startTargetingFor({ kind: "range", weapon }, "enemies");
  }

  // ── Throw / Cast / Target sub-modes ──────────────────────────────

  /** PartyMember matched to the active combatant by name (best-effort). */
  private memberForCurrent(): PartyMember | null {
    return this.memberByCombatantId(this.combat.current.id);
  }

  /**
   * PartyMember matched to a combatant id (party-side only). Used by
   * the durability hooks that need to apply wear to whichever fighter
   * landed (or absorbed) the hit, not just the active turn-taker.
   * Summons share `side: "party"` but have no PartyMember row, so
   * the lookup returns null for them — durability simply skips.
   */
  private memberByCombatantId(id: string): PartyMember | null {
    const c = this.combat.combatants.find((x) => x.id === id);
    if (!c || c.side !== "party") return null;
    const data = gameState.partyData;
    if (!data) return null;
    return data.roster.find((m) => m.name === c.name) ?? null;
  }

  /**
   * Decrement durability for the weapon a party member just hit with.
   * Called after every successful melee bump or ranged shot. Iterates
   * the hand slots so dual-wield setups still wear the right item, and
   * logs a "X's Y shatters!" line if the weapon breaks.
   *
   * Skips silently for monsters and summons — they don't carry the
   * PartyMember durability tracker.
   */
  private applyWeaponDurability(attackerId: string): void {
    const member = this.memberByCombatantId(attackerId);
    if (!member) return;
    // Try right hand first (the common case); only the slot whose
    // item actually exists gets decremented. Both slots have to be
    // tried because a thief's off-hand dagger lives in left_hand.
    const slotsToTry: Array<["right_hand" | "left_hand", "rightHand" | "leftHand"]> = [
      ["right_hand", "rightHand"],
      ["left_hand",  "leftHand"],
    ];
    for (const [slot, field] of slotsToTry) {
      if (!member.equipped[field]) continue;
      // eslint-disable-next-line react-hooks/rules-of-hooks -- `useEquippedDurability` is a plain helper, not a React hook
      const r = useEquippedDurability(member, slot, this.items);
      if (r.kind === "broke") {
        this.combat.log.push(`*** ${member.name}'s ${r.itemName} shatters! ***`);
        this.spawnShatterVfx(attackerId, r.itemName, "weapon");
      }
      return; // only the first hand the attack came from
    }
  }

  /**
   * Decrement body-armor durability when a party member is hit. The
   * Python game has the same hook in `_apply_armor_durability`; here
   * we mirror only the body slot — head/hand armor wear isn't tracked
   * yet because no shipped pieces define durability for those slots.
   */
  private applyArmorDurability(targetId: string): void {
    const member = this.memberByCombatantId(targetId);
    if (!member) return;
    if (!member.equipped.body) return;
    // eslint-disable-next-line react-hooks/rules-of-hooks -- `useEquippedDurability` is a plain helper, not a React hook
    const r = useEquippedDurability(member, "body", this.items);
    if (r.kind === "broke") {
      this.combat.log.push(`*** ${member.name}'s ${r.itemName} is destroyed! ***`);
      this.spawnShatterVfx(targetId, r.itemName, "armor");
    }
  }

  /**
   * Trigger the shatter VFX on the combatant's body sprite, color-
   * coded by gear type so weapons read different from armor. Plays
   * the critical SFX in tandem so the audio + visual cue land
   * together. No-op when the combatant is already off-screen (a
   * downed actor whose sprite was destroyed).
   */
  private spawnShatterVfx(
    combatantId: string, itemName: string, kind: "weapon" | "armor",
  ): void {
    const c = this.combat.combatants.find((x) => x.id === combatantId);
    if (!c) return;
    const at = this.bodyXY(c);
    const color  = kind === "weapon" ? VFX_COLOURS.fire     : VFX_COLOURS.shield;
    const accent = kind === "weapon" ? VFX_COLOURS.ember    : VFX_COLOURS.white;
    shatterEffect(this, at, itemName, color, accent);
    Sfx.play("critical");
  }

  private openThrowPicker(): void {
    const member = this.memberForCurrent();
    const party = gameState.partyData;
    const opts: typeof this.throwOptions = [];
    // Personal inventory first, then shared stash. Filter to throwables.
    if (member) {
      member.inventory.forEach((it, idx) => {
        const def = this.items.get(it.item);
        if (def && isThrowable(def)) {
          opts.push({ item: def, source: "personal", index: idx });
        }
      });
    }
    if (party) {
      party.inventory.forEach((it, idx) => {
        const def = this.items.get(it.item);
        if (def && isThrowable(def)) {
          opts.push({ item: def, source: "stash", index: idx });
        }
      });
    }
    if (opts.length === 0) {
      this.combat.log.push(`${this.combat.current.name} has nothing to throw.`);
      this.refreshLog();
      return;
    }
    this.throwOptions = opts;
    this.pickerCursor = 0;
    this.mode = "pick-throw";
    this.refreshThrowPicker();
  }

  /** Rebuild the throw picker so the cursor + scroll window update. */
  private refreshThrowPicker(): void {
    const lines = this.throwOptions.map(
      (o) => `${o.item.name} (pwr ${o.item.power ?? 1})`
    );
    this.renderPicker("PICK ITEM TO THROW", lines, this.pickerCursor);
  }

  /**
   * Spell-pick → action dispatch. Classifies the spell, and either
   * stages a target prompt (single-target) or casts immediately
   * (self / mass / unsupported).
   */
  private dispatchSpell(spell: Spell): void {
    const member = this.memberForCurrent();
    if (!member) return;
    const kind = classifyCombatCast(spell);
    if (kind === "pick-ally") {
      this.startTargetingFor({ kind: "cast", spell }, "party");
      return;
    }
    if (kind === "pick-enemy") {
      this.startTargetingFor({ kind: "cast", spell }, "enemies");
      return;
    }
    if (kind === "pick-tile") {
      this.startTilePicking(spell);
      return;
    }
    if (kind === "pick-direction") {
      this.startDirectionPicking(spell);
      return;
    }
    // Pre-flight for Turn Undead: if there are no undead enemies on
    // the field the spell fizzles. Mirrors the Python game — the
    // caster keeps both the MP and their turn, and just gets a clear
    // log line so they can pick another action.
    if (spell.effect_type === "undead_damage") {
      const anyUndead = this.combat.combatants.some(
        (c) => c.side === "enemies" && c.hp > 0 && c.undead,
      );
      if (!anyUndead) {
        this.clearPicker();
        this.mode = "default";
        this.combat.log.push(
          `${this.combat.current.name} channels ${spell.name} — no undead here, the holy energy has no effect.`
        );
        this.refreshLog();
        return;
      }
    }
    // The remaining kinds resolve immediately. Spend MP, log, and
    // end the turn — same as a finished single-target cast would.
    if (member.maxMp != null) {
      member.mp = Math.max(0, (member.mp ?? 0) - spell.mp_cost);
    }
    this.clearPicker();
    this.mode = "default";

    const me = this.combat.current;
    Sfx.play(spell.sfx);
    this.castGlowFor(me, this.colorForSpell(spell.effect_type));
    if (kind === "self") {
      if (spell.effect_type === "heal" || spell.effect_type === "major_heal") {
        const r = resolveHealSpell(me, me, spell, defaultRng);
        this.combat.log.push(`${me.name} casts ${spell.name} on self — heals ${r.heal} HP.`);
        void this.healTargetVfx(me);
        this.refreshHp(me);
      } else if (spell.effect_type === "invisibility") {
        // Caster fades from view: an "Invisibility"-tagged AC buff
        // hardens them to attacks, and the scene picks up the matching
        // buff source via refreshVisibility() to actually drop their
        // sprite alpha for the spell's full duration. Reappears
        // automatically when the buff ticks down.
        const turns = typeof spell.duration === "number" ? spell.duration : 3;
        this.combat.addBuff(me.id, {
          kind: "ac_bonus",
          value: 6,
          turnsLeft: turns,
          source: "Invisibility",
        });
        this.combat.log.push(
          `${me.name} casts ${spell.name} — fades from view (+6 AC for ${turns} turns).`
        );
      } else {
        void this.auraOn(me, VFX_COLOURS.buff);
        this.combat.log.push(
          `${me.name} casts ${spell.name} — ${describeStatusCast(me, me, spell)}`
        );
      }
    } else if (kind === "mass-ally") {
      // Bless: party-wide attack-bonus buff. Mirrors the Python game's
      // bless_buffs dict — every alive ally gets +effect_value.attack_bonus
      // for `duration` rounds.
      if (spell.effect_type === "bless") {
        const ev = spell.effect_value ?? {};
        const value = typeof ev.attack_bonus === "number" ? ev.attack_bonus : 2;
        const turns = typeof spell.duration === "number" ? spell.duration : 4;
        let count = 0;
        for (const ally of this.combat.combatants) {
          if (ally.side !== "party" || ally.hp <= 0) continue;
          this.combat.addBuff(ally.id, {
            kind: "attack_bonus",
            value,
            turnsLeft: turns,
            source: "Bless",
          });
          // Stagger the per-ally aura so they sparkle in sequence
          // rather than all flashing at once — feels more "blessing
          // sweeping over the party".
          this.time.delayedCall(count * 60, () => void this.auraOn(ally, VFX_COLOURS.buff));
          count += 1;
        }
        this.combat.log.push(
          `${me.name} casts ${spell.name} — ${count} ${count === 1 ? "ally" : "allies"} gain +${value} to hit for ${turns} turns.`
        );
      } else {
        let total = 0;
        let i = 0;
        for (const ally of this.combat.combatants) {
          if (ally.side !== "party" || ally.hp <= 0) continue;
          if (spell.effect_type === "mass_heal" || spell.effect_type === "heal" || spell.effect_type === "major_heal") {
            const r = resolveHealSpell(me, ally, spell, defaultRng);
            total += r.heal;
            this.time.delayedCall(i * 70, () => void this.healTargetVfx(ally));
            i += 1;
            this.refreshHp(ally);
          }
        }
        this.combat.log.push(
          `${me.name} casts ${spell.name} — party heals ${total} HP total.`
        );
      }
    } else if (kind === "mass-enemy") {
      if (spell.effect_type === "undead_damage") {
        // Turn Undead: each undead saves vs DC = save_dc_base + caster
        // wisMod. Failure → destroyed completely; success → seared for
        // hp_percent of maxHp. Non-undead are untouched (the pre-flight
        // already covered the no-undead case).
        const enemies = this.combat.combatants.filter((c) => c.side === "enemies");
        const wisMod = abilityMod(member.wisdom);
        const result = resolveTurnUndead(enemies, spell, wisMod, defaultRng);
        this.combat.log.push(`${me.name} channels ${spell.name}!`);
        let i = 0;
        for (const o of result.outcomes) {
          const target = this.combat.byId(o.targetId);
          this.combat.log.push(
            o.saved
              ? `${target.name} resists (${o.saveRoll}+${Math.max(0, target.attackBonus - 2)}=${o.saveTotal} vs DC ${o.saveDc}) — seared for ${o.damage} damage!`
              : `${target.name} fails its save (${o.saveRoll}+${Math.max(0, target.attackBonus - 2)}=${o.saveTotal} vs DC ${o.saveDc}) — DESTROYED!`
          );
          const body = this.bodies.get(target.id);
          if (body) {
            const radius = o.saved ? 38 : 56;
            this.time.delayedCall(i * 80, () => {
              flashTarget(this, body, VFX_COLOURS.buff);
              void radialBurst(this, { x: body.x, y: body.y },
                                VFX_COLOURS.buff, VFX_COLOURS.white, radius);
            });
          }
          i += 1;
          this.refreshHp(target);
        }
        if (spell.hit_sfx) Sfx.play(spell.hit_sfx);
      } else {
        // Generic mass-enemy fallback (no other spells use this
        // classifier today, but the branch keeps options open for
        // future "blast every foe" effects without dropping into
        // the unsupported message).
        let total = 0;
        for (const foe of this.combat.combatants) {
          if (foe.side !== "enemies" || foe.hp <= 0) continue;
          const r = resolveDamageSpell(me, foe, spell, defaultRng);
          total += r.damage;
          this.refreshHp(foe);
        }
        this.combat.log.push(
          `${me.name} casts ${spell.name} — enemies take ${total} HP total.`
        );
      }
    } else {
      // unsupported — needs a tile picker we haven't built.
      this.combat.log.push(
        `${me.name} casts ${spell.name} — needs tile selection (not yet supported).`
      );
    }
    this.combat.movePoints = 0;
    this.refreshAll();
    if (this.combat.isOver) return this.endEncounter();
    this.endActorTurn();
  }

  private openSpellPicker(): void {
    const member = this.memberForCurrent();
    if (!member) return;
    const opts = this.spells.filter(
      (s) =>
        spellIsCombatCastable(s, member.class) &&
        member.maxMp != null &&
        (member.mp ?? 0) >= s.mp_cost
    );
    if (opts.length === 0) {
      this.combat.log.push(`${this.combat.current.name} has no spell to cast.`);
      this.refreshLog();
      return;
    }
    this.spellOptions = opts;
    this.pickerCursor = 0;
    this.mode = "pick-spell";
    this.refreshSpellPicker();
  }

  /** Rebuild the spell picker so the cursor + scroll window update. */
  private refreshSpellPicker(): void {
    const tagFor = (s: Spell): string => {
      const k = classifyCombatCast(s);
      if (k === "self")        return "SELF";
      if (k === "pick-ally")   return "ALLY";
      if (k === "pick-enemy")  return "ENEMY";
      if (k === "mass-ally")   return "PARTY";
      if (k === "mass-enemy")  return "ENEMIES";
      return "—";
    };
    const lines = this.spellOptions.map(
      (s) => `${s.name.padEnd(18, " ")} ${s.mp_cost} MP   ${tagFor(s)}`
    );
    this.renderPicker("PICK SPELL", lines, this.pickerCursor);
  }

  /** Splice the picked throw item out of its source list now (so the
   *  player can't pick it again if the throw misses). */
  private consumeThrowItem(opt: typeof this.throwOptions[number]): void {
    const member = this.memberForCurrent();
    const party = gameState.partyData;
    if (opt.source === "personal" && member) {
      member.inventory.splice(opt.index, 1);
    } else if (opt.source === "stash" && party) {
      party.inventory.splice(opt.index, 1);
    }
  }

  private startTargetingFor(action: PendingAction, side: "party" | "enemies"): void {
    this.pendingAction = action;
    this.mode = "pick-target";
    this.clearPicker();
    this.drawTargetBadges(side);
  }

  private currentTargetList(): Combatant[] {
    if (!this.pendingAction) return [];
    let side: "party" | "enemies" = "enemies";
    if (this.pendingAction.kind === "cast") {
      const kind = classifyCombatCast(this.pendingAction.spell);
      side = kind === "pick-ally" ? "party" : "enemies";
    }
    let list = this.combat.combatants
      .filter((c) => c.side === side && c.hp > 0);
    // Range action: only show targets within the weapon's max range
    // (Chebyshev distance from the active member).
    if (this.pendingAction.kind === "range") {
      const me = this.combat.current;
      const max = maxRangeFor(this.pendingAction.weapon);
      list = list.filter((t) => {
        const dc = Math.abs(t.position.col - me.position.col);
        const dr = Math.abs(t.position.row - me.position.row);
        return Math.max(dc, dr) <= max;
      });
    }
    return list.slice(0, 9);
  }

  private async resolveTarget(target: Combatant): Promise<void> {
    const action = this.pendingAction;
    if (!action) return;
    const me = this.combat.current;
    this.busy = true;
    this.clearTargetBadges();
    this.mode = "default";
    try {
      if (action.kind === "throw") {
        const result = resolveThrow(me, target, action.item, defaultRng);
        this.combat.log.push(
          result.hit
            ? `${me.name} throws ${action.item.name} at ${target.name} (d20:${result.roll}=${result.total} vs AC${target.ac}) — ${result.damage} dmg${result.killed ? ", defeated!" : "."}`
            : `${me.name} throws ${action.item.name} at ${target.name} — miss.`
        );
        // Throw whoosh + visible projectile arc from caster → target.
        Sfx.play("chirp");
        await this.animateBump(me, me.position, target.position);
        await this.flyProjectile(me, target, VFX_COLOURS.ember);
        await this.animateHit(target, result);
        this.refreshHp(target);
      } else if (action.kind === "range") {
        // Same dice resolution as Throw — fire-and-forget projectile.
        // The weapon stays equipped (no consume) since it's reusable.
        const result = resolveThrow(me, target, action.weapon, defaultRng);
        this.combat.log.push(
          result.hit
            ? `${me.name} fires ${action.weapon.name} at ${target.name} (d20:${result.roll}=${result.total} vs AC${target.ac}) — ${result.damage} dmg${result.killed ? ", defeated!" : "."}`
            : `${me.name} fires ${action.weapon.name} at ${target.name} — miss.`
        );
        // Bow / crossbow / sling whistle and projectile streak.
        Sfx.play("arrow");
        await this.animateBump(me, me.position, target.position);
        await this.flyProjectile(me, target, VFX_COLOURS.white);
        await this.animateHit(target, result);
        this.refreshHp(target);
        if (result.hit) {
          this.applyWeaponDurability(me.id);
          this.applyArmorDurability(target.id);
        }
      } else if (action.kind === "cast") {
        const spell = action.spell;
        const member = this.memberForCurrent();
        if (member && member.maxMp != null) {
          member.mp = Math.max(0, (member.mp ?? 0) - spell.mp_cost);
        }
        // Cast SFX + caster glow up-front; the per-effect branch below
        // adds the spell-specific VFX and (where present) the impact SFX.
        Sfx.play(spell.sfx);
        this.castGlowFor(me, this.colorForSpell(spell.effect_type));
        const e = spell.effect_type;
        if (e === "heal" || e === "major_heal") {
          const r = resolveHealSpell(me, target, spell, defaultRng);
          this.combat.log.push(
            `${me.name} casts ${spell.name} on ${target.name} — heals ${r.heal} HP.`
          );
          await this.healTargetVfx(target);
          this.refreshHp(target);
        } else if (
          e === "damage" || e === "undead_damage"
        ) {
          // Damage spell: projectile from caster → target, then hit.
          // Magic Arrow gets its own glowing-shaft VFX so it reads
          // distinct from a mundane bow shot; other damage spells
          // keep the generic bowed projectile.
          if (spell.id === "magic_arrow") {
            await magicArrow(this, this.bodyXY(me), this.bodyXY(target));
          } else {
            await this.flyProjectile(me, target, VFX_COLOURS.arcane);
          }
          const r = resolveDamageSpell(me, target, spell, defaultRng);
          this.combat.log.push(
            `${me.name} casts ${spell.name} on ${target.name} — ${r.damage} dmg${r.killed ? ", defeated!" : "."}`
          );
          if (spell.hit_sfx) Sfx.play(spell.hit_sfx);
          await this.animateHit(target, r);
          this.refreshHp(target);
        } else if (e === "lightning_bolt") {
          // Branch out a zigzag bolt from caster to target.
          await this.lightningTo(me, target);
          const r = resolveDamageSpell(me, target, spell, defaultRng);
          this.combat.log.push(
            `${me.name} casts ${spell.name} on ${target.name} — ${r.damage} dmg${r.killed ? ", defeated!" : "."}`
          );
          if (spell.hit_sfx) Sfx.play(spell.hit_sfx);
          await this.animateHit(target, r);
          this.refreshHp(target);
        } else if (e === "ac_buff") {
          // Shield — single ally gains +AC for spell.duration rounds.
          const ev = spell.effect_value ?? {};
          const value = typeof ev.ac_bonus === "number" ? ev.ac_bonus : 1;
          const turns = typeof spell.duration === "number" ? spell.duration : 3;
          this.combat.addBuff(target.id, {
            kind: "ac_bonus",
            value,
            turnsLeft: turns,
            source: "Shield",
          });
          await this.auraOn(target, VFX_COLOURS.shield);
          this.combat.log.push(
            `${me.name} casts ${spell.name} on ${target.name} — +${value} AC for ${turns} turns.`
          );
        } else if (e === "curse") {
          // Curse — single enemy: -ATK to its hit rolls and -AC to
          // its defence (i.e. easier to hit). Mirrors the Python
          // game's curse_buffs which stores both penalties.
          const ev = spell.effect_value ?? {};
          const atk = typeof ev.attack_penalty === "number" ? ev.attack_penalty : 2;
          const acP = typeof ev.ac_penalty === "number" ? ev.ac_penalty : 2;
          const turns = typeof spell.duration === "number" ? spell.duration : 4;
          this.combat.addBuff(target.id, {
            kind: "attack_penalty",
            value: atk,
            turnsLeft: turns,
            source: "Curse",
          });
          this.combat.addBuff(target.id, {
            kind: "ac_penalty",
            value: acP,
            turnsLeft: turns,
            source: "Curse",
          });
          await this.auraOn(target, VFX_COLOURS.curse);
          this.combat.log.push(
            `${me.name} casts ${spell.name} on ${target.name} — -${atk} ATK / -${acP} AC for ${turns} turns.`
          );
        } else if (e === "range_buff") {
          // Long Shanks — single ally gains extra movement range.
          const ev = spell.effect_value ?? {};
          const value = typeof ev.range_bonus === "number" ? ev.range_bonus : 4;
          const turns = typeof spell.duration === "number" ? spell.duration : 3;
          this.combat.addBuff(target.id, {
            kind: "range_bonus",
            value,
            turnsLeft: turns,
            source: "Long Shanks",
          });
          await this.auraOn(target, VFX_COLOURS.heal);
          this.combat.log.push(
            `${me.name} casts ${spell.name} on ${target.name} — +${value} move for ${turns} turns.`
          );
        } else {
          // Status / debuff effects we don't have full mechanics for
          // yet (sleep / charm / cure_poison / restore — these need
          // status models the buff engine doesn't cover). Spell still
          // resolves visibly so the player gets feedback.
          const isAlly = target.side === me.side;
          await this.auraOn(target, isAlly ? VFX_COLOURS.buff : VFX_COLOURS.curse);
          this.combat.log.push(
            `${me.name} casts ${spell.name} on ${target.name} — ${describeStatusCast(me, target, spell)}`
          );
        }
      }
      // Throw / cast each consume the rest of the turn.
      this.combat.movePoints = 0;
      this.refreshAll();
      if (this.combat.isOver) return this.endEncounter();
      this.endActorTurn();
    } finally {
      this.pendingAction = null;
      this.busy = false;
    }
  }

  // ── Picker / target overlays ─────────────────────────────────────

  /**
   * Picker overlay over the right HUD. Lines longer than the visible
   * window scroll; the active row is highlighted with the rust accent
   * stripe and a "> " prefix. Number keys 1..N still pick the Nth
   * visible row as a shortcut.
   *
   * `cursor` is the index into the full `lines` array — pass -1 for
   * a static prompt with no active row (used by the older static
   * popups before they were converted; today every caller passes a
   * cursor).
   */
  private renderPicker(title: string, lines: string[], cursor = -1): void {
    this.clearPicker();
    const VISIBLE_MAX = 12;
    const total = lines.length;
    const visibleCount = Math.min(VISIBLE_MAX, total);
    // Compute scroll window so `cursor` is always in view.
    let topRow = 0;
    if (cursor >= 0 && total > visibleCount) {
      const half = Math.floor(visibleCount / 2);
      topRow = Math.max(0, Math.min(total - visibleCount, cursor - half));
    }
    const rowH = 18;
    const titleH = 24;
    const hintH = 28;
    const bodyH = visibleCount * rowH + 8;
    const w = HUD_W - 12;
    const h = titleH + bodyH + hintH;
    const x = HUD_X + 6;
    const y = HUD_Y + HUD_H - 6 - h;
    // Backing panel with a rust accent border so it pops over the
    // dimmer HUD background.
    const bg = this.add
      .rectangle(x, y, w, h, 0x10101a, 0.98)
      .setOrigin(0)
      .setStrokeStyle(2, C.accent);
    this.pickerObjects.push(bg);
    this.pickerObjects.push(
      this.add.text(x + 10, y + 6, title, FONT_HEAD(C.accent))
    );

    // Scroll indicator (top) — small triangle pointing up if there are
    // hidden rows above.
    if (topRow > 0) {
      this.pickerObjects.push(
        this.add.text(x + w - 24, y + 6, "▲", FONT_MONO(C.gold))
      );
    }

    const startY = y + titleH;
    for (let i = 0; i < visibleCount; i++) {
      const row = topRow + i;
      const line = lines[row];
      const ry = startY + i * rowH;
      const isCursor = row === cursor;
      if (isCursor) {
        // Selection bar + accent stripe down the left edge.
        this.pickerObjects.push(
          this.add.rectangle(x + 4, ry, w - 8, rowH, C.selectBg, 1).setOrigin(0)
        );
        this.pickerObjects.push(
          this.add.rectangle(x + 4, ry, 3, rowH, C.accent, 1).setOrigin(0)
        );
      }
      // Number-key shortcut shows visible row number 1..VISIBLE_MAX.
      const shortcut = i < 9 ? `[${i + 1}] ` : "    ";
      this.pickerObjects.push(
        this.add.text(x + 10, ry + 1, `${shortcut}${line}`,
          FONT_BODY(isCursor ? C.body : C.dim))
      );
    }

    // Scroll indicator (bottom).
    if (topRow + visibleCount < total) {
      this.pickerObjects.push(
        this.add.text(x + w - 24, startY + bodyH - 18, "▼", FONT_MONO(C.gold))
      );
    }

    const hintText = total > visibleCount
      ? "[↑↓] scroll  [Enter] pick  [1-9] shortcut  [ESC] cancel"
      : "[↑↓] move  [Enter] pick  [1-9] shortcut  [ESC] cancel";
    this.pickerObjects.push(
      this.add.text(x + 10, y + h - 22, hintText, FONT_MONO(C.faint))
    );
  }

  private clearPicker(): void {
    for (const o of this.pickerObjects) o.destroy();
    this.pickerObjects = [];
  }

  /** Draw 1..N badges over each valid target on the arena. */
  private drawTargetBadges(side: "party" | "enemies"): void {
    this.clearTargetBadges();
    // Reuse currentTargetList so range filtering / target side is
    // resolved in one place.
    const targets = this.currentTargetList();
    void side;
    targets.forEach((t, i) => {
      const x = this.tileX(t.position.col);
      const y = this.tileY(t.position.row) - TILE / 2 - 4;
      const badge = this.add
        .text(x, y, `${i + 1}`, {
          fontFamily: "Georgia, serif",
          fontSize: "16px",
          color: hex(C.gold),
          stroke: "#1a1a2e",
          strokeThickness: 4,
        })
        .setOrigin(0.5, 1);
      this.targetBadges.push(badge);
      // Click target sprite directly to confirm.
      const body = this.bodies.get(t.id);
      if (body) {
        body.setInteractive({ useHandCursor: true });
        body.once("pointerdown", () => this.resolveTarget(t));
      }
    });
  }

  private clearTargetBadges(): void {
    for (const b of this.targetBadges) b.destroy();
    this.targetBadges = [];
    // Drop the one-shot listeners we attached.
    for (const c of this.combat.combatants) {
      const body = this.bodies.get(c.id);
      if (body) body.off("pointerdown");
    }
  }

  // ── Tile picker ──────────────────────────────────────────────────

  /**
   * Begin tile selection for a spell whose targeting is `select_tile`
   * (or whose effect_type is one of the tile-placed kinds:
   * aoe_fireball / teleport / summon_skeleton). The cursor starts
   * adjacent to the caster — north for ranged spells like Fireball,
   * south for self-relocation like Misty Step.
   */
  private startTilePicking(spell: Spell): void {
    const me = this.combat.current;
    const start = {
      col: Math.max(1, Math.min(ARENA_COLS - 2, me.position.col)),
      row: Math.max(1, Math.min(ARENA_ROWS - 2, me.position.row - 2)),
    };
    this.tileCursorPos = start;
    this.pendingAction = { kind: "tile", spell };
    this.mode = "pick-tile";
    this.clearPicker();
    this.refreshTileCursor();
    // Hint at bottom of right HUD.
    this.renderTilePickerHint(spell);
  }

  /** Move the tile cursor by (dc, dr), clamped to the open arena. */
  private moveTileCursor(dc: number, dr: number): void {
    const next = {
      col: this.tileCursorPos.col + dc,
      row: this.tileCursorPos.row + dr,
    };
    // Clamp to inside the wall ring (1..N-2).
    next.col = Math.max(1, Math.min(ARENA_COLS - 2, next.col));
    next.row = Math.max(1, Math.min(ARENA_ROWS - 2, next.row));
    this.tileCursorPos = next;
    this.refreshTileCursor();
  }

  /** Re-render the tile cursor reticle + AOE preview if applicable. */
  private refreshTileCursor(): void {
    this.clearTileCursor();
    if (this.mode !== "pick-tile") return;
    const action = this.pendingAction;
    if (!action || action.kind !== "tile") return;
    const { col, row } = this.tileCursorPos;
    // Optional radius preview for aoe_fireball-style spells.
    const ev = action.spell.effect_value ?? {};
    const radius = typeof (ev as Record<string, unknown>).radius === "number"
      ? (ev as { radius: number }).radius
      : 0;
    if (radius > 0) {
      for (let dr = -radius; dr <= radius; dr++) {
        for (let dc = -radius; dc <= radius; dc++) {
          const c = col + dc;
          const r = row + dr;
          if (c < 1 || c >= ARENA_COLS - 1 || r < 1 || r >= ARENA_ROWS - 1) continue;
          if (Math.max(Math.abs(dc), Math.abs(dr)) > radius) continue;
          if (dc === 0 && dr === 0) continue; // centre handled below
          const aoe = this.add
            .rectangle(ARENA_X + c * TILE, ARENA_Y + r * TILE, TILE, TILE,
                       0xff8e3c, 0.18)
            .setOrigin(0)
            .setStrokeStyle(1, 0xff8e3c, 0.35)
            .setDepth(15);
          this.tileCursorObjects.push(aoe);
        }
      }
    }
    // Centre reticle — solid rust-red border.
    const cursor = this.add
      .rectangle(ARENA_X + col * TILE, ARENA_Y + row * TILE, TILE, TILE,
                 C.cursor, 0)
      .setOrigin(0)
      .setStrokeStyle(2, C.cursor)
      .setDepth(16);
    this.tileCursorObjects.push(cursor);
  }

  private clearTileCursor(): void {
    for (const o of this.tileCursorObjects) o.destroy();
    this.tileCursorObjects = [];
  }

  // ── Directional projectiles (Magic Dart, etc.) ──────────────────
  //
  // The player presses one of the four arrow keys; the spell flies
  // along that cardinal line until it hits the first creature, runs
  // out of `spell.range` tiles, or smacks a wall. Mirrors Python's
  // _fire_fireball ray-walk.

  /** Enter direction-pick mode for a directional_projectile spell. */
  private startDirectionPicking(spell: Spell): void {
    this.pendingAction = { kind: "direction", spell };
    this.mode = "pick-direction";
    this.clearPicker();
    this.renderDirectionPickerHint(spell);
  }

  /** Bottom-of-HUD prompt explaining the direction controls. */
  private renderDirectionPickerHint(spell: Spell): void {
    const range = typeof spell.range === "number" ? spell.range : 99;
    const lines = [
      `Casting: ${spell.name}`,
      `Range: ${range} tiles`,
      "[↑↓←→] choose direction",
      "[ESC]   cancel",
    ];
    const w = HUD_W - 12, h = lines.length * 18 + 28;
    const x = HUD_X + 6, y = HUD_Y + HUD_H - 6 - h;
    this.pickerObjects.push(
      this.add.rectangle(x, y, w, h, 0x10101a, 0.98)
        .setOrigin(0)
        .setStrokeStyle(2, C.accent)
    );
    this.pickerObjects.push(
      this.add.text(x + 10, y + 8, "PICK A DIRECTION", FONT_HEAD(C.accent))
    );
    lines.forEach((line, i) => {
      this.pickerObjects.push(
        this.add.text(x + 10, y + 30 + i * 18, line, FONT_BODY())
      );
    });
  }

  /**
   * Resolve a direction-locked spell by tracing a ray from the caster
   * in the chosen cardinal direction. Spends MP, plays the cast SFX
   * + projectile VFX, applies damage on the first enemy hit, or logs
   * a fizzle if the ray hits nothing.
   */
  private async fireDirectionalSpell(dir: Direction): Promise<void> {
    const action = this.pendingAction;
    if (!action || action.kind !== "direction") return;
    const me = this.combat.current;
    const spell = action.spell;
    const member = this.memberForCurrent();
    if (member && member.maxMp != null) {
      member.mp = Math.max(0, (member.mp ?? 0) - spell.mp_cost);
    }
    this.busy = true;
    this.mode = "default";
    this.pendingAction = null;
    this.clearPicker();

    const [dCol, dRow] = DIR_DELTAS[dir];
    const range = typeof spell.range === "number" ? spell.range : 99;
    const trace = traceDirectionalRay(
      me.position,
      { dCol, dRow },
      range,
      (c, r) => isWall(c, r),
      (c, r) => this.combat.combatantAt(c, r),
    );

    Sfx.play(spell.sfx);
    this.castGlowFor(me, this.colorForSpell(spell.effect_type));
    try {
      // Animate the projectile from caster → endpoint regardless of
      // whether anything was hit, so the player sees the cast resolve.
      // Per-spell VFX:
      //   - lightning_bolt → jagged zigzag
      //   - Magic Dart (id "fireball" in the data — it isn't, just a
      //     legacy id) → arcane orb with sparkle trail
      //   - everything else → the generic bowed projectile
      const start = this.bodyXY(me);
      const endPx = {
        x: this.tileX(trace.endCol),
        y: this.tileY(trace.endRow),
      };
      if (spell.effect_type === "lightning_bolt") {
        await lightningZigzag(this, start, endPx);
      } else if (spell.id === "fireball" /* Magic Dart */) {
        await magicDart(this, start, endPx, VFX_COLOURS.arcane);
      } else {
        await projectileLine(this, start, endPx, VFX_COLOURS.arcane, 220);
      }

      if (trace.hitId) {
        const target = this.combat.byId(trace.hitId);
        if (target.side === me.side) {
          // Friendly fire isn't supported by the spell flow today —
          // log clearly and refund the cast.
          this.combat.log.push(
            `${me.name}'s ${spell.name} fizzles against an ally — clear the line first!`
          );
        } else {
          const r = resolveDamageSpell(me, target, spell, defaultRng);
          this.combat.log.push(
            `${me.name} casts ${spell.name} → ${target.name} (${dir.toUpperCase()}) — ${r.damage} dmg${r.killed ? ", defeated!" : "."}`
          );
          if (spell.hit_sfx) Sfx.play(spell.hit_sfx);
          await this.animateHit(target, r);
          this.refreshHp(target);
        }
      } else {
        this.combat.log.push(
          `${me.name}'s ${spell.name} flies ${dir.toUpperCase()} — fizzles, nothing in range.`
        );
      }
      // Cast consumes the rest of the turn whether or not the dart
      // connected, mirroring how throw / cast already behave.
      this.combat.movePoints = 0;
      this.refreshAll();
      if (this.combat.isOver) return this.endEncounter();
      this.endActorTurn();
    } finally {
      this.busy = false;
    }
  }

  /** Tiny prompt sitting where the picker overlay used to. */
  private renderTilePickerHint(spell: Spell): void {
    this.clearPicker();
    const lines = [
      `Casting: ${spell.name}`,
      "[↑↓←→] move reticle",
      "[Enter] confirm",
      "[ESC]   cancel",
    ];
    const w = HUD_W - 12, h = lines.length * 18 + 28;
    const x = HUD_X + 6, y = HUD_Y + HUD_H - 6 - h;
    this.pickerObjects.push(
      this.add.rectangle(x, y, w, h, 0x10101a, 0.98)
        .setOrigin(0)
        .setStrokeStyle(2, C.accent)
    );
    this.pickerObjects.push(
      this.add.text(x + 10, y + 8, "PICK A TILE", FONT_HEAD(C.accent))
    );
    lines.forEach((line, i) => {
      this.pickerObjects.push(
        this.add.text(x + 10, y + 30 + i * 18, line, FONT_BODY())
      );
    });
  }

  /**
   * Resolve whatever tile-targeted spell the player just confirmed.
   * Branches by effect_type: AOE damage, teleport, summon (stub).
   */
  private async resolveTileSpell(): Promise<void> {
    const action = this.pendingAction;
    if (!action || action.kind !== "tile") return;
    const me = this.combat.current;
    const spell = action.spell;
    const member = this.memberForCurrent();
    if (member && member.maxMp != null) {
      member.mp = Math.max(0, (member.mp ?? 0) - spell.mp_cost);
    }
    this.busy = true;
    this.mode = "default";
    this.pendingAction = null;
    this.clearTileCursor();
    this.clearPicker();
    // Cast SFX + caster glow before the per-effect VFX kicks in.
    Sfx.play(spell.sfx);
    this.castGlowFor(me, this.colorForSpell(spell.effect_type));
    try {
      const e = spell.effect_type;
      if (e === "aoe_fireball") {
        await this.resolveAoeFireball(me, spell, this.tileCursorPos);
      } else if (e === "teleport") {
        await this.resolveTeleport(me, spell, this.tileCursorPos);
      } else if (e === "summon_skeleton") {
        await this.resolveSummonSkeleton(me, spell, this.tileCursorPos);
      } else {
        this.combat.log.push(
          `${me.name} casts ${spell.name} on a tile — no effect yet.`
        );
      }
      this.combat.movePoints = 0;
      this.refreshAll();
      if (this.combat.isOver) return this.endEncounter();
      this.endActorTurn();
    } finally {
      this.busy = false;
    }
  }

  /**
   * Fireball-style AOE: every alive enemy within `radius` Chebyshev
   * tiles of the chosen cell takes the spell's dice damage.
   */
  private async resolveAoeFireball(
    caster: Combatant, spell: Spell, centre: { col: number; row: number },
  ): Promise<void> {
    const ev = spell.effect_value ?? {};
    const radius = typeof (ev as Record<string, unknown>).radius === "number"
      ? (ev as { radius: number }).radius
      : 3;
    const victims = this.combat.combatants.filter(
      (c) => c.side === "enemies" && c.hp > 0 &&
             Math.max(
               Math.abs(c.position.col - centre.col),
               Math.abs(c.position.row - centre.row),
             ) <= radius
    );
    // Aim a fireball orb at the centre tile, then explode there.
    const burstAt = { x: this.tileX(centre.col), y: this.tileY(centre.row) };
    await projectileLine(
      this,
      { x: this.tileX(caster.position.col), y: this.tileY(caster.position.row) },
      burstAt,
      VFX_COLOURS.fire, 280,
    );
    if (spell.hit_sfx) Sfx.play(spell.hit_sfx);
    screenShake(this, 0.008, 240);
    void radialBurst(this, burstAt, VFX_COLOURS.fire, VFX_COLOURS.ember, 64);
    if (victims.length === 0) {
      this.combat.log.push(
        `${caster.name} casts ${spell.name} at (${centre.col},${centre.row}) — caught nothing.`
      );
      return;
    }
    let total = 0;
    for (const v of victims) {
      const r = resolveDamageSpell(caster, v, spell, defaultRng);
      total += r.damage;
      this.refreshHp(v);
      void this.animateHit(v, r);
    }
    this.combat.log.push(
      `${caster.name} casts ${spell.name} — ${victims.length} foe${victims.length === 1 ? "" : "s"} hit, ${total} dmg total.`
    );
  }

  /**
   * Misty Step / similar — relocate the caster to the chosen tile.
   * Refuses if the tile is a wall or already occupied.
   */
  private async resolveTeleport(
    caster: Combatant, spell: Spell, dest: { col: number; row: number },
  ): Promise<void> {
    if (isWall(dest.col, dest.row)) {
      this.combat.log.push(`${caster.name} can't teleport into a wall.`);
      return;
    }
    if (this.combat.combatantAt(dest.col, dest.row)) {
      this.combat.log.push(`${caster.name} can't teleport onto another combatant.`);
      return;
    }
    caster.position = { ...dest };
    // Snap the sprite + selection ring to the new tile, with a fade
    // out / fade in pair so the relocation reads visually.
    const body = this.bodies.get(caster.id);
    const ring = this.selRings.get(caster.id);
    const x = this.tileX(dest.col);
    const y = this.tileY(dest.row);
    if (body) {
      void radialBurst(this, { x: body.x, y: body.y }, VFX_COLOURS.arcane, VFX_COLOURS.white, 30);
      await new Promise<void>((res) => {
        this.tweens.add({
          targets: body, alpha: 0,
          duration: 140,
          onComplete: () => res(),
        });
      });
      body.x = x; body.y = y;
      if (ring) { ring.x = x; ring.y = y; }
      void radialBurst(this, { x, y }, VFX_COLOURS.arcane, VFX_COLOURS.white, 30);
      await new Promise<void>((res) => {
        this.tweens.add({
          targets: body, alpha: 1,
          duration: 140,
          onComplete: () => res(),
        });
      });
    } else if (ring) {
      ring.x = x; ring.y = y;
    }
    this.combat.log.push(
      `${caster.name} casts ${spell.name} — vanishes and reappears at (${dest.col},${dest.row}).`
    );
  }

  /**
   * Animate Dead — raise a skeleton ally on the chosen tile that fights
   * for the party for `spell.duration` turns, then crumbles to dust.
   *
   * Refuses if the destination is a wall or already occupied. The new
   * combatant is built via `makeSummonedSkeleton` (reads stats out of
   * `effect_value`), then handed to `combat.addCombatant` which seeds
   * its initiative slot and tracks the summon timer. The scene
   * separately wires up its body sprite + selection ring so the right
   * HUD and the arena pick the new actor up immediately.
   */
  private async resolveSummonSkeleton(
    caster: Combatant, spell: Spell, dest: { col: number; row: number },
  ): Promise<void> {
    if (isWall(dest.col, dest.row)) {
      this.combat.log.push(`${caster.name} can't raise the dead in a wall.`);
      return;
    }
    if (this.combat.combatantAt(dest.col, dest.row)) {
      this.combat.log.push(`${caster.name} can't summon onto another combatant.`);
      return;
    }
    const id = `summon-${caster.id}-${this.combat.combatants.length}`;
    const skeleton = makeSummonedSkeleton(spell, id, caster.name);
    const turns = typeof spell.duration === "number" ? spell.duration : 5;
    this.combat.addCombatant(skeleton, dest, turns);

    // Build the matching scene visuals: selection ring + body sprite
    // at the destination tile so the new combatant slots into the
    // arena immediately. Mirrors the loop in drawCombatants() so the
    // entry behaves like one that was there from create().
    const x = this.tileX(dest.col);
    const y = this.tileY(dest.row);
    const ring = this.add
      .rectangle(x, y, TILE, TILE, C.cursor, 0)
      .setStrokeStyle(2, C.cursor)
      .setVisible(false);
    this.selRings.set(id, ring);
    let body: Phaser.GameObjects.Image | Phaser.GameObjects.Rectangle;
    if (skeleton.sprite && this.textures.exists(skeleton.sprite)) {
      body = this.add.image(x, y, skeleton.sprite);
    } else {
      const colorHex = Phaser.Display.Color.GetColor(...skeleton.color);
      body = this.add
        .rectangle(x, y, TILE - 4, TILE - 4, colorHex)
        .setStrokeStyle(2, 0x0a0a14);
    }
    this.bodies.set(id, body);

    // "Claws its way out of the ground" VFX — purple/bone burst at
    // the spawn tile, then a quick scale-up on the body so the entry
    // reads as a summoning rather than a warp-in.
    void radialBurst(this, { x, y }, VFX_COLOURS.curse, VFX_COLOURS.white, 42);
    body.setScale(0.2);
    this.tweens.add({
      targets: body, scale: 1,
      duration: 320, ease: "Back.Out",
    });

    this.combat.log.push(
      `${caster.name} casts ${spell.name}!`
    );
    this.combat.log.push(
      `A skeleton claws its way out of the ground! (${turns} turns)`
    );
  }

  private onTileClicked(col: number, row: number): void {
    if (!this.canTakePlayerInput()) return;
    const actor = this.combat.current;
    const dc = col - actor.position.col;
    const dr = row - actor.position.row;
    if (Math.abs(dc) + Math.abs(dr) !== 1) return;
    let dir: Direction;
    if (dc === 1) dir = "e";
    else if (dc === -1) dir = "w";
    else if (dr === 1) dir = "s";
    else dir = "n";
    void this.tryPlayerStep(dir);
  }

  private onEndTurnClicked(): void {
    if (!this.canTakePlayerInput()) return;
    this.combat.log.push(`${this.combat.current.name} ends their turn.`);
    this.endActorTurn();
  }

  private canTakePlayerInput(): boolean {
    // Player input is only valid when the active actor is a real
    // party member, not an AI-controlled summon on the party side.
    return !this.busy && !this.ended &&
           this.combat.current.side === "party" &&
           !isAiControlled(this.combat.current);
  }

  // ── Turn flow ────────────────────────────────────────────────────

  private async tryPlayerStep(dir: Direction): Promise<void> {
    if (!this.canTakePlayerInput()) return;
    this.busy = true;
    try {
      const actor = this.combat.current;
      const before = { ...actor.position };
      const result = this.combat.tryMove(dir);
      if (result.kind === "moved") {
        await this.animateMove(actor, before, result.to);
      } else if (result.kind === "attacked") {
        const target = this.combat.byId(result.result.targetId);
        await this.animateBump(actor, before, target.position);
        await this.animateHit(target, result.result);
        this.refreshHp(target);
        if (result.result.hit) {
          this.applyWeaponDurability(actor.id);
          this.applyArmorDurability(target.id);
        }
      } else {
        await this.animateBlocked(actor, dir);
      }
      this.refreshAll();
      if (this.combat.isOver) return this.endEncounter();
      if (this.combat.movePoints <= 0) this.endActorTurn();
    } finally {
      this.busy = false;
    }
  }

  private endActorTurn(): void {
    this.clearMoveHints();
    this.combat.endTurn();
    this.refreshAll();
    if (this.combat.isOver) return this.endEncounter();
    this.kickOffCurrentTurn();
  }

  private async runMonsterTurn(): Promise<void> {
    try {
      while (
        !this.combat.isOver &&
        isAiControlled(this.combat.current) &&
        this.combat.movePoints > 0
      ) {
        const intent = this.combat.decideMonsterIntent();
        if (intent.kind === "wait") break;
        if (intent.kind === "attack") {
          const attackerId = this.combat.current.id;
          const result = this.combat.attack(intent.targetId);
          this.combat.movePoints = 0;
          const target = this.combat.byId(result.targetId);
          await this.animateBump(this.combat.current, this.combat.current.position, target.position);
          await this.animateHit(target, result);
          this.refreshHp(target);
          if (result.hit) {
            // attacker is enemy → applyWeaponDurability is a no-op; the
            // call still runs so charmed/summoned attackers wear their
            // weapons too. Target may be a party member — armor wear.
            this.applyWeaponDurability(attackerId);
            this.applyArmorDurability(target.id);
          }
          this.refreshLog();
          break;
        }
        const actor = this.combat.current;
        const before = { ...actor.position };
        const moveResult = this.combat.tryMove(intent.dir);
        if (moveResult.kind === "moved") {
          await this.animateMove(actor, before, moveResult.to);
        } else if (moveResult.kind === "attacked") {
          const target = this.combat.byId(moveResult.result.targetId);
          await this.animateBump(actor, before, target.position);
          await this.animateHit(target, moveResult.result);
          this.refreshHp(target);
          if (moveResult.result.hit) {
            this.applyWeaponDurability(actor.id);
            this.applyArmorDurability(target.id);
          }
          this.refreshLog();
          break;
        } else {
          break;
        }
        this.refreshLog();
      }
    } finally {
      this.busy = false;
    }
    if (this.combat.isOver) return this.endEncounter();
    this.endActorTurn();
  }

  // ── Animations (unchanged from the previous build) ───────────────

  private animateMove(
    actor: Combatant,
    from: { col: number; row: number },
    to: { col: number; row: number }
  ): Promise<void> {
    void from;
    return new Promise((resolve) => {
      const body = this.bodies.get(actor.id)!;
      const ring = this.selRings.get(actor.id)!;
      this.tweens.add({
        targets: [body, ring],
        x: this.tileX(to.col),
        y: this.tileY(to.row),
        duration: 110,
        onUpdate: () => this.syncMonsterBar(actor.id),
        onComplete: () => {
          this.syncMonsterBar(actor.id);
          resolve();
        },
      });
    });
  }

  // ── VFX shortcuts ────────────────────────────────────────────────
  //
  // Thin wrappers that look up the actor's body sprite for screen
  // coordinates and call into web/src/game/combat/Vfx.ts. Keeping the
  // coordinate math here lets the Vfx module stay scene-agnostic.

  private bodyXY(c: Combatant): { x: number; y: number } {
    const body = this.bodies.get(c.id);
    if (body) return { x: body.x, y: body.y };
    return { x: this.tileX(c.position.col), y: this.tileY(c.position.row) };
  }

  /** Pick a thematic VFX colour for a given spell effect_type. */
  private colorForSpell(effect: string): number {
    if (effect === "heal" || effect === "major_heal" || effect === "mass_heal" ||
        effect === "cure_poison" || effect === "restore") return VFX_COLOURS.heal;
    if (effect === "bless" || effect === "ac_buff" || effect === "range_buff" ||
        effect === "invisibility") return VFX_COLOURS.buff;
    if (effect === "curse") return VFX_COLOURS.curse;
    if (effect === "aoe_fireball") return VFX_COLOURS.fire;
    if (effect === "lightning_bolt") return VFX_COLOURS.lightning;
    if (effect === "undead_damage") return VFX_COLOURS.buff;
    if (effect === "teleport") return VFX_COLOURS.arcane;
    return VFX_COLOURS.arcane;
  }

  /** Caster glow used at the start of every cast. */
  private castGlowFor(c: Combatant, color: number): void {
    const body = this.bodies.get(c.id);
    if (body) castGlow(this, body, color);
  }

  /** Fly a projectile arc from `from` → `to` in screen coords. */
  private flyProjectile(from: Combatant, to: Combatant, color: number): Promise<void> {
    return projectileLine(this, this.bodyXY(from), this.bodyXY(to), color, 240);
  }

  /** Lightning zigzag from caster to target. */
  private lightningTo(from: Combatant, to: Combatant): Promise<void> {
    return lightningZigzag(this, this.bodyXY(from), this.bodyXY(to));
  }

  /** Coloured aura ring around a target — buff/debuff status visual. */
  private auraOn(c: Combatant, color: number): Promise<void> {
    return glowAura(this, this.bodyXY(c), color);
  }

  /** Healing sparkle column rising over a target. */
  private healTargetVfx(c: Combatant): Promise<void> {
    return healingSparkles(this, this.bodyXY(c));
  }

  /**
   * Refresh sprite alpha for every combatant based on their state:
   *
   *   - Active "Invisibility" buff → 0.2 (caster is visually faded
   *     out for the spell's full duration; a thin silhouette remains
   *     so the player can still tell where their hero is on the
   *     grid). Returns to 1.0 the moment the buff expires.
   *   - HP <= 0 → 0.4 (existing dim state for downed combatants).
   *   - Otherwise → 1.0.
   *
   * Called from refreshAll so cast / endTurn / animations all keep
   * the visuals in sync without per-call wiring.
   */
  private refreshVisibility(): void {
    for (const c of this.combat.combatants) {
      const body = this.bodies.get(c.id);
      if (!body) continue;
      let alpha = 1;
      if (c.hp <= 0) alpha = 0.4;
      else if (this.combat.hasBuffFromSource(c.id, "Invisibility")) alpha = 0.2;
      // Skip if a tween is in flight on this body so we don't
      // stomp the brief hit-flash yoyo.
      const tweens = this.tweens.getTweensOf(body);
      if (tweens.length > 0) continue;
      body.alpha = alpha;
    }
  }

  private animateBump(
    actor: Combatant,
    from: { col: number; row: number },
    target: { col: number; row: number }
  ): Promise<void> {
    return new Promise((resolve) => {
      const body = this.bodies.get(actor.id)!;
      const ring = this.selRings.get(actor.id)!;
      const startX = this.tileX(from.col);
      const startY = this.tileY(from.row);
      const targetX = this.tileX(target.col);
      const targetY = this.tileY(target.row);
      const midX = startX + (targetX - startX) * 0.4;
      const midY = startY + (targetY - startY) * 0.4;
      this.tweens.add({
        targets: [body, ring],
        x: midX, y: midY,
        duration: 90, yoyo: true,
        onUpdate: () => this.syncMonsterBar(actor.id),
        onComplete: () => {
          this.syncMonsterBar(actor.id);
          resolve();
        },
      });
    });
  }

  private animateBlocked(actor: Combatant, dir: Direction): Promise<void> {
    return new Promise((resolve) => {
      const body = this.bodies.get(actor.id)!;
      const ring = this.selRings.get(actor.id)!;
      const dx = dir === "e" ? 4 : dir === "w" ? -4 : 0;
      const dy = dir === "s" ? 4 : dir === "n" ? -4 : 0;
      this.tweens.add({
        targets: [body, ring],
        x: body.x + dx, y: body.y + dy,
        duration: 50, yoyo: true,
        onUpdate: () => this.syncMonsterBar(actor.id),
        onComplete: () => resolve(),
      });
    });
  }

  private animateHit(target: Combatant, result: AttackResult): Promise<void> {
    return new Promise((resolve) => {
      const body = this.bodies.get(target.id);
      if (!body) return resolve();
      const label = result.hit
        ? result.critical ? `CRIT! -${result.damage}` : `-${result.damage}`
        : "miss";
      const color = result.hit ? (result.critical ? "#ffd470" : "#ff6b6b") : "#bdb38a";
      // SFX + flash. Critical hits play the louder fanfare and shake
      // the camera; misses get the rising "whoosh"; ordinary hits use
      // the side-appropriate hurt SFX so the player can hear who took it.
      if (result.hit) {
        if (result.critical) {
          Sfx.play("critical");
          screenShake(this, 0.006, 220);
        } else {
          Sfx.play(target.side === "party" ? "player_hurt" : "monster_hit");
        }
        flashTarget(this, body, VFX_COLOURS.blood);
      } else {
        Sfx.play("miss");
        floatingX(this, { x: body.x, y: body.y });
      }
      const t = this.add.text(body.x, body.y - 12, label, {
        fontFamily: "Georgia, serif",
        fontSize: "14px",
        color,
        stroke: "#1a1a2e",
        strokeThickness: 4,
      }).setOrigin(0.5, 1);
      this.tweens.add({
        targets: t,
        y: t.y - 22, alpha: 0,
        duration: 600,
        onComplete: () => { t.destroy(); resolve(); },
      });
      if (result.hit) {
        this.tweens.add({
          targets: body, alpha: 0.3,
          duration: 80, yoyo: true, repeat: 1,
        });
      }
    });
  }

  // ── HUD refresh ──────────────────────────────────────────────────

  private refreshAll(): void {
    this.refreshTurnHeader();
    this.refreshActionMenu();
    this.refreshLog();
    for (const x of this.combat.combatants) this.refreshHp(x);
    this.highlightActiveActor();
    this.drawMoveHints();
    this.refreshVisibility();
  }

  private refreshTurnHeader(): void {
    const c = this.combat.current;
    this.turnText.setText(`-- ${c.name.toUpperCase()}'S TURN --`);
    this.movePointsText.setText(
      `Moves: ${this.combat.movePoints}/${c.baseMoveRange}`
    );
  }

  private refreshActionMenu(): void {
    // Player can act only on real party members, not on AI summons
    // that share the party side.
    const playerTurn =
      this.combat.current.side === "party" &&
      !isAiControlled(this.combat.current);
    const member = this.memberForCurrent();
    // Per-action enable state — dynamic based on the active member.
    const canThrow = !!member && this.partyHasThrowable();
    const canCast =
      !!member &&
      member.maxMp != null &&
      this.spells.some(
        (s) =>
          spellIsCombatCastable(s, member.class) &&
          (member.mp ?? 0) >= s.mp_cost
      );
    // Range is enabled when the equipped weapon has ranged: true.
    const equippedWeapon =
      member && member.equipped.rightHand
        ? this.items.get(member.equipped.rightHand) ?? null
        : null;
    const canRange = !!equippedWeapon && isRanged(equippedWeapon);
    const isEnabled = (id: ActionId): boolean => {
      if (!playerTurn) return false;
      if (id === "range") return canRange;
      if (id === "throw") return canThrow;
      if (id === "cast")  return canCast;
      return true;
    };
    for (let i = 0; i < PARTY_ACTIONS.length; i++) {
      const a = PARTY_ACTIONS[i];
      const text = this.actionTexts[i];
      const handle = this.actionRowHandles[i];
      const enabled = isEnabled(a.id);
      const cursor = playerTurn && i === this.actionCursor;
      const color = !enabled ? C.faint : cursor ? C.body : C.dim;
      text.setStyle(FONT_BODY(color));
      const prefix = cursor ? "> " : "  ";
      const suffix = enabled ? "" : "  —";
      text.setText(`${prefix}${a.label}${suffix}`);
      handle.setFillStyle(C.selectBg, cursor && enabled ? 1 : 0);
    }
  }

  /** True when active member or shared stash has at least one item
   *  the items catalog flags as throwable / ranged. */
  private partyHasThrowable(): boolean {
    const member = this.memberForCurrent();
    const party = gameState.partyData;
    const check = (name: string) => {
      const def = this.items.get(name);
      return !!def && isThrowable(def);
    };
    if (member && member.inventory.some((it) => check(it.item))) return true;
    if (party && party.inventory.some((it) => check(it.item))) return true;
    return false;
  }

  private refreshHp(c: Combatant): void {
    if (c.side === "party") {
      const card = this.partyCards.get(c.id);
      if (card) {
        const pct = Math.max(0, c.hp / Math.max(1, c.maxHp));
        card.hpBar.width = Math.max(0, card.fullBarW * pct);
        card.hpBar.setFillStyle(pct <= 0.3 ? C.hpLow : C.hpFull, 1);
        card.hpText.setText(`${c.hp}/${c.maxHp}`);
        // Casters: re-read MP from the live PartyMember and resize bar.
        if (card.mpBar && card.mpText) {
          const member = this.memberByCombatantId(c.id);
          if (member && member.maxMp != null) {
            const mpPct = Math.max(0, (member.mp ?? 0) / Math.max(1, member.maxMp));
            card.mpBar.width = Math.max(0, card.fullBarW * mpPct);
            card.mpText.setText(`${member.mp ?? 0}/${member.maxMp}`);
          }
        }
      }
    }
    if (c.side === "enemies") {
      // Update the floating HP bar above the monster sprite. Hidden
      // entirely once the creature drops to 0 HP so the corpse doesn't
      // keep advertising a full bar.
      const bars = this.monsterHpBars.get(c.id);
      if (bars) {
        const pct = Math.max(0, c.hp / Math.max(1, c.maxHp));
        bars.bar.width = Math.max(0, bars.fullW * pct);
        bars.bar.setFillStyle(pct <= 0.3 ? C.hpLow : C.hpFull, 1);
        if (c.hp <= 0) {
          bars.bg.setVisible(false);
          bars.bar.setVisible(false);
        }
      }
    }
    if (c.hp <= 0) {
      const body = this.bodies.get(c.id);
      if (body instanceof Phaser.GameObjects.Image) body.setTint(0x444466).setAlpha(0.4);
      else if (body) body.setFillStyle(0x2a2a3a).setStrokeStyle(1, 0x444466);
      this.selRings.get(c.id)?.setVisible(false);
    }
  }

  /** Re-sync a monster's floating HP bar to its body's current x/y.
   *  Called from move / bump tween onUpdate so the bar tracks the
   *  sprite mid-animation. */
  private syncMonsterBar(actorId: string): void {
    const bars = this.monsterHpBars.get(actorId);
    const body = this.bodies.get(actorId);
    if (!bars || !body) return;
    bars.bg.x = body.x;
    bars.bg.y = body.y - bars.offsetY;
    bars.bar.x = body.x - bars.fullW / 2;
    bars.bar.y = body.y - bars.offsetY;
  }

  private refreshLog(): void {
    // Show the last seven lines so the dice/mod detail and the
    // turn announcements don't push the encounter banner off the
    // top in the first round.
    this.logText.setText(this.combat.log.slice(-7).join("\n"));
  }

  private highlightActiveActor(): void {
    const activeId = this.combat.current.id;
    for (const c of this.combat.combatants) {
      const ring = this.selRings.get(c.id);
      if (!ring) continue;
      ring.setVisible(c.id === activeId && c.hp > 0);
    }
  }

  private drawMoveHints(): void {
    this.clearMoveHints();
    if (this.combat.current.side !== "party") return;
    const actor = this.combat.current;
    const dirs: [number, number][] = [[-1, 0], [1, 0], [0, -1], [0, 1]];
    for (const [dc, dr] of dirs) {
      const nc = actor.position.col + dc;
      const nr = actor.position.row + dr;
      if (isWall(nc, nr)) continue;
      const occupant = this.combat.combatantAt(nc, nr);
      if (occupant && occupant.side === actor.side) continue;
      const hint = this.add
        .rectangle(this.tileX(nc), this.tileY(nr), TILE - 6, TILE - 6, C.moveHint, 0.35)
        .setStrokeStyle(1, C.moveHint);
      this.moveHintRects.push(hint);
    }
  }

  private clearMoveHints(): void {
    for (const r of this.moveHintRects) r.destroy();
    this.moveHintRects.length = 0;
  }

  private endEncounter(): void {
    if (this.ended) return;
    this.ended = true;
    this.clearMoveHints();
    const winner = this.combat.winner;
    if (winner === "party") {
      Sfx.play("victory");
      this.showOverlay("Victory!", "#a3d9a5");
    } else if (winner === "enemies") {
      Sfx.play("defeat");
      this.showOverlay("Defeat…", "#ff6b6b");
    }
    if (this.fromWorld) {
      if (winner === "party" && this.triggerKey) {
        gameState.consumedTriggers.add(this.triggerKey);
      }
      if (winner === "party") {
        // Spawn-tile boss fight: mark the tile as destroyed so the
        // overworld will rewrite it to grass and stop spawning from it.
        if (this.destroySpawnKey) {
          gameState.destroyedSpawns.add(this.destroySpawnKey);
          // Any roamers tied to this destroyed spawn vanish too —
          // their lair is gone.
          gameState.roamingMonsters = gameState.roamingMonsters.filter(
            (m) => m.sourceKey !== this.destroySpawnKey,
          );
        }
        // Roamer engagement: just remove that one entry.
        if (this.roamerId) {
          gameState.roamingMonsters = gameState.roamingMonsters.filter(
            (m) => m.id !== this.roamerId,
          );
        }
        // XP + gold: sum from defeated enemies, share with all alive
        // party members, run level-up, then refresh the HUD bars so
        // any HP/MP gains show before we fade out. awardRewards is
        // fire-and-forget here — fade waits on its own timer so a
        // slow class-template fetch doesn't stall the transition.
        void this.awardRewards();
      }
      if (winner === "enemies") {
        gameState.defeated = true;
      }
      // Carry HP back to the live roster so wounds persist across
      // encounters. Pretty important now that combat reads the real
      // party — without this, every encounter would refresh HP from
      // the (frozen) party.json values.
      if (gameState.partyData) {
        syncCombatHpBack(gameState.partyData, this.combat.combatants);
      }
      this.time.delayedCall(2400, () => {
        this.cameras.main.fadeOut(220, 0, 0, 0);
        this.cameras.main.once("camerafadeoutcomplete", () => {
          this.scene.start("OverworldScene");
        });
      });
    }
  }

  /**
   * Compute and apply victory rewards: sum XP + rolled gold from every
   * defeated enemy, hand each to all *alive* party members, then run
   * the level-up loop per member. Drops a brief panel beneath the
   * "Victory!" overlay summarising what was earned.
   *
   * Class templates are fetched lazily; if the fetch fails we silently
   * skip the level-up step rather than blocking the post-combat
   * transition. XP is still added to the member's `exp` either way.
   */
  private async awardRewards(): Promise<void> {
    const enemies = this.combat.combatants.filter((c) => c.side === "enemies");
    const totalXp   = enemies.reduce((s, m) => s + (m.xpReward   ?? 0), 0);
    const totalGold = enemies.reduce((s, m) => s + (m.goldReward ?? 0), 0);
    const party = gameState.partyData;
    if (!party) {
      this.showRewardSummary(totalXp, totalGold, []);
      return;
    }
    party.gold += totalGold;
    const aliveMembers: PartyMember[] = [];
    for (const c of this.combat.combatants) {
      if (c.side !== "party" || c.hp <= 0) continue;
      const m = party.roster.find((r) => r.name === c.name);
      if (m) aliveMembers.push(m);
    }
    const levelUps: LevelUpEvent[] = [];
    if (totalXp > 0 && aliveMembers.length > 0) {
      const races = await loadRaces().catch(() => null);
      for (const m of aliveMembers) {
        let tpl: ClassTemplate | null = null;
        try { tpl = await loadClass(m.class); } catch { /* skip leveling */ }
        if (!tpl) {
          // Still credit the raw XP so the bar fills next time the
          // class file loads — saves the player some grinding.
          m.exp += totalXp;
          continue;
        }
        const race = races ? races.get(m.race) ?? null : null;
        levelUps.push(...awardXp(m, totalXp, tpl, race));
      }
      for (const ev of levelUps) Sfx.play("victory");
      // Refresh the HUD so HP/MP bars catch any gains.
      for (const c of this.combat.combatants) this.refreshHp(c);
    }
    this.showRewardSummary(totalXp, totalGold, levelUps);
  }

  /** Stack a short reward-summary panel under the "Victory!" overlay
   *  so the player can see XP / gold gained and any level-ups before
   *  we fade back to the overworld. */
  private showRewardSummary(
    xp: number, gold: number, events: LevelUpEvent[],
  ): void {
    const lines: string[] = [];
    if (xp > 0)   lines.push(`+${xp} XP`);
    if (gold > 0) lines.push(`+${gold} gold`);
    for (const ev of events) lines.push(ev.message);
    if (lines.length === 0) return;
    const text = lines.join("\n");
    const t = this.add.text(
      ARENA_X + ARENA_W / 2,
      ARENA_Y + ARENA_H / 2 + 56,
      text,
      {
        fontFamily: "Georgia, serif",
        fontSize: "18px",
        color: "#ffd470",
        align: "center",
        stroke: "#1a1a2e",
        strokeThickness: 4,
        lineSpacing: 4,
      },
    ).setOrigin(0.5).setDepth(120);
    // Fade in a beat after the "Victory!" headline so the eye reads
    // them in order, then leave it on screen until the scene fades.
    t.setAlpha(0);
    this.tweens.add({
      targets: t, alpha: 1, duration: 300, delay: 350,
    });
  }

  private showOverlay(label: string, color: string): void {
    if (this.overlayText) this.overlayText.destroy();
    this.overlayText = this.add
      .text(ARENA_X + ARENA_W / 2, ARENA_Y + ARENA_H / 2, label, {
        fontFamily: "Georgia, serif",
        fontSize: "48px",
        color,
        stroke: "#1a1a2e",
        strokeThickness: 8,
      })
      .setOrigin(0.5);
  }
}
