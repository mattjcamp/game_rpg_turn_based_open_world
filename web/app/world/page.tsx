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
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col items-center px-4 py-8">
      <div className="mb-4 flex w-full items-center justify-between">
        <Link href="/" className="text-sm text-parchment/60 hover:text-parchment">
          &larr; Back
        </Link>
        <h1 className="font-display text-2xl text-parchment">Overworld</h1>
        <span className="w-16" /> {/* spacer */}
      </div>
      <GameCanvas startScene="OverworldScene" />
      <p className="mt-4 max-w-[960px] text-center text-xs text-parchment/40">
        Walk around with WASD / arrow keys, or tap a tile next to you. Stepping
        on a glowing ✦ tile triggers an encounter — defeat the enemies to clear it.
      </p>
    </main>
  );
}
