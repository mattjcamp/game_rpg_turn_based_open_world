"use client";

import dynamic from "next/dynamic";
import Link from "next/link";

// Phaser touches `window` at import time, so the canvas component must only
// load on the client. `ssr: false` tells Next not to attempt server-render.
const GameCanvas = dynamic(() => import("@/components/GameCanvas"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[540px] w-[960px] max-w-full items-center justify-center text-parchment/60">
      Loading combat&hellip;
    </div>
  ),
});

export default function CombatPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col items-center px-4 py-8">
      <div className="mb-4 flex w-full items-center justify-between">
        <Link href="/" className="text-sm text-parchment/60 hover:text-parchment">
          &larr; Back
        </Link>
        <h1 className="font-display text-2xl text-parchment">Combat Demo</h1>
        <span className="w-16" /> {/* spacer */}
      </div>
      <GameCanvas />
      <p className="mt-4 text-xs text-parchment/40">
        Click an action, then click a target. Initiative determines turn order.
      </p>
    </main>
  );
}
