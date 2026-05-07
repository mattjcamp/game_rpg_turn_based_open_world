"use client";

import dynamic from "next/dynamic";
import Link from "next/link";

const GameCanvas = dynamic(() => import("@/components/GameCanvas"), {
  ssr: false,
  loading: () => (
    <div className="flex aspect-[4/3] w-full max-w-[960px] items-center justify-center text-parchment/60">
      Loading the world&hellip;
    </div>
  ),
});

export default function WorldPage() {
  // h-screen + overflow-hidden prevents the page from scrolling when the
  // viewport is shorter than 720px + chrome. The canvas wrapper is
  // `flex-1` + `min-h-0` so it auto-shrinks to fill remaining space, and
  // Phaser's Scale.FIT scales the 960×720 canvas to whatever room it has.
  return (
    <main className="mx-auto flex h-screen max-w-5xl flex-col items-center overflow-hidden px-4 py-2">
      <div className="mb-1 flex w-full shrink-0 items-center justify-between">
        <Link href="/" className="text-sm text-parchment/60 hover:text-parchment">
          &larr; Back
        </Link>
        <h1 className="font-display text-xl text-parchment">Overworld</h1>
        <span className="w-16" /> {/* spacer */}
      </div>
      <div className="flex min-h-0 w-full flex-1 items-center justify-center">
        <GameCanvas startScene="OverworldScene" />
      </div>
      <p className="mt-1 max-w-[960px] shrink-0 text-center text-xs text-parchment/40">
        Walk around with WASD / arrow keys, or tap a tile next to you. Stepping
        on a glowing ✦ tile triggers an encounter — defeat the enemies to clear it.
      </p>
    </main>
  );
}
