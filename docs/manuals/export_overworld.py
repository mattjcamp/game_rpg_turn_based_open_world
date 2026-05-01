"""Export the active module's overworld map as a single PNG.

Reads the module's ``static_overworld.json`` (preferred) or
``overview_map.json``, looks up each tile's sprite via
``data/tile_manifest.json``, and stitches them into a single image
that matches what the in-game renderer draws on the overworld.

Includes per-tile decorations, sprite overrides, and unique-tile
placements when the source data carries them, so re-running this
on a future module produces a faithful screenshot regardless of
how richly populated the map is.

Usage
-----
    python3 docs/manuals/export_overworld.py
    # → docs/manuals/overview_map.png

    python3 docs/manuals/export_overworld.py modules/foo
    # exports modules/foo's overworld instead of the active module

The output is sized at 32 px per tile (the in-game tile size) which
matches the screenshots elsewhere in this folder. Pass ``--scale 2``
on the command line to double-size for a poster-style print.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DEFAULT_OUT = HERE / "overview_map.png"


# ── Active-module discovery ────────────────────────────────────────


def _config_active_module() -> Path | None:
    """Return ``data/config.json``'s active_module_path, or None."""
    cfg_path = REPO / "data" / "config.json"
    if not cfg_path.is_file():
        return None
    try:
        with cfg_path.open() as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    p = cfg.get("active_module_path")
    if not p:
        return None
    p = Path(p)
    return p if p.is_absolute() else (REPO / p)


# ── Map loading ────────────────────────────────────────────────────


def _load_module_map(module_dir: Path) -> dict | None:
    """Return a normalised dict ``{w, h, tiles, decorations, sprite_overrides,
    tile_properties, unique_tile_placements}`` for the module's overworld.

    Tries ``static_overworld.json`` first (the richer format) then
    falls back to ``overview_map.json`` (the editor's overview).
    """
    static = module_dir / "static_overworld.json"
    if static.is_file():
        with static.open() as f:
            data = json.load(f)
        w = int(data.get("width", 0))
        h = int(data.get("height", 0))
        tiles = data.get("tiles") or []
        if w and h and tiles and len(tiles) == h:
            return {
                "w": w, "h": h, "tiles": tiles,
                "decorations": data.get("decorations") or {},
                "sprite_overrides": data.get("sprite_overrides") or {},
                "tile_properties": data.get("tile_properties") or {},
                "unique_tile_placements":
                    data.get("unique_tile_placements") or [],
            }

    overview = module_dir / "overview_map.json"
    if overview.is_file():
        with overview.open() as f:
            data = json.load(f)
        mc = data.get("map_config", {})
        w = int(mc.get("width", 0))
        h = int(mc.get("height", 0))
        tiles = data.get("tiles") or []
        if w and h and tiles and len(tiles) == h:
            return {
                "w": w, "h": h, "tiles": tiles,
                "decorations": data.get("decorations") or {},
                "sprite_overrides": data.get("sprite_overrides") or {},
                "tile_properties": data.get("tile_properties") or {},
                "unique_tile_placements":
                    data.get("unique_tile_placements") or [],
            }
    return None


# ── Sprite lookup ──────────────────────────────────────────────────


class SpriteResolver:
    """Resolve a tile_id (or a relative asset path) to a 32×32 PIL image.

    Mirrors what the in-game renderer does for the overworld: load by
    tile_id from ``data/tile_manifest.json`` first; if a tile carries
    a per-cell sprite override or a unique-tile def, use that path
    instead. Caches loaded sprites so a 40×30 map only opens each
    distinct PNG once.
    """

    def __init__(self):
        self.repo = REPO
        with (REPO / "data" / "tile_manifest.json").open() as f:
            manifest = json.load(f)
        with (REPO / "data" / "tile_defs.json").open() as f:
            self.tile_defs = json.load(f)
        # Build tile_id -> entry index from every category in the
        # manifest.  Earlier categories take precedence (matches the
        # in-game loader, which iterates the manifest in dict order).
        self._by_tid: dict[int, dict] = {}
        for cat, section in manifest.items():
            if cat.startswith("_") or not isinstance(section, dict):
                continue
            for name, entry in section.items():
                if not isinstance(entry, dict) or "path" not in entry:
                    continue
                tid = entry.get("tile_id")
                if tid is None:
                    continue
                self._by_tid.setdefault(int(tid), entry)
        self._cache: dict[str, Image.Image | None] = {}

    def by_tile_id(self, tile_id: int) -> Image.Image | None:
        entry = self._by_tid.get(int(tile_id))
        if not entry:
            return None
        return self.by_path(entry["path"])

    def by_path(self, rel_path: str) -> Image.Image | None:
        if rel_path in self._cache:
            return self._cache[rel_path]
        # Module sprite paths in the data files are stored without the
        # ``src/`` prefix in some cases (``game/terrain/grass.png``)
        # and with it in others (``src/assets/...``). Try both layouts.
        candidates = [self.repo / rel_path]
        if not rel_path.startswith("src/"):
            candidates.append(self.repo / "src" / "assets" / rel_path)
        img = None
        for cand in candidates:
            if cand.is_file():
                try:
                    img = Image.open(cand).convert("RGBA")
                except OSError:
                    img = None
                if img:
                    break
        if img and img.size != (32, 32):
            img = img.resize((32, 32), Image.NEAREST)
        # Mirror the renderer's "make black transparent" pass for U4
        # sprites — characters, monsters, dungeon, items, etc.
        if img and any(d in rel_path for d in
                       ("characters/", "npcs/", "dungeon/", "monsters/",
                        "u4_tiles/", "items/", "unassigned/")):
            img = _make_black_transparent(img)
        self._cache[rel_path] = img
        return img

    def fallback_for_tid(self, tile_id: int) -> Image.Image:
        """Last-resort coloured square using tile_defs.json's RGB hint
        so missing sprites still give the export a visible block in
        roughly the right colour rather than a hole."""
        d = self.tile_defs.get(str(tile_id), {})
        col = d.get("color") or [200, 0, 200]  # garish magenta = warn
        return Image.new("RGBA", (32, 32),
                         (int(col[0]), int(col[1]), int(col[2]), 255))


def _make_black_transparent(img: Image.Image) -> Image.Image:
    """Replace fully-black pixels with transparent — matches the in-game
    renderer's behaviour for U4-origin sprites."""
    r, g, b, a = img.split()
    px = img.load()
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    op = out.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            pr, pg, pb, pa = px[x, y]
            if pa > 0 and (pr, pg, pb) != (0, 0, 0):
                op[x, y] = (pr, pg, pb, pa)
    return out


# ── Renderer ───────────────────────────────────────────────────────


def render(module_dir: Path, out_path: Path, scale: int = 1) -> Path:
    data = _load_module_map(module_dir)
    if data is None:
        raise SystemExit(
            f"No overworld data found in {module_dir} "
            f"(looked for static_overworld.json, overview_map.json)")

    w, h = data["w"], data["h"]
    tile_size = 32
    canvas = Image.new("RGBA", (w * tile_size, h * tile_size),
                       (0, 0, 0, 255))
    sprites = SpriteResolver()

    # ── Base tile pass ──
    missing: dict[int, int] = {}
    for r in range(h):
        row = data["tiles"][r]
        for c in range(min(w, len(row))):
            tid = int(row[c])
            img = sprites.by_tile_id(tid)
            if img is None:
                missing[tid] = missing.get(tid, 0) + 1
                img = sprites.fallback_for_tid(tid)
            canvas.paste(img, (c * tile_size, r * tile_size), img)

    # ── Per-cell sprite overrides ──
    # ``sprite_overrides`` is keyed by "col,row" with a relative asset
    # path. The in-game renderer uses these to give individual tiles a
    # custom look without changing their base tile_id.
    for key, rel in data.get("sprite_overrides", {}).items():
        try:
            c_str, r_str = str(key).split(",")
            c, r = int(c_str), int(r_str)
        except (ValueError, AttributeError):
            continue
        if not (0 <= c < w and 0 <= r < h):
            continue
        img = sprites.by_path(str(rel))
        if img is not None:
            canvas.paste(img, (c * tile_size, r * tile_size), img)

    # ── Decoration overlay ──
    # Decorations are tile_ids drawn ON TOP of the base tile, with the
    # base tile remaining the source of truth for walkability. Used
    # for cosmetics like wall torches in dungeons; less common on the
    # overworld but supported here for completeness.
    for key, dec_tid in data.get("decorations", {}).items():
        try:
            c_str, r_str = str(key).split(",")
            c, r = int(c_str), int(r_str)
        except (ValueError, AttributeError):
            continue
        if not (0 <= c < w and 0 <= r < h):
            continue
        img = sprites.by_tile_id(int(dec_tid))
        if img is not None:
            canvas.paste(img, (c * tile_size, r * tile_size), img)

    # ── Unique-tile placements ──
    # Modules can attach a custom unique-tile def to a coord (e.g. a
    # moongate, a whispering-stones shrine). The placement carries an
    # ``id`` plus a ``def`` dict — the def's ``sprite`` field (when
    # present) is the asset path to draw on top of the base tile.
    for placement in data.get("unique_tile_placements", []) or []:
        try:
            c = int(placement.get("col", 0))
            r = int(placement.get("row", 0))
        except (TypeError, ValueError):
            continue
        if not (0 <= c < w and 0 <= r < h):
            continue
        udef = placement.get("def") or {}
        sprite_path = udef.get("sprite")
        if sprite_path:
            img = sprites.by_path(str(sprite_path))
            if img is not None:
                canvas.paste(img, (c * tile_size, r * tile_size), img)

    # ── Optional upscale for poster-style export ──
    if scale and scale != 1:
        canvas = canvas.resize(
            (canvas.width * scale, canvas.height * scale),
            Image.NEAREST)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG", optimize=True)

    if missing:
        sys.stderr.write(
            "[export_overworld] Warning: tile_ids without manifest "
            "entries fell back to coloured squares — "
            f"{dict(sorted(missing.items()))}\n")

    return out_path


# ── CLI ────────────────────────────────────────────────────────────


def main(argv=None):
    p = argparse.ArgumentParser(
        description=("Export the active (or specified) module's "
                     "overworld map as a PNG."))
    p.add_argument("module", nargs="?",
                   help=("Path to a module directory. Defaults to "
                         "the active_module_path in data/config.json."))
    p.add_argument("-o", "--out", default=str(DEFAULT_OUT),
                   help="Output PNG path (default: docs/manuals/overview_map.png)")
    p.add_argument("--scale", type=int, default=1,
                   help="Integer upscale (1 = native 32 px tiles)")
    args = p.parse_args(argv)

    if args.module:
        module_dir = Path(args.module)
        if not module_dir.is_absolute():
            module_dir = REPO / module_dir
    else:
        module_dir = _config_active_module()
        if module_dir is None:
            raise SystemExit(
                "No active module found. Pass a module path on the "
                "command line, or set active_module_path in "
                "data/config.json.")

    out = render(module_dir, Path(args.out), args.scale)
    print(f"Wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
