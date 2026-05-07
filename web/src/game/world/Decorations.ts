/**
 * Tile decoration glyphs for `tile_properties.effect` and
 * `tile_properties.item` data.
 *
 * Effects and items don't change gameplay yet — they're flavour.
 * Rather than ship a sprite per kind, we render a small Unicode glyph
 * over the tile (same approach as the ✦ encounter marker on the
 * overworld). Glyphs are colour-coded so the player can read them at
 * a glance: fire is hot orange, fairy lights are pale blue, rising
 * smoke is grey, items are gold.
 */

export interface DecoSpec {
  glyph: string;
  color: string;
  /** Optional outline so the glyph reads on any background. */
  stroke?: string;
}

// `fire` / `torch` / `fairy_light` / `rising_smoke` are deliberately
// absent — they're rendered as live animations by `TileEffects.ts`,
// which subsumes the static glyphs they used to ship with. Anything
// else an author drops in `tile_properties.effect` is unrecognised
// and silently ignored (returns null below).
const EFFECTS: Record<string, DecoSpec> = {};

/**
 * Look up a decoration for a tile_properties entry. Returns `null`
 * when the entry has nothing renderable (no effect, or the explicit
 * "(none)" sentinel that authors use to clear an inherited effect).
 */
export function decorationFor(entry: unknown): DecoSpec | null {
  if (!entry || typeof entry !== "object") return null;
  const e = entry as { effect?: string; item?: string };
  if (e.item) {
    return { glyph: "★", color: "#ffd470", stroke: "#1a1a2e" };
  }
  if (e.effect && e.effect !== "(none)") {
    return EFFECTS[e.effect] ?? null;
  }
  return null;
}
