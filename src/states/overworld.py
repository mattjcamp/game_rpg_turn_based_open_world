"""
Overworld state - the main exploration mode.

This is where the party walks around the overworld map, encounters
towns, dungeons, and random encounters. It's the "hub" state of
the game.
"""

import math
import random

import pygame

from src.states.base_state import BaseState
from src.states.inventory_mixin import InventoryMixin
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_TOWN, TILE_DUNGEON, TILE_CHEST, TILE_GRASS,
    TILE_WATER, TILE_MACHINE,
)
from src.dungeon_generator import generate_dungeon, generate_house_dungeon
from src.monster import create_random_monster, create_encounter, create_monster


# How many monsters roam the overworld at a time
_MAX_OVERWORLD_ORCS = 2
# Minimum Chebyshev distance from party when spawning
_SPAWN_MIN_DIST = 8
_SPAWN_MAX_DIST = 14


class OverworldState(InventoryMixin, BaseState):
    """Handles overworld exploration."""

    def __init__(self, game):
        super().__init__(game)
        self.message = ""
        self.message_timer = 0  # ms remaining to show message
        self.move_cooldown = 0  # ms until next move allowed
        self._init_inventory_state()

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

        # Push spell expanding-wave animation
        # dict with keys: timer, duration, max_radius
        self.push_spell_anim = None

        # Lingering repel effect: monsters flee for N movement steps
        # dict with keys: steps_remaining, radius
        self.repel_effect = None

    def enter(self):
        if self.pending_combat_message:
            self.show_message(self.pending_combat_message, 2500)
            self.pending_combat_message = None
        elif not self.overworld_monsters:
            self.message = "Welcome, adventurers! Use arrow keys to explore."
            self.message_timer = 3000
            # Spawn initial orcs
            self._spawn_orcs()
            # ── TEST: place a spell-casting Dark Mage near the start ──
            self._spawn_test_spellcaster()

    def _interact_machine(self):
        """Handle stepping on the gnome machine tile (Keys of Shadow)."""
        kd = self.game.key_dungeons
        if not kd:
            self.show_message("A strange machine hums ominously.", 2000)
            return

        # Count keys the party currently holds
        party = self.game.party
        key_names = [d["key_name"] for d in kd.values()]
        held_keys = [k for k in key_names if party.inv_count(k) > 0]

        total = len(kd)
        inserted = self.game.keys_inserted

        if held_keys:
            # Insert all held keys
            for key in held_keys:
                party.inv_remove(key)
                self.game.keys_inserted += 1
            inserted = self.game.keys_inserted
            n = len(held_keys)
            names = ", ".join(held_keys)
            self.show_message(
                f"Inserted {names}! ({inserted}/{total} keys placed)", 3500)

            # Check victory
            if inserted >= total:
                self._trigger_victory()
        elif inserted >= total:
            self.show_message(
                "The machine is deactivated. Sunlight bathes the land!", 3000)
        elif inserted > 0:
            remaining = total - inserted
            self.show_message(
                f"The machine hums... {inserted}/{total} keys inserted. "
                f"{remaining} more needed.", 3000)
        else:
            self.show_message(
                "A massive gnomish machine blocks the sun! "
                "It has 8 empty keyhole slots.", 3500)

    def _trigger_victory(self):
        """Called when all 8 keys are inserted — the sun returns!"""
        self.game.darkness_active = False
        # Award XP and gold to all alive party members
        for m in self.game.party.active_members():
            if m.is_alive():
                m.exp += 500
                msgs = m.check_level_up()
                for msg in msgs:
                    self.game.log(msg)
        self.game.party.gold += 1000
        self.game.log("*** THE MACHINE POWERS DOWN! ***")
        self.game.log("Sunlight floods the land once more!")
        self.game.log("The people of Duskhollow are saved!")
        self.game.log("VICTORY! +500 XP, +1000 Gold")
        self.show_message(
            "THE MACHINE POWERS DOWN! Sunlight returns! VICTORY!", 6000)

    def _spawn_test_spellcaster(self):
        """Place a spell-casting Dark Mage 4 tiles east of the party start.

        This is for testing the monster spell system — walk into it to
        trigger a Dark Coven encounter with sleep/curse spells.
        """
        party = self.game.party
        tile_map = self.game.tile_map
        # Try a few offsets near the player
        for dc, dr in [(4, 0), (3, 0), (5, 0), (4, 1), (3, -1), (0, 4)]:
            c, r = party.col + dc, party.row + dr
            if 0 <= c < tile_map.width and 0 <= r < tile_map.height:
                if tile_map.is_walkable(c, r):
                    mage = create_monster("Dark Mage")
                    mage.encounter_template = {
                        "name": "Dark Coven",
                        "monster_names": ["Dark Mage", "Orc Shaman", "Goblin"],
                        "monster_party_tile": "Dark Mage",
                    }
                    mage.col = c
                    mage.row = r
                    self.overworld_monsters.append(mage)
                    return

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

    # ── Orc spawning ──────────────────────────────────────────────

    def _spawn_orcs(self):
        """Top-up roaming orcs to _MAX_OVERWORLD_ORCS.

        Each candidate position is classified as ``"land"`` or ``"sea"``
        based on the tile type, and the encounter template is chosen to
        match.  Sea encounters can only appear on water tiles, and land
        encounters can only appear on walkable land tiles.

        Also prunes any monster that has somehow ended up on a water tile
        (safety net for movement edge-cases or legacy state).
        """
        tile_map = self.game.tile_map
        party = self.game.party

        # Keep only alive monsters that are NOT standing on invalid terrain.
        # Land monsters on water tiles are removed as a safety net.
        valid = []
        for m in self.overworld_monsters:
            if not m.is_alive():
                continue
            tile_id = tile_map.get_tile(m.col, m.row)
            if getattr(m, "terrain", "land") != "sea" and tile_id == TILE_WATER:
                continue  # land monster on water — remove it
            valid.append(m)
        self.overworld_monsters = valid

        needed = _MAX_OVERWORLD_ORCS - len(valid)

        for _ in range(needed):
            placed = False
            for _attempt in range(60):
                c = party.col + random.randint(-_SPAWN_MAX_DIST, _SPAWN_MAX_DIST)
                r = party.row + random.randint(-_SPAWN_MAX_DIST, _SPAWN_MAX_DIST)
                dist = max(abs(c - party.col), abs(r - party.row))
                if dist < _SPAWN_MIN_DIST:
                    continue
                if not (0 <= c < tile_map.width and 0 <= r < tile_map.height):
                    continue

                # Determine terrain at this position
                tile_id = tile_map.get_tile(c, r)
                if tile_id == TILE_WATER:
                    terrain = "sea"
                else:
                    # Land monsters require a walkable tile
                    if not tile_map.is_walkable(c, r):
                        continue
                    terrain = "land"

                # Pick an encounter matching this terrain
                enc = create_encounter("overworld", terrain=terrain)
                if enc is None:
                    # No encounters defined for this terrain — skip
                    continue

                orc = create_monster(enc["monster_party_tile"])
                orc.encounter_template = {
                    "name": enc["name"],
                    "monster_names": [m.name for m in enc["monsters"]],
                    "monster_party_tile": enc["monster_party_tile"],
                }
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
                # Tick Galadriel's Light step counter
                self._tick_galadriels_light()
            else:
                self.move_cooldown = MOVE_REPEAT_DELAY
                self.show_message("Blocked!", 800)

    # ── Galadriel's Light step tracking ─────────────────────────

    def _tick_galadriels_light(self):
        """Decrement Galadriel's Light step counter and auto-remove when expired."""
        party = self.game.party
        if not party.has_effect("Galadriel's Light"):
            return
        if party.galadriels_light_steps <= 0:
            return
        party.galadriels_light_steps -= 1
        if party.galadriels_light_steps <= 0:
            for slot_key in party.EFFECT_SLOTS:
                if party.get_effect(slot_key) == "Galadriel's Light":
                    party.set_effect(slot_key, None)
                    break
            self.show_message("Galadriel's Light fades away...", 3000)

    # ── Monster helpers ───────────────────────────────────────────

    def _get_monster_at(self, col, row):
        """Return the alive orc at (col, row), or None."""
        for mon in self.overworld_monsters:
            if mon.col == col and mon.row == row and mon.is_alive():
                return mon
        return None

    def _move_monsters(self):
        """Each alive orc wanders randomly, but pursues if within 6 tiles.

        While a repel effect is active, monsters inside its radius flee
        *away* from the party instead of pursuing.
        """
        party = self.game.party
        alive = [m for m in self.overworld_monsters if m.is_alive()]
        occupied = {(m.col, m.row) for m in alive}

        repel = self.repel_effect  # may be None

        for mon in alive:
            occupied.discard((mon.col, mon.row))
            cheb = max(abs(mon.col - party.col), abs(mon.row - party.row))

            # If repel effect is active and monster is within radius, flee
            if repel and cheb <= repel["radius"]:
                # Move away: target is opposite direction from party
                flee_col = mon.col + (mon.col - party.col)
                flee_row = mon.row + (mon.row - party.row)
                mon.try_move_toward(
                    flee_col, flee_row,
                    self.game.tile_map,
                    occupied,
                )
            elif abs(mon.col - party.col) + abs(mon.row - party.row) <= 6:
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

        # Tick down the lingering repel effect (one step per party move)
        if repel:
            repel["steps_remaining"] -= 1
            if repel["steps_remaining"] <= 0:
                self.repel_effect = None

    def _check_monster_contact(self):
        """If an orc is adjacent to the party, start combat."""
        party = self.game.party
        for mon in self.overworld_monsters:
            if not mon.is_alive():
                continue
            if abs(mon.col - party.col) + abs(mon.row - party.row) == 1:
                self._start_orc_combat(mon)
                return

    # ── Push spell (repel monsters) ───────────────────────────

    def _on_spell_repel_monsters(self, radius, push_distance, duration=0):
        """Push all overworld monsters within *radius* tiles away from the
        party, moving them *push_distance* steps in the opposite direction.
        Also triggers an expanding-wave animation on the map.

        If *duration* > 0 the repel effect lingers: for that many movement
        steps, all monsters within the radius will flee instead of pursuing.
        """
        self._push_monsters_away(radius, push_distance)

        # Set up lingering repel effect that lasts *duration* movement steps.
        # The visual animation is tied to this effect's lifetime.
        if duration > 0:
            self.repel_effect = {
                "steps_remaining": duration,
                "total_steps": duration,
                "radius": radius,
            }

        # Start the initial expanding-wave burst animation
        burst_ms = 1200
        self.push_spell_anim = {
            "burst_timer": burst_ms,
            "burst_duration": burst_ms,
            "max_radius": radius,
            "elapsed_ms": 0.0,       # total ms since cast (for pulsing)
        }

        self.game.sfx.play("magic_burst")

    def _push_monsters_away(self, radius, push_distance):
        """Immediately push all monsters within *radius* tiles away from
        the party by up to *push_distance* steps."""
        party = self.game.party
        tile_map = self.game.tile_map

        occupied = {(m.col, m.row) for m in self.overworld_monsters
                    if m.is_alive()}

        for mon in self.overworld_monsters:
            if not mon.is_alive():
                continue
            dx = mon.col - party.col
            dy = mon.row - party.row
            dist = max(abs(dx), abs(dy))  # Chebyshev distance
            if dist > radius or dist == 0:
                continue

            # Normalise direction away from party
            dir_x = (1 if dx > 0 else (-1 if dx < 0 else 0))
            dir_y = (1 if dy > 0 else (-1 if dy < 0 else 0))

            # Push step by step (terrain-aware so sea creatures stay in
            # water and land creatures stay on land)
            occupied.discard((mon.col, mon.row))
            for _step in range(push_distance):
                nc = mon.col + dir_x
                nr = mon.row + dir_y
                if (mon._can_enter(nc, nr, tile_map)
                        and (nc, nr) not in occupied
                        and (nc, nr) != (party.col, party.row)):
                    mon.col = nc
                    mon.row = nr
                else:
                    break
            occupied.add((mon.col, mon.row))

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
            pcol, prow = self.game.party.col, self.game.party.row

            # Check if this is a Keys of Shadow key dungeon
            kd = self.game.key_dungeons.get((pcol, prow))
            if kd and kd["status"] in ("active", "artifact_found"):
                dungeon_state.enter_quest_dungeon(
                    kd["levels"], pcol, prow
                )

            # Check if this is the Shadow Crystal quest dungeon
            elif (self.game.quest
                    and self.game.quest["status"] in ("active", "artifact_found")
                    and pcol == self.game.quest["dungeon_col"]
                    and prow == self.game.quest["dungeon_row"]):
                dungeon_state.enter_quest_dungeon(
                    self.game.quest["levels"], pcol, prow
                )

            # Check if this is the house quest dungeon
            elif self._is_house_quest_dungeon(pcol, prow):
                hq = self.game.house_quest
                dungeon_state.enter_quest_dungeon(
                    hq["levels"], pcol, prow
                )

            else:
                # Generate a fresh dungeon each time!
                dungeon_data = generate_dungeon("The Depths")
                dungeon_state.enter_dungeon(
                    dungeon_data, pcol, prow
                )
            self.game.change_state("dungeon")
            return

        elif tile_id == TILE_MACHINE:
            self._interact_machine()
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

        # ── Special quest handling ──
        quest_id = utile.get("interact_data", {}).get("quest_id")
        if quest_id == "house_quest":
            self._activate_house_quest()

    # ── House quest ───────────────────────────────────────────

    def _is_house_quest_dungeon(self, col, row):
        """Check if the tile at (col, row) is the active house quest dungeon."""
        hq = getattr(self.game, "house_quest", None)
        if not hq or hq["status"] not in ("active", "artifact_found"):
            return False
        return col == hq["dungeon_col"] and row == hq["dungeon_row"]

    def _activate_house_quest(self):
        """Activate the house quest when the party speaks to Elara."""
        hq = getattr(self.game, "house_quest", None)
        if hq and hq["status"] != "not_started":
            # Quest already active or completed
            if hq["status"] == "completed":
                self.show_message("Elara: Thank you again for returning my heirloom!", 3000)
            elif hq["status"] == "artifact_found":
                self.show_message("Elara: You found it! Thank you so much!", 3000)
                self._complete_house_quest()
            else:
                self.show_message("Elara: Please, my heirloom is still in the basement!", 3000)
            return

        # Generate the house dungeon
        levels = generate_house_dungeon()
        house_col, house_row = 7, 10  # fixed house dungeon location

        # Store house quest state
        self.game.house_quest = {
            "name": "Family Heirloom",
            "status": "active",
            "dungeon_col": house_col,
            "dungeon_row": house_row,
            "levels": levels,
            "current_level": 0,
            "artifact_name": "Family Heirloom",
        }

        self.show_message("Elara: Thank you! The house is just north of here. Be careful!", 4000)
        self.game.game_log.append("Quest accepted: Retrieve the Family Heirloom from Elara's house.")

    def _complete_house_quest(self):
        """Complete the house quest: remove heirloom, give reward."""
        party = self.game.party

        # Remove the heirloom
        party.inv_remove("Family Heirloom")

        # Give gold reward
        reward_gold = 100
        party.gold += reward_gold

        # Give XP to all alive members
        for member in party.alive_members():
            member.exp += 30

        self.game.house_quest["status"] = "completed"
        self.game.game_log.append(
            f"Quest complete! Elara rewards the party with {reward_gold} gold."
        )

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
        ("Short Bow",     1),
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

        # Push spell animation — lives as long as the repel effect is active
        if self.push_spell_anim:
            anim = self.push_spell_anim
            anim["elapsed_ms"] += dt_ms
            if anim["burst_timer"] > 0:
                anim["burst_timer"] -= dt_ms
                if anim["burst_timer"] < 0:
                    anim["burst_timer"] = 0
            # Clear the animation only when the repel effect is also gone
            if not self.repel_effect and anim["burst_timer"] <= 0:
                self.push_spell_anim = None

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
                effect_cursor=self.effect_cursor,
                showing_spell_list=self.showing_spell_list,
                spell_list_items=self.spell_list_items,
                spell_list_cursor=self.spell_list_cursor,
                choosing_heal_target=self.choosing_heal_target,
                heal_target_cursor=self.heal_target_cursor,
                showing_brew_list=self.showing_brew_list,
                brew_list_items=self.brew_list_items,
                brew_list_cursor=self.brew_list_cursor,
                brew_result_msg=self.brew_result_msg,
                tinker_available=self._can_tinker())
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
            push_anim=self.push_spell_anim,
            repel_effect=self.repel_effect,
            darkness_active=getattr(self.game, "darkness_active", False),
        )
        if self.showing_help:
            renderer.draw_overworld_help_overlay()
        if self.showing_log:
            renderer.draw_log_overlay(self.game.game_log, self.log_scroll)
