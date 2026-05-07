/**
 * Next.js config.
 *
 * Two deploy modes:
 *   - Local dev: served from "/" with no basePath. The default — works
 *     out of the box with `npm run dev` / `npm run build`.
 *   - GitHub Pages: served from "/<repo>/". Set NEXT_PUBLIC_BASE_PATH
 *     to the repo prefix (e.g. "/game_rpg_turn_based_open_world") and
 *     this config switches Next to static-export mode and prepends the
 *     prefix to routes + asset URLs.
 *
 * The same env var is read at runtime by `withBase()` in Module.ts so
 * Phaser's `load.image` / fetch() calls (which Next.js doesn't auto-
 * prefix the way it does <Link>/<Image>) end up at the right URL.
 */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  ...(basePath
    ? {
        // Static export for GitHub Pages.
        output: "export",
        basePath,
        // Trailing slash so /world/ resolves to /world/index.html under
        // a static host (GH Pages serves directories with a trailing
        // slash; without this, /world 404s).
        trailingSlash: true,
        images: { unoptimized: true },
      }
    : {}),
};

export default nextConfig;
