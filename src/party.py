"""
Party management – Ultima III style.

Each character has a race, class, and four attributes: STR, DEX, INT, WIS.
Magic points are derived from INT (sorcerer) or WIS (priest) depending on
class.  Damage uses (weapon_power + 1.5 * STR).  Evasion comes from armor.

Item data (weapons, armors, descriptions, shop prices) is loaded from
data/items.json at startup.  Edit that file to add or tweak items without
touching this code.
"""

from src.data_loader import load_items

# ── Load all item tables from data/items.json ─────────────────────
WEAPONS, ARMORS, ITEM_INFO, SHOP_INVENTORY = load_items()


def get_sell_price(item_name):
    """Return the sell price for an item. Falls back to 5 gold if unlisted."""
    info = SHOP_INVENTORY.get(item_name)
    if info:
        return info["sell"]
    return 5


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

        # Equipment slots: right hand, left hand, body armor, head
        self.equipped = {
            "right_hand": "Fists",
            "left_hand": None,
            "body": "Cloth",
            "head": None,
        }

        # Inventory — list of item name strings the character is carrying
        self.inventory = []

        # Mutable MP pool — initialized lazily on first access
        self._current_mp = None

        # Ammo tracking for throwable weapons {weapon_name: count}
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

    def is_ranged(self, party=None):
        """True if the equipped weapon can attack at range and has ammo.

        Throwable weapons need copies in inventory to throw.
        Ammo weapons (bows) need ammo charges in party shared inventory.
        """
        wdata = WEAPONS.get(self.weapon, {"ranged": False})
        if not wdata.get("ranged", False):
            return False
        # Throwable weapons need items in inventory to throw
        if wdata.get("throwable", False):
            count = self.inventory.count(self.weapon)
            if party:
                count += party.inv_count(self.weapon)
            return count > 0
        # Ammo weapons need charges in shared inventory
        ammo_type = wdata.get("ammo")
        if ammo_type and party:
            return party.inv_get_charges(ammo_type) > 0
        elif ammo_type:
            return False  # No party reference, can't check ammo
        return True

    def is_throwable_weapon(self):
        """True if the equipped weapon is thrown and consumed on ranged use."""
        return WEAPONS.get(self.weapon, {}).get("throwable", False)

    def get_ammo_type(self):
        """Return the ammo item name required by the equipped weapon, or None."""
        return WEAPONS.get(self.weapon, {}).get("ammo")

    def uses_ammo(self):
        """True if the equipped weapon requires ammunition from shared inventory."""
        return self.get_ammo_type() is not None

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

    # Equipment slot order and defaults
    _EQUIP_SLOTS = ["right_hand", "left_hand", "body", "head"]
    _SLOT_LABELS = {
        "right_hand": "RIGHT HAND",
        "left_hand": "LEFT HAND",
        "body": "BODY",
        "head": "HEAD",
    }
    _SLOT_DEFAULTS = {
        "right_hand": "Fists",
        "left_hand": None,
        "body": "Cloth",
        "head": None,
    }

    def _determine_slot(self, item_name):
        """Return the equipment slot for an item, or None if not equippable."""
        if item_name in ARMORS:
            return "body"
        wp = WEAPONS.get(item_name)
        if wp:
            return "right_hand"
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
        # Weapon is in the right hand; combat engine uses .weapon
        self.weapon = self.equipped.get("right_hand") or "Fists"


class Party:
    """
    The adventuring party.

    Holds up to 4 members and a position on the current map.
    """

    # Party-level equipment slot names and defaults
    PARTY_SLOTS = ["light", "navigation", "camping", "special"]
    PARTY_SLOT_LABELS = {
        "light": "LIGHT",
        "navigation": "NAVIGATION",
        "camping": "CAMPING",
        "special": "SPECIAL",
    }
    PARTY_SLOT_DEFAULTS = {"light": None, "navigation": None,
                           "camping": None, "special": None}

    # ── Inventory item helpers ──────────────────────────────────
    # Shared inventory entries can be a plain string ("Sword") or a dict
    # with charges: {"name": "Torch", "charges": 15}.  These helpers
    # let the rest of the code work with either form transparently.

    @staticmethod
    def item_name(entry):
        """Return the display name of an inventory entry (str or dict)."""
        if isinstance(entry, dict):
            return entry["name"]
        return entry

    @staticmethod
    def item_charges(entry):
        """Return charges for an inventory entry, or None if uncharged."""
        if isinstance(entry, dict):
            return entry.get("charges")
        return None

    @staticmethod
    def _make_inv_entry(name, charges=None):
        """Create an inventory entry — plain string if no charges, dict otherwise."""
        if charges is not None:
            return {"name": name, "charges": charges}
        return name

    def _find_inv_index(self, item_name):
        """Find the index of the first inventory entry matching item_name."""
        for i, entry in enumerate(self.shared_inventory):
            if self.item_name(entry) == item_name:
                return i
        return -1

    def inv_count(self, item_name):
        """Count how many inventory entries match item_name."""
        return sum(1 for e in self.shared_inventory
                   if self.item_name(e) == item_name)

    def inv_remove(self, item_name):
        """Remove the first inventory entry matching item_name. Returns the removed entry."""
        idx = self._find_inv_index(item_name)
        if idx >= 0:
            return self.shared_inventory.pop(idx)
        return None

    def inv_names(self):
        """Return a list of display names for all shared inventory entries."""
        return [self.item_name(e) for e in self.shared_inventory]

    def inv_add(self, item_name, charges=None):
        """Add an item to shared inventory, stacking charges if stackable.

        If the item is stackable and already exists in inventory, merge
        the charges into the existing entry instead of creating a new one.
        """
        info = ITEM_INFO.get(item_name, {})
        is_stackable = info.get("stackable", False)
        # Default charges from item data if not specified
        if charges is None:
            charges = info.get("charges")

        if is_stackable and charges is not None:
            # Look for an existing stack to merge into
            idx = self._find_inv_index(item_name)
            if idx >= 0:
                entry = self.shared_inventory[idx]
                if isinstance(entry, dict):
                    entry["charges"] = entry.get("charges", 0) + charges
                    return
            # No existing stack — create a new entry
            self.shared_inventory.append({"name": item_name, "charges": charges})
        elif charges is not None:
            self.shared_inventory.append({"name": item_name, "charges": charges})
        else:
            self.shared_inventory.append(item_name)

    def inv_get_charges(self, item_name):
        """Return the charges on the first inventory entry matching item_name, or 0."""
        idx = self._find_inv_index(item_name)
        if idx < 0:
            return 0
        entry = self.shared_inventory[idx]
        ch = self.item_charges(entry)
        return ch if ch is not None else 0

    def inv_consume_charge(self, item_name):
        """Consume one charge from a stackable item. Returns True if successful.

        Removes the entry entirely when charges reach 0.
        """
        idx = self._find_inv_index(item_name)
        if idx < 0:
            return False
        entry = self.shared_inventory[idx]
        if isinstance(entry, dict) and entry.get("charges", 0) > 0:
            entry["charges"] -= 1
            if entry["charges"] <= 0:
                self.shared_inventory.pop(idx)
            return True
        return False

    # ── Constructor ───────────────────────────────────────────

    def __init__(self, start_col, start_row):
        self.col = start_col
        self.row = start_row
        self.members = []
        self.gold = 100  # Shared party gold
        self.shared_inventory = []  # Party-wide item pool

        # Party-level equipment: 4 utility slots
        self.equipped = {s: None for s in self.PARTY_SLOTS}

    def party_equip(self, item_name, slot):
        """Equip an item from shared inventory into a party slot.

        Preserves charges from the inventory entry if present,
        otherwise loads max charges from ITEM_INFO.
        Returns True if successful.
        """
        idx = self._find_inv_index(item_name)
        if idx < 0:
            return False
        if slot not in self.equipped:
            return False
        # Move current equipped item back to inventory
        old = self.equipped[slot]
        if old is not None:
            self.shared_inventory.append(
                self._make_inv_entry(old["name"], old.get("charges")))
        # Pop the inventory entry (may carry charges)
        inv_entry = self.shared_inventory.pop(idx)
        existing_charges = self.item_charges(inv_entry)
        if existing_charges is not None:
            charges = existing_charges
        else:
            charges = ITEM_INFO.get(item_name, {}).get("charges")
        self.equipped[slot] = {"name": item_name, "charges": charges}
        return True

    def party_unequip(self, slot):
        """Unequip a party slot back to shared inventory.
        Preserves remaining charges on the returned item.
        Returns True if something was unequipped."""
        if slot not in self.equipped:
            return False
        current = self.equipped[slot]
        if current is None:
            return False
        self.shared_inventory.append(
            self._make_inv_entry(current["name"], current.get("charges")))
        self.equipped[slot] = None
        return True

    def get_equipped_name(self, slot):
        """Return the name of the item in the given party slot, or None."""
        entry = self.equipped.get(slot)
        return entry["name"] if entry else None

    def get_equipped_charges(self, slot):
        """Return remaining charges for the given party slot, or None."""
        entry = self.equipped.get(slot)
        if entry is None:
            return None
        return entry.get("charges")

    def give_item_to_member(self, item_index, member_index):
        """Move an item from shared inventory to a party member's inventory.

        Charged items are given as their name only (members don't track charges).
        Returns True if successful, False otherwise.
        """
        if item_index < 0 or item_index >= len(self.shared_inventory):
            return False
        if member_index < 0 or member_index >= len(self.members):
            return False
        entry = self.shared_inventory.pop(item_index)
        self.members[member_index].inventory.append(self.item_name(entry))
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
    """Create a classic balanced party of 4 characters (Ultima III style).

    Everyone starts humble: cloth armor, a simple weapon, and one shared
    torch.  Better gear must be found or purchased.
    """
    party = Party(start_col, start_row)

    # 1. Dwarf Fighter — front-line tank
    roland = PartyMember(
        "Roland", "Fighter", race="Dwarf",
        hp=30, strength=16, dexterity=12,
        intelligence=8, wisdom=10, level=1,
    )
    roland.equipped = {"right_hand": "Club", "left_hand": None, "body": "Cloth", "head": None}
    roland.weapon = "Club"
    roland.armor = "Cloth"
    party.add_member(roland)

    # 2. Bobbit Cleric — healer, priest spells
    mira = PartyMember(
        "Mira", "Cleric", race="Bobbit",
        hp=22, strength=10, dexterity=10,
        intelligence=10, wisdom=18, level=1,
    )
    mira.equipped = {"right_hand": "Club", "left_hand": None, "body": "Cloth", "head": None}
    mira.weapon = "Club"
    mira.armor = "Cloth"
    party.add_member(mira)

    # 3. Fuzzy Wizard — nuker, sorcerer spells
    theron = PartyMember(
        "Theron", "Wizard", race="Fuzzy",
        hp=14, strength=6, dexterity=14,
        intelligence=20, wisdom=8, level=1,
    )
    theron.equipped = {"right_hand": "Dagger", "left_hand": None, "body": "Cloth", "head": None}
    theron.weapon = "Dagger"
    theron.armor = "Cloth"
    party.add_member(theron)

    # 4. Elf Thief — trap disarmer, high evasion
    sable = PartyMember(
        "Sable", "Thief", race="Elf",
        hp=20, strength=12, dexterity=18,
        intelligence=10, wisdom=8, level=1,
    )
    sable.equipped = {"right_hand": "Dagger", "left_hand": None, "body": "Cloth", "head": None}
    sable.weapon = "Dagger"
    sable.armor = "Cloth"
    party.add_member(sable)

    # Shared party stash — start with a torch the player can equip
    # Shared party stash — torch and starting ammo
    party.shared_inventory = ["Torch"]
    party.inv_add("Arrows", charges=10)

    return party
