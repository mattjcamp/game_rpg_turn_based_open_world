import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-6 text-center">
      <h1 className="font-display text-5xl text-parchment">Realm of Shadow</h1>
      <p className="mt-4 text-parchment/70">
        Experimental web build. Same combat math as the desktop version,
        rebuilt in TypeScript so you can play in the browser.
      </p>
      <Link
        href="/combat"
        className="mt-10 rounded-md border border-ember bg-ember/20 px-6 py-3 text-lg text-parchment transition hover:bg-ember/40"
      >
        Enter Combat &rarr;
      </Link>
      <p className="mt-12 text-xs text-parchment/40">
        Tagged release of the original Pygame project remains in the repo
        root. This build lives under <code>web/</code>.
      </p>
    </main>
  );
}
