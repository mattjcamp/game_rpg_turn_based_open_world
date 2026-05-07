"use client";

/**
 * Mounts the Phaser game into a div on the client side. Phaser touches
 * `window` at import time, so this component must never be SSR'd —
 * the parent page imports it via `next/dynamic({ ssr: false })`.
 *
 * Props:
 *   startScene — which scene to boot first. Defaults to OverworldScene.
 */

import { useEffect, useRef } from "react";
import type Phaser from "phaser";
import type { StartScene } from "@/game/PhaserGame";

export default function GameCanvas({
  startScene = "OverworldScene",
}: {
  startScene?: StartScene;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<Phaser.Game | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!containerRef.current) return;

    import("@/game/PhaserGame").then(({ startGame }) => {
      if (cancelled || !containerRef.current) return;
      gameRef.current = startGame(containerRef.current, startScene);
    });

    return () => {
      cancelled = true;
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, [startScene]);

  // The canvas is 960×720 inside Phaser; the wrapper enforces a 4:3
  // aspect ratio plus an explicit max width AND max height, so a tall
  // wrapper still keeps the canvas at the same aspect (no letterbox
  // stretching) and a short wrapper shrinks it without overflowing.
  // Phaser.Scale.FIT inside the game does the actual canvas scaling.
  return (
    <div
      id="phaser-container"
      ref={containerRef}
      className="aspect-[4/3] max-h-full w-auto max-w-[960px] overflow-hidden rounded-md border border-parchment/20 shadow-lg"
      style={{ aspectRatio: "4 / 3" }}
    />
  );
}
