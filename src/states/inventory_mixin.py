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

        # Spell casting overlay
        self.showing_spell_list = False
        self.spell_list_items = []       # [(spell_id, label, mp_cost, member_idx)]
        self.spell_list_cursor = 0

        # Heal target selection (choosing which party member to heal)
        self.choosing_heal_target = False
        self.heal_target_cursor = 0
        # Stored spell info while picking a target:
        # (spell_id, cost, member_index, spell_data_dict)
        self.pending_heal_spell = None

        # Game log overlay
        self.showing_log = False
        self.log_scroll = 0

        # Potion crafting overlay
        self.showing_brew_list = False
        self.brew_list_items = []     # [(recipe_id, recipe_data, can_brew)]
        self.brew_list_cursor = 0
        self.brew_result_msg = None   # message shown after a brew attempt
        self.brew_result_timer = 0

    # ── Messages ───────────────────────────────────────────────

    def show_message(self, text, duration_ms=2000):
        """Display a temporary message."""
        self.message = text
        self.message_timer = duration_ms
        if text:
            self.game.game_log.append(text)

    # ── Hook methods (overridden by subclasses) ────────────────

    def _on_effect_assigned(self, effect_name):
        """Called after an effect is assigned to a slot."""
        pass

    def _on_effect_removed(self, effect_name):
        """Called after an effect is removed from a slot."""
        pass

    def _on_item_equipped(self, item_name):
        """Called after a stash item is equipped into an effect slot."""
        pass

    def _start_pickpocket_targeting(self):
        """Close the stash and enter pickpocket target selection on the map.

        Overridden by TownState; default is a no-op.
        """
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

    def _handle_equip_action(self, member):
        """Open the action menu for the selected item/slot."""
        options = self._get_action_options(member)
        if not options:
            self.message = "Empty slot — equip items from inventory"
            self.message_timer = 2000
            return
        self.char_action_menu = True
        self.char_action_cursor = 0

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

        if effect == "combat_only":
            self.show_message(f"{item_name} can only be used in combat!", 2500)
            return
        elif effect == "rest":
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
        elif effect == "buff_strength":
            buffs = getattr(member, "potion_buffs", {})
            buffs["strength"] = buffs.get("strength", 0) + power
            member.potion_buffs = buffs
            self.game.game_log.append(
                f"{member.name} drinks {item_name}. (+{power} STR for next combat)")
            self.show_message(
                f"{member.name}: +{power} STR (next combat)", 3000)
        elif effect == "buff_ac":
            buffs = getattr(member, "potion_buffs", {})
            buffs["ac"] = buffs.get("ac", 0) + power
            member.potion_buffs = buffs
            self.game.game_log.append(
                f"{member.name} drinks {item_name}. (+{power} AC for next combat)")
            self.show_message(
                f"{member.name}: +{power} AC (next combat)", 3000)
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

    # Index of the CAST row in the unified cursor (right after effect rows)
    def _stash_layout(self):
        """Return (NUM_EFFECTS, CAST_INDEX, BREW_INDEX, STASH_START, total,
                   PICK_INDEX, TINK_INDEX).

        NUM_EFFECT_ROWS counts active effects + available (unassigned) effects.
        PICK_INDEX is -1 when the Pickpocket row is hidden.
        TINK_INDEX is -1 when the Tinker row is hidden.
        """
        party = self.game.party
        n = len(self._all_effect_rows())
        cast_idx = n                        # one row for CAST
        brew_idx = cast_idx + 1             # one row for BREW
        # Pickpocket row shows only when effect is active + adjacent NPC
        pick_idx = -1
        tink_idx = -1
        next_idx = brew_idx + 1
        if self._can_pickpocket():
            pick_idx = next_idx
            next_idx += 1
        if self._can_tinker():
            tink_idx = next_idx
            next_idx += 1
        stash_start = next_idx
        total = stash_start + len(party.shared_inventory)
        return n, cast_idx, brew_idx, stash_start, total, pick_idx, tink_idx

    def _has_alchemist(self):
        """Return the first alive Alchemist in the party, or None."""
        for m in self.game.party.members:
            if m.is_alive() and m.char_class == "Alchemist":
                return m
        return None

    # ── Pickpocket helpers ────────────────────────────────────

    # Low-level loot table: (weight, item_name)
    _PICKPOCKET_LOOT = [
        (25, "Gold"),               # just some coins (special-cased below)
        (20, "Healing Herb"),
        (12, "Torch"),
        (10, "Arrows"),
        (10, "Antidote"),
        (8,  "Lockpick"),
        (5,  "Dagger"),
        (4,  "Mana Potion"),
        (3,  "Stones"),
        (2,  "Smoke Bomb"),
        (1,  "Holy Water"),
    ]

    def _get_adjacent_npc(self):
        """Return an NPC adjacent to the party, or None.

        Only works in TownState where town_data with NPCs is available.
        """
        town_data = getattr(self, "town_data", None)
        if town_data is None:
            return None
        party = self.game.party
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if dc == 0 and dr == 0:
                    continue
                npc = town_data.get_npc_at(party.col + dc, party.row + dr)
                if npc is not None:
                    return npc
        return None

    def _get_halfling(self):
        """Return the first alive Halfling in the party, or None."""
        for m in self.game.party.members:
            if m.is_alive() and m.race == "Halfling":
                return m
        return None

    def _can_pickpocket(self):
        """True when an alive Halfling is in the party, at least one
        NPC is adjacent, and the party hasn't pickpocketed today."""
        if self._get_halfling() is None:
            return False
        # Once per day limit
        party = self.game.party
        if party.last_pickpocket_day == party.clock.day_index:
            return False
        return self._get_adjacent_npc() is not None

    def _get_adjacent_npcs(self):
        """Return a list of all NPCs adjacent to the party (8 directions)."""
        town_data = getattr(self, "town_data", None)
        if town_data is None:
            return []
        party = self.game.party
        npcs = []
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if dc == 0 and dr == 0:
                    continue
                npc = town_data.get_npc_at(party.col + dc, party.row + dr)
                if npc is not None:
                    npcs.append(npc)
        return npcs

    def _attempt_pickpocket(self, npc=None):
        """Perform a pickpocket attempt against the given NPC.

        Uses a DEX-based saving throw:
          roll = d20 + halfling's DEX modifier
          DC 12 = success, DC < 12 = failure (caught!)

        On success: a random low-level item is added to shared inventory.
        On failure: a small gold penalty and the NPC reacts.
        """
        halfling = self._get_halfling()
        if npc is None:
            npc = self._get_adjacent_npc()
        if not halfling or not npc:
            self.show_message("No one nearby to pickpocket!", 2000)
            return

        party = self.game.party

        # Record that pickpocket was used today (win or lose)
        party.last_pickpocket_day = party.clock.day_index

        roll = random.randint(1, 20)
        dex_mod = halfling.get_modifier(halfling.dexterity)
        total = roll + dex_mod
        dc = 12

        if total >= dc:
            # Success — pick a random item from the loot table
            item = self._pick_loot()
            if item == "Gold":
                amount = random.randint(3, 15)
                party.gold += amount
                self.show_message(
                    f"{halfling.name} pilfers {amount} gold from {npc.name}! "
                    f"(d20:{roll}+{dex_mod}={total} vs DC{dc})", 3500)
            else:
                party.shared_inventory.append(item)
                self.show_message(
                    f"{halfling.name} steals a {item} from {npc.name}! "
                    f"(d20:{roll}+{dex_mod}={total} vs DC{dc})", 3500)
        else:
            # Failure — caught! Lose some gold as a bribe/fine
            fine = random.randint(5, 20)
            actual_fine = min(fine, party.gold)
            party.gold -= actual_fine
            self.show_message(
                f"{halfling.name} is caught by {npc.name}! Lost {actual_fine} gold. "
                f"(d20:{roll}+{dex_mod}={total} vs DC{dc})", 3500)

    def _pick_loot(self):
        """Choose a random item from the pickpocket loot table."""
        total_weight = sum(w for w, _ in self._PICKPOCKET_LOOT)
        r = random.randint(1, total_weight)
        cumulative = 0
        for weight, item in self._PICKPOCKET_LOOT:
            cumulative += weight
            if r <= cumulative:
                return item
        return self._PICKPOCKET_LOOT[-1][1]  # fallback

    # ── Tinker helpers ─────────────────────────────────────────

    # Tiered loot tables keyed by minimum gnome level
    _TINKER_LOOT_TIERS = [
        # (min_level, [(weight, item_name), ...])
        (1, [
            (25, "Arrows"),
            (20, "Stones"),
            (15, "Torch"),
            (15, "Lockpick"),
            (10, "Dagger"),
            (10, "Healing Herb"),
            (5,  "Antidote"),
        ]),
        (4, [
            (20, "Arrows"),
            (15, "Mana Potion"),
            (15, "Lockpick"),
            (12, "Short Sword"),
            (10, "Smoke Bomb"),
            (10, "Holy Water"),
            (8,  "Healing Herb"),
            (5,  "Short Bow"),
            (5,  "Bolts"),
        ]),
        (7, [
            (18, "Mana Potion"),
            (15, "Holy Water"),
            (12, "Smoke Bomb"),
            (12, "Long Sword"),
            (10, "Chain Mail"),
            (10, "Steel Shield"),
            (8,  "Bolts"),
            (8,  "Fire Bomb"),
            (7,  "Crossbow"),
        ]),
    ]

    def _get_gnome(self):
        """Return the first alive Gnome in the party, or None."""
        for m in self.game.party.members:
            if m.is_alive() and m.race == "Gnome":
                return m
        return None

    def _can_tinker(self):
        """True when an alive Gnome is in the party and hasn't tinkered today."""
        if self._get_gnome() is None:
            return False
        party = self.game.party
        if party.last_tinker_day == party.clock.day_index:
            return False
        return True

    def _get_tinker_loot_table(self, gnome_level):
        """Return the best loot table the gnome qualifies for by level."""
        best = self._TINKER_LOOT_TIERS[0][1]
        for min_lvl, table in self._TINKER_LOOT_TIERS:
            if gnome_level >= min_lvl:
                best = table
        return best

    def _attempt_tinker(self):
        """Perform a tinker attempt — the gnome crafts a random item.

        Uses an INT-based roll:
          roll = d20 + gnome's INT modifier
          DC 8 = success (easy — gnomes are natural tinkerers!)

        On success: a random item from the level-appropriate loot table.
        On failure: the attempt is wasted with no item produced.
        """
        gnome = self._get_gnome()
        if not gnome:
            self.show_message("No Gnome in the party!", 2000)
            return

        party = self.game.party

        # Record that tinker was used today (win or lose)
        party.last_tinker_day = party.clock.day_index

        roll = random.randint(1, 20)
        int_mod = gnome.get_modifier(gnome.intelligence)
        total = roll + int_mod
        dc = 8

        if total >= dc:
            # Success — pick a random item from the level-appropriate table
            table = self._get_tinker_loot_table(gnome.level)
            total_weight = sum(w for w, _ in table)
            r = random.randint(1, total_weight)
            cumulative = 0
            item = table[-1][1]
            for weight, item_name in table:
                cumulative += weight
                if r <= cumulative:
                    item = item_name
                    break
            party.shared_inventory.append(item)
            msg = (f"{gnome.name} tinkers a {item}! "
                   f"(d20:{roll}+{int_mod}={total} vs DC{dc})")
            self.show_message(msg, 3500)

            # Move cursor to the newly created item so its detail shows
            _, _, _, stash_start, _, _, _ = self._stash_layout()
            new_item_idx = len(party.shared_inventory) - 1
            self.party_inv_cursor = stash_start + new_item_idx

            # Trigger a crafting animation overlay
            self.use_item_anim = {
                "effect": "tinker",
                "timer": 2000,
                "duration": 2000,
                "text": f"Crafted {item}!",
            }
        else:
            # Failure — materials wasted
            msg = (f"{gnome.name}'s tinkering fails... scraps everywhere! "
                   f"(d20:{roll}+{int_mod}={total} vs DC{dc})")
            self.show_message(msg, 3500)

            # Trigger a failure animation
            self.use_item_anim = {
                "effect": "tinker_fail",
                "timer": 1500,
                "duration": 1500,
                "text": "Tinkering failed!",
            }

    def _active_effects(self):
        """Return a list of (slot_key, effect_name) for non-empty effect slots."""
        party = self.game.party
        return [(s, party.get_effect(s)) for s in party.EFFECT_SLOTS
                if party.get_effect(s) is not None]

    def _available_effects(self):
        """Return a list of effect dicts the party qualifies for but hasn't slotted."""
        return self.game.party.get_available_effects()

    def _all_effect_rows(self):
        """Build the combined effect list: active first, then available.

        Returns a list of tuples:
          ('active', slot_key, effect_name)   — currently slotted
          ('available', effect_dict)          — can be assigned
        """
        rows = []
        for slot_key, eff_name in self._active_effects():
            rows.append(('active', slot_key, eff_name))
        for eff in self._available_effects():
            rows.append(('available', eff))
        return rows

    def _handle_party_inv_input(self, event):
        """Handle input for the shared party inventory screen.

        The unified cursor covers effect slots, a CAST row, then stash items.
        """
        party = self.game.party
        inv = party.shared_inventory
        NUM_EFFECTS, CAST_INDEX, BREW_INDEX, STASH_START, total_items, PICK_INDEX, TINK_INDEX = self._stash_layout()

        # Heal target selection overlay is open — delegate input
        if self.choosing_heal_target:
            self._handle_heal_target_input(event)
            return

        # Spell list overlay is open — delegate input
        if self.showing_spell_list:
            self._handle_spell_list_input(event)
            return

        # Brew list overlay is open — delegate input
        if self.showing_brew_list:
            self._handle_brew_list_input(event)
            return

        # Examining an item — close on ESC/Enter/Space
        if self.examining_item is not None:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.examining_item = None
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

        # Browsing unified list (active effects + CAST + inventory)
        if event.key == pygame.K_UP and total_items > 0:
            self.party_inv_cursor = (self.party_inv_cursor - 1) % total_items
        elif event.key == pygame.K_DOWN and total_items > 0:
            self.party_inv_cursor = (self.party_inv_cursor + 1) % total_items
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and total_items > 0:
            idx = self.party_inv_cursor
            if idx < NUM_EFFECTS:
                # Effect row — toggle: remove if active, assign if available
                all_rows = self._all_effect_rows()
                if idx < len(all_rows):
                    row = all_rows[idx]
                    if row[0] == 'active':
                        # Remove the active effect
                        slot_key, eff_name = row[1], row[2]
                        # Galadriel's Light: clear step counter on removal
                        if eff_name == "Galadriel's Light":
                            party.galadriels_light_steps = 0
                        self._on_effect_removed(eff_name)
                        party.set_effect(slot_key, None)
                    else:
                        # Assign available effect to first free slot
                        eff_dict = row[1]
                        eff_name = eff_dict["name"]
                        assigned = False
                        for slot_key in party.EFFECT_SLOTS:
                            if party.get_effect(slot_key) is None:
                                party.set_effect(slot_key, eff_name)
                                # Galadriel's Light: init step counter + day cooldown
                                if eff_dict.get("id") == "galadriels_light":
                                    party.galadriels_light_steps = eff_dict.get("duration", 500)
                                    party.last_galadriels_light_day = party.clock.day_index
                                self._on_effect_assigned(eff_name)
                                assigned = True
                                break
                        if not assigned:
                            self.show_message(
                                "All effect slots are full!", 2000)
                    # Adjust cursor if needed after change
                    new_n, _, _, _, new_total, _, _ = self._stash_layout()
                    if self.party_inv_cursor >= new_total and new_total > 0:
                        self.party_inv_cursor = new_total - 1
            elif idx == CAST_INDEX:
                # Open spell casting overlay
                spells = self._build_castable_spells()
                self.spell_list_items = spells
                self.spell_list_cursor = 0
                self.showing_spell_list = True
            elif idx == BREW_INDEX:
                # Open potion crafting overlay
                self._open_brew_list()
            elif PICK_INDEX >= 0 and idx == PICK_INDEX:
                # Close stash and enter pickpocket targeting mode on the map
                self._start_pickpocket_targeting()
            elif TINK_INDEX >= 0 and idx == TINK_INDEX:
                # Gnome tinkers a random item on the spot
                self._attempt_tinker()
            else:
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
        NUM_EFFECTS, CAST_INDEX, BREW_INDEX, STASH_START, _, PICK_INDEX, TINK_INDEX = self._stash_layout()
        idx = self.party_inv_cursor

        if idx < NUM_EFFECTS:
            # Effect rows are handled directly by Enter (remove), not action menu
            self.party_inv_action_menu = False
        elif idx == CAST_INDEX:
            # CAST row — handled by browsing Enter, not by action menu
            self.party_inv_action_menu = False
        elif idx >= STASH_START:
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
        NUM_EFFECTS, CAST_INDEX, BREW_INDEX, STASH_START, _, PICK_INDEX, TINK_INDEX = self._stash_layout()
        idx = self.party_inv_cursor

        if idx < NUM_EFFECTS:
            # Effect rows — no action menu; Enter removes directly
            return []
        elif idx == CAST_INDEX:
            # No action menu for the CAST row — Enter opens spell list directly
            return []
        elif idx >= STASH_START:
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

        if effect == "combat_only":
            self.show_message(f"{item_name} can only be used in combat!", 2500)
            return
        elif effect == "rest":
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
        elif effect == "buff_strength":
            # Apply to the first alive member
            target = None
            for m in party.members:
                if m.is_alive():
                    target = m
                    break
            if target:
                buffs = getattr(target, "potion_buffs", {})
                buffs["strength"] = buffs.get("strength", 0) + power
                target.potion_buffs = buffs
                self.game.game_log.append(
                    f"{target.name} drinks {item_name}. (+{power} STR for next combat)")
                self.show_message(
                    f"{target.name}: +{power} STR (next combat)", 3000)
            else:
                self.show_message("No one is alive!", 2500)
                return
        elif effect == "buff_ac":
            # Apply to the first alive member
            target = None
            for m in party.members:
                if m.is_alive():
                    target = m
                    break
            if target:
                buffs = getattr(target, "potion_buffs", {})
                buffs["ac"] = buffs.get("ac", 0) + power
                target.potion_buffs = buffs
                self.game.game_log.append(
                    f"{target.name} drinks {item_name}. (+{power} AC for next combat)")
                self.show_message(
                    f"{target.name}: +{power} AC (next combat)", 3000)
            else:
                self.show_message("No one is alive!", 2500)
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

    # ── Spell casting from party stash ────────────────────────────

    def _get_screen_context(self):
        """Return the usable_in tag for the current game state."""
        from src.states.overworld import OverworldState
        from src.states.town import TownState
        from src.states.dungeon import DungeonState
        if isinstance(self, OverworldState):
            return "overworld"
        elif isinstance(self, TownState):
            return "town"
        elif isinstance(self, DungeonState):
            return "dungeon"
        return None

    def _build_castable_spells(self):
        """Build a list of spells castable from the party stash screen.

        Filters by current screen context, class, level, MP, and alive status.
        Returns a list of (spell_id, label, mp_cost, member_index) tuples.
        """
        from src.party import SPELLS_DATA
        context = self._get_screen_context()
        if context is None:
            return []

        party = self.game.party
        result = []
        for mi, member in enumerate(party.members):
            if not member.is_alive():
                continue
            if not member.can_cast:
                continue
            member_class = member.char_class.strip().lower()
            member_level = getattr(member, "level", 1)
            for spell_id, spell in SPELLS_DATA.items():
                # Check screen context
                if context not in spell.get("usable_in", []):
                    continue
                # Check class requirement
                allowed = [c.lower() for c in spell.get("allowable_classes", [])]
                if member_class not in allowed:
                    continue
                # Check level requirement
                if member_level < spell.get("min_level", 1):
                    continue
                # Check MP
                cost = spell["mp_cost"]
                if member.current_mp < cost:
                    continue
                label = f"{member.name}: {spell['name']} ({cost}MP)"
                result.append((spell_id, label, cost, mi))
        return result

    def _handle_spell_list_input(self, event):
        """Handle input while the spell list overlay is open."""
        if not self.spell_list_items:
            if event.key in (pygame.K_ESCAPE, pygame.K_c,
                             pygame.K_RETURN, pygame.K_SPACE):
                self.showing_spell_list = False
            return

        if event.key == pygame.K_UP:
            self.spell_list_cursor = (
                (self.spell_list_cursor - 1) % len(self.spell_list_items))
        elif event.key == pygame.K_DOWN:
            self.spell_list_cursor = (
                (self.spell_list_cursor + 1) % len(self.spell_list_items))
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            spell_id, _label, cost, mi = (
                self.spell_list_items[self.spell_list_cursor])
            self._cast_exploration_spell(spell_id, cost, mi)
            self.showing_spell_list = False
        elif event.key in (pygame.K_ESCAPE, pygame.K_c):
            self.showing_spell_list = False

    # ── Heal target selection ────────────────────────────────────

    def _handle_heal_target_input(self, event):
        """Handle input while the heal-target chooser is open."""
        party = self.game.party
        n = len(party.members)
        if event.key == pygame.K_UP:
            self.heal_target_cursor = (self.heal_target_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self.heal_target_cursor = (self.heal_target_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._apply_heal_to_target(self.heal_target_cursor)
            self.choosing_heal_target = False
            self.pending_heal_spell = None
            self.showing_spell_list = False
        elif event.key in (pygame.K_ESCAPE, pygame.K_c):
            # Cancel — MP was already refunded
            self.choosing_heal_target = False
            self.pending_heal_spell = None

    def _apply_heal_to_target(self, target_index):
        """Roll healing dice and apply HP to the chosen party member."""
        if not self.pending_heal_spell:
            return
        spell_id, cost, caster_index, spell = self.pending_heal_spell
        party = self.game.party
        caster = party.members[caster_index]
        target = party.members[target_index]
        spell_name = spell.get("name", spell_id)

        # Check the caster still has enough MP (in case something changed)
        if caster.current_mp < cost:
            self.show_message(
                f"{caster.name} doesn't have enough MP!", 2000)
            return

        # Deduct MP now that the target is confirmed
        caster.current_mp -= cost

        if not target.is_alive():
            self.show_message(
                f"{target.name} is dead — heal cannot help!", 2000)
            return

        missing = target.max_hp - target.hp
        if missing <= 0:
            self.show_message(
                f"{caster.name} casts {spell_name}! "
                f"{target.name} is already at full health.", 3000)
            return

        ev = spell.get("effect_value", {})
        if "dice_count" in ev:
            num_dice = ev.get("dice_count", 1)
            die_size = ev.get("dice_sides", 8)
        else:
            dice_str = ev.get("dice", "1d8")
            parts = dice_str.split("d")
            num_dice = int(parts[0]) if len(parts) == 2 else 1
            die_size = int(parts[1]) if len(parts) == 2 else 8
        heal = sum(random.randint(1, die_size) for _ in range(num_dice))
        heal += ev.get("flat_bonus", 0)
        min_heal = ev.get("min_heal", 1)
        max_heal = ev.get("max_heal", 9999)
        heal = max(min_heal, min(heal, max_heal))
        target.hp = min(target.max_hp, target.hp + heal)
        self.show_message(
            f"{caster.name} casts {spell_name}! "
            f"{target.name} healed for {heal} HP.", 3000)

    def _cast_exploration_spell(self, spell_id, cost, member_index):
        """Cast a spell from the exploration stash screen."""
        from src.party import SPELLS_DATA
        party = self.game.party
        member = party.members[member_index]
        spell = SPELLS_DATA.get(spell_id)
        if spell is None:
            return

        # Deduct MP
        member.current_mp = member.current_mp - cost

        effect_type = spell.get("effect_type", "")
        spell_name = spell.get("name", spell_id)

        if effect_type == "repel_monsters":
            radius = spell.get("effect_value", {}).get("radius", 5)
            push_dist = spell.get("effect_value", {}).get("push_distance", 3)
            duration = spell.get("duration", 0)
            self._on_spell_repel_monsters(radius, push_dist, duration)
            # Close the inventory so the player sees the wave on the map
            self.showing_party_inv = False
            self.show_message(
                f"{member.name} casts {spell_name}! Monsters flee!", 3000)

        elif effect_type in ("heal", "major_heal"):
            # Refund MP — it will be re-deducted when the player confirms
            # a target (or stays refunded if they cancel).
            member.current_mp = member.current_mp + cost
            # Enter target selection mode so the player picks who to heal
            self.pending_heal_spell = (spell_id, cost, member_index, spell)
            self.heal_target_cursor = 0
            self.choosing_heal_target = True
            return  # don't close the inventory overlay yet

        elif effect_type == "cure_poison":
            cured = False
            for m in party.members:
                if getattr(m, "poisoned", False):
                    m.poisoned = False
                    self.show_message(
                        f"{member.name} casts {spell_name}! "
                        f"{m.name}'s poison was cured!", 3000)
                    cured = True
                    break
            if not cured:
                self.show_message(
                    f"{member.name} casts {spell_name}! "
                    f"Nobody is poisoned.", 3000)

        elif effect_type == "resurrect":
            ev = spell.get("effect_value", {})
            # Find first dead (non-ash) member
            target = None
            for m in party.members:
                if m.hp <= 0 and not getattr(m, "is_ash", False):
                    target = m
                    break
            if target:
                chance = ev.get("success_chance", 0.75)
                if random.random() < chance:
                    target.hp = max(1, target.max_hp // 4)
                    self.show_message(
                        f"{member.name} casts {spell_name}! "
                        f"{target.name} returns to life!", 3000)
                else:
                    target.is_ash = True
                    self.show_message(
                        f"{member.name} casts {spell_name}... "
                        f"{target.name} crumbles to ash!", 3000)
            else:
                self.show_message(
                    f"{member.name} casts {spell_name}! "
                    f"No fallen allies to raise.", 3000)

        elif effect_type == "light":
            ev = spell.get("effect_value", {})
            duration = spell.get("duration", 10)
            self._on_spell_light(ev.get("radius", 2),
                                 ev.get("light_level", "short"),
                                 duration)
            self.show_message(
                f"{member.name} casts {spell_name}! "
                f"The area is illuminated.", 3000)

        elif effect_type == "magic_light":
            ev = spell.get("effect_value", {})
            steps = ev.get("steps", 100)
            self._on_spell_magic_light(steps)
            self.showing_party_inv = False
            self.show_message(
                f"{member.name} casts {spell_name}! "
                f"A radiant orb illuminates the way.", 3000)

        elif effect_type == "reveal_map":
            self._on_spell_reveal_map()
            self.show_message(
                f"{member.name} casts {spell_name}! "
                f"The surroundings are revealed.", 3000)

        elif effect_type in ("dungeon_rise", "dungeon_sink",
                             "dungeon_teleport", "dungeon_surface",
                             "surface_teleport"):
            self._on_spell_dungeon_nav(effect_type,
                                       spell.get("effect_value", {}))
            self.show_message(
                f"{member.name} casts {spell_name}!", 3000)

        else:
            # Fallback for unimplemented spell effects
            self.show_message(
                f"{member.name} casts {spell_name}! "
                f"(Effect not yet implemented)", 3000)

    # ── Spell effect hooks (overridden by concrete states) ────────

    def _on_spell_repel_monsters(self, radius, push_distance, duration=0):
        """Called when a repel_monsters spell is cast. Override in states."""
        pass

    def _on_spell_light(self, radius, light_level, duration):
        """Called when a light spell is cast. Override in dungeon state."""
        pass

    def _on_spell_magic_light(self, steps):
        """Called when a magic_light spell is cast. Override in dungeon state."""
        pass

    def _on_spell_reveal_map(self):
        """Called when a reveal_map spell is cast. Override in states."""
        pass

    def _on_spell_dungeon_nav(self, effect_type, effect_value):
        """Called for dungeon navigation spells. Override in dungeon state."""
        pass

    # ── Potion Crafting System ─────────────────────────────────────

    def _open_brew_list(self):
        """Open the potion crafting overlay with the recipe list."""
        from src.party import POTIONS_DATA

        alchemist = self._has_alchemist()
        if not alchemist:
            self.show_message("No alchemist in the party!", 2000)
            return

        recipes = POTIONS_DATA.get("recipes", {})
        if not recipes:
            self.show_message("No recipes known!", 2000)
            return

        party = self.game.party
        brew_list = []
        for recipe_id, recipe in recipes.items():
            can_brew = self._check_reagents(recipe, party)
            brew_list.append((recipe_id, recipe, can_brew))

        self.brew_list_items = brew_list
        self.brew_list_cursor = 0
        self.brew_result_msg = None
        self.brew_result_timer = 0
        self.showing_brew_list = True

    def _check_reagents(self, recipe, party):
        """Check if the party has all required reagents for a recipe."""
        for reagent_name, qty_needed in recipe.get("reagents", {}).items():
            available = party.inv_get_charges(reagent_name)
            # Also count non-charged entries
            if available <= 0:
                count = sum(1 for e in party.shared_inventory
                            if party.item_name(e) == reagent_name
                            and party.item_charges(e) is None)
                available = count
            if available < qty_needed:
                return False
        return True

    def _consume_reagents(self, recipe, party):
        """Consume all reagents for a recipe from the party stash."""
        for reagent_name, qty_needed in recipe.get("reagents", {}).items():
            for _ in range(qty_needed):
                # Try consuming a charge first (stackable reagents)
                if not party.inv_consume_charge(reagent_name):
                    # Fall back to removing a plain item entry
                    party.inv_remove(reagent_name)

    def _handle_brew_list_input(self, event):
        """Handle input for the potion crafting overlay."""
        # If showing a result message, any key dismisses it
        if self.brew_result_msg:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self.brew_result_msg = None
                # Refresh the brew list in case reagents changed
                self._refresh_brew_list()
            return

        items = self.brew_list_items
        if not items:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.showing_brew_list = False
            return

        if event.key == pygame.K_UP:
            self.brew_list_cursor = (self.brew_list_cursor - 1) % len(items)
        elif event.key == pygame.K_DOWN:
            self.brew_list_cursor = (self.brew_list_cursor + 1) % len(items)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            recipe_id, recipe, can_brew = items[self.brew_list_cursor]
            if can_brew:
                self._attempt_brew(recipe_id, recipe)
            else:
                self.brew_result_msg = "Missing reagents!"
        elif event.key == pygame.K_ESCAPE:
            self.showing_brew_list = False

    def _refresh_brew_list(self):
        """Refresh the brew list to reflect current reagent counts."""
        from src.party import POTIONS_DATA
        recipes = POTIONS_DATA.get("recipes", {})
        party = self.game.party
        brew_list = []
        for recipe_id, recipe in recipes.items():
            can_brew = self._check_reagents(recipe, party)
            brew_list.append((recipe_id, recipe, can_brew))
        self.brew_list_items = brew_list
        if self.brew_list_cursor >= len(brew_list):
            self.brew_list_cursor = max(0, len(brew_list) - 1)

    def _attempt_brew(self, recipe_id, recipe):
        """Attempt to brew a potion. Consumes reagents, then INT check."""
        party = self.game.party
        alchemist = self._has_alchemist()
        if not alchemist:
            self.brew_result_msg = "No alchemist available!"
            return

        # Double-check reagents before consuming
        if not self._check_reagents(recipe, party):
            self.brew_result_msg = "Missing reagents!"
            return

        # Consume the reagents
        self._consume_reagents(recipe, party)

        # INT check: d20 + INT modifier >= DC
        dc = recipe.get("dc", 10)
        int_mod = alchemist.get_modifier(alchemist.intelligence)
        roll = random.randint(1, 20)
        total = roll + int_mod

        result_item = recipe.get("result_item", recipe_id)
        result_count = recipe.get("result_count", 1)

        if total >= dc:
            # Success — add the crafted item
            for _ in range(result_count):
                party.inv_add(result_item)
            self.brew_result_msg = (
                f"Success! {alchemist.name} rolled {roll} "
                f"(+{int_mod}) = {total} vs DC {dc}. "
                f"Brewed {result_item}!"
            )
            self.game.sfx.play("heal")
        else:
            # Failure — reagents wasted
            self.brew_result_msg = (
                f"Failed! {alchemist.name} rolled {roll} "
                f"(+{int_mod}) = {total} vs DC {dc}. "
                f"The reagents are ruined."
            )
            self.game.sfx.play("miss")
