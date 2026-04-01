"""
Module-level link registry for tile-to-tile connections.

Every link between maps is stored as a directional record with a
unique ID.  Each record describes a source endpoint (map + position)
and a target endpoint (map + position).  When the player steps on
a source tile, the runtime looks up the corresponding target and
places the party at the exact target position — no BFS guessing.

Bidirectional links (a typical door) are stored as two records
that reference each other via ``partner_id``.

Map addresses
-------------
Each endpoint carries a ``map_type`` and ``map_name`` that together
uniquely identify a map surface within the module:

    overworld        — the overworld grid
    town:Aseroth     — town "Aseroth" (the town-level tile grid)
    building:Inn:Bar — building "Inn", space "Bar"
    dungeon:Crypt:2  — dungeon "Crypt", level 2
    interior:Shrine  — overworld inline interior "Shrine"

The colon-delimited format is the **canonical map address** used
as dict keys in the registry and in ``links.json``.

File format  (``links.json`` in module directory)
-------------------------------------------------
::

    [
      {
        "link_id":    "lnk_abc123",
        "source_map": "overworld",
        "source_pos": [10, 14],
        "target_map": "town:Aseroth",
        "target_pos": [12, 24],
        "partner_id": "lnk_def456",
        "label":      "Aseroth main gate"
      },
      {
        "link_id":    "lnk_def456",
        "source_map": "town:Aseroth",
        "source_pos": [12, 24],
        "target_map": "overworld",
        "target_pos": [10, 14],
        "partner_id": "lnk_abc123",
        "label":      "Exit to overworld"
      }
    ]
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ─── Data model ───────────────────────────────────────────────────

@dataclass
class LinkEndpoint:
    """One side of a tile link — a specific tile on a specific map."""
    map_address: str = ""       # canonical "type:name" or "overworld"
    col: int = 0
    row: int = 0

    @property
    def pos(self) -> Tuple[int, int]:
        return (self.col, self.row)

    def to_dict(self) -> dict:
        return {
            "map_address": self.map_address,
            "col": self.col,
            "row": self.row,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LinkEndpoint":
        return cls(
            map_address=d.get("map_address", ""),
            col=d.get("col", 0),
            row=d.get("row", 0),
        )


@dataclass
class LinkRecord:
    """A single directional link between two tiles.

    For a bidirectional door, two LinkRecords exist and reference
    each other via ``partner_id``.
    """
    link_id: str                    # unique ID (e.g. "lnk_abc123")
    source: LinkEndpoint = field(default_factory=LinkEndpoint)
    target: LinkEndpoint = field(default_factory=LinkEndpoint)
    partner_id: str = ""            # link_id of the reverse record
    label: str = ""                 # human-readable label

    def to_dict(self) -> dict:
        d = {
            "link_id": self.link_id,
            "source_map": self.source.map_address,
            "source_pos": [self.source.col, self.source.row],
            "target_map": self.target.map_address,
            "target_pos": [self.target.col, self.target.row],
        }
        if self.partner_id:
            d["partner_id"] = self.partner_id
        if self.label:
            d["label"] = self.label
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LinkRecord":
        sp = d.get("source_pos", [0, 0])
        tp = d.get("target_pos", [0, 0])
        return cls(
            link_id=d.get("link_id", ""),
            source=LinkEndpoint(
                map_address=d.get("source_map", ""),
                col=sp[0] if len(sp) >= 2 else 0,
                row=sp[1] if len(sp) >= 2 else 0,
            ),
            target=LinkEndpoint(
                map_address=d.get("target_map", ""),
                col=tp[0] if len(tp) >= 2 else 0,
                row=tp[1] if len(tp) >= 2 else 0,
            ),
            partner_id=d.get("partner_id", ""),
            label=d.get("label", ""),
        )


def generate_link_id() -> str:
    """Generate a unique link ID."""
    return f"lnk_{uuid.uuid4().hex[:12]}"


# ─── Canonical map address helpers ────────────────────────────────

def make_map_address(map_type: str, map_name: str = "",
                     sub_name: str = "") -> str:
    """Build a canonical map address string.

    Examples::

        make_map_address("overworld")            → "overworld"
        make_map_address("town", "Aseroth")      → "town:Aseroth"
        make_map_address("building", "Inn", "Bar")→ "building:Inn:Bar"
        make_map_address("dungeon", "Crypt", "2") → "dungeon:Crypt:2"
    """
    if map_type == "overworld" and not map_name:
        return "overworld"
    parts = [map_type]
    if map_name:
        parts.append(map_name)
    if sub_name:
        parts.append(sub_name)
    return ":".join(parts)


def parse_map_address(address: str) -> Tuple[str, str, str]:
    """Split a canonical map address into (type, name, sub_name).

    Returns ("overworld", "", "") for the bare "overworld" address.
    """
    parts = address.split(":", 2)
    map_type = parts[0] if parts else ""
    map_name = parts[1] if len(parts) > 1 else ""
    sub_name = parts[2] if len(parts) > 2 else ""
    return (map_type, map_name, sub_name)


# ─── Link Registry ────────────────────────────────────────────────

class LinkRegistry:
    """Holds all tile-to-tile links for a module.

    The registry is the single source of truth for map transitions.
    It is loaded from ``links.json`` at module load time, and each
    map's ``TileMap.links`` dict is populated *from* it so the
    per-frame renderer/state code can still use ``tmap.get_link()``.

    Key lookup indexes
    ------------------
    _by_id : dict[str, LinkRecord]
        All records keyed by link_id.
    _by_source : dict[(map_address, col, row), LinkRecord]
        Fast lookup when the player steps on a tile.
    _by_map : dict[map_address, list[LinkRecord]]
        All links that originate from a given map.
    """

    def __init__(self):
        self._records: List[LinkRecord] = []
        self._by_id: Dict[str, LinkRecord] = {}
        self._by_source: Dict[Tuple[str, int, int], LinkRecord] = {}
        self._by_map: Dict[str, List[LinkRecord]] = {}
        self._dirty = False

    # ── Loading / saving ──────────────────────────────────────

    def load(self, module_path: str) -> None:
        """Load links.json from a module directory."""
        self.clear()
        fpath = os.path.join(module_path, "links.json")
        if not os.path.isfile(fpath):
            return
        try:
            with open(fpath, "r") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load links.json: %s", exc)
            return

        if isinstance(raw, list):
            for entry in raw:
                rec = LinkRecord.from_dict(entry)
                if rec.link_id:
                    self._add(rec)
        log.info("Loaded %d links from %s", len(self._records), fpath)

    def save(self, module_path: str) -> None:
        """Write all links to links.json in the module directory."""
        fpath = os.path.join(module_path, "links.json")
        data = [rec.to_dict() for rec in self._records]
        try:
            with open(fpath, "w") as fh:
                json.dump(data, fh, indent=2)
            self._dirty = False
            log.info("Saved %d links to %s", len(data), fpath)
        except OSError as exc:
            log.error("Failed to save links.json: %s", exc)

    @property
    def dirty(self) -> bool:
        return self._dirty

    # ── Query ─────────────────────────────────────────────────

    def get_by_id(self, link_id: str) -> Optional[LinkRecord]:
        """Look up a link by its unique ID."""
        return self._by_id.get(link_id)

    def get_at(self, map_address: str, col: int, row: int
               ) -> Optional[LinkRecord]:
        """Look up the link originating from a specific tile."""
        return self._by_source.get((map_address, col, row))

    def get_links_for_map(self, map_address: str) -> List[LinkRecord]:
        """Return all links that originate from a given map."""
        return list(self._by_map.get(map_address, []))

    def get_all(self) -> List[LinkRecord]:
        """Return all link records."""
        return list(self._records)

    def get_partner(self, rec: LinkRecord) -> Optional[LinkRecord]:
        """Return the partner (reverse) link, if any."""
        if rec.partner_id:
            return self._by_id.get(rec.partner_id)
        return None

    # ── Pending link (editor workflow) ────────────────────────

    def has_pending(self) -> bool:
        """True if a half-link is waiting for its target."""
        return hasattr(self, "_pending") and self._pending is not None

    def start_link(self, source: LinkEndpoint,
                   label: str = "") -> LinkRecord:
        """Begin a new link from *source*.  Target is unset.

        The record is NOT added to the registry yet — call
        ``complete_link()`` once the target is chosen.
        """
        rec = LinkRecord(
            link_id=generate_link_id(),
            source=source,
            label=label,
        )
        self._pending = rec
        return rec

    def get_pending(self) -> Optional[LinkRecord]:
        return getattr(self, "_pending", None)

    def complete_link(self, target: LinkEndpoint,
                      bidirectional: bool = True) -> LinkRecord:
        """Finish the pending link by setting its target.

        If *bidirectional*, a reverse link record is also created
        and the two are connected via ``partner_id``.

        Returns the completed forward link record.
        """
        rec = self._pending
        if rec is None:
            raise RuntimeError("No pending link to complete")
        rec.target = target
        self._add(rec)

        if bidirectional:
            reverse = LinkRecord(
                link_id=generate_link_id(),
                source=target,
                target=rec.source,
                partner_id=rec.link_id,
                label=f"{rec.label} (return)" if rec.label else "",
            )
            rec.partner_id = reverse.link_id
            self._add(reverse)

        self._pending = None
        self._dirty = True
        return rec

    def cancel_pending(self) -> None:
        """Discard the pending link."""
        self._pending = None

    # ── Mutation ──────────────────────────────────────────────

    def add(self, rec: LinkRecord) -> None:
        """Add a fully-formed link record."""
        self._add(rec)
        self._dirty = True

    def remove(self, link_id: str, remove_partner: bool = True) -> None:
        """Remove a link by ID.  Also removes its partner if requested."""
        rec = self._by_id.get(link_id)
        if rec is None:
            return
        partner = None
        if remove_partner and rec.partner_id:
            partner = self._by_id.get(rec.partner_id)
        self._remove(rec)
        if partner:
            self._remove(partner)
        self._dirty = True

    def clear(self) -> None:
        """Remove all links."""
        self._records.clear()
        self._by_id.clear()
        self._by_source.clear()
        self._by_map.clear()
        self._pending = None

    # ── Sync to TileMap ───────────────────────────────────────

    def populate_tile_map(self, tile_map, map_address: str) -> None:
        """Populate a TileMap's ``links`` dict from the registry.

        Call this after loading a map so the existing per-tile
        ``tmap.get_link()`` API works with registry-sourced data.
        Existing links on the TileMap are preserved; registry links
        are merged in (registry wins on conflict).

        The dict format is backward-compatible with the legacy
        ``tile_links`` system: ``target_map`` holds the bare name
        (e.g. ``"Midherm"`` not ``"town:Midherm"``), ``target_type``
        is ``"town"``/``"building"``/``"dungeon"``/etc., and
        ``interior`` mirrors ``target_map`` so old code paths that
        check ``link.get("interior")`` still work.
        """
        for rec in self.get_links_for_map(map_address):
            pos = rec.source.pos
            tgt_type, tgt_name, tgt_sub = parse_map_address(
                rec.target.map_address)
            # Use bare name for backward compat with runtime lookups
            # that do _find_town_by_name(link["target_map"]).
            bare_name = tgt_name or tgt_type
            entry = {
                "target_map": bare_name,
                "target_type": tgt_type,
                "target_pos": rec.target.pos,
                "source_map": rec.source.map_address,
                "source_pos": rec.source.pos,
                "link_id": rec.link_id,
                # Legacy fields — some runtime code checks these
                "interior": bare_name,
                "type": tgt_type,
            }
            if tgt_sub:
                entry["sub_interior"] = tgt_sub
            tile_map.links[pos] = entry

    # ── Import from legacy tile_links ─────────────────────────

    def import_from_tile_links(self, tile_links: dict,
                               source_map: str = "overworld",
                               towns_data: list = None,
                               buildings_data: list = None) -> int:
        """Convert legacy tile_links into registry records.

        Reads the overworld's ``tile_links`` dict and, where possible,
        resolves the target_pos by finding the entry/exit tile in the
        destination map data.

        Returns the number of link records created.
        """
        count = 0
        towns_by_name = {}
        if towns_data:
            for t in towns_data:
                tname = t.get("name", "")
                if tname:
                    towns_by_name[tname] = t

        buildings_by_name = {}
        if buildings_data:
            for b in buildings_data:
                bname = b.get("name", "")
                if bname:
                    buildings_by_name[bname] = b

        for pos_key, info in tile_links.items():
            if not isinstance(info, dict):
                continue
            interior_name = info.get("interior", "")
            if not interior_name:
                continue
            link_type = info.get("type", "")

            # Parse position
            if isinstance(pos_key, tuple):
                sc, sr = pos_key
            elif isinstance(pos_key, str) and "," in pos_key:
                parts = pos_key.split(",")
                try:
                    sc, sr = int(parts[0]), int(parts[1])
                except (ValueError, IndexError):
                    continue
            else:
                continue

            # Determine target map address
            if link_type == "town":
                target_addr = make_map_address("town", interior_name)
            elif link_type == "dungeon":
                target_addr = make_map_address("dungeon", interior_name)
            elif link_type == "building":
                target_addr = make_map_address("building", interior_name)
            else:
                target_addr = make_map_address("interior", interior_name)

            # Try to resolve target entry position
            target_col, target_row = 0, 0
            resolved = False

            if link_type == "town" and interior_name in towns_by_name:
                town = towns_by_name[interior_name]
                layout = town.get("layout", {})
                tiles = layout.get("tiles", {})
                # Find an exit tile in the town for the return link
                for tk, tv in tiles.items():
                    if isinstance(tv, dict) and tv.get("to_overworld"):
                        parts = tk.split(",")
                        if len(parts) == 2:
                            target_col = int(parts[0])
                            target_row = int(parts[1])
                            resolved = True
                            break
                if not resolved:
                    # Use entry_col/entry_row
                    target_col = layout.get("entry_col", 0)
                    target_row = layout.get("entry_row", 0)
                    if target_col or target_row:
                        resolved = True

            elif link_type == "building" and interior_name in buildings_by_name:
                bld = buildings_by_name[interior_name]
                spaces = bld.get("spaces", [])
                if spaces:
                    sp = spaces[0]
                    sp_tiles = sp.get("tiles", {})
                    for tk, tv in sp_tiles.items():
                        if isinstance(tv, dict) and tv.get("to_overworld"):
                            parts = tk.split(",")
                            if len(parts) == 2:
                                target_col = int(parts[0])
                                target_row = int(parts[1])
                                resolved = True
                                break

            source = LinkEndpoint(source_map, sc, sr)
            target = LinkEndpoint(target_addr, target_col, target_row)
            forward = LinkRecord(
                link_id=generate_link_id(),
                source=source,
                target=target,
                label=interior_name,
            )
            self._add(forward)
            count += 1

            # Create return link if we resolved target
            if resolved:
                reverse = LinkRecord(
                    link_id=generate_link_id(),
                    source=target,
                    target=source,
                    partner_id=forward.link_id,
                    label=f"Exit to {source_map}",
                )
                forward.partner_id = reverse.link_id
                self._add(reverse)
                count += 1

        self._dirty = True
        return count

    # ── Internal ──────────────────────────────────────────────

    def _add(self, rec: LinkRecord) -> None:
        self._records.append(rec)
        self._by_id[rec.link_id] = rec
        key = (rec.source.map_address, rec.source.col, rec.source.row)
        self._by_source[key] = rec
        self._by_map.setdefault(rec.source.map_address, []).append(rec)

    def _remove(self, rec: LinkRecord) -> None:
        if rec in self._records:
            self._records.remove(rec)
        self._by_id.pop(rec.link_id, None)
        key = (rec.source.map_address, rec.source.col, rec.source.row)
        self._by_source.pop(key, None)
        lst = self._by_map.get(rec.source.map_address, [])
        if rec in lst:
            lst.remove(rec)


# ─── Helpers ──────────────────────────────────────────────────────

def _infer_target_type(map_address: str) -> str:
    """Derive a target_type string from a canonical map address.

    Used when populating TileMap.links for backward compat with
    code that checks ``link["target_type"]``.
    """
    mtype, _, _ = parse_map_address(map_address)
    type_map = {
        "overworld": "overworld",
        "town": "town",
        "building": "building",
        "dungeon": "dungeon",
        "interior": "interior",
    }
    return type_map.get(mtype, mtype)
