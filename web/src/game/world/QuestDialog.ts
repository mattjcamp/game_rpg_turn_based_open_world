/**
 * Shared quest-dialog UI builder.
 *
 * The Accept / Active / Turn-in overlay is identical across town and
 * overworld scenes — same layout, same prompts, same status-line
 * format. This module owns the rendering so the two scenes only have
 * to track their own keyboard dispatch + reward delivery.
 *
 * Returns a `QuestDialogHandles` object the scene stores; calling
 * `closeQuestDialog(handles)` destroys every Phaser object.
 */

import Phaser from "phaser";
import type { QuestDef, QuestState } from "./Quests";
import { locationHint, findQuest } from "./Quests";

export type QuestDialogMode = "available" | "active" | "completed";

export interface QuestDialogHandles {
  objects: Phaser.GameObjects.GameObject[];
  questName: string;
  mode: QuestDialogMode;
}

interface OpenOptions {
  /** Display name shown before the em-dash in the title. */
  npcName: string;
  /** Quest name — also stored on the handles for the close path. */
  questName: string;
  /** Loaded quest defs — looked up by name. */
  defs: QuestDef[];
  /** Per-quest state map; the dialog branches on `state.status`. */
  state: QuestState;
  /** Top-level depth — town uses 50, overworld uses 50 too. */
  depth?: number;
}

/**
 * Build and render the quest dialog. Returns null when the quest is
 * already turned in or definition / state are missing — caller treats
 * that as a no-op.
 */
export function openQuestDialog(
  scene: Phaser.Scene,
  opts: OpenOptions,
): QuestDialogHandles | null {
  const def = findQuest(opts.defs, opts.questName);
  if (!def) return null;
  const state = opts.state;
  if (state.status === "turned_in") return null;

  const W = 720;
  const H = 380;
  const X = (960 - W) / 2;
  const Y = (720 - H) / 2;
  const depth = opts.depth ?? 50;
  const objects: Phaser.GameObjects.GameObject[] = [];

  objects.push(
    scene.add
      .rectangle(X, Y, W, H, 0x161629, 0.97)
      .setOrigin(0)
      .setStrokeStyle(2, 0xc8553d)
      .setScrollFactor(0)
      .setDepth(depth),
  );
  objects.push(
    scene.add
      .text(X + 16, Y + 12, `${opts.npcName} — ${def.name}`, {
        fontFamily: "Georgia, serif",
        fontSize: "18px",
        color: "#ffd470",
      })
      .setScrollFactor(0)
      .setDepth(depth + 1),
  );

  let body: string;
  let prompt: string;
  let mode: QuestDialogMode;
  if (state.status === "available") {
    mode = "available";
    const hint = locationHint(def);
    body = def.giverDialogue + (hint ? `\n\n${hint}` : "");
    body += `\n\nReward: ${formatReward(def)}`;
    prompt = "[Y] Accept    [N] Decline";
  } else if (state.status === "active") {
    mode = "active";
    body = activeQuestStatusBody(def, state.stepProgress, state.stepKills);
    prompt = "[ESC] Close";
  } else {
    mode = "completed";
    body = `Thank you, friend. You have done what was asked.\n\nReward: ${formatReward(def)}`;
    prompt = "[Y] Claim reward    [N] Not yet";
  }

  objects.push(
    scene.add
      .text(X + 16, Y + 44, body, {
        fontFamily: "Georgia, serif",
        fontSize: "15px",
        color: "#f6efd6",
        wordWrap: { width: W - 32 },
      })
      .setScrollFactor(0)
      .setDepth(depth + 1),
  );
  objects.push(
    scene.add
      .text(X + W - 16, Y + H - 24, prompt, {
        fontFamily: "monospace",
        fontSize: "13px",
        color: "#bdb38a",
      })
      .setOrigin(1, 0)
      .setScrollFactor(0)
      .setDepth(depth + 1),
  );

  return { objects, questName: opts.questName, mode };
}

export function closeQuestDialog(handles: QuestDialogHandles | undefined): void {
  if (!handles) return;
  for (const obj of handles.objects) obj.destroy();
}

/** Reward-line formatter shared with the dialog and the quest log. */
export function formatReward(def: QuestDef): string {
  const parts: string[] = [];
  if (def.rewardXp > 0) parts.push(`${def.rewardXp} XP`);
  if (def.rewardGold > 0) parts.push(`${def.rewardGold} gold`);
  if (def.rewardItems.length > 0) parts.push(def.rewardItems.join(", "));
  return parts.length > 0 ? parts.join(", ") : "the realm's gratitude";
}

/** Multi-line "active quest" status block: description + each step
 *  with a check or dash, plus an in-progress fraction for kill steps
 *  whose target_count > 1. Mirrors the player's expectation of seeing
 *  what's left when they re-talk to the giver mid-quest. */
export function activeQuestStatusBody(
  def: QuestDef,
  progress: boolean[],
  stepKills: Record<number, number>,
): string {
  const lines: string[] = [def.description, ""];
  for (let i = 0; i < def.steps.length; i++) {
    const step = def.steps[i];
    const done = progress[i];
    const mark = done ? "✓" : "·";
    let suffix = "";
    if (!done && step.stepType === "kill" && step.targetCount > 1) {
      const k = stepKills[i] ?? 0;
      suffix = ` (${k}/${step.targetCount})`;
    }
    lines.push(`  ${mark} ${step.description}${suffix}`);
  }
  return lines.join("\n");
}

/**
 * Center-screen "STEP COMPLETE" / "QUEST COMPLETE" callout that fades
 * in, holds, then fades out. Mirrors the Python game's quest-step
 * banner — emerald border on step completion, gold on full-quest.
 *
 * Auto-dismisses after ~3 s; clicking / tapping anywhere skips the
 * hold so impatient players can move on. Multiple callouts queue
 * via stacking (the new one fades in over the old one).
 */
export function showStepCompleteCallout(
  scene: Phaser.Scene,
  opts: { questName: string; description: string; questComplete?: boolean },
): void {
  const W = 520;
  const H = 88;
  const X = (960 - W) / 2;
  const Y = 96;
  const isComplete = !!opts.questComplete;
  const borderColor = isComplete ? 0xffd470 : 0x5adc82;
  const titleColor  = isComplete ? "#ffe48a" : "#90f0aa";
  const titleText   = isComplete ? "QUEST COMPLETE!" : "STEP COMPLETE";

  const bg = scene.add
    .rectangle(X, Y, W, H, 0x0a1e12, 0.85)
    .setOrigin(0)
    .setStrokeStyle(3, borderColor)
    .setScrollFactor(0)
    .setDepth(75);
  const title = scene.add
    .text(X + W / 2, Y + 14, titleText, {
      fontFamily: "Georgia, serif",
      fontSize: "20px",
      color: titleColor,
      fontStyle: "bold",
    })
    .setOrigin(0.5, 0)
    .setScrollFactor(0)
    .setDepth(76);
  const info = `${opts.questName} — ${opts.description}`;
  const infoText = scene.add
    .text(X + W / 2, Y + 48, info, {
      fontFamily: "Georgia, serif",
      fontSize: "14px",
      color: "#dcf5e1",
      wordWrap: { width: W - 28 },
      align: "center",
    })
    .setOrigin(0.5, 0)
    .setScrollFactor(0)
    .setDepth(76);

  // Pulse the border between the base color and a brighter variant
  // so the callout reads as celebratory rather than static.
  const pulseTween = scene.tweens.addCounter({
    from: 0,
    to: 1,
    duration: 600,
    yoyo: true,
    repeat: -1,
    onUpdate: (t) => {
      const v = t.getValue();
      const lit = Phaser.Display.Color.Interpolate.ColorWithColor(
        Phaser.Display.Color.IntegerToColor(borderColor),
        Phaser.Display.Color.IntegerToColor(0xffffff),
        100,
        Math.floor(v * 30),
      );
      bg.setStrokeStyle(3, Phaser.Display.Color.GetColor(lit.r, lit.g, lit.b));
    },
  });

  const destroy = (): void => {
    pulseTween.stop();
    bg.destroy();
    title.destroy();
    infoText.destroy();
  };
  // Hold ~2.6 s, then fade.
  scene.tweens.add({
    targets: [bg, title, infoText],
    alpha: 0,
    delay: 2200,
    duration: 600,
    onComplete: destroy,
  });
}

/** Build a brief on-screen banner — used by quest turn-in flashes
 *  and step-completion callouts. Auto-destroys after `durationMs`. */
export function flashQuestMessage(scene: Phaser.Scene, text: string, durationMs = 2400): void {
  const bg = scene.add
    .rectangle(480, 120, 0, 36, 0x161629, 0.92)
    .setStrokeStyle(2, 0xc8553d)
    .setScrollFactor(0)
    .setDepth(60);
  const t = scene.add
    .text(480, 120, text, {
      fontFamily: "Georgia, serif",
      fontSize: "16px",
      color: "#ffd470",
      padding: { x: 16, y: 6 },
    })
    .setOrigin(0.5)
    .setScrollFactor(0)
    .setDepth(61);
  bg.width = t.width + 24;
  scene.time.delayedCall(durationMs, () => { bg.destroy(); t.destroy(); });
}

/** Read-only quest log overlay. Lists every known quest grouped by
 *  status (active, completed, available). Mirrors what the Python
 *  game's quest log shows on the J / Q hotkey. Dismissed with any
 *  key. Returns the destroy function so the caller can chain it
 *  to a custom close handler if needed. */
export function openQuestLog(
  scene: Phaser.Scene,
  defs: QuestDef[],
  states: Map<string, QuestState>,
): () => void {
  const W = 720;
  const H = 540;
  const X = (960 - W) / 2;
  const Y = (720 - H) / 2;
  const objects: Phaser.GameObjects.GameObject[] = [];
  objects.push(
    scene.add
      .rectangle(X, Y, W, H, 0x161629, 0.97)
      .setOrigin(0)
      .setStrokeStyle(2, 0xc8553d)
      .setScrollFactor(0)
      .setDepth(70),
  );
  objects.push(
    scene.add
      .text(X + 16, Y + 12, "Quest Log", {
        fontFamily: "Georgia, serif",
        fontSize: "22px",
        color: "#ffd470",
      })
      .setScrollFactor(0)
      .setDepth(71),
  );
  // Group quests by status. Order: active → completed → available →
  // turned_in (the last lives at the bottom as historical record).
  const groups: Array<{ label: string; status: QuestState["status"] }> = [
    { label: "Active",     status: "active" },
    { label: "Completed (turn in for reward)", status: "completed" },
    { label: "Available",  status: "available" },
    { label: "Finished",   status: "turned_in" },
  ];
  let cursorY = Y + 48;
  for (const group of groups) {
    const inGroup = defs.filter((d) => states.get(d.name)?.status === group.status);
    if (inGroup.length === 0) continue;
    objects.push(
      scene.add
        .text(X + 16, cursorY, group.label, {
          fontFamily: "Georgia, serif",
          fontSize: "16px",
          color: "#c8553d",
        })
        .setScrollFactor(0)
        .setDepth(71),
    );
    cursorY += 22;
    for (const def of inGroup) {
      const state = states.get(def.name)!;
      const lines: string[] = [`  ${def.name}`];
      if (group.status === "active") {
        for (let i = 0; i < def.steps.length; i++) {
          const step = def.steps[i];
          const done = state.stepProgress[i];
          const mark = done ? "✓" : "·";
          let suffix = "";
          if (!done && step.stepType === "kill" && step.targetCount > 1) {
            const k = state.stepKills[i] ?? 0;
            suffix = ` (${k}/${step.targetCount})`;
          }
          lines.push(`     ${mark} ${step.description}${suffix}`);
        }
      } else if (group.status === "completed") {
        lines.push(`     Reward: ${formatReward(def)}`);
      }
      const block = scene.add
        .text(X + 16, cursorY, lines.join("\n"), {
          fontFamily: "Georgia, serif",
          fontSize: "14px",
          color: "#f6efd6",
          wordWrap: { width: W - 32 },
        })
        .setScrollFactor(0)
        .setDepth(71);
      cursorY += block.height + 6;
      objects.push(block);
      if (cursorY > Y + H - 60) break;
    }
    cursorY += 6;
    if (cursorY > Y + H - 60) break;
  }
  objects.push(
    scene.add
      .text(X + W - 16, Y + H - 24, "[Q] [ESC] close", {
        fontFamily: "monospace",
        fontSize: "13px",
        color: "#bdb38a",
      })
      .setOrigin(1, 0)
      .setScrollFactor(0)
      .setDepth(71),
  );
  return () => { for (const obj of objects) obj.destroy(); };
}

/** Full-screen victory modal — shown when the final quest turns in.
 *  Dismissed with any key. */
export function openVictoryModal(scene: Phaser.Scene, text: string): void {
  const bg = scene.add
    .rectangle(0, 0, 960, 720, 0x000000, 0.92)
    .setOrigin(0)
    .setScrollFactor(0)
    .setDepth(80);
  const title = scene.add
    .text(480, 220, "Victory!", {
      fontFamily: "Georgia, serif",
      fontSize: "48px",
      color: "#ffd470",
    })
    .setOrigin(0.5)
    .setScrollFactor(0)
    .setDepth(81);
  const body = scene.add
    .text(480, 320, text, {
      fontFamily: "Georgia, serif",
      fontSize: "18px",
      color: "#f6efd6",
      wordWrap: { width: 720 },
      align: "center",
    })
    .setOrigin(0.5, 0)
    .setScrollFactor(0)
    .setDepth(81);
  const hint = scene.add
    .text(480, 660, "Press any key to continue", {
      fontFamily: "monospace",
      fontSize: "13px",
      color: "#bdb38a",
    })
    .setOrigin(0.5)
    .setScrollFactor(0)
    .setDepth(81);
  const close = (): void => {
    bg.destroy(); title.destroy(); body.destroy(); hint.destroy();
    scene.input.keyboard?.off("keydown", close);
  };
  scene.input.keyboard?.once("keydown", close);
}
