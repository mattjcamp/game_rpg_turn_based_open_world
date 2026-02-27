"""
Party management – Ultima III style.

Each character has a race, class, and four attributes: STR, DEX, INT, WIS.
Magic points are derived from INT (sorcerer) or WIS (priest) depending on
class.  Damage uses (weapon_power + 1.5 * STR).  Evasion comes from armor.
"""


# ── Weapon table ──────────────────────────────────────────────────
WEAPONS = {
    "Dagger":       {"power": 1, "ranged": True, "consumable": True},
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


# ── Item descriptions & visual metadata ──────────────────────────
# Each entry: { "desc": str, "icon": str (for pixel-art type) }
# icon types: "sword", "axe", "bow", "dagger", "mace", "spear",
#             "halberd", "gloves", "armor_light", "armor_heavy",
#             "shield", "potion", "herb", "scroll", "torch", "rope",
#             "tool", "bomb", "holy", "gem"
ITEM_INFO = {
    # ── Weapons ──
    "Fists":        {"desc": "Bare knuckles. Not much, but always available.",
                     "icon": "gloves"},
    "Dagger":       {"desc": "A short, light blade. Can be thrown at enemies.",
                     "icon": "dagger"},
    "Mace":         {"desc": "A heavy flanged club, favored by clerics.",
                     "icon": "mace"},
    "Sling":        {"desc": "A simple ranged weapon that hurls stones.",
                     "icon": "bow"},
    "Axe":          {"desc": "A single-headed battle axe. Reliable and brutal.",
                     "icon": "axe"},
    "Sword":        {"desc": "A well-balanced longsword. Standard fighter fare.",
                     "icon": "sword"},
    "Spear":        {"desc": "A long thrusting weapon with good reach.",
                     "icon": "spear"},
    "Broad Axe":    {"desc": "A massive double-headed axe. Devastating blows.",
                     "icon": "axe"},
    "Bow":          {"desc": "A sturdy longbow. Excellent at range.",
                     "icon": "bow"},
    "Iron Sword":   {"desc": "A finely forged iron blade. Sharp and durable.",
                     "icon": "sword"},
    "Gloves":       {"desc": "Enchanted gauntlets that strike with magic force.",
                     "icon": "gloves"},
    "Halberd":      {"desc": "A polearm combining axe and spear. Fearsome reach.",
                     "icon": "halberd"},
    "Silver Bow":   {"desc": "A silver-inlaid bow. Deadly against the undead.",
                     "icon": "bow"},
    "Sun Sword":    {"desc": "A radiant blade infused with solar energy.",
                     "icon": "sword"},
    "Mystic Sword": {"desc": "An ancient blade pulsing with arcane power.",
                     "icon": "sword"},
    # ── Armor ──
    "Cloth":        {"desc": "Simple cloth garments. Minimal protection.",
                     "icon": "armor_light"},
    "Leather":      {"desc": "Toughened leather armor. Light and flexible.",
                     "icon": "armor_light"},
    "Chain":        {"desc": "Interlocking metal rings. Good all-round defense.",
                     "icon": "armor_heavy"},
    "Plate":        {"desc": "Heavy steel plates. Excellent protection.",
                     "icon": "armor_heavy"},
    "+2 Chain":     {"desc": "Enchanted chainmail. Magically reinforced links.",
                     "icon": "armor_heavy"},
    "+2 Plate":     {"desc": "Enchanted plate armor. Nearly impenetrable.",
                     "icon": "armor_heavy"},
    "Exotic":       {"desc": "Mysterious armor of unknown origin. Supreme defense.",
                     "icon": "armor_heavy"},
    # ── General items ──
    "Healing Herb":  {"desc": "A fragrant herb that restores a small amount of HP.",
                      "icon": "herb"},
    "Antidote":      {"desc": "A bitter tincture that cures poison.",
                      "icon": "potion"},
    "Torch":         {"desc": "A wooden torch. Lights the way in dark places.",
                      "icon": "torch"},
    "Rope":          {"desc": "A sturdy hemp rope. Useful for climbing.",
                      "icon": "rope"},
    "Holy Water":    {"desc": "Blessed water from a sacred spring. Burns the undead.",
                      "icon": "holy"},
    "Scroll of Fire":{"desc": "A single-use scroll containing a fire spell.",
                      "icon": "scroll"},
    "Mana Potion":   {"desc": "A shimmering blue liquid that restores magic points.",
                      "icon": "potion"},
    "Lockpick":      {"desc": "A set of fine tools for opening locked chests.",
                      "icon": "tool"},
    "Smoke Bomb":    {"desc": "A small bomb that creates a blinding cloud.",
                      "icon": "bomb"},
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

        # Equipment slots: body armor, melee weapon, ranged weapon
        self.equipped = {
            "body": "Cloth",
            "melee": "Fists",
            "ranged": None,       # None means no ranged weapon equipped
        }

        # Inventory — list of item name strings the character is carrying
        self.inventory = []

        # Mutable MP pool — initialized lazily on first access
        self._current_mp = None

        # Ammo tracking for consumable ranged weapons {weapon_name: count}
        self.ammo = {}

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

    @property
    def current_mp(self):
        """Mutable MP pool. Initializes to max_mp on first access."""
        if self._current_mp is None:
            self._current_mp = self.mp
        return self._current_mp

    @current_mp.setter
    def current_mp(self, value):
        self._current_mp = max(0, min(value, self.max_mp))

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
        """True if the equipped weapon can attack at range and has ammo (if consumable)."""
        wdata = WEAPONS.get(self.weapon, {"ranged": False})
        if not wdata.get("ranged", False):
            return False
        # Consumable weapons need ammo to fire
        if wdata.get("consumable", False):
            return self.get_ammo() > 0
        return True

    def is_consumable_weapon(self):
        """True if the equipped weapon is consumed on ranged use."""
        return WEAPONS.get(self.weapon, {}).get("consumable", False)

    def get_ammo(self):
        """Return current ammo count for the equipped weapon."""
        return self.ammo.get(self.weapon, 0)

    def consume_ammo(self):
        """Use one ammo for the equipped weapon. Returns True if successful."""
        if self.weapon in self.ammo and self.ammo[self.weapon] > 0:
            self.ammo[self.weapon] -= 1
            return True
        return False

    # ── Magic helpers ──────────────────────────────────────────

    def can_cast_priest(self):
        cls = self.char_class.lower()
        return cls in ("cleric", "paladin", "illusionist", "druid", "ranger")

    def can_cast_sorcerer(self):
        cls = self.char_class.lower()
        return cls in ("wizard", "lark", "alchemist", "druid", "ranger")

    # ── Equipment management ──────────────────────────────────

    # Default items for each slot (cannot be unequipped below these)
    _SLOT_DEFAULTS = {"body": "Cloth", "melee": "Fists", "ranged": None}

    def _determine_slot(self, item_name):
        """Return the equipment slot for an item, or None if not equippable."""
        if item_name in ARMORS:
            return "body"
        wp = WEAPONS.get(item_name)
        if wp:
            return "ranged" if wp.get("ranged", False) else "melee"
        return None

    def equip_item(self, item_name):
        """Equip an item from inventory to the appropriate slot.

        Returns True if the item was equipped, False otherwise.
        The previously equipped item in that slot (if any) is moved to inventory.
        """
        if item_name not in self.inventory:
            return False
        slot = self._determine_slot(item_name)
        if slot is None:
            return False

        # Move the currently equipped item back to inventory (if not a default)
        old_item = self.equipped.get(slot)
        if old_item and old_item != self._SLOT_DEFAULTS.get(slot):
            self.inventory.append(old_item)

        # Remove from inventory and equip
        self.inventory.remove(item_name)
        self.equipped[slot] = item_name

        # Sync legacy fields used by combat engine
        self._sync_legacy_fields()
        return True

    def unequip_slot(self, slot):
        """Unequip the item in the given slot, moving it to inventory.

        Returns True if something was unequipped, False if slot was already
        empty or at its default.
        """
        current = self.equipped.get(slot)
        default = self._SLOT_DEFAULTS.get(slot)
        if current is None or current == default:
            return False

        self.inventory.append(current)
        self.equipped[slot] = default

        # Sync legacy fields
        self._sync_legacy_fields()
        return True

    def return_item_to_party(self, item_name, party):
        """Move an item from personal inventory to the party shared stash.

        Returns True if the item was returned, False otherwise.
        """
        if item_name not in self.inventory:
            return False
        self.inventory.remove(item_name)
        party.shared_inventory.append(item_name)
        return True

    def return_equipped_to_party(self, slot, party):
        """Unequip an item and send it to the party shared stash.

        Returns True if something was returned, False if slot was at default.
        """
        current = self.equipped.get(slot)
        default = self._SLOT_DEFAULTS.get(slot)
        if current is None or current == default:
            return False
        party.shared_inventory.append(current)
        self.equipped[slot] = default
        self._sync_legacy_fields()
        return True

    def _sync_legacy_fields(self):
        """Keep the old .weapon and .armor fields in sync with equipped dict."""
        self.armor = self.equipped.get("body") or "Cloth"
        # Weapon defaults to melee; combat engine uses .weapon for active weapon
        self.weapon = self.equipped.get("melee") or "Fists"


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
        self.shared_inventory = []  # Party-wide item pool

    def give_item_to_member(self, item_index, member_index):
        """Move an item from shared inventory to a party member's inventory.

        Returns True if successful, False otherwise.
        """
        if item_index < 0 or item_index >= len(self.shared_inventory):
            return False
        if member_index < 0 or member_index >= len(self.members):
            return False
        item = self.shared_inventory.pop(item_index)
        self.members[member_index].inventory.append(item)
        return True

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
    roland.equipped = {"body": "Chain", "melee": "Iron Sword", "ranged": None}
    roland.inventory = ["Torch", "Healing Herb", "Rope"]
    party.add_member(roland)

    # 2. Bobbit Cleric — healer, priest spells, decent armor
    mira = PartyMember(
        "Mira", "Cleric", race="Bobbit",
        hp=22, strength=10, dexterity=10,
        intelligence=10, wisdom=18, level=1,
    )
    mira.weapon = "Mace"
    mira.armor = "Chain"
    mira.equipped = {"body": "Chain", "melee": "Mace", "ranged": "Sling"}
    mira.inventory = ["Holy Water", "Healing Herb", "Antidote"]
    party.add_member(mira)

    # 3. Fuzzy Wizard — nuker, mass-destruction spells
    theron = PartyMember(
        "Theron", "Wizard", race="Fuzzy",
        hp=14, strength=6, dexterity=14,
        intelligence=20, wisdom=8, level=1,
    )
    theron.weapon = "Dagger"
    theron.armor = "Cloth"
    theron.equipped = {"body": "Cloth", "melee": "Dagger", "ranged": None}
    theron.inventory = ["Scroll of Fire", "Mana Potion", "Torch"]
    party.add_member(theron)

    # 4. Elf Thief — trap disarmer, thrown daggers, high evasion
    sable = PartyMember(
        "Sable", "Thief", race="Elf",
        hp=20, strength=12, dexterity=18,
        intelligence=10, wisdom=8, level=1,
    )
    sable.weapon = "Dagger"
    sable.armor = "Leather"
    sable.equipped = {"body": "Leather", "melee": "Sword", "ranged": "Dagger"}
    sable.ammo = {"Dagger": 5}
    sable.inventory = ["Lockpick", "Smoke Bomb", "Healing Herb", "Torch"]
    party.add_member(sable)

    # Shared party stash
    party.shared_inventory = [
        "Healing Herb", "Healing Herb", "Antidote",
        "Torch", "Torch",
        "Leather", "Axe", "Bow",
    ]

    return party
