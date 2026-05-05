/**
 * Phaser bootstrap. Imported only by the client GameCanvas component.
 *
 * Keeping the config out of the React component makes it easier to
 * test the scene independently and to add scenes later (overworld,
 * town, dungeon) by appending to the `scene` array.
 */

import Phaser from "phaser";
import { CombatScene } from "./scenes/CombatScene";

export function startGame(parent: HTMLElement): Phaser.Game {
  const config: Phaser.Types.Core.GameConfig = {
    type: Phaser.AUTO,
    parent,
    width: 960,
    height: 540,
    backgroundColor: "#0f0f1a",
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
    scene: [CombatScene],
  };
  return new Phaser.Game(config);
}
