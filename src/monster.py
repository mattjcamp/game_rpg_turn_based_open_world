"""
Monster definitions for combat encounters.

Loads monster stats from data/monsters.json so new creatures can be added
or tweaked without touching code. Each monster has D&D-style stats: HP,
AC, attack bonus, damage dice, and rewards (XP and gold).
"""

import json
import os
import random

from src.data_loader import _load_json
from src.settings import TILE_WATER

# ── Default data directory ────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

# ── Active module data directory (None = use defaults) ────────────
_module_data_dir = None

# ── Load monster data from JSON ─────────────────────────────────

_MONSTER_DATA = _load_json("monsters.json")

MONSTERS = _MONSTER_DATA["monsters"]
SPAWN_TABLES = _MONSTER_DATA.get("spawn_tables", {})


class Monster:
    """A hostile creature the party can fight."""

    def __init__(self, name, hp, ac, attack_bonus,
                 damage_dice=1, damage_sides=4, damage_bonus=0,
                 xp_reward=25, gold_reward=10, color=(200, 50, 50),
                 tile=None, undead=False, humanoid=False, terrain="land",
                 ranged=None, spells=None,
                 move_range=1, post_attack_move=0,
                 on_hit_effects=None, passives=None,
                 resist=None, vulnerable=None,
                 battle_scale=1):
        self.name = name
        self.max_hp = hp
        self.hp = hp
        self.ac = ac
        self.attack_bonus = attack_bonus
        self.damage_dice = damage_dice
        self.damage_sides = damage_sides
        self.damage_bonus = damage_bonus
        self.xp_reward = xp_reward
        self.gold_reward = gold_reward
        self.color = color   # Fallback color for procedural rendering
        self.tile = tile     # Filename in src/assets/ (e.g. "orc_f1.png")
        self.undead = undead  # True for undead creatures (skeleton, zombie, etc.)
        self.humanoid = humanoid  # True for humanoid creatures (orc, goblin, etc.)
        self.terrain = terrain  # "land" or "sea" — restricts where this monster can move
        self.charmed = False    # True when under Charm Person — fights for the player

        # Ranged attack capability (None = melee only)
        # Dict with: range, attack_bonus, damage_dice, damage_sides,
        #            damage_bonus, projectile_color, projectile_symbol, label
        self.ranged = ranged

        # Spell-like abilities (list of dicts, or None)
        # Each: type, name, range, cast_chance, + type-specific fields
        self.spells = spells or []

        # ── Movement & tactical attributes (combat arena) ──
        self.move_range = max(1, move_range)  # squares per combat turn
        self.post_attack_move = max(0, post_attack_move)  # retreat after melee

        # On-hit effects applied when melee attack lands
        # List of dicts: [{type, chance, ...}]
        #   type "poison"  → damage_per_turn, duration
        #   type "stun"    → duration (target skips turns)
        #   type "slow"    → duration (target move_range halved)
        #   type "drain"   → amount (heals monster for that much)
        self.on_hit_effects = on_hit_effects or []

        # Passive abilities always active during combat
        # List of dicts: [{type, ...}]
        #   type "regen"           → amount (HP healed per turn)
        #   type "fire_resistance" → (halves fire damage)  [legacy form]
        #   type "ice_resistance"  → (halves ice damage)   [legacy form]
        #   type "poison_immunity" → (immune to poison status)
        self.passives = passives or []

        # Damage-type resistances and vulnerabilities (modern form).
        # ``resist[]``  halves incoming damage of that type.
        # ``vulnerable[]`` doubles it.  Both are simple lists of strings
        # (e.g. ["fire", "holy"]).  These complement the legacy
        # ``passives`` resistance flags above — both forms are honored
        # in combat's _scale_damage_for_type.
        self.resist = list(resist) if resist else []
        self.vulnerable = list(vulnerable) if vulnerable else []

        # Battle scale: how many tiles wide/tall the monster is in combat.
        # 1 = normal (1x1), 2 = large (2x2), 3 = huge (3x3), etc.
        self.battle_scale = max(1, int(battle_scale))

        # Position on the dungeon map (set by generator)
        self.col = 0
        self.row = 0

    def is_alive(self):
        return self.hp > 0

    def _can_enter(self, col, row, tile_map):
        """Return True if this monster's terrain allows it onto (col, row).

        Sea creatures can only move on water tiles.  Land creatures use
        the normal walkability check (which already excludes water).
        """
        if not (0 <= col < tile_map.width and 0 <= row < tile_map.height):
            return False
        if self.terrain == "sea":
            return tile_map.get_tile(col, row) == TILE_WATER
        return tile_map.is_walkable(col, row)

    def try_move_toward(self, target_col, target_row, tile_map,
                        occupied_positions):
        """
        Attempt to move one step toward the target (the party).

        Uses simple cardinal-direction pursuit: pick the axis with the
        largest gap and try to close it.  If that tile is blocked, try
        the other axis.  If both are blocked, stay put.

        Parameters
        ----------
        target_col, target_row : int
            Where the party is standing.
        tile_map : TileMap
            Used for walkability / terrain checks.
        occupied_positions : set of (col, row)
            Tiles already occupied by other monsters (prevents stacking).
        """
        if not self.is_alive():
            return

        dx = target_col - self.col
        dy = target_row - self.row

        # Determine preferred movement order (largest gap first)
        moves = []
        if abs(dx) >= abs(dy):
            if dx != 0:
                moves.append((1 if dx > 0 else -1, 0))
            if dy != 0:
                moves.append((0, 1 if dy > 0 else -1))
        else:
            if dy != 0:
                moves.append((0, 1 if dy > 0 else -1))
            if dx != 0:
                moves.append((1 if dx > 0 else -1, 0))

        for mc, mr in moves:
            nc, nr = self.col + mc, self.row + mr
            if (self._can_enter(nc, nr, tile_map)
                    and (nc, nr) != (target_col, target_row)
                    and (nc, nr) not in occupied_positions):
                self.col = nc
                self.row = nr
                return

    def try_move_random(self, tile_map, occupied_positions,
                        party_col=None, party_row=None):
        """
        Attempt to move one step in a random cardinal direction.

        The monster picks a random walkable, unoccupied neighbour and
        moves there.  If no direction is free, it stays put.

        Parameters
        ----------
        tile_map : TileMap
            Used for walkability / terrain checks.
        occupied_positions : set of (col, row)
            Tiles already occupied by other monsters.
        party_col, party_row : int or None
            Party position – the monster will avoid stepping onto the
            party tile directly (combat is handled elsewhere).
        """
        if not self.is_alive():
            return

        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        random.shuffle(directions)

        for dc, dr in directions:
            nc, nr = self.col + dc, self.row + dr
            if not self._can_enter(nc, nr, tile_map):
                continue
            if (nc, nr) in occupied_positions:
                continue
            if party_col is not None and (nc, nr) == (party_col, party_row):
                continue
            self.col = nc
            self.row = nr
            return


# ── Monster factory functions ───────────────────────────────────

def create_monster(name):
    """Create a monster by name from the JSON data."""
    data = MONSTERS.get(name)
    if not data:
        raise ValueError(f"Unknown monster: {name}")
    return Monster(
        name=name,
        hp=data["hp"],
        ac=data["ac"],
        attack_bonus=data["attack_bonus"],
        damage_dice=data.get("damage_dice", 1),
        damage_sides=data.get("damage_sides", 4),
        damage_bonus=data.get("damage_bonus", 0),
        xp_reward=data.get("xp_reward", 25),
        gold_reward=random.randint(
            data.get("gold_min", 5), data.get("gold_max", 15)),
        color=tuple(data.get("color", [200, 50, 50])),
        tile=data.get("tile"),
        undead=data.get("undead", False),
        humanoid=data.get("humanoid", False),
        terrain=data.get("terrain", "land"),
        ranged=data.get("ranged"),
        spells=data.get("spells"),
        move_range=data.get("move_range", 1),
        post_attack_move=data.get("post_attack_move", 0),
        on_hit_effects=data.get("on_hit_effects"),
        passives=data.get("passives"),
        resist=data.get("resist"),
        vulnerable=data.get("vulnerable"),
        battle_scale=data.get("battle_scale", 1),
    )


def create_random_monster(table="dungeon"):
    """Pick a random monster using weighted spawn tables from JSON."""
    pool = SPAWN_TABLES.get(table, list(MONSTERS.keys()))
    # Build weighted list from spawn_weight values
    weighted = []
    for name in pool:
        data = MONSTERS.get(name)
        if data:
            weighted.append((name, data.get("spawn_weight", 20)))
    if not weighted:
        # Fallback to first monster
        return create_monster(list(MONSTERS.keys())[0])

    total = sum(w for _, w in weighted)
    roll = random.randint(1, total)
    cumulative = 0
    for name, weight in weighted:
        cumulative += weight
        if roll <= cumulative:
            return create_monster(name)
    # Shouldn't reach here, but just in case
    return create_monster(weighted[0][0])


# ── Encounter templates ─────────────────────────────────────────

_ENCOUNTER_DATA = _load_json("encounters.json")

ENCOUNTERS = _ENCOUNTER_DATA.get("encounters", {})


def _monster_difficulty(name):
    """Return the difficulty tier set on monster *name*, or ``"any"``.

    A monster with no ``difficulty`` field — or with the explicit
    sentinel ``"any"`` — is treated as a wildcard that fits any
    dungeon tier.  Used by the dungeon-difficulty encounter filter.
    """
    data = MONSTERS.get(name) or {}
    return data.get("difficulty", "any") or "any"


def _encounter_matches_difficulty(enc, dungeon_difficulty):
    """True if every monster in *enc* fits the dungeon tier.

    A monster fits when its difficulty is exactly the dungeon's
    difficulty OR the wildcard ``"any"`` (which is also the default
    for untagged monsters).  Empty encounters fail closed — they have
    no monsters that could match.
    """
    monster_names = enc.get("monsters") or []
    if not monster_names:
        return False
    for name in monster_names:
        tier = _monster_difficulty(name)
        if tier != "any" and tier != dungeon_difficulty:
            return False
    return True


def create_encounter(area="dungeon", terrain="land",
                     min_level=None, max_level=None,
                     dungeon_difficulty=None):
    """Pick a random encounter template matching *terrain* and level range.

    Parameters
    ----------
    area : str
        Encounter pool key (``"overworld"``, ``"dungeon"``, etc.).
    terrain : str
        ``"land"`` or ``"sea"``.  Only encounters whose ``"terrain"``
        field matches are eligible.  Encounters without the field
        default to ``"land"``.
    min_level : int or None
        If set, only encounters with ``"level" >= min_level`` are eligible.
    max_level : int or None
        If set, only encounters with ``"level" <= max_level`` are eligible.
    dungeon_difficulty : str or None
        When set (one of ``"easy"``, ``"normal"``, ``"hard"``,
        ``"deadly"``), restrict the pool to encounters where every
        constituent monster has ``difficulty`` equal to this value or
        the wildcard ``"any"``.  Untagged monsters (no ``difficulty``
        field at all) count as wildcards.  This is what lets a player
        say "easy dungeons should only have rats and wolves" by
        tagging tougher creatures with their proper tier.  ``None``
        skips this filter entirely (current behaviour for the
        overworld and other non-tier-aware callers).

    Returns a dict with keys:
        name : str            — display name (e.g. "Goblin Ambush")
        monsters : list       — list of Monster objects
        monster_party_tile : str — monster name whose sprite represents
                                   the group on the map
        level : int           — encounter difficulty level (1-8)
    Uses weighted random selection from data/encounters.json.
    """
    all_pool = ENCOUNTERS.get(area, [])
    # Filter by terrain
    pool = [e for e in all_pool if e.get("terrain", "land") == terrain]
    # Filter by level range
    if min_level is not None:
        pool = [e for e in pool if e.get("level", 1) >= min_level]
    if max_level is not None:
        pool = [e for e in pool if e.get("level", 1) <= max_level]
    # Filter by per-monster difficulty tier.  An encounter is eligible
    # only when EVERY monster in it is either untagged ("any" or
    # missing) or tagged with the dungeon's exact difficulty.  This
    # implements the "exact tier" rule the editor exposes: tagging
    # Dragon = "deadly" pulls it from every easy/normal/hard pool.
    if dungeon_difficulty:
        pool = [e for e in pool
                if _encounter_matches_difficulty(e, dungeon_difficulty)]
    if not pool:
        # No encounters for this terrain — return None so caller can skip
        if terrain != "land":
            return None
        # When a dungeon-difficulty filter is active, an empty pool
        # means no on-tier encounters exist for this slice.  Return
        # None instead of falling back to a random monster, which
        # could pull a creature from any tier and undo the author's
        # tagging.  Caller (e.g. generate_dungeon) will leave the
        # room empty.
        if dungeon_difficulty:
            return None
        # Fallback for land if no templates at all
        m = create_random_monster(area)
        return {"name": m.name, "monsters": [m],
                "monster_party_tile": m.name}

    total = sum(e.get("weight", 10) for e in pool)
    roll = random.randint(1, total)
    cumulative = 0
    chosen = pool[0]
    for entry in pool:
        cumulative += entry.get("weight", 10)
        if roll <= cumulative:
            chosen = entry
            break

    enc_name = chosen.get("name", "Encounter")
    enc_level = chosen.get("level", 1)
    # ``monster_party_tile`` chooses which monster's sprite represents
    # the group on the map.  Some authored encounters have the key
    # present but blank ("") — dict.get's default only fires when the
    # key is missing, so an explicit empty string sneaks through and
    # later crashes ``create_monster("")``.  Treat empty/None the
    # same as missing and fall back to the first monster in the
    # encounter's ``monsters`` list.
    chosen_monsters = chosen.get("monsters") or []
    party_tile = chosen.get("monster_party_tile")
    if not party_tile:
        party_tile = chosen_monsters[0] if chosen_monsters else None
    monsters = []
    for name in chosen_monsters:
        if not name:
            continue  # skip blank entries in the monster list
        monsters.append(create_monster(name))
    if not monsters:
        # Same reasoning as the empty-pool branch: don't smuggle in
        # an off-tier random monster when difficulty filtering is on.
        if dungeon_difficulty:
            return None
        m = create_random_monster(area)
        return {"name": m.name, "monsters": [m],
                "monster_party_tile": m.name, "level": 1}
    return {"name": enc_name, "monsters": monsters,
            "monster_party_tile": party_tile, "level": enc_level}


def find_encounter_template(name):
    """Return the raw encounter template dict with ``name`` or None.

    Searches every bucket in ``ENCOUNTERS`` (dungeon / overworld /
    house_basement / …) so map-editor placements — which only store
    the encounter's display name — can be resolved regardless of
    which bucket the template was authored into. Returns the first
    match; template names should be unique but if they collide the
    first bucket wins.
    """
    if not isinstance(ENCOUNTERS, dict):
        return None
    for bucket in ENCOUNTERS.values():
        if not isinstance(bucket, list):
            continue
        for entry in bucket:
            if isinstance(entry, dict) and entry.get("name") == name:
                return entry
    return None


def create_encounter_from_template(name):
    """Build a combat-ready encounter dict from a named template.

    Mirrors the return shape of :func:`create_encounter` so existing
    code that consumes ``create_encounter()`` (or the
    ``encounter_template`` attribute set on spawned "party leader"
    monsters) works unchanged::

        {"name": str,
         "monsters": [Monster, ...],
         "monster_party_tile": str,
         "level": int,
         "xp_override": int | None,
         "loot": list[dict] | None}

    Returns None if the template name isn't found. Extra fields
    (``xp_override``, ``loot``) are forwarded so downstream combat
    code can honour the template's custom rewards — combat code
    that doesn't know about them simply ignores the extras.
    """
    tmpl = find_encounter_template(name)
    if tmpl is None:
        return None
    enc_name = tmpl.get("name", name)
    enc_level = tmpl.get("level", 1)
    monster_names = list(tmpl.get("monsters", []))
    party_tile = tmpl.get("monster_party_tile")
    if not party_tile and monster_names:
        party_tile = monster_names[0]
    monsters = [create_monster(n) for n in monster_names]
    # If every monster name was unknown we'd end up with an empty
    # list — fall back to a single generic monster so combat can
    # still start rather than crashing on an empty party.
    if not monsters:
        monsters = [create_random_monster("dungeon")]
        if not party_tile:
            party_tile = monsters[0].name
    return {
        "name": enc_name,
        "monsters": monsters,
        "monster_party_tile": party_tile,
        "level": enc_level,
        "xp_override": tmpl.get("xp_override"),
        "loot": tmpl.get("loot") or None,
    }


def reload_module_data(module_data_dir=None):
    """Reload monster and encounter data from a module directory.

    If *module_data_dir* is None, reloads from the default ``data/`` folder.
    """
    global MONSTERS, SPAWN_TABLES, ENCOUNTERS, _module_data_dir

    _module_data_dir = module_data_dir

    monster_data = _load_json("monsters.json", module_data_dir)
    MONSTERS = monster_data["monsters"]
    SPAWN_TABLES = monster_data.get("spawn_tables", {})

    encounter_data = _load_json("encounters.json", module_data_dir)
    ENCOUNTERS = encounter_data.get("encounters", {})


# ── Legacy factory functions (for backward compatibility) ───────

def create_giant_rat():
    return create_monster("Giant Rat")

def create_skeleton():
    return create_monster("Skeleton")

def create_orc():
    return create_monster("Orc")
