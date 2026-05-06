import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-6 text-center">
      <h1 className="font-display text-5xl text-parchment">Realm of Shadow</h1>
      <p className="mt-4 text-parchment/70">
        Experimental web build. Same combat math as the desktop version,
        rebuilt in TypeScript so you can play in the browser.
      </p>
      <div className="mt-10 flex flex-col gap-3 sm:flex-row">
        <Link
          href="/world"
          className="rounded-md border border-ember bg-ember/20 px-6 py-3 text-lg text-parchment transition hover:bg-ember/40"
        >
          Enter the World &rarr;
        </Link>
        <Link
          href="/combat"
          className="rounded-md border border-parchment/30 px-6 py-3 text-lg text-parchment/80 transition hover:bg-parchment/10"
        >
          Combat-only Demo
        </Link>
      </div>
      <p className="mt-12 max-w-md text-xs text-parchment/40">
        World mode loads the bundled overworld map and lets the party wander.
        Stepping on a glowing tile starts a turn-based fight using the ported
        combat engine. Combat-only mode skips straight to a fixed encounter.
      </p>
    </main>
  );
}
