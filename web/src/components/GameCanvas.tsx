"use client";

/**
 * Mounts the Phaser game into a div on the client side. Phaser touches
 * `window` at import time, so this component must never be SSR'd —
 * the parent page imports it via `next/dynamic({ ssr: false })`.
 */

import { useEffect, useRef } from "react";
import type Phaser from "phaser";

export default function GameCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<Phaser.Game | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!containerRef.current) return;

    // Dynamic import keeps Phaser out of the server bundle entirely.
    import("@/game/PhaserGame").then(({ startGame }) => {
      if (cancelled || !containerRef.current) return;
      gameRef.current = startGame(containerRef.current);
    });

    return () => {
      cancelled = true;
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, []);

  return (
    <div
      id="phaser-container"
      ref={containerRef}
      className="aspect-video w-full max-w-[960px] overflow-hidden rounded-md border border-parchment/20 shadow-lg"
    />
  );
}
