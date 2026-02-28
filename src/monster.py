"""
Monster definitions for combat encounters.

Loads monster stats from data/monsters.json so new creatures can be added
or tweaked without touching code. Each monster has D&D-style stats: HP,
AC, attack bonus, damage dice, and rewards (XP and gold).
"""

import json
import os
import random


# ── Load monster data from JSON ─────────────────────────────────

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "monsters.json")

with open(_DATA_PATH, "r") as f:
    _MONSTER_DATA = json.load(f)

MONSTERS = _MONSTER_DATA["monsters"]
SPAWN_TABLES = _MONSTER_DATA.get("spawn_tables", {})


class Monster:
    """A hostile creature the party can fight."""

    def __init__(self, name, hp, ac, attack_bonus,
                 damage_dice=1, damage_sides=4, damage_bonus=0,
                 xp_reward=25, gold_reward=10, color=(200, 50, 50),
                 tile=None, undead=False):
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

        # Position on the dungeon map (set by generator)
        self.col = 0
        self.row = 0

    def is_alive(self):
        return self.hp > 0

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
            Used for walkability checks.
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
            if (tile_map.is_walkable(nc, nr)
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
            Used for walkability checks.
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
            if not tile_map.is_walkable(nc, nr):
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


# ── Legacy factory functions (for backward compatibility) ───────

def create_giant_rat():
    return create_monster("Giant Rat")

def create_skeleton():
    return create_monster("Skeleton")

def create_orc():
    return create_monster("Orc")
