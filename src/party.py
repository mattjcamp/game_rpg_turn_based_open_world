"""
Party management.

The party is the group of 4 adventurers the player controls.
On the overworld, they move as a single unit. In combat, they
act individually (to be implemented later).

For now, this tracks the party's position on the map and handles
movement with collision checking.
"""


class PartyMember:
    """A single character in the party."""

    def __init__(self, name, char_class, hp=20, mp=5, strength=10,
                 dexterity=10, intelligence=10, level=1):
        self.name = name
        self.char_class = char_class
        self.max_hp = hp
        self.hp = hp
        self.max_mp = mp
        self.mp = mp
        self.strength = strength
        self.dexterity = dexterity
        self.intelligence = intelligence
        self.level = level
        self.exp = 0
        self.gold = 0
        self.weapon = "Fists"
        self.armor = "Cloth"

    def is_alive(self):
        return self.hp > 0

    # ----- D&D-style combat helpers -----

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

    def get_ac(self):
        """Armor class: 10 + DEX modifier (+ armor bonus later)."""
        return 10 + self.dex_mod

    def get_attack_bonus(self):
        """Melee attack bonus: STR modifier (+ weapon bonus later)."""
        return self.str_mod

    def get_damage_dice(self):
        """Return (count, sides, bonus) for weapon damage.
        For now, weapon type determines dice. Fists = 1d4+STR."""
        weapon_table = {
            "Fists":       (1, 4, self.str_mod),
            "Short Sword": (1, 6, self.str_mod),
            "Long Sword":  (1, 8, self.str_mod),
            "Mace":        (1, 6, self.str_mod),
            "Dagger":      (1, 4, self.dex_mod),  # finesse
            "Staff":       (1, 6, self.int_mod),
        }
        return weapon_table.get(self.weapon, (1, 4, self.str_mod))


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


def create_default_party(start_col, start_row):
    """Create a starter party of 4 characters for testing."""
    party = Party(start_col, start_row)
    roland = PartyMember("Roland", "Fighter",
                         hp=30, mp=0, strength=16, dexterity=12, intelligence=8)
    roland.weapon = "Long Sword"
    roland.armor = "Chain Mail"
    party.add_member(roland)

    mira = PartyMember("Mira", "Cleric",
                       hp=22, mp=15, strength=10, dexterity=10, intelligence=14)
    mira.weapon = "Mace"
    mira.armor = "Chain Mail"
    party.add_member(mira)

    theron = PartyMember("Theron", "Mage",
                         hp=16, mp=25, strength=8, dexterity=10, intelligence=18)
    theron.weapon = "Staff"
    theron.armor = "Cloth"
    party.add_member(theron)

    sable = PartyMember("Sable", "Thief",
                        hp=20, mp=5, strength=12, dexterity=18, intelligence=10)
    sable.weapon = "Dagger"
    sable.armor = "Leather"
    party.add_member(sable)
    return party
