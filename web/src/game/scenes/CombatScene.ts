/**
 * Phaser scene that renders a single turn-based combat encounter.
 *
 * All gameplay decisions live in `Combat` — this file only translates
 * Combat state into rectangles, text, and click handlers. If you find
 * yourself reaching for combat math here, push it down into the
 * controller instead.
 *
 * Layout:
 *   ┌────────────────────────────────────────────────────┐
 *   │ Initiative bar (current actor highlighted)         │
 *   ├──────────────────────┬─────────────────────────────┤
 *   │   Party portraits    │     Enemy portraits         │
 *   │   (HP bars)          │     (HP bars, clickable     │
 *   │                      │      when targeting)        │
 *   ├──────────────────────┴─────────────────────────────┤
 *   │ Action menu (Attack / Defend / Flee)               │
 *   ├────────────────────────────────────────────────────┤
 *   │ Combat log (last 4 lines)                          │
 *   └────────────────────────────────────────────────────┘
 */

import Phaser from "phaser";
import { Combat } from "../combat/Combat";
import { makeSampleParty } from "../data/fighters";
import { makeSampleEncounter } from "../data/monsters";
import type { Combatant } from "../types";

const W = 960;
const H = 540;

type Phase = "choose-action" | "choose-target" | "resolving" | "ended";

export class CombatScene extends Phaser.Scene {
  private combat!: Combat;
  private phase: Phase = "choose-action";

  // UI handles we redraw on each state change
  private portraitGroup!: Phaser.GameObjects.Group;
  private hpTexts = new Map<string, Phaser.GameObjects.Text>();
  private hpBars = new Map<string, Phaser.GameObjects.Rectangle>();
  private portraitRects = new Map<string, Phaser.GameObjects.Rectangle>();
  private initiativeText!: Phaser.GameObjects.Text;
  private actionTexts: Phaser.GameObjects.Text[] = [];
  private logText!: Phaser.GameObjects.Text;
  private overlayText?: Phaser.GameObjects.Text;

  constructor() {
    super({ key: "CombatScene" });
  }

  create(): void {
    this.combat = new Combat(makeSampleParty(), makeSampleEncounter());
    this.cameras.main.setBackgroundColor("#0f0f1a");

    this.portraitGroup = this.add.group();
    this.drawArena();
    this.drawInitiativeBar();
    this.drawActionMenu();
    this.drawLog();

    this.refreshTurn();
  }

  // ── Rendering ────────────────────────────────────────────────────

  private drawArena(): void {
    const party = this.combat.combatants.filter((c) => c.side === "party");
    const enemies = this.combat.combatants.filter((c) => c.side === "enemies");
    party.forEach((c, i) => this.drawPortrait(c, 60, 80 + i * 90, "left"));
    enemies.forEach((c, i) => this.drawPortrait(c, W - 60 - 160, 100 + i * 110, "right"));
  }

  private drawPortrait(c: Combatant, x: number, y: number, _facing: "left" | "right"): void {
    const colorHex = Phaser.Display.Color.GetColor(...c.color);
    const rect = this.add.rectangle(x, y, 160, 70, colorHex)
      .setOrigin(0, 0)
      .setStrokeStyle(2, 0x2a2a3a);
    this.portraitRects.set(c.id, rect);
    this.portraitGroup.add(rect);

    this.add.text(x + 8, y + 6, c.name, {
      fontFamily: "Georgia, serif",
      fontSize: "16px",
      color: "#1a1a2e",
    });

    // HP bar background
    const barY = y + 50;
    this.add.rectangle(x + 8, barY, 144, 8, 0x2a2a3a).setOrigin(0, 0);
    const bar = this.add
      .rectangle(x + 8, barY, 144, 8, 0xc8553d)
      .setOrigin(0, 0);
    this.hpBars.set(c.id, bar);

    const hp = this.add.text(x + 8, y + 28, "", {
      fontFamily: "monospace",
      fontSize: "14px",
      color: "#1a1a2e",
    });
    this.hpTexts.set(c.id, hp);

    rect.setInteractive({ useHandCursor: true });
    rect.on("pointerdown", () => this.onPortraitClicked(c));

    this.refreshHp(c);
  }

  private refreshHp(c: Combatant): void {
    const bar = this.hpBars.get(c.id);
    const text = this.hpTexts.get(c.id);
    const rect = this.portraitRects.get(c.id);
    if (!bar || !text || !rect) return;
    bar.width = 144 * Math.max(0, c.hp / c.maxHp);
    text.setText(`HP ${c.hp}/${c.maxHp}`);
    if (c.hp <= 0) {
      rect.setFillStyle(0x2a2a3a);
      rect.disableInteractive();
    }
  }

  private drawInitiativeBar(): void {
    this.initiativeText = this.add.text(W / 2, 24, "", {
      fontFamily: "Georgia, serif",
      fontSize: "18px",
      color: "#f6efd6",
    }).setOrigin(0.5, 0.5);
  }

  private drawActionMenu(): void {
    const labels = ["Attack", "Defend", "Flee"];
    labels.forEach((label, i) => {
      const t = this.add.text(40 + i * 140, H - 90, label, {
        fontFamily: "Georgia, serif",
        fontSize: "20px",
        color: "#f6efd6",
        backgroundColor: "#1a1a2e",
        padding: { x: 16, y: 10 },
      });
      t.setInteractive({ useHandCursor: true });
      t.on("pointerdown", () => this.onActionClicked(label));
      this.actionTexts.push(t);
    });
  }

  private drawLog(): void {
    this.logText = this.add.text(40, H - 40, "", {
      fontFamily: "monospace",
      fontSize: "13px",
      color: "#bdb38a",
      wordWrap: { width: W - 80 },
    });
  }

  private refreshLog(): void {
    const last4 = this.combat.log.slice(-4);
    this.logText.setText(last4.join("  ·  "));
  }

  // ── Turn flow ────────────────────────────────────────────────────

  private refreshTurn(): void {
    if (this.combat.isOver) return this.endEncounter();

    const c = this.combat.current;
    const totals = this.combat.initiativeOrder
      .map((r) => `${this.combat.byId(r.combatantId).name}:${r.total}`)
      .join("  ");
    this.initiativeText.setText(`Turn — ${c.name}    │    ${totals}`);

    // Highlight active portrait
    this.portraitRects.forEach((rect, id) => {
      rect.setStrokeStyle(id === c.id ? 4 : 2, id === c.id ? 0xc8553d : 0x2a2a3a);
    });

    if (c.side === "party") {
      this.phase = "choose-action";
      this.actionTexts.forEach((t) => t.setAlpha(1));
    } else {
      this.phase = "resolving";
      this.actionTexts.forEach((t) => t.setAlpha(0.4));
      // Give the player a beat to see whose turn it is, then resolve.
      this.time.delayedCall(550, () => this.resolveMonsterTurn());
    }
  }

  private onActionClicked(label: string): void {
    if (this.phase !== "choose-action") return;
    if (label === "Attack") {
      this.phase = "choose-target";
      this.initiativeText.setText("Choose a target…");
      // Outline live enemies in ember to indicate they're targetable.
      this.combat.alive("enemies").forEach((e) => {
        const r = this.portraitRects.get(e.id);
        r?.setStrokeStyle(3, 0xc8553d);
      });
    } else if (label === "Defend") {
      // Placeholder — first slice doesn't model defense yet.
      this.combat.log.push(`${this.combat.current.name} braces for impact.`);
      this.refreshLog();
      this.combat.endTurn();
      this.refreshTurn();
    } else if (label === "Flee") {
      this.combat.log.push(`${this.combat.current.name} flees the encounter.`);
      this.refreshLog();
      this.phase = "ended";
      this.showOverlay("You escaped.", "#bdb38a");
    }
  }

  private onPortraitClicked(target: Combatant): void {
    if (this.phase !== "choose-target") return;
    if (target.side !== "enemies" || target.hp <= 0) return;

    const result = this.combat.attack(target.id);
    this.flashDamage(target, result.damage, result.hit, result.critical);
    this.refreshHp(target);
    this.refreshLog();

    this.phase = "resolving";
    this.time.delayedCall(450, () => {
      this.combat.endTurn();
      this.refreshTurn();
    });
  }

  private resolveMonsterTurn(): void {
    if (this.combat.isOver) return this.endEncounter();
    const result = this.combat.takeMonsterTurn();
    if (!result) return this.endEncounter();
    const target = this.combat.byId(result.targetId);
    this.flashDamage(target, result.damage, result.hit, result.critical);
    this.refreshHp(target);
    this.refreshLog();
    this.time.delayedCall(450, () => {
      this.combat.endTurn();
      this.refreshTurn();
    });
  }

  private flashDamage(target: Combatant, dmg: number, hit: boolean, crit: boolean): void {
    const rect = this.portraitRects.get(target.id);
    if (!rect) return;
    const text = hit ? (crit ? `CRIT! -${dmg}` : `-${dmg}`) : "miss";
    const color = hit ? (crit ? "#ffd470" : "#ff6b6b") : "#bdb38a";
    const t = this.add.text(rect.x + 80, rect.y - 6, text, {
      fontFamily: "Georgia, serif",
      fontSize: "18px",
      color,
      stroke: "#1a1a2e",
      strokeThickness: 4,
    }).setOrigin(0.5, 1);
    this.tweens.add({
      targets: t,
      y: t.y - 30,
      alpha: 0,
      duration: 700,
      onComplete: () => t.destroy(),
    });
    if (hit) {
      this.tweens.add({
        targets: rect,
        x: rect.x + (target.side === "enemies" ? -8 : 8),
        duration: 60,
        yoyo: true,
        repeat: 2,
      });
    }
  }

  private endEncounter(): void {
    this.phase = "ended";
    if (this.combat.winner === "party") {
      this.showOverlay("Victory!", "#a3d9a5");
    } else if (this.combat.winner === "enemies") {
      this.showOverlay("Defeat…", "#ff6b6b");
    }
    this.actionTexts.forEach((t) => t.setAlpha(0.3));
  }

  private showOverlay(label: string, color: string): void {
    if (this.overlayText) this.overlayText.destroy();
    this.overlayText = this.add.text(W / 2, H / 2, label, {
      fontFamily: "Georgia, serif",
      fontSize: "64px",
      color,
      stroke: "#1a1a2e",
      strokeThickness: 8,
    }).setOrigin(0.5, 0.5);
  }
}
