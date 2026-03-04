"""
Party management – Ultima III style.

Each character has a race, class, and four attributes: STR, DEX, INT, WIS.
Magic points are derived from INT (sorcerer) or WIS (priest) depending on
class.  Damage uses (weapon_power + 1.5 * STR).  Evasion comes from armor.

Item data (weapons, armors, descriptions, shop prices) is loaded from
data/items.json at startup.  Edit that file to add or tweak items without
touching this code.
"""

import json
import os

from src.data_loader import load_items, load_races, _load_json

# ── Default data directory ────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

# ── Active module data directory (None = use defaults) ────────────
_module_data_dir = None

# ── Load all item tables from data/items.json ─────────────────────
WEAPONS, ARMORS, ITEM_INFO, SHOP_INVENTORY = load_items()

# ── Load race definitions from data/races.json ────────────────────
RACE_INFO = load_races()

# ── Load party config from data/party.json ────────────────────────
_PARTY_JSON = os.path.join(_DEFAULT_DATA_DIR, "party.json")

# ── Load effect definitions from data/effects.json ───────────────
_EFFECTS_JSON = os.path.join(_DEFAULT_DATA_DIR, "effects.json")

# ── Load spell definitions from data/spells.json ─────────────────
_SPELLS_JSON = os.path.join(_DEFAULT_DATA_DIR, "spells.json")


def _load_party_config():
    """Load party configuration from the active module or default data/party.json."""
    if _module_data_dir is not None:
        mod_path = os.path.join(_module_data_dir, "party.json")
        if os.path.isfile(mod_path):
            with open(mod_path, "r") as f:
                return json.load(f)
    with open(_PARTY_JSON, "r") as f:
        return json.load(f)


def _roster_member_to_json(member):
    """Serialize a PartyMember into the party.json roster entry format."""
    data = {
        "name": member.name,
        "class": member.char_class,
        "race": member.race,
        "gender": member.gender,
        "hp": member.max_hp,
        "strength": member.strength,
        "dexterity": member.dexterity,
        "intelligence": member.intelligence,
        "wisdom": member.wisdom,
        "level": member.level,
        "equipped": {
            "right_hand": member.equipped.get("right_hand"),
            "left_hand": member.equipped.get("left_hand"),
            "body": member.equipped.get("body"),
            "head": member.equipped.get("head"),
        },
        "inventory": list(member.inventory),
    }
    if member.sprite:
        data["sprite"] = member.sprite
    return data


def save_roster(party):
    """Persist the current roster and active_party back to party.json.

    Saves to the active module's party.json if one is set,
    otherwise to the default data/party.json.
    Preserves non-roster fields (start_position, gold, party_effects,
    inventory, comments) from the existing file and only updates the
    roster and active_party arrays.
    """
    # Read current file so we preserve game-default fields
    cfg = _load_party_config()

    # Update roster and active party
    cfg["roster"] = [_roster_member_to_json(m) for m in party.roster]
    cfg["active_party"] = list(party.active_indices)

    # Determine save path: module dir if set, else default
    save_path = _PARTY_JSON
    if _module_data_dir is not None:
        mod_path = os.path.join(_module_data_dir, "party.json")
        if os.path.isfile(mod_path):
            save_path = mod_path

    with open(save_path, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def _load_effects_config():
    """Load effect definitions from the active module or data/effects.json."""
    return _load_json("effects.json", _module_data_dir)


# Pre-load effect definitions at import time
EFFECTS_DATA = _load_effects_config().get("effects", [])


def _load_spells_config():
    """Load spell definitions from the active module or data/spells.json."""
    return _load_json("spells.json", _module_data_dir)


# Pre-load spell definitions at import time (keyed by spell id)
SPELLS_DATA = {s["id"]: s for s in _load_spells_config().get("spells", [])}


def _load_potions_config():
    """Load potion recipe definitions from the active module or data/potions.json."""
    return _load_json("potions.json", _module_data_dir)


# Pre-load potion recipes at import time
POTIONS_DATA = _load_potions_config()


def reload_module_data(module_data_dir=None):
    """Reload all party-related data from a module directory.

    If *module_data_dir* is None, reloads from the default ``data/`` folder.
    This re-assigns the module-level globals so every module that imported
    them (WEAPONS, ARMORS, etc.) picks up the new values on next access.

    Also clears the class-template cache so classes are re-read from the
    module directory.
    """
    global WEAPONS, ARMORS, ITEM_INFO, SHOP_INVENTORY
    global RACE_INFO, EFFECTS_DATA, SPELLS_DATA, POTIONS_DATA
    global _module_data_dir

    _module_data_dir = module_data_dir

    # Reload items, races
    WEAPONS, ARMORS, ITEM_INFO, SHOP_INVENTORY = load_items(module_data_dir)
    RACE_INFO = load_races(module_data_dir)

    # Reload effects and spells
    EFFECTS_DATA = _load_effects_config().get("effects", [])
    SPELLS_DATA = {s["id"]: s for s in _load_spells_config().get("spells", [])}
    POTIONS_DATA = _load_potions_config()

    # Clear class template cache so they reload from the module directory
    PartyMember._class_templates.clear()


def get_sell_price(item_name):
    """Return the sell price for an item. Falls back to 5 gold if unlisted."""
    info = SHOP_INVENTORY.get(item_name)
    if info:
        return info["sell"]
    return 5


VALID_RACES = ("Human", "Dwarf", "Halfling", "Elf", "Gnome")

class PartyMember:
    """A single character in the party."""

    VALID_GENDERS = ("Male", "Female")

    def __init__(self, name, char_class, race="Human", gender="Male",
                 hp=20, strength=10, dexterity=10,
                 intelligence=10, wisdom=10, level=1, sprite=None):
        self.name = name
        self.char_class = char_class
        self.race = race
        self.gender = gender
        self.sprite = sprite  # custom tile file path (relative to project root)

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

        # Bonus MP gained from leveling up
        self._bonus_mp = 0

        # Ammo tracking for throwable weapons {weapon_name: count}
        self.ammo = {}

        # Potion buffs — consumed at end of next combat
        # Keys: "strength", "ac"; values: int bonus
        self.potion_buffs = {}

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
        """MP cap equals the derived mp value plus any bonus from leveling."""
        return self.mp + self._bonus_mp

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

    # ── Leveling ───────────────────────────────────────────────────

    def check_level_up(self):
        """Check if enough XP has been earned to level up.

        Level N requires N * exp_per_level total XP (from class template):
          e.g. with exp_per_level=500: Level 2 at 500, Level 3 at 1000, ...

        Returns a list of message strings for each level gained.
        """
        messages = []
        template = self._load_class_template(self.char_class)
        xp_per = template["exp_per_level"]
        while self.exp >= self.level * xp_per:
            self.level += 1
            hp_gain = template["hp_per_level"]
            mp_gain = template["mp_per_level"]

            self.max_hp += hp_gain
            self.hp = min(self.hp + hp_gain, self.max_hp)

            if mp_gain > 0:
                self._bonus_mp += mp_gain
                self._current_mp = min(
                    getattr(self, "_current_mp", 0) + mp_gain, self.max_mp)

            msg = f"{self.name} reached Level {self.level}! HP+{hp_gain}"
            if mp_gain > 0:
                msg += f" MP+{mp_gain}"
            messages.append(msg)
        return messages

    # ── Equipment proficiency ─────────────────────────────────────
    #
    # Loaded once from data/classes/<classname>.json.  Each file may set
    # "allowed_weapons" and "allowed_armor" to either "all" (no
    # restriction) or a list of item names.  If no file exists for a
    # class, everything is allowed (fighter-like).

    _class_templates = {}   # class cache: {classname: dict}

    @classmethod
    def _load_class_template(cls, class_name):
        """Load and cache a class template from classes/<name>.json.

        Checks the active module's ``classes/`` subdirectory first,
        then falls back to the default ``data/classes/`` directory.
        """
        key = class_name.lower()
        if key in cls._class_templates:
            return cls._class_templates[key]

        data = None
        # Try module directory first
        if _module_data_dir is not None:
            mod_path = os.path.join(_module_data_dir, "classes", f"{key}.json")
            if os.path.isfile(mod_path):
                with open(mod_path, "r") as fh:
                    data = json.load(fh)
        # Fallback to default data/classes/
        if data is None:
            path = os.path.join(_DEFAULT_DATA_DIR, "classes", f"{key}.json")
            if os.path.isfile(path):
                with open(path, "r") as fh:
                    data = json.load(fh)
            else:
                data = {}  # unknown class — allow everything

        # Normalise into sets (or None for "all")
        template = {}
        for field in ("allowed_weapons", "allowed_armor"):
            raw = data.get(field, "all")
            if raw == "all":
                template[field] = None       # None means no restriction
            else:
                template[field] = set(raw)   # convert list → set

        # Allowed races (None means all races allowed)
        raw_races = data.get("allowed_races", "all")
        if raw_races == "all":
            template["allowed_races"] = None
        else:
            template["allowed_races"] = set(raw_races)

        # Scalar attributes with defaults
        template["hp_per_level"] = data.get("hp_per_level", 6)
        template["mp_per_level"] = data.get("mp_per_level", 0)
        template["range"] = data.get("range", 1)
        template["exp_per_level"] = data.get("exp_per_level", 500)
        template["spell_type"] = data.get("spell_type", "none")

        # mp_source: None for non-casters, or dict with percentage.
        # Single-stat format:  {"ability": str, "percentage": int}
        # Dual-stat format:    {"abilities": [str, str], "mode": "higher"|"lower", "percentage": int}
        raw_mp_source = data.get("mp_source")
        if raw_mp_source is not None:
            if "abilities" in raw_mp_source:
                template["mp_source"] = {
                    "abilities": list(raw_mp_source["abilities"]),
                    "mode": raw_mp_source["mode"],
                    "percentage": raw_mp_source["percentage"],
                }
            else:
                template["mp_source"] = {
                    "ability": raw_mp_source["ability"],
                    "percentage": raw_mp_source["percentage"],
                }
        else:
            template["mp_source"] = None

        # mp_regen_multiplier: how fast MP regenerates (default 1)
        template["mp_regen_multiplier"] = data.get("mp_regen_multiplier", 1)

        # abilities: list of {"name": str, "description": str}
        template["abilities"] = data.get("abilities", [])

        cls._class_templates[key] = template
        return template

    def can_use_weapon(self, weapon_name):
        """Return True if this character's class can wield the named weapon."""
        if weapon_name is None:
            return True
        tmpl = self._load_class_template(self.char_class)
        allowed = tmpl["allowed_weapons"]
        if allowed is None:
            return True
        weapon_data = WEAPONS.get(weapon_name, {})
        item_type = weapon_data.get("item_type", weapon_name.lower())
        return item_type in allowed

    def can_use_armor(self, armor_name):
        """Return True if this character's class can wear the named armor."""
        if armor_name is None:
            return True
        tmpl = self._load_class_template(self.char_class)
        allowed = tmpl["allowed_armor"]
        if allowed is None:
            return True
        armor_data = ARMORS.get(armor_name, {})
        item_type = armor_data.get("item_type", armor_name.lower())
        return item_type in allowed

    @classmethod
    def allowed_races_for_class(cls, char_class):
        """Return the set of allowed race keys for a class, or None for all."""
        tmpl = cls._load_class_template(char_class)
        return tmpl["allowed_races"]

    @classmethod
    def is_race_class_valid(cls, race, char_class):
        """Return True if the given race is allowed for the given class."""
        allowed = cls.allowed_races_for_class(char_class)
        if allowed is None:
            return True
        return race.lower() in allowed

    @property
    def race_info(self):
        """Return the full race data dict for this character's race."""
        return RACE_INFO.get(self.race, {})

    @property
    def racial_effects(self):
        """Return the list of innate racial effects for this character."""
        return self.race_info.get("effects", [])

    def has_racial_effect(self, effect):
        """Return True if this character's race grants the given effect."""
        return effect in self.racial_effects

    @property
    def racial_stat_modifiers(self):
        """Return dict of stat → modifier from this character's race."""
        return self.race_info.get("stat_modifiers", {})

    @property
    def range(self):
        """Attack range in tiles (from class template)."""
        tmpl = self._load_class_template(self.char_class)
        return tmpl["range"]

    @property
    def spell_type(self):
        """Spell type for this class: 'none', 'priest', or 'sorcerer'."""
        tmpl = self._load_class_template(self.char_class)
        return tmpl["spell_type"]

    @property
    def can_cast(self):
        """Return True if this character's class can cast spells."""
        return self.spell_type != "none"

    @property
    def abilities(self):
        """Return list of class abilities (each a dict with name and description)."""
        tmpl = self._load_class_template(self.char_class)
        return tmpl.get("abilities", [])

    @property
    def mp_source(self):
        """Return mp_source dict or None for non-casters.

        Dict has 'ability' (str) and 'percentage' (int 0-100).
        """
        tmpl = self._load_class_template(self.char_class)
        return tmpl["mp_source"]

    def calc_mp_from_source(self):
        """Calculate MP contribution from the class mp_source.

        Single-stat: stat * (percentage / 100).
        Dual-stat:   pick higher or lower of two stats, then apply percentage.
        Returns 0 for non-casters.
        """
        src = self.mp_source
        if src is None:
            return 0
        if "abilities" in src:
            # Dual-stat mode (e.g. Druid uses higher of INT/WIS)
            values = [getattr(self, a, 0) for a in src["abilities"]]
            if src["mode"] == "higher":
                stat_value = max(values)
            else:  # "lower"
                stat_value = min(values)
        else:
            stat_value = getattr(self, src["ability"], 0)
        return int(stat_value * src["percentage"] / 100)

    @property
    def mp_regen_multiplier(self):
        """MP regeneration multiplier (e.g. 2 for Druid)."""
        tmpl = self._load_class_template(self.char_class)
        return tmpl["mp_regen_multiplier"]

    def can_use_item(self, item_name):
        """Return True if this character's class can equip the named item."""
        if item_name is None:
            return True
        if item_name in WEAPONS:
            return self.can_use_weapon(item_name)
        if item_name in ARMORS:
            return self.can_use_armor(item_name)
        return True

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
        """Armor class based on armor evasion + DEX modifier + potion buffs."""
        base = ARMORS.get(self.armor, {"evasion": 50})["evasion"]
        ac = 10 + self.dex_mod + (base - 50) // 5
        ac += getattr(self, "potion_buffs", {}).get("ac", 0)
        return ac

    def get_attack_bonus(self):
        """Melee attack bonus: STR modifier + potion buffs."""
        bonus = self.str_mod
        bonus += getattr(self, "potion_buffs", {}).get("strength", 0)
        return bonus

    def get_weapon_power(self, weapon_name=None):
        """Return a weapon's power rating. Defaults to main-hand weapon."""
        wname = weapon_name or self.weapon
        return WEAPONS.get(wname, {"power": 0})["power"]

    def get_damage(self):
        """Ultima III damage: weapon power + 1.5 * STR (min 1).
        Includes potion buff bonus to strength."""
        wp = self.get_weapon_power()
        str_total = self.strength + getattr(self, "potion_buffs", {}).get("strength", 0)
        return max(1, int(wp + 1.5 * str_total))

    def get_damage_dice(self, weapon_name=None):
        """Return (count, sides, bonus) for weapon damage.
        Uses weapon power to determine dice size, STR as bonus.
        Optionally specify a weapon_name to get dice for a specific weapon."""
        wp = self.get_weapon_power(weapon_name)
        if wp <= 2:
            return (1, 4, self.str_mod)
        elif wp <= 5:
            return (1, 6, self.str_mod)
        elif wp <= 8:
            return (1, 8, self.str_mod)
        else:
            return (1, 10, self.str_mod)

    def get_ranged_weapon(self):
        """Return the name of the first ranged weapon found in either hand, or None.

        Checks right_hand first, then left_hand.
        """
        for slot in ("right_hand", "left_hand"):
            wp_name = self.equipped.get(slot)
            if wp_name:
                wdata = WEAPONS.get(wp_name, {})
                if wdata.get("ranged", False):
                    return wp_name
        return None

    def is_ranged(self, party=None):
        """True if a ranged weapon is equipped in either hand and has ammo.

        Throwable weapons need copies in inventory to throw.
        Ammo weapons (bows) need ammo charges in party shared inventory
        or in the character's personal inventory.
        """
        rw = self.get_ranged_weapon()
        if not rw:
            return False
        wdata = WEAPONS[rw]
        # Throwable weapons need items in inventory to throw
        if wdata.get("throwable", False):
            count = self.inventory.count(rw)
            if party:
                count += party.inv_count(rw)
            return count > 0
        # Ammo weapons need charges in shared or personal inventory
        ammo_type = wdata.get("ammo")
        if ammo_type:
            total = self._count_personal_ammo(ammo_type)
            if party:
                total += party.inv_get_charges(ammo_type)
            return total > 0
        return True

    def _count_personal_ammo(self, ammo_type):
        """Count ammo charges in the character's personal inventory."""
        total = 0
        for entry in self.inventory:
            if isinstance(entry, dict):
                if entry.get("name") == ammo_type:
                    total += entry.get("charges", 1)
            elif entry == ammo_type:
                total += 1
        return total

    def is_throwable_weapon(self):
        """True if the ranged weapon is thrown and consumed on ranged use."""
        rw = self.get_ranged_weapon()
        if not rw:
            return False
        return WEAPONS.get(rw, {}).get("throwable", False)

    def get_ammo_type(self):
        """Return the ammo item name required by the ranged weapon, or None."""
        rw = self.get_ranged_weapon()
        if not rw:
            return None
        return WEAPONS.get(rw, {}).get("ammo")

    def uses_ammo(self):
        """True if the ranged weapon requires ammunition from shared inventory."""
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
        return self.spell_type in ("priest", "both")

    def can_cast_sorcerer(self):
        return self.spell_type in ("sorcerer", "both")

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

    def get_valid_slots(self, item_name):
        """Return a list of equipment slots this item can be placed in.

        Reads from the item's 'slots' field in the data files.
        Falls back to legacy logic if no slots field is defined.
        Returns an empty list if the item is not equippable.
        """
        # Check weapons first, then armors
        wp = WEAPONS.get(item_name)
        if wp:
            return list(wp.get("slots", ["right_hand"]))
        arm = ARMORS.get(item_name)
        if arm:
            return list(arm.get("slots", ["body"]))
        return []

    def equip_item(self, item_name, slot=None):
        """Equip an item from inventory to the given slot.

        If slot is None, falls back to the first valid slot (legacy behavior).
        Returns True if the item was equipped, False otherwise.
        The previously equipped item in that slot (if any) is moved to inventory.
        """
        if item_name not in self.inventory:
            return False
        # Check class proficiency (weapons and armor)
        if not self.can_use_item(item_name):
            return False
        valid_slots = self.get_valid_slots(item_name)
        if not valid_slots:
            return False
        if slot is None:
            slot = valid_slots[0]
        elif slot not in valid_slots:
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
    PARTY_SLOTS = ["navigation", "camping", "special"]
    PARTY_SLOT_LABELS = {
        "navigation": "NAVIGATION",
        "camping": "CAMPING",
        "special": "SPECIAL",
    }
    PARTY_SLOT_DEFAULTS = {"navigation": None,
                           "camping": None, "special": None}

    # Party-level passive effect slots (4 slots)
    EFFECT_SLOTS = ["effect_1", "effect_2", "effect_3", "effect_4"]
    EFFECT_SLOT_LABELS = {
        "effect_1": "EFFECT 1",
        "effect_2": "EFFECT 2",
        "effect_3": "EFFECT 3",
        "effect_4": "EFFECT 4",
    }

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

    MAX_ROSTER = 20

    def __init__(self, start_col, start_row):
        self.col = start_col
        self.row = start_row
        self.roster = []            # All created characters (up to MAX_ROSTER)
        self.active_indices = []    # Indices into roster for the active party
        self.members = []           # The active party (up to 4, refs into roster)
        self.gold = 100  # Shared party gold
        self.shared_inventory = []  # Party-wide item pool

        # Party-level equipment: utility slots + light (shown in effects)
        self.equipped = {s: None for s in self.PARTY_SLOTS}
        self.equipped["light"] = None  # torch slot; rendered in Effects

        # Party-level passive effects: 4 effect slots
        self.effects = {s: None for s in self.EFFECT_SLOTS}

        # Game clock — tracks day, hour, lunar phase
        from src.game_time import GameClock
        self.clock = GameClock()

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

    def get_effect(self, slot):
        """Return the effect name in the given effect slot, or None."""
        return self.effects.get(slot)

    def set_effect(self, slot, effect_name):
        """Set an effect in the given slot. Pass None to clear.

        Special handling for "Torch": equipping moves a Torch from the
        shared stash into equipped["light"]; clearing moves it back.
        """
        if slot not in self.effects:
            return
        old = self.effects[slot]
        # Unequip old torch if we're replacing or clearing a Torch effect
        if old == "Torch" and effect_name != "Torch":
            self.party_unequip("light")
        self.effects[slot] = effect_name
        # Equip new torch from stash
        if effect_name == "Torch" and old != "Torch":
            self.party_equip("Torch", "light")

    def has_effect(self, effect_name):
        """Return True if the party has the named effect in any slot."""
        return any(v == effect_name for v in self.effects.values())

    def get_available_effects(self):
        """Return list of effect dicts from EFFECTS_DATA that the party qualifies for.

        Requirements use ALL-match logic:
          - class: party must have an alive member of that class
          - race:  party must have an alive member of that race
          - min_level: party must have an alive member at or above that level

        Effects already slotted are excluded.
        Also includes "Torch" if the party has a torch in stash inventory
        and no torch is currently slotted.
        """
        slotted = set(v for v in self.effects.values() if v is not None)
        available = []
        for eff in EFFECTS_DATA:
            if eff["name"] in slotted:
                continue
            reqs = eff.get("requirements", {})
            if not self._meets_requirements(reqs):
                continue
            available.append(eff)

        # Offer Torch as an assignable effect if one is in the stash
        if "Torch" not in slotted:
            has_torch = any(
                self.item_name(e) == "Torch" for e in self.shared_inventory
            )
            if has_torch:
                available.append({
                    "id": "torch",
                    "name": "Torch",
                    "description": "Lights the way in dark places.",
                    "duration": "permanent",
                })
        return available

    def _meets_requirements(self, reqs):
        """Check if the party meets ALL requirements."""
        alive = [m for m in self.members if m.is_alive()]
        if not alive:
            return False

        req_class = reqs.get("class")
        req_race = reqs.get("race")
        req_min_level = reqs.get("min_level")

        # Find members that match class/race requirements
        candidates = alive

        if req_class is not None:
            candidates = [m for m in candidates
                          if m.char_class == req_class]
            if not candidates:
                return False

        if req_race is not None:
            candidates = [m for m in candidates
                          if m.race == req_race]
            if not candidates:
                return False

        if req_min_level is not None:
            candidates = [m for m in candidates
                          if m.level >= req_min_level]
            if not candidates:
                return False

        return True

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

    def add_to_roster(self, member):
        """Add a character to the roster (max MAX_ROSTER).

        Returns the roster index, or -1 if full.
        """
        if len(self.roster) >= self.MAX_ROSTER:
            return -1
        self.roster.append(member)
        return len(self.roster) - 1

    def set_active_party(self, indices):
        """Set the active party from roster indices (max 4).

        Replaces self.members with the selected roster characters.
        """
        self.active_indices = list(indices[:4])
        self.members = [self.roster[i] for i in self.active_indices
                        if 0 <= i < len(self.roster)]

    def get_roster_index(self, member):
        """Return the roster index for a given party member, or -1."""
        try:
            return self.roster.index(member)
        except ValueError:
            return -1

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


def _build_member_from_cfg(char_cfg):
    """Build a PartyMember from a character config dict.

    Used by both create_default_party() and the save/load system.
    """
    member = PartyMember(
        name=char_cfg["name"],
        char_class=char_cfg["class"],
        race=char_cfg.get("race", "Human"),
        gender=char_cfg.get("gender", "Male"),
        hp=char_cfg.get("hp", 20),
        strength=char_cfg.get("strength", 10),
        dexterity=char_cfg.get("dexterity", 10),
        intelligence=char_cfg.get("intelligence", 10),
        wisdom=char_cfg.get("wisdom", 10),
        level=char_cfg.get("level", 1),
        sprite=char_cfg.get("sprite"),
    )
    # Equipment slots
    equip = char_cfg.get("equipped", {})
    member.equipped = {
        "right_hand": equip.get("right_hand", "Fists"),
        "left_hand": equip.get("left_hand"),
        "body": equip.get("body", "Cloth"),
        "head": equip.get("head"),
    }
    member._sync_legacy_fields()

    # Personal inventory
    for item in char_cfg.get("inventory", []):
        member.inventory.append(item)

    return member


def create_default_party(start_col=None, start_row=None):
    """Create a party from data/party.json configuration.

    Characters are loaded into a roster; the active_party indices
    select which characters form the adventuring party.
    If start_col/start_row are provided they override the JSON values.
    """
    cfg = _load_party_config()
    if start_col is None:
        start_col = cfg["start_position"]["col"]
    if start_row is None:
        start_row = cfg["start_position"]["row"]
    party = Party(start_col, start_row)

    # ── Build roster from JSON ──
    # Support both new "roster" key and legacy "characters" key
    roster_cfg = cfg.get("roster", cfg.get("characters", []))
    for char_cfg in roster_cfg:
        member = _build_member_from_cfg(char_cfg)
        party.add_to_roster(member)

    # ── Select active party from roster ──
    active = cfg.get("active_party")
    if active is not None:
        party.set_active_party(active)
    else:
        # Legacy fallback: all roster members are active (up to 4)
        party.set_active_party(list(range(min(4, len(party.roster)))))

    # ── Party-level config ──
    party.gold = cfg.get("gold", 100)

    # ── Party-level equipment slots from JSON (includes "light") ──
    party_eq = cfg.get("party_equipped", {})
    for slot in list(party.equipped.keys()):
        entry = party_eq.get(slot)
        if entry is not None:
            party.equipped[slot] = {
                "name": entry["name"],
                "charges": entry.get("charges"),
            }

    # ── Party-level passive effects from JSON ──
    party_eff = cfg.get("party_effects", {})
    for slot in party.EFFECT_SLOTS:
        effect = party_eff.get(slot)
        if effect is not None:
            party.effects[slot] = effect

    # ── Shared inventory ──
    party.shared_inventory = []
    for entry in cfg.get("inventory", []):
        item_name = entry["item"]
        charges = entry.get("charges")
        if charges is not None:
            party.inv_add(item_name, charges=charges)
        else:
            party.shared_inventory.append(item_name)

    return party
