/**
 * Landing page — the first thing a player sees when they open the
 * game. Two buttons:
 *
 *   • Return to Game — only rendered when localStorage has a rolling
 *     save. Routes straight to /world; the world page hydrates the
 *     save, OverworldScene's resume branch transitions the player
 *     back into the dungeon / town they were last in.
 *
 *   • Start New Game — drops any existing save, resets the in-memory
 *     game state, and routes to /new-game which shows the module's
 *     dramatic intro paragraph.
 *
 * The "Return to Game" button is gated behind a `useEffect` since
 * `hasSave()` reads `localStorage` and that's not available on the
 * server during SSR — rendering it server-side would cause a
 * hydration mismatch.
 */
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function HomePage() {
  const router = useRouter();
  const [savedRun, setSavedRun] = useState<boolean | null>(null);

  useEffect(() => {
    void import("@/game/save").then(({ hasSave }) => {
      setSavedRun(hasSave());
    });
  }, []);

  const onNewGame = async () => {
    const { startFreshSession } = await import("@/game/save");
    startFreshSession();
    router.push("/new-game");
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-6 text-center">
      <h1 className="font-display text-5xl text-parchment">Realm of Shadow</h1>
      <p className="mt-4 text-parchment/70">
        A turn-based fantasy adventure. Form a party, walk the realm,
        clear the wards, and end the dragon.
      </p>

      <div className="mt-12 flex flex-col gap-3 sm:flex-row">
        {savedRun ? (
          <Link
            href="/world"
            className="rounded-md border border-ember bg-ember/30 px-8 py-3 text-lg text-parchment transition hover:bg-ember/50"
          >
            Return to Game &rarr;
          </Link>
        ) : null}
        <button
          onClick={onNewGame}
          className="rounded-md border border-parchment/30 px-8 py-3 text-lg text-parchment/90 transition hover:bg-parchment/10"
        >
          Start New Game
        </button>
      </div>

      {savedRun === false && (
        <p className="mt-6 text-xs text-parchment/40">
          No saved run on this device — choose Start New Game to begin.
        </p>
      )}
    </main>
  );
}
