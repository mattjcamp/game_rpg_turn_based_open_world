"""
D&D-style combat engine.

Handles dice rolling, attack resolution, damage calculation,
and initiative. All the math lives here so combat states just
call these functions.
"""

import random


def roll_dice(count, sides):
    """Roll <count>d<sides> and return the total."""
    return sum(random.randint(1, sides) for _ in range(count))


def roll_d20():
    """Roll a single d20."""
    return random.randint(1, 20)


def get_modifier(stat_value):
    """D&D ability modifier: (stat - 10) // 2."""
    return (stat_value - 10) // 2


def roll_initiative(dex_mod):
    """Roll initiative: d20 + DEX modifier."""
    roll = roll_d20()
    return roll + dex_mod, roll


def roll_attack(attack_bonus, defender_ac):
    """
    Roll a melee attack: d20 + attack_bonus vs defender_ac.

    Returns:
        (hit: bool, roll: int, total: int, critical: bool)
    """
    roll = roll_d20()
    total = roll + attack_bonus
    critical = (roll == 20)
    # Natural 20 always hits, natural 1 always misses
    if roll == 1:
        return False, roll, total, False
    if critical:
        return True, roll, total, True
    return total >= defender_ac, roll, total, False


def roll_damage(dice_count, dice_sides, bonus, critical=False):
    """
    Roll damage: <dice_count>d<dice_sides> + bonus.
    On a critical hit, double the dice (not the bonus).
    """
    multiplier = 2 if critical else 1
    damage = roll_dice(dice_count * multiplier, dice_sides) + bonus
    return max(1, damage)  # Minimum 1 damage on a hit


def format_modifier(mod):
    """Format a modifier as +N or -N."""
    return f"+{mod}" if mod >= 0 else str(mod)
