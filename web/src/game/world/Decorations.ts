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
 *
 * **Items.** A tile with `tile_properties[col,row].item: "<name>"`
 * shows a per-icon glyph that matches the Python game's
 * `_draw_item_icon` switch. The icon comes from the items catalog's
 * `icon` field (e.g. "torch", "potion", "sword"); when the catalog
 * isn't available or doesn't know the item, we fall back to a generic
 * gold star so authors still see *something* on the tile rather than
 * silently dropping the marker.
 */

import type { Item } from "./Items";
import { ANIMATED_ITEM_ICONS } from "./TileEffects";

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
 * Glyph + colour per items.json `icon` value. Glyphs are picked from
 * the Basic Multilingual Plane so they render on every system Phaser
 * targets without a font fallback. Colours follow the in-world
 * material — wood is brown, steel is grey, magic is purple, fire is
 * orange. The mapping mirrors the categories the Python renderer
 * draws as primitive shapes; we get a similar read with text.
 */
const ICON_DECOS: Record<string, DecoSpec> = {
  // Light + camp
  torch:       { glyph: "♦", color: "#ffb84a" },  // orange flame
  campfire:    { glyph: "△", color: "#ff7a3a" },  // tent + flame
  // Consumables
  potion:      { glyph: "♥", color: "#ff6b8a" },  // red phial
  herb:        { glyph: "✿", color: "#88e09c" },  // green flower
  scroll:      { glyph: "≡", color: "#dcc69a" },  // parchment lines
  holy:        { glyph: "✚", color: "#fff0a3" },  // pale gold cross
  // Tools & utility
  tool:        { glyph: "⚒", color: "#aaa890" },  // hammer
  key:         { glyph: "⚷", color: "#ffd470" },  // gold key
  rope:        { glyph: "∽", color: "#a37f5a" },  // brown coil
  bomb:        { glyph: "◉", color: "#bdb38a" },  // round shell
  // Armor
  armor_light: { glyph: "▲", color: "#a89478" },  // tan leather
  armor_heavy: { glyph: "▲", color: "#9bb0c7" },  // steel
  // Weapons
  sword:       { glyph: "†", color: "#dcdcdc" },  // sword/cross
  dagger:      { glyph: "↟", color: "#dcdcdc" },  // sharp short blade
  club:        { glyph: "▮", color: "#a37f5a" },  // wood club
  mace:        { glyph: "✺", color: "#aaaaaa" },  // flanged head
  halberd:     { glyph: "⚔", color: "#aaaaaa" },  // crossed weapons
  bow:         { glyph: "›", color: "#a37f5a" },  // wooden curve
  spear:       { glyph: "↑", color: "#9bb0c7" },  // pointed shaft
  axe:         { glyph: "⚒", color: "#a89478" },
  gloves:      { glyph: "◇", color: "#a37f5a" },
  fists:       { glyph: "◯", color: "#dcdcdc" },
  rock:        { glyph: "●", color: "#888888" },
  // Ammo
  ammo:        { glyph: "▶", color: "#bdb38a" },  // arrowhead
  // Quest / artifact
  artifact:    { glyph: "✦", color: "#c28bff" },  // arcane sparkle
};

/** Generic fallback when a tile's item isn't in the catalog or has
 *  no `icon` field — keeps the marker visible. Same gold star the
 *  module rendered before per-icon decoration landed. */
const FALLBACK_ITEM_DECO: DecoSpec = { glyph: "★", color: "#ffd470" };

/**
 * Look up a decoration for a tile_properties entry. Returns `null`
 * when the entry has nothing renderable (no effect, or the explicit
 * "(none)" sentinel that authors use to clear an inherited effect).
 *
 * Pass `items` (the loaded items catalog) to enable per-icon glyphs
 * for tiles with an `item` attribute. Without it (e.g. tests or a
 * scene that hasn't loaded items yet), every item-bearing tile
 * falls back to the gold star.
 */
export function decorationFor(
  entry: unknown,
  items?: Map<string, Item>,
): DecoSpec | null {
  if (!entry || typeof entry !== "object") return null;
  const e = entry as { effect?: string; item?: string };
  if (e.item) {
    const def = items?.get(e.item);
    const icon = def?.icon;
    // Some icons are rendered as live animations by TileEffects.ts
    // (torches especially — the static glyph never read as a torch).
    // Return null here so the scene draws ONLY the animation; we'd
    // otherwise double-render with a glyph stacked on the flame.
    if (icon && ANIMATED_ITEM_ICONS.has(icon)) return null;
    const base = (icon && ICON_DECOS[icon]) ? ICON_DECOS[icon] : FALLBACK_ITEM_DECO;
    return { ...base, stroke: "#1a1a2e" };
  }
  if (e.effect && e.effect !== "(none)") {
    return EFFECTS[e.effect] ?? null;
  }
  return null;
}
