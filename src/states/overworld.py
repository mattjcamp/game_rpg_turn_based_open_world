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
from src.monster import create_random_monster


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

    def _handle_party_inv_input(self, event):
        """Handle input for the shared party inventory screen.

        The unified cursor covers 4 party equipment slots (indices 0-3)
        followed by shared inventory items (indices 4+).
        """
        party = self.game.party
        inv = party.shared_inventory
        members = party.members
        NUM_SLOTS = len(party.PARTY_SLOTS)
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        total_items = NUM_SLOTS + NUM_EFFECTS + len(inv)

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
                eff_idx = self.party_inv_cursor - NUM_SLOTS
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
        NUM_SLOTS = len(party.PARTY_SLOTS)
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        idx = self.party_inv_cursor

        if idx < NUM_SLOTS:
            # Acting on an equipment slot
            slot = party.PARTY_SLOTS[idx]
            if chosen == "UNEQUIP":
                party.party_unequip(slot)
                self.party_inv_action_menu = False
            elif chosen == "EXAMINE":
                item = party.get_equipped_name(slot)
                if item:
                    self.examining_item = item
        elif idx < NUM_SLOTS + NUM_EFFECTS:
            # Acting on an effect slot
            eff_idx = idx - NUM_SLOTS
            slot_key = party.EFFECT_SLOTS[eff_idx]
            if chosen == "ASSIGN EFFECT":
                self.effect_list = party.get_available_effects()
                self.effect_cursor = 0
                self.choosing_effect = True
                self.party_inv_action_menu = False
            elif chosen == "REMOVE":
                party.set_effect(slot_key, None)
                self.party_inv_action_menu = False
        else:
            # Acting on a shared inventory item
            inv_idx = idx - NUM_SLOTS - NUM_EFFECTS
            inv = party.shared_inventory
            if inv_idx < len(inv):
                item_name = party.item_name(inv[inv_idx])
                if chosen == "EXAMINE":
                    self.examining_item = item_name
                elif chosen.startswith("GIVE TO "):
                    give_name = chosen[8:].strip()
                    for mi, member in enumerate(party.members):
                        if member.name.upper() == give_name:
                            party.give_item_to_member(inv_idx, mi)
                            break
                    self.party_inv_action_menu = False
                    new_total = NUM_SLOTS + NUM_EFFECTS + len(party.shared_inventory)
                    if self.party_inv_cursor >= new_total:
                        self.party_inv_cursor = max(0, new_total - 1)
                elif chosen.startswith("EQUIP → "):
                    slot = chosen.split("→ ", 1)[1].strip().lower()
                    party.party_equip(item_name, slot)
                    self.party_inv_action_menu = False
                    # Clamp cursor after removal
                    new_total = NUM_SLOTS + NUM_EFFECTS + len(party.shared_inventory)
                    if self.party_inv_cursor >= new_total:
                        self.party_inv_cursor = max(0, new_total - 1)

    def _get_party_inv_action_options(self):
        """Build action options for the selected party inventory entry."""
        party = self.game.party
        NUM_SLOTS = len(party.PARTY_SLOTS)
        NUM_EFFECTS = len(party.EFFECT_SLOTS)
        idx = self.party_inv_cursor

        if idx < NUM_SLOTS:
            # Equipment slot — show UNEQUIP if occupied, EXAMINE
            slot = party.PARTY_SLOTS[idx]
            item = party.get_equipped_name(slot)
            if item is None:
                return []
            return ["UNEQUIP", "EXAMINE"]
        elif idx < NUM_SLOTS + NUM_EFFECTS:
            # Effect slot
            eff_idx = idx - NUM_SLOTS
            slot_key = party.EFFECT_SLOTS[eff_idx]
            current = party.get_effect(slot_key)
            options = []
            if party.get_available_effects():
                options.append("ASSIGN EFFECT")
            if current is not None:
                options.append("REMOVE")
            return options
        else:
            # Shared inventory item
            inv_idx = idx - NUM_SLOTS - NUM_EFFECTS
            inv = party.shared_inventory
            if inv_idx >= len(inv):
                return []
            options = []
            # Offer equip to each empty party slot
            for s in party.PARTY_SLOTS:
                if party.get_equipped_name(s) is None:
                    label = party.PARTY_SLOT_LABELS[s]
                    options.append(f"EQUIP → {label}")
            for mi, member in enumerate(self.game.party.members):
                options.append(f"GIVE TO {member.name.upper()}")
            options.append("EXAMINE")
            return options

    # ── Orc spawning ──────────────────────────────────────────────

    def _spawn_orcs(self):
        """Top-up roaming orcs to _MAX_OVERWORLD_ORCS."""
        alive = [m for m in self.overworld_monsters if m.is_alive()]
        self.overworld_monsters = alive
        needed = _MAX_OVERWORLD_ORCS - len(alive)
        tile_map = self.game.tile_map
        party = self.game.party

        for _ in range(needed):
            orc = create_random_monster("overworld")
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
        """Start combat against TWO orcs (the contacted one + a reinforcement)."""
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

        # The primary orc is the one on the map
        self.game.sfx.play("encounter")
        combat_state.start_combat(fighter, orc, source_state="overworld")
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
        )
