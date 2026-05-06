/**
 * Phaser bootstrap.
 *
 * Both scenes are always registered so cross-scene transitions work
 * (overworld → combat → overworld). The page chooses which scene boots
 * first; the array is reordered so Phaser's default auto-start picks
 * up the right one.
 */

import Phaser from "phaser";
import { CombatScene } from "./scenes/CombatScene";
import { OverworldScene } from "./scenes/OverworldScene";
import { TownScene } from "./scenes/TownScene";

export type StartScene = "OverworldScene" | "CombatScene";

export function startGame(parent: HTMLElement, startScene: StartScene = "OverworldScene"): Phaser.Game {
  // Phaser auto-starts the first scene in the array. Reorder so the
  // requested starting scene is first; all scenes stay registered so
  // cross-scene transitions (`this.scene.start(key, data)`) work.
  const sceneOrder = startScene === "CombatScene"
    ? [CombatScene, OverworldScene, TownScene]
    : [OverworldScene, CombatScene, TownScene];
  const config: Phaser.Types.Core.GameConfig = {
    type: Phaser.AUTO,
    parent,
    // 4:3 (960×720) — chosen so the full 18×21 combat arena fits at
    // native 32px tiles, and the overworld gets more visible vertical
    // map. Phaser.Scale.FIT scales to the parent container's size.
    width: 960,
    height: 720,
    backgroundColor: "#0f0f1a",
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
    scene: sceneOrder,
  };
  return new Phaser.Game(config);
}
