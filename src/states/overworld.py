"""
Overworld state - the main exploration mode.

This is where the party walks around the overworld map, encounters
towns, dungeons, and random encounters. It's the "hub" state of
the game.
"""

import random

import pygame

from src.states.base_state import BaseState
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_TOWN, TILE_DUNGEON, TILE_CHEST, TILE_GRASS,
)
from src.dungeon_generator import generate_dungeon
from src.monster import create_random_monster, create_encounter, create_monster


# How many monsters roam the overworld at a time
_MAX_OVERWORLD_ORCS = 2
# Minimum Chebyshev distance from party when spawning
_SPAWN_MIN_DIST = 8
_SPAWN_MAX_DIST = 14


class OverworldState(BaseState):
    """Handles overworld exploration."""

    def __init__(self, game):
        super().__init__(game)
        self.message = ""
        self.message_timer = 0  # ms remaining to show message
        self.move_cooldown = 0  # ms until next move allowed
        self.showing_party = False
        self.showing_char_detail = None  # index 0-3, or None
        self.char_sheet_cursor = 0       # cursor position in equip/item list
        self.char_sheet_origin = None    # "inventory", "party", or None (direct)
        self.char_action_menu = False    # True when action popup is open
        self.char_action_cursor = 0      # selected option in action popup
        self.examining_item = None       # item name being examined, or None
        self.showing_party_inv = False   # party shared inventory screen
        self.party_inv_cursor = 0        # selected item in shared inventory
        self.party_inv_choosing = False  # True when picking a member to give to
        self.party_inv_member = 0        # selected member index
        self.party_inv_action_menu = False   # action menu in party inventory
        self.party_inv_action_cursor = 0     # selected option in party inv action
        self.choosing_effect = False          # True when picking an effect to assign
        self.effect_list = []                 # available effects for current slot
        self.effect_cursor = 0               # cursor in effect chooser

        # Use-item animation overlay
        self.use_item_anim = None

        # Game log overlay
        self.showing_log = False
        self.log_scroll = 0

        # Help overlay
        self.showing_help = False

        # Unique tile discovery display
        self.unique_tile_text = ""
        self.unique_tile_timer = 0       # ms remaining to show text
        self.unique_tile_flash = 0.0     # animation phase (radians)
        self.unique_tile_pos = None      # (col, row) for map flash effect

        # Roaming overworld orcs
        self.overworld_monsters = []

        # Track original tiles under placed chests: {(col, row): tile_id}
        self.chest_under_tiles = {}

        # Message queued by combat state on return
        self.pending_combat_message = None

    def enter(self):
        if self.pending_combat_message:
            self.show_message(self.pending_combat_message, 2500)
            self.pending_combat_message = None
        elif not self.overworld_monsters:
            self.message = "Welcome, adventurers! Use arrow keys to explore."
            self.message_timer = 3000
            # Spawn initial orcs
            self._spawn_orcs()

    # ── Equipment management ─────────────────────────────────────

    def _handle_equip_action(self, member):
        """Open the action menu for the selected item/slot."""
        options = self._get_action_options(member)
        if not options:
            self.message = "Empty slot — equip items from inventory"
            self.message_timer = 2000
            return
        self.char_action_menu = True
        self.char_action_cursor = 0

    def _get_item_at_cursor(self, member):
        """Return the item name at the current char_sheet_cursor position."""
        idx = self.char_sheet_cursor
        if idx < 4:
            slot_keys = ["right_hand", "left_hand", "body", "head"]
            return member.equipped.get(slot_keys[idx])
        else:
            inv_idx = idx - 4
            if inv_idx < len(member.inventory):
                return member.inventory[inv_idx]
        return None

    def _get_action_options(self, member):
        """Build the list of action option keys for the current cursor position."""
        from src.party import PartyMember
        idx = self.char_sheet_cursor
        options = []
        if idx < 4:
            slot_keys = ["right_hand", "left_hand", "body", "head"]
            slot = slot_keys[idx]
            current = member.equipped.get(slot)
            if current:
                options.append("UNEQUIP")
                options.append("RETURN TO PARTY STASH")
                options.append("EXAMINE")
        else:
            inv_idx = idx - 4
            if inv_idx < len(member.inventory):
                item_name = member.inventory[inv_idx]
                from src.party import ITEM_INFO
                info = ITEM_INFO.get(item_name, {})
                if info.get("usable", False):
                    options.append("USE")
                if member.can_use_item(item_name):
                    valid_slots = member.get_valid_slots(item_name)
                    for s in valid_slots:
                        label = PartyMember._SLOT_LABELS[s]
                        options.append(f"EQUIP \u2192 {label}")
                options.append("RETURN TO PARTY STASH")
                options.append("EXAMINE")
        return options

    def _handle_char_action_input(self, event):
        """Handle input while the action menu popup is open."""
        # If examining an item, ESC/Enter/Space closes the examine view
        if self.examining_item is not None:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.examining_item = None
            return

        member = self.game.party.members[self.showing_char_detail]
        options = self._get_action_options(member)

        if not options:
            self.char_action_menu = False
            return

        if event.key == pygame.K_UP:
            self.char_action_cursor = (self.char_action_cursor - 1) % len(options)
        elif event.key == pygame.K_DOWN:
            self.char_action_cursor = (self.char_action_cursor + 1) % len(options)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            chosen = options[self.char_action_cursor]
            idx = self.char_sheet_cursor
            if chosen == "EXAMINE":
                self.examining_item = self._get_item_at_cursor(member)
                return
            elif chosen == "USE":
                inv_idx = idx - 4
                if inv_idx < len(member.inventory):
                    item_name = member.inventory[inv_idx]
                    self._use_char_item(member, item_name, inv_idx)
            elif chosen == "UNEQUIP":
                if idx < 4:
                    slot_keys = ["right_hand", "left_hand", "body", "head"]
                    if not member.unequip_slot(slot_keys[idx]):
                        self.message = f"Cannot remove basic {member.equipped.get(slot_keys[idx], 'gear')}!"
                        self.message_timer = 2000
            elif chosen.startswith("EQUIP"):
                inv_idx = idx - 4
                if inv_idx < len(member.inventory):
                    # Parse slot from "EQUIP → LABEL"
                    from src.party import PartyMember
                    _label_to_key = {v: k for k, v in PartyMember._SLOT_LABELS.items()}
                    slot_label = chosen.split("\u2192 ", 1)[1].strip()
                    slot_key = _label_to_key.get(slot_label)
                    member.equip_item(member.inventory[inv_idx], slot_key)
            elif chosen == "RETURN TO PARTY STASH":
                if idx < 4:
                    slot_keys = ["right_hand", "left_hand", "body", "head"]
                    member.return_equipped_to_party(slot_keys[idx], self.game.party)
                else:
                    inv_idx = idx - 4
                    if inv_idx < len(member.inventory):
                        member.return_item_to_party(
                            member.inventory[inv_idx], self.game.party)
            self.char_action_menu = False
            # Clamp cursor
            total = 4 + len(member.inventory)
            if self.char_sheet_cursor >= total:
                self.char_sheet_cursor = max(0, total - 1)
        elif event.key == pygame.K_ESCAPE:
            self.char_action_menu = False

    def _use_char_item(self, member, item_name, inv_idx):
        """Use a consumable item from a character's personal inventory."""
        from src.party import ITEM_INFO
        info = ITEM_INFO.get(item_name, {})
        effect = info.get("effect", "")
        power = info.get("power", 0)

        if effect == "rest":
            if member.hp <= 0:
                self.message = f"{member.name} is unconscious!"
                self.message_timer = 2500
                return
            hp_restore = max(1, int(member.max_hp * 0.35)) + random.randint(1, 8)
            mp_restore = max(1, int(member.max_mp * 0.30)) + random.randint(1, 4)
            old_hp, old_mp = member.hp, getattr(member, "current_mp", 0)
            member.hp = min(member.max_hp, member.hp + hp_restore)
            member.current_mp = min(member.max_mp, getattr(member, "current_mp", 0) + mp_restore)
            actual_hp = member.hp - old_hp
            actual_mp = member.current_mp - old_mp
            self.game.game_log.append(
                f"{member.name} rests using {item_name}. (+{actual_hp} HP, +{actual_mp} MP)")
            self.message = f"{member.name}: +{actual_hp} HP, +{actual_mp} MP"
            self.message_timer = 3000
        elif effect == "heal_hp":
            if member.hp <= 0:
                self.message = f"{member.name} is unconscious!"
                self.message_timer = 2500
                return
            missing = member.max_hp - member.hp
            if missing <= 0:
                self.message = f"{member.name} is already at full health!"
                self.message_timer = 2500
                return
            heal = power + random.randint(1, 6)
            member.hp = min(member.max_hp, member.hp + heal)
            self.game.game_log.append(
                f"{member.name} uses {item_name}. (+{heal} HP)")
            self.message = f"{member.name}: +{heal} HP"
            self.message_timer = 3000
        elif effect == "heal_mp":
            if member.hp <= 0:
                self.message = f"{member.name} is unconscious!"
                self.message_timer = 2500
                return
            missing = member.max_mp - getattr(member, "current_mp", 0)
            if missing <= 0:
                self.message = f"{member.name} is already at full mana!"
                self.message_timer = 2500
                return
            restore = power + random.randint(1, 4)
            member.current_mp = min(member.max_mp,
                                    getattr(member, "current_mp", 0) + restore)
            self.game.game_log.append(
                f"{member.name} uses {item_name}. (+{restore} MP)")
            self.message = f"{member.name}: +{restore} MP"
            self.message_timer = 3000
        elif effect == "cure_poison":
            if getattr(member, "poisoned", False):
                member.poisoned = False
                self.game.game_log.append(f"{member.name}'s poison was cured!")
                self.message = f"{member.name}: Poison cured!"
                self.message_timer = 3000
            else:
                self.message = f"{member.name} is not poisoned!"
                self.message_timer = 2500
                return
        else:
            self.game.game_log.append(f"{member.name} used {item_name}.")
            self.message = f"Used {item_name}"
            self.message_timer = 2000

        # Start use-item animation
        anim_text = self.message or f"Used {item_name}"
        self.use_item_anim = {
            "effect": effect,
            "timer": 1800,
            "duration": 1800,
            "text": anim_text,
        }

        # Remove the item from the character's inventory
        if inv_idx < len(member.inventory):
            member.inventory.pop(inv_idx)

    def _handle_party_inv_input(self, event):
        """Handle input for the shared party inventory screen.

        The unified cursor covers effect slots, a torch slot,
        and then shared inventory items.
        """
        party = self.game.party
        inv = party.shared_inventory
        members = party.members
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        STASH_START = NUM_EFFECTS
        total_items = STASH_START + len(inv)

        # Examining an item — close on ESC/Enter/Space
        if self.examining_item is not None:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.examining_item = None
            return

        # Effect chooser is open
        if self.choosing_effect:
            if event.key == pygame.K_ESCAPE:
                self.choosing_effect = False
            elif event.key == pygame.K_UP and self.effect_list:
                self.effect_cursor = (self.effect_cursor - 1) % len(self.effect_list)
            elif event.key == pygame.K_DOWN and self.effect_list:
                self.effect_cursor = (self.effect_cursor + 1) % len(self.effect_list)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.effect_list:
                chosen_eff = self.effect_list[self.effect_cursor]
                eff_idx = self.party_inv_cursor
                slot_key = party.EFFECT_SLOTS[eff_idx]
                party.set_effect(slot_key, chosen_eff["name"])
                self.choosing_effect = False
            return

        # Action menu is open
        if self.party_inv_action_menu:
            options = self._get_party_inv_action_options()
            if not options:
                self.party_inv_action_menu = False
                return
            if event.key == pygame.K_UP:
                self.party_inv_action_cursor = (self.party_inv_action_cursor - 1) % len(options)
            elif event.key == pygame.K_DOWN:
                self.party_inv_action_cursor = (self.party_inv_action_cursor + 1) % len(options)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                chosen = options[self.party_inv_action_cursor]
                self._handle_party_inv_action(chosen)
            elif event.key == pygame.K_ESCAPE:
                self.party_inv_action_menu = False
            return

        # Browsing unified list (equip slots + inventory)
        if True:
            if event.key == pygame.K_UP and total_items > 0:
                self.party_inv_cursor = (self.party_inv_cursor - 1) % total_items
            elif event.key == pygame.K_DOWN and total_items > 0:
                self.party_inv_cursor = (self.party_inv_cursor + 1) % total_items
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and total_items > 0:
                options = self._get_party_inv_action_options()
                if options:
                    self.party_inv_action_menu = True
                    self.party_inv_action_cursor = 0
            elif event.key == pygame.K_ESCAPE:
                self.showing_party_inv = False
            elif event.key == pygame.K_p:
                self.showing_party_inv = False
                self.showing_party = False
            else:
                # Number keys 1-4: open character detail sheet
                num = {pygame.K_1: 0, pygame.K_2: 1,
                       pygame.K_3: 2, pygame.K_4: 3}.get(event.key)
                if num is not None and num < len(self.game.party.members):
                    self.showing_party_inv = False
                    self.showing_char_detail = num
                    self.char_sheet_cursor = 0
                    self.char_sheet_origin = "inventory"

    def _handle_party_inv_action(self, chosen):
        """Execute the chosen action on the selected party inventory entry."""
        party = self.game.party
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        STASH_START = NUM_EFFECTS
        idx = self.party_inv_cursor

        if idx < NUM_EFFECTS:
            slot_key = party.EFFECT_SLOTS[idx]
            if chosen == "ASSIGN EFFECT":
                self.effect_list = party.get_available_effects()
                self.effect_cursor = 0
                self.choosing_effect = True
                self.party_inv_action_menu = False
            elif chosen == "REMOVE":
                party.set_effect(slot_key, None)
                self.party_inv_action_menu = False
        else:
            inv_idx = idx - STASH_START
            inv = party.shared_inventory
            if inv_idx < len(inv):
                item_name = party.item_name(inv[inv_idx])
                if chosen == "USE":
                    self._use_party_item(item_name, inv_idx)
                    self.party_inv_action_menu = False
                    new_total = STASH_START + len(party.shared_inventory)
                    if self.party_inv_cursor >= new_total:
                        self.party_inv_cursor = max(0, new_total - 1)
                elif chosen == "EQUIP":
                    for slot_key in party.EFFECT_SLOTS:
                        if party.get_effect(slot_key) is None:
                            party.set_effect(slot_key, item_name)
                            break
                    self.party_inv_action_menu = False
                    new_total = STASH_START + len(party.shared_inventory)
                    if self.party_inv_cursor >= new_total:
                        self.party_inv_cursor = max(0, new_total - 1)
                elif chosen == "EXAMINE":
                    self.examining_item = item_name
                elif chosen.startswith("GIVE TO "):
                    give_name = chosen[8:].strip()
                    for mi, member in enumerate(party.members):
                        if member.name.upper() == give_name:
                            party.give_item_to_member(inv_idx, mi)
                            break
                    self.party_inv_action_menu = False
                    new_total = STASH_START + len(party.shared_inventory)
                    if self.party_inv_cursor >= new_total:
                        self.party_inv_cursor = max(0, new_total - 1)

    def _get_party_inv_action_options(self):
        """Build action options for the selected party inventory entry."""
        party = self.game.party
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        STASH_START = NUM_EFFECTS
        idx = self.party_inv_cursor

        if idx < NUM_EFFECTS:
            slot_key = party.EFFECT_SLOTS[idx]
            current = party.get_effect(slot_key)
            options = []
            if party.get_available_effects():
                options.append("ASSIGN EFFECT")
            if current is not None:
                options.append("REMOVE")
            return options
        else:
            inv_idx = idx - STASH_START
            inv = party.shared_inventory
            if inv_idx >= len(inv):
                return []
            options = []
            item_name = party.item_name(inv[inv_idx])
            from src.party import ITEM_INFO
            info = ITEM_INFO.get(item_name, {})
            if info.get("usable", False):
                options.append("USE")
            if info.get("party_can_equip", False):
                already = party.has_effect(item_name)
                has_free = any(
                    party.get_effect(s) is None for s in party.EFFECT_SLOTS
                )
                if not already and has_free:
                    options.append("EQUIP")
            for mi, member in enumerate(self.game.party.members):
                options.append(f"GIVE TO {member.name.upper()}")
            options.append("EXAMINE")
            return options

    # ── Use consumable items from party stash ─────────────────────

    def _use_party_item(self, item_name, inv_idx):
        """Use a consumable item from the party stash."""
        from src.party import ITEM_INFO
        party = self.game.party
        info = ITEM_INFO.get(item_name, {})
        effect = info.get("effect", "")
        power = info.get("power", 0)

        if effect == "rest":
            total_hp = 0
            total_mp = 0
            for m in party.members:
                if m.hp <= 0:
                    continue
                hp_restore = max(1, int(m.max_hp * 0.35)) + random.randint(1, 8)
                mp_restore = max(1, int(m.max_mp * 0.30)) + random.randint(1, 4)
                old_hp, old_mp = m.hp, getattr(m, "current_mp", 0)
                m.hp = min(m.max_hp, m.hp + hp_restore)
                m.current_mp = min(m.max_mp, getattr(m, "current_mp", 0) + mp_restore)
                total_hp += m.hp - old_hp
                total_mp += m.current_mp - old_mp
            self.game.game_log.append(f"The party rests using {item_name}...")
            self.game.game_log.append(
                f"  Restored {total_hp} HP and {total_mp} MP across the party!")
            self.show_message(f"Rested! +{total_hp} HP, +{total_mp} MP", 3500)
        elif effect == "heal_hp":
            best = None
            best_missing = 0
            for m in party.members:
                if m.hp <= 0:
                    continue
                missing = m.max_hp - m.hp
                if missing > best_missing:
                    best_missing = missing
                    best = m
            if best and best_missing > 0:
                heal = power + random.randint(1, 6)
                best.hp = min(best.max_hp, best.hp + heal)
                self.game.game_log.append(
                    f"{best.name} uses {item_name}. (+{heal} HP)")
                self.show_message(f"{best.name}: +{heal} HP", 3000)
            else:
                self.game.game_log.append("Everyone is already at full health!")
                self.show_message("Everyone is at full health!", 2500)
                return
        elif effect == "heal_mp":
            best = None
            best_missing = 0
            for m in party.members:
                if m.hp <= 0:
                    continue
                missing = m.max_mp - getattr(m, "current_mp", 0)
                if missing > best_missing:
                    best_missing = missing
                    best = m
            if best and best_missing > 0:
                restore = power + random.randint(1, 4)
                best.current_mp = min(best.max_mp,
                                      getattr(best, "current_mp", 0) + restore)
                self.game.game_log.append(
                    f"{best.name} uses {item_name}. (+{restore} MP)")
                self.show_message(f"{best.name}: +{restore} MP", 3000)
            else:
                self.game.game_log.append("Everyone is already at full mana!")
                self.show_message("Everyone is at full mana!", 2500)
                return
        elif effect == "cure_poison":
            cured = False
            for m in party.members:
                if getattr(m, "poisoned", False):
                    m.poisoned = False
                    self.game.game_log.append(f"{m.name}'s poison was cured!")
                    cured = True
                    break
            if not cured:
                self.game.game_log.append("Nobody is poisoned!")
                self.show_message("Nobody is poisoned!", 2500)
                return
        else:
            self.game.game_log.append(f"Used {item_name}.")
            self.show_message(f"Used {item_name}", 2000)

        # Start use-item animation
        anim_text = self.message or f"Used {item_name}"
        self.use_item_anim = {
            "effect": effect,
            "timer": 1800,
            "duration": 1800,
            "text": anim_text,
        }

        # Consume charge or remove item
        entry = party.shared_inventory[inv_idx] if inv_idx < len(party.shared_inventory) else None
        if entry is not None and isinstance(entry, dict) and entry.get("charges", 0) > 0:
            party.inv_consume_charge(item_name)
        else:
            party.inv_remove(item_name)

    # ── Orc spawning ──────────────────────────────────────────────

    def _spawn_orcs(self):
        """Top-up roaming orcs to _MAX_OVERWORLD_ORCS."""
        alive = [m for m in self.overworld_monsters if m.is_alive()]
        self.overworld_monsters = alive
        needed = _MAX_OVERWORLD_ORCS - len(alive)
        tile_map = self.game.tile_map
        party = self.game.party

        for _ in range(needed):
            # Pre-roll encounter template; use monster_party_tile for map sprite
            enc = create_encounter("overworld")
            orc = create_monster(enc["monster_party_tile"])
            orc.encounter_template = {
                "name": enc["name"],
                "monster_names": [m.name for m in enc["monsters"]],
                "monster_party_tile": enc["monster_party_tile"],
            }
            placed = False
            for _attempt in range(60):
                c = party.col + random.randint(-_SPAWN_MAX_DIST, _SPAWN_MAX_DIST)
                r = party.row + random.randint(-_SPAWN_MAX_DIST, _SPAWN_MAX_DIST)
                dist = max(abs(c - party.col), abs(r - party.row))
                if dist < _SPAWN_MIN_DIST:
                    continue
                if (0 <= c < tile_map.width and 0 <= r < tile_map.height
                        and tile_map.is_walkable(c, r)):
                    orc.col = c
                    orc.row = r
                    placed = True
                    break
            if placed:
                self.overworld_monsters.append(orc)

    # ── Input ─────────────────────────────────────────────────────

    def handle_input(self, events, keys_pressed):
        """Handle arrow key movement with repeat delay."""
        for event in events:
            if event.type == pygame.KEYDOWN:
                # ── Help overlay input ──
                if self.showing_help:
                    if event.key in (pygame.K_h, pygame.K_ESCAPE):
                        self.showing_help = False
                    return

                # ── Log overlay input ──
                if self.showing_log:
                    if event.key == pygame.K_l or event.key == pygame.K_ESCAPE:
                        self.showing_log = False
                    elif event.key == pygame.K_UP:
                        self.log_scroll += 3
                    elif event.key == pygame.K_DOWN:
                        self.log_scroll = max(0, self.log_scroll - 3)
                    return

                # ── Party inventory screen input ──
                if self.showing_party_inv:
                    self._handle_party_inv_input(event)
                    return

                # ── Action menu input ──
                if self.char_action_menu and self.showing_char_detail is not None:
                    self._handle_char_action_input(event)
                    return

                if event.key == pygame.K_ESCAPE:
                    if self.showing_char_detail is not None:
                        origin = self.char_sheet_origin
                        self.showing_char_detail = None
                        self.char_sheet_cursor = 0
                        self.char_sheet_origin = None
                        if origin == "inventory":
                            self.showing_party_inv = True
                        elif origin == "party":
                            self.showing_party = True
                        return
                    if self.showing_party:
                        self.showing_party = False
                        return
                    self.game.running = False
                    return
                if event.key == pygame.K_p:
                    if self.showing_char_detail is not None:
                        origin = self.char_sheet_origin
                        self.showing_char_detail = None
                        self.char_sheet_cursor = 0
                        self.char_sheet_origin = None
                        if origin == "inventory":
                            self.showing_party_inv = True
                        elif origin == "party":
                            self.showing_party = True
                        return
                    if self.showing_party_inv:
                        self.showing_party_inv = False
                        return
                    if self.showing_party:
                        self.showing_party = False
                        return
                    self.showing_party_inv = True
                    self.party_inv_cursor = 0
                    self.party_inv_choosing = False
                    self.party_inv_member = 0
                    return
                if event.key == pygame.K_l:
                    self.showing_log = True
                    self.log_scroll = 0
                    return
                if event.key == pygame.K_h:
                    self.showing_help = True
                    return
                # Character sheet cursor navigation
                if self.showing_char_detail is not None:
                    member = self.game.party.members[self.showing_char_detail]
                    total_rows = 4 + len(member.inventory)
                    if event.key == pygame.K_UP:
                        self.char_sheet_cursor = (self.char_sheet_cursor - 1) % total_rows
                        return
                    elif event.key == pygame.K_DOWN:
                        self.char_sheet_cursor = (self.char_sheet_cursor + 1) % total_rows
                        return
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self._handle_equip_action(member)
                        return
                # 1-4 keys for char detail, 5 for party inventory
                if self.showing_party and self.showing_char_detail is None:
                    num = None
                    if event.key == pygame.K_1:
                        num = 0
                    elif event.key == pygame.K_2:
                        num = 1
                    elif event.key == pygame.K_3:
                        num = 2
                    elif event.key == pygame.K_4:
                        num = 3
                    if num is not None and num < len(self.game.party.members):
                        self.showing_char_detail = num
                        self.char_sheet_cursor = 0
                        self.char_sheet_origin = "party"
                        return
                    if event.key == pygame.K_5:
                        self.showing_party_inv = True
                        self.party_inv_cursor = 0
                        self.party_inv_choosing = False
                        self.party_inv_member = 0
                        return

        # If showing party, character detail, or party inventory, block all other input
        if self.showing_party or self.showing_char_detail is not None or self.showing_party_inv:
            return

        # Movement only if cooldown has elapsed
        if self.move_cooldown > 0:
            return

        dcol, drow = 0, 0
        if keys_pressed[pygame.K_LEFT] or keys_pressed[pygame.K_a]:
            dcol = -1
        elif keys_pressed[pygame.K_RIGHT] or keys_pressed[pygame.K_d]:
            dcol = 1
        elif keys_pressed[pygame.K_UP] or keys_pressed[pygame.K_w]:
            drow = -1
        elif keys_pressed[pygame.K_DOWN] or keys_pressed[pygame.K_s]:
            drow = 1

        if dcol != 0 or drow != 0:
            party = self.game.party
            target_col = party.col + dcol
            target_row = party.row + drow

            # Bump-to-fight: check if an orc is on the target tile
            orc = self._get_monster_at(target_col, target_row)
            if orc:
                self._start_orc_combat(orc)
                self.move_cooldown = MOVE_REPEAT_DELAY
                return

            moved = party.try_move(dcol, drow, self.game.tile_map)

            if moved:
                self.move_cooldown = MOVE_REPEAT_DELAY
                party.clock.advance(10)
                self.game.tile_map.tick_cooldowns()
                self._check_tile_events()
                # Move orcs after party moves
                self._move_monsters()
                self._check_monster_contact()
                # Occasionally respawn orcs that were killed
                if random.random() < 0.08:
                    self._spawn_orcs()
            else:
                self.move_cooldown = MOVE_REPEAT_DELAY
                self.show_message("Blocked!", 800)

    # ── Monster helpers ───────────────────────────────────────────

    def _get_monster_at(self, col, row):
        """Return the alive orc at (col, row), or None."""
        for mon in self.overworld_monsters:
            if mon.col == col and mon.row == row and mon.is_alive():
                return mon
        return None

    def _move_monsters(self):
        """Each alive orc wanders randomly, but pursues if within 6 tiles."""
        party = self.game.party
        alive = [m for m in self.overworld_monsters if m.is_alive()]
        occupied = {(m.col, m.row) for m in alive}
        for mon in alive:
            occupied.discard((mon.col, mon.row))
            dist = abs(mon.col - party.col) + abs(mon.row - party.row)
            if dist <= 6:
                mon.try_move_toward(
                    party.col, party.row,
                    self.game.tile_map,
                    occupied,
                )
            else:
                mon.try_move_random(
                    self.game.tile_map,
                    occupied,
                    party_col=party.col,
                    party_row=party.row,
                )
            occupied.add((mon.col, mon.row))

    def _check_monster_contact(self):
        """If an orc is adjacent to the party, start combat."""
        party = self.game.party
        for mon in self.overworld_monsters:
            if not mon.is_alive():
                continue
            if abs(mon.col - party.col) + abs(mon.row - party.row) == 1:
                self._start_orc_combat(mon)
                return

    def _start_orc_combat(self, orc):
        """Start combat against the contacted orc and any nearby orcs."""
        combat_state = self.game.states.get("combat")
        if not combat_state:
            return

        fighter = None
        for member in self.game.party.members:
            if member.is_alive():
                fighter = member
                break
        if not fighter:
            return

        # Use the pre-assigned encounter template stored on the map monster.
        # Fall back to a random encounter if not present.
        tmpl = getattr(orc, "encounter_template", None)
        if tmpl is None:
            enc = create_encounter("overworld")
            monsters = enc["monsters"]
            enc_name = enc["name"]
        else:
            monsters = [create_monster(n) for n in tmpl["monster_names"]]
            enc_name = tmpl["name"]
        for m in monsters:
            m.col = orc.col
            m.row = orc.row

        self.game.sfx.play("encounter")
        combat_state.start_combat(fighter, monsters,
                                  source_state="overworld",
                                  encounter_name=enc_name,
                                  map_monster_refs=[orc])
        self.game.change_state("combat")

    # ── Tile events ───────────────────────────────────────────────

    def _check_tile_events(self):
        """Check if the party stepped on a special tile."""
        tile_id = self.game.tile_map.get_tile(
            self.game.party.col, self.game.party.row
        )

        if tile_id == TILE_TOWN:
            # Enter the town!
            town_state = self.game.states["town"]
            town_state.enter_town(
                self.game.town_data,
                self.game.party.col,
                self.game.party.row
            )
            self.game.change_state("town")
            return

        elif tile_id == TILE_DUNGEON:
            dungeon_state = self.game.states["dungeon"]
            # Check if this is the quest dungeon location
            quest = self.game.quest
            if (quest and quest["status"] in ("active", "artifact_found")
                    and self.game.party.col == quest["dungeon_col"]
                    and self.game.party.row == quest["dungeon_row"]):
                # Enter the persistent quest dungeon
                dungeon_state.enter_quest_dungeon(
                    quest["levels"],
                    self.game.party.col,
                    self.game.party.row
                )
            else:
                # Generate a fresh dungeon each time!
                dungeon_data = generate_dungeon("The Depths")
                dungeon_state.enter_dungeon(
                    dungeon_data,
                    self.game.party.col,
                    self.game.party.row
                )
            self.game.change_state("dungeon")
            return

        elif tile_id == TILE_CHEST:
            self._open_chest()
            # Restore the original tile that was under the chest
            pos = (self.game.party.col, self.game.party.row)
            original = self.chest_under_tiles.pop(pos, TILE_GRASS)
            self.game.tile_map.set_tile(pos[0], pos[1], original)
            return

        # ── Unique tile check ──
        self._check_unique_tile()

    # ── Unique tile interaction ────────────────────────────────

    def _check_unique_tile(self):
        """Check if the party is standing on a unique tile and trigger it."""
        tmap = self.game.tile_map
        col, row = self.game.party.col, self.game.party.row
        utile = tmap.get_unique(col, row)
        if not utile:
            return

        # One-time tiles that have already been triggered
        one_time = utile.get("interact_data", {}).get("one_time", False)
        if one_time and tmap.is_unique_triggered(col, row):
            return

        # Cooldown check
        if tmap.is_unique_on_cooldown(col, row):
            return

        # ── Show the description and interact text ──
        name = utile.get("name", "Something")
        description = utile.get("description", "")
        interact_text = utile.get("interact_text", "")

        # Log the discovery
        self.game.game_log.append(f"-- {name} --")
        if description:
            self.game.game_log.append(description)
        if interact_text:
            self.game.game_log.append(interact_text)

        # Show a brief floating message on screen
        self.show_message(name, 3500)

        # Show description in bottom bar with animation
        self.unique_tile_text = description or interact_text or name
        self.unique_tile_timer = 5000  # 5 seconds
        self.unique_tile_flash = 0.0
        self.unique_tile_pos = (col, row)

        # Mark one-time tiles
        if one_time:
            tmap.mark_unique_triggered(col, row)

        # Apply cooldown if specified
        cooldown = utile.get("interact_data", {}).get("cooldown_steps", 0)
        if cooldown > 0:
            tmap.set_unique_cooldown(col, row, cooldown)

    # ── Chest loot ─────────────────────────────────────────────

    _CHEST_LOOT = [
        (None,           10),   # gold only
        ("Torch",         6),
        ("Healing Herb",  5),
        ("Antidote",      3),
        ("Dagger",        3),
        ("Club",          3),
        ("Mace",          2),
        ("Leather",       2),
        ("Sling",         2),
        ("Axe",           1),
        ("Sword",         1),
        ("Chain",         1),
        ("Bow",           1),
    ]

    def _open_chest(self):
        """Roll random loot from a chest: gold, an item, or both."""
        self.game.sfx.play("treasure")
        gold = random.randint(5, 30)
        self.game.party.gold += gold

        total_weight = sum(w for _, w in self._CHEST_LOOT)
        roll = random.randint(1, total_weight)
        cumulative = 0
        chosen_item = None
        for item, weight in self._CHEST_LOOT:
            cumulative += weight
            if roll <= cumulative:
                chosen_item = item
                break

        if chosen_item:
            self.game.party.inv_add(chosen_item)
            self.show_message(
                f"Treasure! {gold} gold and {chosen_item}!", 2500)
        else:
            self.show_message(f"Treasure! Found {gold} gold!", 2000)

    def show_message(self, text, duration_ms=2000):
        """Display a temporary message."""
        self.message = text
        self.message_timer = duration_ms
        if text:
            self.game.game_log.append(text)

    def update(self, dt):
        """Update timers."""
        dt_ms = dt * 1000  # convert seconds to ms
        if self.message_timer > 0:
            self.message_timer -= dt_ms
            if self.message_timer <= 0:
                self.message = ""
                self.message_timer = 0

        if self.move_cooldown > 0:
            self.move_cooldown -= dt_ms
            if self.move_cooldown < 0:
                self.move_cooldown = 0

        # Tick use-item animation
        if self.use_item_anim and self.use_item_anim["timer"] > 0:
            self.use_item_anim["timer"] -= dt_ms
            if self.use_item_anim["timer"] <= 0:
                self.use_item_anim = None

        # Unique tile discovery animation
        if self.unique_tile_timer > 0:
            self.unique_tile_timer -= dt_ms
            self.unique_tile_flash += dt * 6.0  # ~6 radians/sec for pulsing
            if self.unique_tile_timer <= 0:
                self.unique_tile_timer = 0
                self.unique_tile_text = ""
                self.unique_tile_pos = None

    def draw(self, renderer):
        """Draw the overworld in Ultima III style."""
        if self.showing_party_inv:
            action_opts = self._get_party_inv_action_options() if self.party_inv_action_menu else None
            renderer.draw_party_inventory_u3(
                self.game.party, self.party_inv_cursor,
                self.party_inv_choosing, self.party_inv_member,
                self.party_inv_action_menu, self.party_inv_action_cursor,
                action_options=action_opts,
                choosing_effect=self.choosing_effect,
                effect_list=self.effect_list,
                effect_cursor=self.effect_cursor)
            if self.use_item_anim:
                renderer.draw_use_item_animation(self.game.party, self.use_item_anim)
            if self.examining_item:
                renderer.draw_item_examine(self.examining_item)
            return
        if self.showing_char_detail is not None:
            idx = self.showing_char_detail
            member = self.game.party.members[idx]
            action_opts = self._get_action_options(member) if self.char_action_menu else None
            renderer.draw_character_sheet_u3(
                member, idx, self.char_sheet_cursor,
                self.char_action_menu, self.char_action_cursor,
                action_options=action_opts)
            if self.examining_item:
                renderer.draw_item_examine(self.examining_item)
            return
        if self.showing_party:
            renderer.draw_party_screen_u3(self.game.party)
            return
        renderer.draw_overworld_u3(
            self.game.party,
            self.game.tile_map,
            message=self.message,
            overworld_monsters=self.overworld_monsters,
            unique_text=self.unique_tile_text,
            unique_flash=self.unique_tile_flash,
            unique_pos=self.unique_tile_pos,
        )
        if self.showing_help:
            renderer.draw_overworld_help_overlay()
        if self.showing_log:
            renderer.draw_log_overlay(self.game.game_log, self.log_scroll)
