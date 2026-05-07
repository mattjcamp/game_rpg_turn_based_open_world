"use client";

import dynamic from "next/dynamic";
import Link from "next/link";

// Phaser touches `window` at import time, so the canvas component must only
// load on the client. `ssr: false` tells Next not to attempt server-render.
const GameCanvas = dynamic(() => import("@/components/GameCanvas"), {
  ssr: false,
  loading: () => (
    <div className="flex aspect-[4/3] w-full max-w-[960px] items-center justify-center text-parchment/60">
      Loading combat&hellip;
    </div>
  ),
});

export default function CombatPage() {
  return (
    <main className="mx-auto flex h-screen max-w-5xl flex-col items-center overflow-hidden px-4 py-2">
      <div className="mb-1 flex w-full shrink-0 items-center justify-between">
        <Link href="/" className="text-sm text-parchment/60 hover:text-parchment">
          &larr; Back
        </Link>
        <h1 className="font-display text-xl text-parchment">Combat Demo</h1>
        <span className="w-16" /> {/* spacer */}
      </div>
      <div className="flex min-h-0 w-full flex-1 items-center justify-center">
        <GameCanvas startScene="CombatScene" />
      </div>
      <p className="mt-1 shrink-0 text-xs text-parchment/40">
        Standalone combat demo. WASD/arrows or tap an adjacent tile to move;
        bumping an enemy attacks them.
      </p>
    </main>
  );
}
