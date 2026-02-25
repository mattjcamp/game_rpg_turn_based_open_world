"""
Party management – Ultima III style.

Each character has a race, class, and four attributes: STR, DEX, INT, WIS.
Magic points are derived from INT (sorcerer) or WIS (priest) depending on
class.  Damage uses (weapon_power + 1.5 * STR).  Evasion comes from armor.
"""


# ── Weapon table ──────────────────────────────────────────────────
WEAPONS = {
    "Dagger":       {"power": 1, "ranged": False},
    "Mace":         {"power": 2, "ranged": False},
    "Sling":        {"power": 3, "ranged": True},
    "Axe":          {"power": 4, "ranged": False},
    "Sword":        {"power": 5, "ranged": False},
    "Spear":        {"power": 6, "ranged": False},
    "Broad Axe":    {"power": 7, "ranged": False},
    "Bow":          {"power": 7, "ranged": True},
    "Iron Sword":   {"power": 8, "ranged": False},
    "Gloves":       {"power": 8, "ranged": False},
    "Halberd":      {"power": 9, "ranged": False},
    "Silver Bow":   {"power": 9, "ranged": True},
    "Sun Sword":    {"power": 10, "ranged": False},
    "Mystic Sword": {"power": 10, "ranged": False},
    "Fists":        {"power": 0, "ranged": False},
}

# ── Armor table ───────────────────────────────────────────────────
ARMORS = {
    "Cloth":     {"evasion": 50},
    "Leather":   {"evasion": 56},
    "Chain":     {"evasion": 58},
    "Plate":     {"evasion": 60},
    "+2 Chain":  {"evasion": 62},
    "+2 Plate":  {"evasion": 64},
    "Exotic":    {"evasion": 67},
}


class PartyMember:
    """A single character in the party."""

    def __init__(self, name, char_class, race="Human",
                 hp=20, strength=10, dexterity=10,
                 intelligence=10, wisdom=10, level=1):
        self.name = name
        self.char_class = char_class
        self.race = race

        self.max_hp = hp
        self.hp = hp
        self.strength = strength
        self.dexterity = dexterity
        self.intelligence = intelligence
        self.wisdom = wisdom
        self.level = level
        self.exp = 0

        self.weapon = "Fists"
        self.armor = "Cloth"

    # ── Derived stats ──────────────────────────────────────────

    @property
    def mp(self):
        """Magic points depend on class and relevant mental stat."""
        cls = self.char_class.lower()
        if cls in ("wizard", "alchemist"):
            return self.intelligence
        elif cls in ("cleric", "illusionist"):
            return self.wisdom
        elif cls == "lark":
            return self.intelligence // 2
        elif cls == "paladin":
            return self.wisdom // 2
        elif cls == "druid":
            return max(self.intelligence, self.wisdom) // 2
        elif cls == "ranger":
            return min(self.intelligence, self.wisdom) // 2
        return 0

    @property
    def max_mp(self):
        """MP cap equals the derived mp value."""
        return self.mp

    def is_alive(self):
        return self.hp > 0

    # ── Combat helpers ─────────────────────────────────────────

    def get_modifier(self, stat_value):
        """D&D ability modifier: (stat - 10) // 2."""
        return (stat_value - 10) // 2

    @property
    def str_mod(self):
        return self.get_modifier(self.strength)

    @property
    def dex_mod(self):
        return self.get_modifier(self.dexterity)

    @property
    def int_mod(self):
        return self.get_modifier(self.intelligence)

    @property
    def wis_mod(self):
        return self.get_modifier(self.wisdom)

    def get_ac(self):
        """Armor class based on armor evasion + DEX modifier."""
        base = ARMORS.get(self.armor, {"evasion": 50})["evasion"]
        return 10 + self.dex_mod + (base - 50) // 5

    def get_attack_bonus(self):
        """Melee attack bonus: STR modifier (+ weapon bonus later)."""
        return self.str_mod

    def get_weapon_power(self):
        """Return the equipped weapon's power rating."""
        return WEAPONS.get(self.weapon, {"power": 0})["power"]

    def get_damage(self):
        """Ultima III damage: weapon power + 1.5 * STR (min 1)."""
        wp = self.get_weapon_power()
        return max(1, int(wp + 1.5 * self.strength))

    def get_damage_dice(self):
        """Return (count, sides, bonus) for weapon damage.
        Uses weapon power to determine dice size, STR as bonus."""
        wp = self.get_weapon_power()
        if wp <= 2:
            return (1, 4, self.str_mod)
        elif wp <= 5:
            return (1, 6, self.str_mod)
        elif wp <= 8:
            return (1, 8, self.str_mod)
        else:
            return (1, 10, self.str_mod)

    def is_ranged(self):
        """True if the equipped weapon can attack at range."""
        return WEAPONS.get(self.weapon, {"ranged": False})["ranged"]

    # ── Magic helpers ──────────────────────────────────────────

    def can_cast_priest(self):
        cls = self.char_class.lower()
        return cls in ("cleric", "paladin", "illusionist", "druid", "ranger")

    def can_cast_sorcerer(self):
        cls = self.char_class.lower()
        return cls in ("wizard", "lark", "alchemist", "druid", "ranger")


class Party:
    """
    The adventuring party.

    Holds up to 4 members and a position on the current map.
    """

    def __init__(self, start_col, start_row):
        self.col = start_col
        self.row = start_row
        self.members = []
        self.gold = 100  # Shared party gold

    def add_member(self, member):
        """Add a party member (max 4)."""
        if len(self.members) < 4:
            self.members.append(member)
            return True
        return False

    def try_move(self, dcol, drow, tile_map):
        """
        Attempt to move the party by (dcol, drow).
        Returns True if the move succeeded, False if blocked.
        """
        new_col = self.col + dcol
        new_row = self.row + drow
        if tile_map.is_walkable(new_col, new_row):
            self.col = new_col
            self.row = new_row
            return True
        return False

    def get_position(self):
        return (self.col, self.row)

    def alive_members(self):
        """Return list of alive party members."""
        return [m for m in self.members if m.is_alive()]


def create_default_party(start_col, start_row):
    """Create a classic balanced party of 4 characters (Ultima III style)."""
    party = Party(start_col, start_row)

    # 1. Dwarf Fighter — front-line tank, best weapons/armor
    roland = PartyMember(
        "Roland", "Fighter", race="Dwarf",
        hp=30, strength=16, dexterity=12,
        intelligence=8, wisdom=10, level=1,
    )
    roland.weapon = "Iron Sword"
    roland.armor = "Chain"
    party.add_member(roland)

    # 2. Bobbit Cleric — healer, priest spells, decent armor
    mira = PartyMember(
        "Mira", "Cleric", race="Bobbit",
        hp=22, strength=10, dexterity=10,
        intelligence=10, wisdom=18, level=1,
    )
    mira.weapon = "Mace"
    mira.armor = "Chain"
    party.add_member(mira)

    # 3. Fuzzy Wizard — nuker, mass-destruction spells
    theron = PartyMember(
        "Theron", "Wizard", race="Fuzzy",
        hp=14, strength=6, dexterity=14,
        intelligence=20, wisdom=8, level=1,
    )
    theron.weapon = "Dagger"
    theron.armor = "Cloth"
    party.add_member(theron)

    # 4. Elf Thief — trap disarmer, ranged attacks, high evasion
    sable = PartyMember(
        "Sable", "Thief", race="Elf",
        hp=20, strength=12, dexterity=18,
        intelligence=10, wisdom=8, level=1,
    )
    sable.weapon = "Bow"
    sable.armor = "Leather"
    party.add_member(sable)

    return party
