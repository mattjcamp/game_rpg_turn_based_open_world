"""
Inventory handling mixin shared by town, overworld, and dungeon states.

Provides character inventory (equip/unequip/use) and party stash
(browse/give/use/equip effects) UI logic.  Each concrete state class
inherits this mixin alongside BaseState and calls _init_inventory_state()
in its __init__.

Dungeon-specific behaviour (torch activation on equip/remove) is handled
through three hook methods that DungeonState overrides.
"""

import random

import pygame


class InventoryMixin:
    """Shared inventory UI methods for all exploration states."""

    # ── Initialisation ─────────────────────────────────────────

    def _init_inventory_state(self):
        """Set up all instance variables used by the inventory UI.

        Call this from the concrete state's __init__ after super().__init__.
        """
        # Party / character sheet overlay
        self.showing_party = False
        self.showing_char_detail = None   # member index 0-3, or None
        self.char_sheet_cursor = 0        # cursor in equip/item list
        self.char_sheet_origin = None     # "inventory", "party", or None
        self.char_action_menu = False     # True when action popup open
        self.char_action_cursor = 0       # selected option in popup
        self.examining_item = None        # item name being examined

        # Party shared-inventory screen
        self.showing_party_inv = False
        self.party_inv_cursor = 0
        self.party_inv_choosing = False
        self.party_inv_member = 0
        self.party_inv_action_menu = False
        self.party_inv_action_cursor = 0

        # Effect chooser
        self.choosing_effect = False
        self.effect_list = []
        self.effect_cursor = 0

        # Use-item animation overlay
        self.use_item_anim = None

        # Game log overlay
        self.showing_log = False
        self.log_scroll = 0

    # ── Messages ───────────────────────────────────────────────

    def show_message(self, text, duration_ms=2000):
        """Display a temporary message."""
        self.message = text
        self.message_timer = duration_ms
        if text:
            self.game.game_log.append(text)

    # ── Hook methods (overridden by DungeonState) ──────────────

    def _on_effect_assigned(self, effect_name):
        """Called after an effect is assigned to a slot."""
        pass

    def _on_effect_removed(self, effect_name):
        """Called after an effect is removed from a slot."""
        pass

    def _on_item_equipped(self, item_name):
        """Called after a stash item is equipped into an effect slot."""
        pass

    # ── Character inventory helpers ────────────────────────────

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
        from src.party import PartyMember, ITEM_INFO
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
        """Handle input while the character action menu popup is open."""
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
                        self.message = (
                            f"Cannot remove basic "
                            f"{member.equipped.get(slot_keys[idx], 'gear')}!")
                        self.message_timer = 2000
            elif chosen.startswith("EQUIP"):
                inv_idx = idx - 4
                if inv_idx < len(member.inventory):
                    from src.party import PartyMember
                    _label_to_key = {
                        v: k for k, v in PartyMember._SLOT_LABELS.items()
                    }
                    slot_label = chosen.split("\u2192 ", 1)[1].strip()
                    slot_key = _label_to_key.get(slot_label)
                    member.equip_item(member.inventory[inv_idx], slot_key)
            elif chosen == "RETURN TO PARTY STASH":
                if idx < 4:
                    slot_keys = ["right_hand", "left_hand", "body", "head"]
                    member.return_equipped_to_party(
                        slot_keys[idx], self.game.party)
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
                self.show_message(f"{member.name} is unconscious!", 2500)
                return
            hp_restore = max(1, int(member.max_hp * 0.35)) + random.randint(1, 8)
            mp_restore = max(1, int(member.max_mp * 0.30)) + random.randint(1, 4)
            old_hp, old_mp = member.hp, getattr(member, "current_mp", 0)
            member.hp = min(member.max_hp, member.hp + hp_restore)
            member.current_mp = min(
                member.max_mp,
                getattr(member, "current_mp", 0) + mp_restore)
            actual_hp = member.hp - old_hp
            actual_mp = member.current_mp - old_mp
            self.game.game_log.append(
                f"{member.name} rests using {item_name}. "
                f"(+{actual_hp} HP, +{actual_mp} MP)")
            self.show_message(
                f"{member.name}: +{actual_hp} HP, +{actual_mp} MP", 3000)
        elif effect == "heal_hp":
            if member.hp <= 0:
                self.show_message(f"{member.name} is unconscious!", 2500)
                return
            missing = member.max_hp - member.hp
            if missing <= 0:
                self.show_message(
                    f"{member.name} is already at full health!", 2500)
                return
            heal = power + random.randint(1, 6)
            member.hp = min(member.max_hp, member.hp + heal)
            self.game.game_log.append(
                f"{member.name} uses {item_name}. (+{heal} HP)")
            self.show_message(f"{member.name}: +{heal} HP", 3000)
        elif effect == "heal_mp":
            if member.hp <= 0:
                self.show_message(f"{member.name} is unconscious!", 2500)
                return
            missing = member.max_mp - getattr(member, "current_mp", 0)
            if missing <= 0:
                self.show_message(
                    f"{member.name} is already at full mana!", 2500)
                return
            restore = power + random.randint(1, 4)
            member.current_mp = min(
                member.max_mp,
                getattr(member, "current_mp", 0) + restore)
            self.game.game_log.append(
                f"{member.name} uses {item_name}. (+{restore} MP)")
            self.show_message(f"{member.name}: +{restore} MP", 3000)
        elif effect == "cure_poison":
            if getattr(member, "poisoned", False):
                member.poisoned = False
                self.game.game_log.append(
                    f"{member.name}'s poison was cured!")
                self.show_message(f"{member.name}: Poison cured!", 3000)
            else:
                self.show_message(f"{member.name} is not poisoned!", 2500)
                return
        else:
            self.game.game_log.append(f"{member.name} used {item_name}.")
            self.show_message(f"Used {item_name}", 2000)

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

    # ── Party stash screen ─────────────────────────────────────

    def _handle_party_inv_input(self, event):
        """Handle input for the shared party inventory screen.

        The unified cursor covers effect slots and then shared inventory items.
        """
        party = self.game.party
        inv = party.shared_inventory
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
                self._on_effect_assigned(chosen_eff["name"])
                self.choosing_effect = False
            return

        # Action menu is open
        if self.party_inv_action_menu:
            options = self._get_party_inv_action_options()
            if not options:
                self.party_inv_action_menu = False
                return
            if event.key == pygame.K_UP:
                self.party_inv_action_cursor = (
                    (self.party_inv_action_cursor - 1) % len(options))
            elif event.key == pygame.K_DOWN:
                self.party_inv_action_cursor = (
                    (self.party_inv_action_cursor + 1) % len(options))
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                chosen = options[self.party_inv_action_cursor]
                self._handle_party_inv_action(chosen)
            elif event.key == pygame.K_ESCAPE:
                self.party_inv_action_menu = False
            return

        # Browsing unified list (effect slots + inventory)
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
                removed = party.get_effect(slot_key)
                self._on_effect_removed(removed)
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
                    self._on_item_equipped(item_name)
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
                m.current_mp = min(
                    m.max_mp, getattr(m, "current_mp", 0) + mp_restore)
                total_hp += m.hp - old_hp
                total_mp += m.current_mp - old_mp
            self.game.game_log.append(
                f"The party rests using {item_name}...")
            self.game.game_log.append(
                f"  Restored {total_hp} HP and {total_mp} MP across the party!")
            self.show_message(
                f"Rested! +{total_hp} HP, +{total_mp} MP", 3500)
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
                self.game.game_log.append(
                    "Everyone is already at full health!")
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
                best.current_mp = min(
                    best.max_mp,
                    getattr(best, "current_mp", 0) + restore)
                self.game.game_log.append(
                    f"{best.name} uses {item_name}. (+{restore} MP)")
                self.show_message(f"{best.name}: +{restore} MP", 3000)
            else:
                self.game.game_log.append(
                    "Everyone is already at full mana!")
                self.show_message("Everyone is at full mana!", 2500)
                return
        elif effect == "cure_poison":
            cured = False
            for m in party.members:
                if getattr(m, "poisoned", False):
                    m.poisoned = False
                    self.game.game_log.append(
                        f"{m.name}'s poison was cured!")
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
        entry = (party.shared_inventory[inv_idx]
                 if inv_idx < len(party.shared_inventory) else None)
        if (entry is not None and isinstance(entry, dict)
                and entry.get("charges", 0) > 0):
            party.inv_consume_charge(item_name)
        else:
            party.inv_remove(item_name)
