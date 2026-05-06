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
import { Combat } from "../combat/Combat";
import {
  ARENA_COLS,
  ARENA_ROWS,
  isWall,
  type Direction,
} from "../combat/Arena";
import { makeSampleParty, PARTY_SPRITES } from "../data/fighters";
import { makeSampleEncounter, MONSTER_SPRITES } from "../data/monsters";
import { gameState } from "../state";
import { tileSpriteKey, populateRuntimeDefs, spriteManifest } from "../world/Tiles";
import type { Combatant, AttackResult } from "../types";

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
}

// ── Layout (canvas is 960×720) ────────────────────────────────────
const TILE = 26;
const HEADER_H = 32;
const ARENA_X = 12;
const ARENA_Y = HEADER_H + 8;             // 40
const ARENA_W = ARENA_COLS * TILE;        // 18 × 26 = 468
const ARENA_H = ARENA_ROWS * TILE;        // 21 × 26 = 546
const HUD_X = ARENA_X + ARENA_W + 12;     // 492
const HUD_W = 960 - HUD_X - 12;           // 456
const HUD_Y = ARENA_Y;
const HUD_H = ARENA_H;
const LOG_X = 12;
const LOG_Y = ARENA_Y + ARENA_H + 8;      // 594
const LOG_W = 960 - 24;                   // 936
const LOG_H = 720 - LOG_Y - 12;           // 114

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

/** Action menu — what the active party member can do this turn. */
type ActionId = "attack" | "end" | "flee" | "throw" | "defend";

interface ActionEntry {
  id: ActionId;
  label: string;
  /** When false the row renders dim and Enter shows a "coming soon" line. */
  enabled: boolean;
}

const PARTY_ACTIONS: ActionEntry[] = [
  { id: "attack", label: "Attack",  enabled: true  },
  { id: "end",    label: "End Turn", enabled: true },
  { id: "flee",   label: "Flee",    enabled: true  },
  { id: "throw",  label: "Throw",   enabled: false },
  { id: "defend", label: "Defend",  enabled: false },
];

export class CombatScene extends Phaser.Scene {
  private combat!: Combat;
  private fromWorld = false;
  private triggerKey: string | null = null;
  private terrainTileId: number | null = null;

  private bodies = new Map<string, Phaser.GameObjects.Image | Phaser.GameObjects.Rectangle>();
  private selRings = new Map<string, Phaser.GameObjects.Rectangle>();
  private moveHintRects: Phaser.GameObjects.Rectangle[] = [];
  /** Per-party-member HP/MP card UI, kept so we can refresh in place. */
  private partyCards = new Map<string, {
    hpBar: Phaser.GameObjects.Rectangle;
    hpText: Phaser.GameObjects.Text;
  }>();

  private logText!: Phaser.GameObjects.Text;
  private turnText!: Phaser.GameObjects.Text;
  private movePointsText!: Phaser.GameObjects.Text;
  private actionTexts: Phaser.GameObjects.Text[] = [];
  private actionRowHandles: Phaser.GameObjects.Rectangle[] = [];
  private actionCursor = 0;

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
    this.busy = false;
    this.ended = false;
    this.actionCursor = 0;
    this.bodies.clear();
    this.selRings.clear();
    this.moveHintRects.length = 0;
    this.partyCards.clear();
    this.actionTexts.length = 0;
    this.actionRowHandles.length = 0;
  }

  preload(): void {
    for (const path of [...PARTY_SPRITES, ...MONSTER_SPRITES]) {
      this.load.image(path, path);
    }
    // Tile sprites for the arena floor — load the full tile manifest
    // so we can render whatever terrain the encounter sat on.
    this.textures.on("addtexture", (key: string) => {
      const tex = this.textures.get(key);
      if (tex) tex.setFilter(Phaser.Textures.FilterMode.NEAREST);
    });
    this.load.json("tile_defs_combat", "/data/tile_defs.json");
    this.load.once("filecomplete-json-tile_defs_combat", () => {
      const raw = this.cache.json.get("tile_defs_combat");
      if (raw) populateRuntimeDefs(raw);
      for (const { key, path } of spriteManifest()) {
        this.load.image(key, path);
      }
    });
  }

  create(): void {
    const party = this.fromWorld ? gameState.party : makeSampleParty();
    this.combat = new Combat(party, makeSampleEncounter());
    this.cameras.main.setBackgroundColor("#0c0c14");
    this.cameras.main.fadeIn(220, 0, 0, 0);

    this.drawHeader();
    this.drawArena();
    this.drawHud();
    this.drawLog();
    this.drawCombatants();
    this.installInput();

    this.refreshAll();
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
        // U3 styling.
        if (terrainKey && this.textures.exists(terrainKey)) {
          this.add.image(x, y, terrainKey).setOrigin(0).setDisplaySize(TILE, TILE);
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
        if (!a.enabled) return;
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
    this.add.text(tx, y + 6, c.name, FONT_BODY());
    // HP bar
    const barW = w - (tx - x) - 12;
    const barY = y + h - 18;
    this.add.rectangle(tx, barY, barW, 8, 0x1c1c2a, 1).setOrigin(0)
      .setStrokeStyle(1, C.panelEdge);
    const hpBar = this.add
      .rectangle(tx + 1, barY + 1, barW - 2, 6, C.hpFull, 1)
      .setOrigin(0);
    const hpText = this.add
      .text(tx + barW - 2, y + 6, `${c.hp}/${c.maxHp}`,
            FONT_MONO(C.dim))
      .setOrigin(1, 0);
    this.partyCards.set(c.id, { hpBar, hpText });
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
        body = this.add.image(x, y, c.sprite);
        body.setDisplaySize(TILE, TILE);
      } else {
        const colorHex = Phaser.Display.Color.GetColor(...c.color);
        body = this.add
          .rectangle(x, y, TILE - 4, TILE - 4, colorHex)
          .setStrokeStyle(2, 0x0a0a14);
      }
      this.bodies.set(c.id, body);
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
    k.on("keydown-SPACE", () => this.activateAction());
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
    if (key === "UP")    return this.moveActionCursor(-1);
    if (key === "DOWN")  return this.moveActionCursor(1);
    if (key === "LEFT" || key === "RIGHT") return; // unused on the menu
    void this.tryPlayerStep(dir);
  }

  private moveActionCursor(delta: number): void {
    const enabled = PARTY_ACTIONS.map((a, i) => (a.enabled ? i : -1)).filter((i) => i >= 0);
    if (enabled.length === 0) return;
    const cur = enabled.indexOf(this.actionCursor);
    const next = (cur + delta + enabled.length) % enabled.length;
    this.actionCursor = enabled[next];
    this.refreshActionMenu();
  }

  private activateAction(): void {
    if (!this.canTakePlayerInput()) return;
    const a = PARTY_ACTIONS[this.actionCursor];
    if (!a) return;
    if (!a.enabled) {
      this.combat.log.push(`(${a.label} is not implemented yet.)`);
      this.refreshLog();
      return;
    }
    if (a.id === "attack") {
      // Find an adjacent enemy and bump-attack. If none, the action
      // does nothing visible — the log records the attempt.
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
    if (a.id === "end")  return this.onEndTurnClicked();
    if (a.id === "flee") return this.onFleeClicked();
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

  private onFleeClicked(): void {
    if (this.ended || this.busy) return;
    if (this.combat.current.side !== "party") return;
    this.combat.log.push(`${this.combat.current.name} flees the encounter.`);
    this.refreshLog();
    this.ended = true;
    this.showOverlay("You escaped.", "#bdb38a");
  }

  private canTakePlayerInput(): boolean {
    return !this.busy && !this.ended && this.combat.current.side === "party";
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
    if (this.combat.current.side === "enemies") {
      this.busy = true;
      this.time.delayedCall(450, () => void this.runMonsterTurn());
    }
  }

  private async runMonsterTurn(): Promise<void> {
    try {
      while (
        !this.combat.isOver &&
        this.combat.current.side === "enemies" &&
        this.combat.movePoints > 0
      ) {
        const intent = this.combat.decideMonsterIntent();
        if (intent.kind === "wait") break;
        if (intent.kind === "attack") {
          const result = this.combat.attack(intent.targetId);
          this.combat.movePoints = 0;
          const target = this.combat.byId(result.targetId);
          await this.animateBump(this.combat.current, this.combat.current.position, target.position);
          await this.animateHit(target, result);
          this.refreshHp(target);
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
        onComplete: () => resolve(),
      });
    });
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
        onComplete: () => resolve(),
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
  }

  private refreshTurnHeader(): void {
    const c = this.combat.current;
    this.turnText.setText(`-- ${c.name.toUpperCase()}'S TURN --`);
    this.movePointsText.setText(
      `Moves: ${this.combat.movePoints}/${c.baseMoveRange}`
    );
  }

  private refreshActionMenu(): void {
    const playerTurn = this.combat.current.side === "party";
    for (let i = 0; i < PARTY_ACTIONS.length; i++) {
      const a = PARTY_ACTIONS[i];
      const text = this.actionTexts[i];
      const handle = this.actionRowHandles[i];
      const cursor = playerTurn && i === this.actionCursor;
      const color = !playerTurn || !a.enabled ? C.faint
                  : cursor ? C.body : C.dim;
      text.setStyle(FONT_BODY(color));
      const prefix = cursor ? "> " : "  ";
      text.setText(`${prefix}${a.label}${a.enabled ? "" : "  (coming soon)"}`);
      handle.setFillStyle(C.selectBg, cursor ? 1 : 0);
      // Cursor accent bar on the left edge
      if (cursor) {
        handle.setStrokeStyle(0);
      }
    }
  }

  private refreshHp(c: Combatant): void {
    if (c.side === "party") {
      const card = this.partyCards.get(c.id);
      if (card) {
        const pct = Math.max(0, c.hp / Math.max(1, c.maxHp));
        const fullW = (HUD_W - 24) - (44 + 16) - 12 - 2;
        card.hpBar.width = Math.max(0, fullW * pct);
        card.hpBar.setFillStyle(pct <= 0.3 ? C.hpLow : C.hpFull, 1);
        card.hpText.setText(`${c.hp}/${c.maxHp}`);
      }
    }
    if (c.hp <= 0) {
      const body = this.bodies.get(c.id);
      if (body instanceof Phaser.GameObjects.Image) body.setTint(0x444466).setAlpha(0.4);
      else if (body) body.setFillStyle(0x2a2a3a).setStrokeStyle(1, 0x444466);
      this.selRings.get(c.id)?.setVisible(false);
    }
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
    if (winner === "party") this.showOverlay("Victory!", "#a3d9a5");
    else if (winner === "enemies") this.showOverlay("Defeat…", "#ff6b6b");
    if (this.fromWorld) {
      if (winner === "party" && this.triggerKey) {
        gameState.consumedTriggers.add(this.triggerKey);
      }
      if (winner === "enemies") {
        gameState.defeated = true;
      }
      this.time.delayedCall(1400, () => {
        this.cameras.main.fadeOut(220, 0, 0, 0);
        this.cameras.main.once("camerafadeoutcomplete", () => {
          this.scene.start("OverworldScene");
        });
      });
    }
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
