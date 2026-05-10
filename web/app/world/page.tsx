"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";

const GameCanvas = dynamic(() => import("@/components/GameCanvas"), {
  ssr: false,
  loading: () => (
    <div className="flex aspect-[4/3] w-full max-w-[960px] items-center justify-center text-parchment/60">
      Loading the world&hellip;
    </div>
  ),
});

export default function WorldPage() {
  // Hydrate the rolling save before the canvas mounts. The canvas
  // boots Phaser which boots OverworldScene, which reads
  // `gameState.lastScene` and routes the player back into the
  // dungeon / town they were last in. Done in an effect so it only
  // fires once per mount and never on the server.
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void import("@/game/save").then(({ load }) => {
      load();  // false on first run / after "Start New Game" — fine
      setReady(true);
    });
  }, []);

  // h-screen + overflow-hidden prevents the page from scrolling when the
  // viewport is shorter than 720px + chrome. The canvas wrapper is
  // `flex-1` + `min-h-0` so it auto-shrinks to fill remaining space, and
  // Phaser's Scale.FIT scales the 960×720 canvas to whatever room it has.
  //
  // The page chrome here is intentionally minimal — just a Back link
  // — because the Phaser scene now owns the only HUD surface (the
  // bottom-of-canvas log strip painted by `SceneLog`). The "Overworld"
  // title was misleading once the scene swapped between overworld /
  // town / dungeon modes; the bottom how-to-play hint duplicated
  // information players had already learned from the in-canvas log.
  return (
    <main className="mx-auto flex h-screen max-w-5xl flex-col items-center overflow-hidden px-4 py-2">
      <div className="mb-1 flex w-full shrink-0 items-center">
        <Link href="/" className="text-sm text-parchment/60 hover:text-parchment">
          &larr; Back
        </Link>
      </div>
      <div className="flex min-h-0 w-full flex-1 items-center justify-center">
        {ready ? <GameCanvas startScene="OverworldScene" /> : (
          <div className="text-parchment/60">Loading the world&hellip;</div>
        )}
      </div>
    </main>
  );
}
