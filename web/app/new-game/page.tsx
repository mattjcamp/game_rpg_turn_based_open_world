/**
 * New-Game intro screen.
 *
 * Fetches the active module's `module.json` and renders
 * `metadata.name` + `metadata.description` as the dramatic opening
 * paragraph. "Next" routes the player into the existing party
 * formation screen (`/party`) where they can edit their roster, and
 * the party page's "Begin Adventure" button takes them from there
 * into `/world`.
 *
 * Gets here via the landing page's "Start New Game" button, which
 * calls `startFreshSession()` (clearSave + resetGameState) before
 * navigating — so by the time we mount, any previous save is gone.
 *
 * Module loading is one-shot via fetch on mount. Any failure leaves
 * the page in a graceful error state with a Back link instead of a
 * dead screen.
 */
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

interface ModuleMetadata {
  name?: string;
  description?: string;
}

const ACTIVE_MODULE = "the_dragon_of_dagorn";

export default function NewGamePage() {
  const [meta, setMeta] = useState<ModuleMetadata | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetch(`/modules/${ACTIVE_MODULE}/module.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j: { metadata?: ModuleMetadata }) => {
        setMeta(j.metadata ?? {});
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center px-6 py-10 text-center">
      {error ? (
        <>
          <h1 className="font-display text-3xl text-parchment">
            Couldn&apos;t load the module
          </h1>
          <p className="mt-4 text-parchment/70">{error}</p>
          <Link
            href="/"
            className="mt-8 rounded border border-parchment/30 px-6 py-2 text-parchment/80 hover:bg-parchment/10"
          >
            &larr; Back
          </Link>
        </>
      ) : !meta ? (
        <p className="text-parchment/60">Loading the module&hellip;</p>
      ) : (
        <>
          <h1 className="font-display text-4xl text-parchment">
            {meta.name ?? "Untitled Adventure"}
          </h1>
          <p className="mt-8 max-w-2xl text-left text-base leading-relaxed text-parchment/85">
            {meta.description ?? ""}
          </p>
          <div className="mt-12 flex gap-3">
            <Link
              href="/"
              className="rounded border border-parchment/30 px-5 py-2 text-sm text-parchment/70 hover:bg-parchment/10"
            >
              &larr; Back
            </Link>
            <Link
              href="/party"
              className="rounded border border-ember bg-ember/30 px-8 py-2 text-lg text-parchment transition hover:bg-ember/50"
            >
              Next &rarr;
            </Link>
          </div>
        </>
      )}
    </main>
  );
}
