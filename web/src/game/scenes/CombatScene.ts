/**
 * Phaser scene that renders the tactical grid combat encounter.
 *
 * All gameplay rules live in `Combat` — this file only:
 *   - Maps grid coordinates to canvas pixels
 *   - Translates keyboard / pointer input into Combat method calls
 *   - Animates the resulting state changes
 *   - Renders the side HUD (initiative, move points, roster, log)
 *
 * Input model:
 *   - Keyboard: WASD or arrow keys move the active fighter one tile.
 *   - Pointer: tapping a cardinally-adjacent tile moves there.
 *     Tapping an adjacent enemy tile bumps into them (attack).
 *   - "End Turn" button skips remaining moves.
 *   - "Flee" button exits combat.
 *
 * During animations and during monster turns input is locked.
 */

import Phaser from "phaser";
import { Combat } from "../combat/Combat";
import {
  ARENA_COLS,
  ARENA_ROWS,
  isWall,
  type Direction,
} from "../combat/Arena";
import { makeSampleParty } from "../data/fighters";
import { makeSampleEncounter } from "../data/monsters";
import type { Combatant, AttackResult } from "../types";

const TILE = 22;
const ARENA_X = 20;
const ARENA_Y = 20;
const ARENA_W = ARENA_COLS * TILE; // 396
const ARENA_H = ARENA_ROWS * TILE; // 462

const HUD_X = ARENA_X + ARENA_W + 24; // 440
const HUD_W = 960 - HUD_X - 20; // 500

const COLOR_FLOOR = 0x1f1f33;
const COLOR_FLOOR_ALT = 0x232340;
const COLOR_WALL = 0x111122;
const COLOR_GRID_LINE = 0x2a2a3a;
const COLOR_HIGHLIGHT = 0xc8553d;
const COLOR_MOVE_HINT = 0x44648a;

export class CombatScene extends Phaser.Scene {
  private combat!: Combat;

  // Sprite handles keyed by combatant id.
  private bodies = new Map<string, Phaser.GameObjects.Rectangle>();
  private nameTexts = new Map<string, Phaser.GameObjects.Text>();
  // HUD widgets per combatant
  private rosterHpBars = new Map<string, Phaser.GameObjects.Rectangle>();
  private rosterHpTexts = new Map<string, Phaser.GameObjects.Text>();

  private turnText!: Phaser.GameObjects.Text;
  private movePointsText!: Phaser.GameObjects.Text;
  private logText!: Phaser.GameObjects.Text;
  private overlayText?: Phaser.GameObjects.Text;
  private moveHintRects: Phaser.GameObjects.Rectangle[] = [];

  /** True while we're animating something — input locked. */
  private busy = false;
  private ended = false;

  constructor() {
    super({ key: "CombatScene" });
  }

  create(): void {
    this.combat = new Combat(makeSampleParty(), makeSampleEncounter());
    this.cameras.main.setBackgroundColor("#0f0f1a");

    this.drawArenaGrid();
    this.drawHud();
    this.drawCombatants();
    this.installKeyboard();

    this.refreshTurn();
  }

  // ── Coordinate helpers ───────────────────────────────────────────

  private tileX(col: number): number {
    return ARENA_X + col * TILE + TILE / 2;
  }
  private tileY(row: number): number {
    return ARENA_Y + row * TILE + TILE / 2;
  }

  // ── Static rendering ─────────────────────────────────────────────

  private drawArenaGrid(): void {
    // Border
    this.add
      .rectangle(ARENA_X, ARENA_Y, ARENA_W, ARENA_H, 0x000000, 0)
      .setOrigin(0)
      .setStrokeStyle(2, COLOR_GRID_LINE);

    // Tiles
    for (let row = 0; row < ARENA_ROWS; row++) {
      for (let col = 0; col < ARENA_COLS; col++) {
        const x = ARENA_X + col * TILE;
        const y = ARENA_Y + row * TILE;
        const wall = isWall(col, row);
        const fill = wall
          ? COLOR_WALL
          : (col + row) % 2 === 0
            ? COLOR_FLOOR
            : COLOR_FLOOR_ALT;
        const tile = this.add
          .rectangle(x, y, TILE, TILE, fill)
          .setOrigin(0)
          .setStrokeStyle(1, COLOR_GRID_LINE);
        if (!wall) {
          tile.setInteractive({ useHandCursor: false });
          tile.on("pointerdown", () => this.onTileClicked(col, row));
        }
      }
    }
  }

  private drawHud(): void {
    this.add
      .rectangle(HUD_X, 20, HUD_W, ARENA_H, 0x161629)
      .setOrigin(0)
      .setStrokeStyle(1, COLOR_GRID_LINE);

    this.turnText = this.add.text(HUD_X + 16, 32, "", {
      fontFamily: "Georgia, serif",
      fontSize: "20px",
      color: "#f6efd6",
    });

    this.movePointsText = this.add.text(HUD_X + 16, 64, "", {
      fontFamily: "monospace",
      fontSize: "14px",
      color: "#bdb38a",
    });

    // Action buttons
    this.makeButton(HUD_X + 16, 96, "End Turn", () => this.onEndTurnClicked());
    this.makeButton(HUD_X + 130, 96, "Flee", () => this.onFleeClicked());

    // Roster header
    this.add.text(HUD_X + 16, 144, "Party", {
      fontFamily: "Georgia, serif",
      fontSize: "16px",
      color: "#a3d9a5",
    });
    this.add.text(HUD_X + 16, 280, "Enemies", {
      fontFamily: "Georgia, serif",
      fontSize: "16px",
      color: "#ff8585",
    });

    this.drawRoster("party", 168);
    this.drawRoster("enemies", 304);

    // Log
    this.logText = this.add.text(HUD_X + 16, ARENA_H - 80, "", {
      fontFamily: "monospace",
      fontSize: "12px",
      color: "#bdb38a",
      wordWrap: { width: HUD_W - 32 },
    });
  }

  private drawRoster(side: "party" | "enemies", startY: number): void {
    const list = this.combat.combatants.filter((c) => c.side === side);
    list.forEach((c, i) => {
      const y = startY + i * 28;
      this.add.text(HUD_X + 24, y, c.name, {
        fontFamily: "Georgia, serif",
        fontSize: "14px",
        color: "#f6efd6",
      });
      // HP bar
      this.add
        .rectangle(HUD_X + 130, y + 4, 100, 10, 0x2a2a3a)
        .setOrigin(0);
      const bar = this.add
        .rectangle(HUD_X + 130, y + 4, 100, 10, 0xc8553d)
        .setOrigin(0);
      this.rosterHpBars.set(c.id, bar);
      const txt = this.add.text(HUD_X + 240, y, "", {
        fontFamily: "monospace",
        fontSize: "12px",
        color: "#bdb38a",
      });
      this.rosterHpTexts.set(c.id, txt);
    });
  }

  private makeButton(x: number, y: number, label: string, onClick: () => void): void {
    const t = this.add.text(x, y, label, {
      fontFamily: "Georgia, serif",
      fontSize: "16px",
      color: "#f6efd6",
      backgroundColor: "#1a1a2e",
      padding: { x: 10, y: 6 },
    });
    t.setInteractive({ useHandCursor: true });
    t.on("pointerdown", onClick);
  }

  private drawCombatants(): void {
    for (const c of this.combat.combatants) {
      const colorHex = Phaser.Display.Color.GetColor(...c.color);
      const body = this.add
        .rectangle(this.tileX(c.position.col), this.tileY(c.position.row),
          TILE - 4, TILE - 4, colorHex)
        .setStrokeStyle(2, 0x0a0a14);
      this.bodies.set(c.id, body);

      // Single-letter sigil so combatants are recognizable on the grid.
      const sigil = c.name.slice(0, 1).toUpperCase();
      const text = this.add.text(body.x, body.y, sigil, {
        fontFamily: "Georgia, serif",
        fontSize: "14px",
        color: "#1a1a2e",
        fontStyle: "bold",
      }).setOrigin(0.5);
      this.nameTexts.set(c.id, text);
    }
  }

  // ── Input ────────────────────────────────────────────────────────

  private installKeyboard(): void {
    const k = this.input.keyboard;
    if (!k) return;
    const map: Record<string, Direction> = {
      W: "n", A: "w", S: "s", D: "e",
      UP: "n", DOWN: "s", LEFT: "w", RIGHT: "e",
    };
    Object.entries(map).forEach(([key, dir]) => {
      k.on(`keydown-${key}`, () => this.tryPlayerStep(dir));
    });
    k.on("keydown-SPACE", () => this.onEndTurnClicked());
  }

  private onTileClicked(col: number, row: number): void {
    if (!this.canTakePlayerInput()) return;
    const actor = this.combat.current;
    const dc = col - actor.position.col;
    const dr = row - actor.position.row;
    // Only respond to cardinally-adjacent clicks.
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
        // Blocked — small shake feedback so the input feels acknowledged.
        await this.animateBlocked(actor, dir);
      }
      this.refreshLog();
      this.refreshHud();

      if (this.combat.isOver) return this.endEncounter();
      if (this.combat.movePoints <= 0) this.endActorTurn();
    } finally {
      this.busy = false;
    }
  }

  private endActorTurn(): void {
    this.clearMoveHints();
    this.combat.endTurn();
    this.refreshTurn();
  }

  private refreshTurn(): void {
    if (this.combat.isOver) return this.endEncounter();
    this.refreshHud();
    this.highlightActiveActor();
    this.drawMoveHints();

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
          this.combat.movePoints = 0; // an attack ends the turn
          const target = this.combat.byId(result.targetId);
          await this.animateBump(
            this.combat.current,
            this.combat.current.position,
            target.position
          );
          await this.animateHit(target, result);
          this.refreshHp(target);
          this.refreshLog();
          break;
        }
        // Move intent
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
          break; // blocked — bail
        }
        this.refreshLog();
      }
    } finally {
      this.busy = false;
    }
    if (this.combat.isOver) return this.endEncounter();
    this.endActorTurn();
  }

  // ── Animations ───────────────────────────────────────────────────

  private animateMove(
    actor: Combatant,
    from: { col: number; row: number },
    to: { col: number; row: number }
  ): Promise<void> {
    void from; // current sprite is at `from`; tween targets `to`.
    return new Promise((resolve) => {
      const body = this.bodies.get(actor.id)!;
      const text = this.nameTexts.get(actor.id)!;
      const x = this.tileX(to.col);
      const y = this.tileY(to.row);
      this.tweens.add({
        targets: [body, text],
        x,
        y,
        duration: 120,
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
      const text = this.nameTexts.get(actor.id)!;
      const startX = this.tileX(from.col);
      const startY = this.tileY(from.row);
      const targetX = this.tileX(target.col);
      const targetY = this.tileY(target.row);
      // Lurch ~40% of the way toward the target then snap back.
      const midX = startX + (targetX - startX) * 0.4;
      const midY = startY + (targetY - startY) * 0.4;
      this.tweens.add({
        targets: [body, text],
        x: midX,
        y: midY,
        duration: 90,
        yoyo: true,
        onComplete: () => resolve(),
      });
    });
  }

  private animateBlocked(actor: Combatant, dir: Direction): Promise<void> {
    return new Promise((resolve) => {
      const body = this.bodies.get(actor.id)!;
      const text = this.nameTexts.get(actor.id)!;
      const dx = dir === "e" ? 4 : dir === "w" ? -4 : 0;
      const dy = dir === "s" ? 4 : dir === "n" ? -4 : 0;
      this.tweens.add({
        targets: [body, text],
        x: body.x + dx,
        y: body.y + dy,
        duration: 50,
        yoyo: true,
        onComplete: () => resolve(),
      });
    });
  }

  private animateHit(target: Combatant, result: AttackResult): Promise<void> {
    return new Promise((resolve) => {
      const body = this.bodies.get(target.id);
      if (!body) return resolve();
      const label = result.hit
        ? result.critical
          ? `CRIT! -${result.damage}`
          : `-${result.damage}`
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
        y: t.y - 22,
        alpha: 0,
        duration: 600,
        onComplete: () => {
          t.destroy();
          resolve();
        },
      });
      if (result.hit) {
        this.tweens.add({
          targets: body,
          alpha: 0.3,
          duration: 80,
          yoyo: true,
          repeat: 1,
        });
      }
    });
  }

  // ── HUD refresh ──────────────────────────────────────────────────

  private refreshHud(): void {
    const c = this.combat.current;
    this.turnText.setText(`Turn — ${c.name}`);
    this.movePointsText.setText(
      `Moves: ${this.combat.movePoints}/${c.baseMoveRange}`
    );
    for (const x of this.combat.combatants) this.refreshHp(x);
    this.refreshLog();
  }

  private refreshHp(c: Combatant): void {
    const bar = this.rosterHpBars.get(c.id);
    const txt = this.rosterHpTexts.get(c.id);
    if (bar) bar.width = 100 * Math.max(0, c.hp / c.maxHp);
    if (txt) txt.setText(`${c.hp}/${c.maxHp}`);
    if (c.hp <= 0) {
      const body = this.bodies.get(c.id);
      const t = this.nameTexts.get(c.id);
      if (body) body.setFillStyle(0x2a2a3a).setStrokeStyle(1, 0x444466);
      if (t) t.setColor("#666688");
    }
  }

  private refreshLog(): void {
    this.logText.setText(this.combat.log.slice(-5).join("\n"));
  }

  private highlightActiveActor(): void {
    for (const c of this.combat.combatants) {
      const body = this.bodies.get(c.id);
      if (!body || c.hp <= 0) continue;
      const isActive = c.id === this.combat.current.id;
      body.setStrokeStyle(isActive ? 3 : 2, isActive ? COLOR_HIGHLIGHT : 0x0a0a14);
    }
  }

  private drawMoveHints(): void {
    this.clearMoveHints();
    if (this.combat.current.side !== "party") return;
    const actor = this.combat.current;
    const dirs: [number, number][] = [
      [-1, 0], [1, 0], [0, -1], [0, 1],
    ];
    for (const [dc, dr] of dirs) {
      const nc = actor.position.col + dc;
      const nr = actor.position.row + dr;
      if (isWall(nc, nr)) continue;
      const occupant = this.combat.combatantAt(nc, nr);
      if (occupant && occupant.side === actor.side) continue;
      const x = this.tileX(nc);
      const y = this.tileY(nr);
      const hint = this.add
        .rectangle(x, y, TILE - 6, TILE - 6, COLOR_MOVE_HINT, 0.35)
        .setStrokeStyle(1, COLOR_MOVE_HINT);
      this.moveHintRects.push(hint);
    }
  }

  private clearMoveHints(): void {
    for (const r of this.moveHintRects) r.destroy();
    this.moveHintRects.length = 0;
  }

  // ── End state ────────────────────────────────────────────────────

  private endEncounter(): void {
    if (this.ended) return;
    this.ended = true;
    this.clearMoveHints();
    if (this.combat.winner === "party") {
      this.showOverlay("Victory!", "#a3d9a5");
    } else if (this.combat.winner === "enemies") {
      this.showOverlay("Defeat…", "#ff6b6b");
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
