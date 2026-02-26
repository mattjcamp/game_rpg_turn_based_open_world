"""
Monster definitions for combat encounters.

Each monster has D&D-style stats: HP, AC, attack bonus, damage dice,
and rewards (XP and gold). Factory functions create specific monster types.
"""

import random


class Monster:
    """A hostile creature the party can fight."""

    def __init__(self, name, hp, ac, attack_bonus,
                 damage_dice=1, damage_sides=4, damage_bonus=0,
                 xp_reward=25, gold_reward=10, color=(200, 50, 50)):
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
        self.color = color  # For rendering on map and in combat

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


# ----- Monster factory functions -----

def create_giant_rat():
    """A large rat. Weak but fast."""
    return Monster(
        name="Giant Rat",
        hp=8, ac=12, attack_bonus=2,
        damage_dice=1, damage_sides=4, damage_bonus=0,
        xp_reward=15, gold_reward=random.randint(2, 8),
        color=(140, 100, 80),
    )


def create_skeleton():
    """An undead skeleton warrior. Medium difficulty."""
    return Monster(
        name="Skeleton",
        hp=16, ac=13, attack_bonus=3,
        damage_dice=1, damage_sides=6, damage_bonus=1,
        xp_reward=30, gold_reward=random.randint(5, 20),
        color=(220, 220, 200),
    )


def create_orc():
    """A brutal orc. Tough fight."""
    return Monster(
        name="Orc",
        hp=22, ac=13, attack_bonus=5,
        damage_dice=1, damage_sides=8, damage_bonus=2,
        xp_reward=50, gold_reward=random.randint(10, 30),
        color=(80, 140, 60),
    )


def create_random_monster():
    """Pick a random monster appropriate for early-game dungeons."""
    roll = random.random()
    if roll < 0.4:
        return create_giant_rat()
    elif roll < 0.75:
        return create_skeleton()
    else:
        return create_orc()
