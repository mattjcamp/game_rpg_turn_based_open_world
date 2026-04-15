"""
Tile Manifest — unified graphics loader for all game sprites.

Reads data/tile_manifest.json and provides a single interface to load,
cache and look up any tile sprite by tile_id or by category + name.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# Project root — one level up from this file's directory (src/)
_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir))


class TileManifest:
    """Load and cache all game sprites from a single JSON manifest."""

    def __init__(self, manifest_path=None):
        if manifest_path is None:
            manifest_path = os.path.join(_PROJECT_ROOT, "data",
                                         "tile_manifest.json")
        self._manifest_path = manifest_path
        self._raw = {}            # full parsed JSON
        self._by_tile_id = {}     # tile_id (int) -> {"path": ..., ...}
        self._by_name = {}        # (category, name) -> {"path": ..., ...}
        self._sprite_cache = {}   # (abs_path, size) -> pygame Surface
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self):
        """Parse the manifest JSON and build lookup tables."""
        with open(self._manifest_path) as f:
            self._raw = json.load(f)

        # Clear previous lookups so reloads start fresh
        self._by_tile_id.clear()
        self._by_name.clear()

        for category, entries in self._raw.items():
            if category.startswith("_"):
                continue
            if not isinstance(entries, dict):
                continue
            for name, entry in entries.items():
                if not isinstance(entry, dict) or "path" not in entry:
                    continue
                self._by_name[(category, name)] = entry
                tid = entry.get("tile_id")
                if tid is not None:
                    self._by_tile_id[int(tid)] = entry

        self._loaded = True

    # ------------------------------------------------------------------
    # Lookups (no pygame dependency — just data)
    # ------------------------------------------------------------------

    def get_entry(self, tile_id):
        """Return manifest entry dict for a TILE_* constant, or None."""
        return self._by_tile_id.get(tile_id)

    def get_entry_by_name(self, category, name):
        """Return manifest entry dict for a (category, name) pair."""
        return self._by_name.get((category, name))

    def get_path(self, category, name):
        """Return the relative asset path for (category, name), or None."""
        entry = self._by_name.get((category, name))
        return entry["path"] if entry else None

    def get_abs_path(self, category, name):
        """Return the absolute asset path for (category, name), or None."""
        rel = self.get_path(category, name)
        if rel is None:
            return None
        return os.path.join(_PROJECT_ROOT, rel)

    def categories(self):
        """Return list of category names."""
        return [k for k in self._raw if not k.startswith("_")]

    def names_in(self, category):
        """Return list of entry names within a category."""
        section = self._raw.get(category, {})
        if not isinstance(section, dict):
            return []
        return [k for k, v in section.items()
                if isinstance(v, dict) and "path" in v]

    # ------------------------------------------------------------------
    # Sprite loading (requires pygame)
    # ------------------------------------------------------------------

    def get_sprite(self, tile_id, size=32):
        """Load and cache a sprite by TILE_* constant.

        Returns a pygame Surface scaled to *size*, or None.
        """
        entry = self._by_tile_id.get(tile_id)
        if entry is None:
            return None
        return self._load_sprite(entry["path"], size)

    def get_sprite_by_name(self, category, name, size=32):
        """Load and cache a sprite by (category, name).

        Returns a pygame Surface scaled to *size*, or None.
        """
        entry = self._by_name.get((category, name))
        if entry is None:
            return None
        return self._load_sprite(entry["path"], size)

    def _load_sprite(self, rel_path, size):
        """Internal: load a PNG, make black transparent for u4 tiles,
        scale to *size*, cache and return."""
        import pygame

        abs_path = os.path.join(_PROJECT_ROOT, rel_path)
        cache_key = (abs_path, size)
        if cache_key in self._sprite_cache:
            return self._sprite_cache[cache_key]

        if not os.path.exists(abs_path):
            logger.warning("Manifest sprite missing: %s", rel_path)
            return None

        raw = pygame.image.load(abs_path).convert_alpha()

        # Make black pixels transparent for U4-origin tiles (characters,
        # NPCs, dungeon, monsters) and any remaining u4_tiles references.
        _transparent_dirs = ("characters/", "npcs/", "dungeon/", "monsters/",
                             "u4_tiles/", "items/")
        if any(d in rel_path for d in _transparent_dirs):
            raw = self._make_black_transparent(raw)

        # Scale to target size
        w, h = raw.get_size()
        if w != size or h != size:
            raw = pygame.transform.scale(raw, (size, size))

        self._sprite_cache[cache_key] = raw
        return raw

    @staticmethod
    def _make_black_transparent(surface):
        """Replace fully-black pixels with transparent.

        Matches the existing renderer behaviour for U4 tiles.
        Uses surfarray for speed when available, falls back to
        pixel-by-pixel iteration (needed in test environments).
        """
        import pygame
        surf = surface.copy()
        try:
            arr = pygame.surfarray.pixels3d(surf)
            alpha = pygame.surfarray.pixels_alpha(surf)
            mask = ((arr[:, :, 0] == 0) & (arr[:, :, 1] == 0)
                    & (arr[:, :, 2] == 0))
            alpha[mask] = 0
            del arr, alpha          # unlock surface
        except (AttributeError, Exception):
            # Fallback: pixel-by-pixel (matches original renderer code)
            w, h = surf.get_size()
            for px in range(w):
                for py in range(h):
                    r, g, b, a = surf.get_at((px, py))
                    if r == 0 and g == 0 and b == 0:
                        surf.set_at((px, py), (0, 0, 0, 0))
        return surf

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self):
        """Check every path in the manifest exists on disk.

        Returns a list of (category, name, path) tuples for missing files.
        """
        missing = []
        for (cat, name), entry in self._by_name.items():
            abs_path = os.path.join(_PROJECT_ROOT, entry["path"])
            if not os.path.exists(abs_path):
                missing.append((cat, name, entry["path"]))
        return missing
