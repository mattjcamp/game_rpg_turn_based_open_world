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
