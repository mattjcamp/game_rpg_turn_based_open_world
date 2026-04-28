"""
Overworld state - the main exploration mode.

This is where the party walks around the overworld map, encounters
towns, dungeons, and random encounters. It's the "hub" state of
the game.
"""

import random

import pygame

from src.states.base_state import BaseState
from src.states.inventory_mixin import InventoryMixin
from src.states.lock_mixin import LockInteractionMixin
from src.settings import (
    MOVE_REPEAT_DELAY, TILE_TOWN, TILE_DUNGEON, TILE_CHEST, TILE_GRASS,
    TILE_WATER, TILE_BOAT, TILE_DUNGEON_CLEARED, TILE_SPAWN, TILE_SPAWN_CAMPFIRE, TILE_SPAWN_GRAVEYARD,
    GUARDIAN_LEASH, GUARDIAN_INTERCEPT_RANGE_OVERWORLD, GUARDIAN_INTERCEPT_RANGE_INTERIOR,
    NPC_WANDER_RANGE, ORC_RESPAWN_CHANCE,
)
from src.dungeon_generator import generate_dungeon, generate_house_dungeon
from src.monster import create_encounter, create_monster


# How many monsters roam the overworld at a time
_MAX_OVERWORLD_ORCS = 2
# Minimum Chebyshev distance from party when spawning
_SPAWN_MIN_DIST = 8
_SPAWN_MAX_DIST = 14


def _try_pickup_ground_item(game, tile_map, col, row,
                             log_sink=None, msg_sink=None):
    """Pick up any ground item at (col, row) on *tile_map*.

    Uses ``TileMap.pop_ground_item`` so the item is removed from the
    map (and therefore disappears visually) and added to the party's
    shared stash via ``party.inv_add``.

    *log_sink*  — optional callable taking a string (game log append)
    *msg_sink*  — optional callable taking (str, duration_ms) for an
                 on-screen pickup message

    Returns the item name that was picked up, or None.
    """
    if tile_map is None:
        return None
    item_name = tile_map.pop_ground_item(col, row)
    if not item_name:
        return None
    try:
        game.party.inv_add(item_name)
    except Exception:
        # Don't let a bad item name crash the game — put it back so it
        # can be picked up after the fix / investigated.
        props = getattr(tile_map, "tile_properties", None)
        if props is not None:
            props.setdefault(f"{col},{row}", {})["item"] = item_name
        return None
    message = f"Picked up {item_name}!"
    if callable(log_sink):
        try:
            log_sink(message)
        except Exception:
            pass
    if callable(msg_sink):
        try:
            msg_sink(message, 2000)
        except Exception:
            pass
    try:
        game.sfx.play("chirp")
    except Exception:
        pass
    return item_name


class OverworldState(LockInteractionMixin, InventoryMixin, BaseState):
    """Handles overworld exploration."""

    def __init__(self, game):
        super().__init__(game)
        self.message = ""
        self.message_timer = 0  # ms remaining to show message
        self.move_cooldown = 0  # ms until next move allowed
        self._init_inventory_state()
        # Pick-lock / Knock dialog (shared with dungeon/town).
        self._init_lock_interaction()

        # Help overlay
        self.showing_help = False

        # Unique tile discovery display
        self.unique_tile_text = ""
        self.unique_tile_timer = 0       # ms remaining to show text
        self.unique_tile_flash = 0.0     # animation phase (radians)
        self.unique_tile_pos = None      # (col, row) for map flash effect

        # Roaming overworld orcs
        self.overworld_monsters = []

        # Note on designer-placed encounters: the spawn-once tracking
        # set is attached to each tile_map (as
        # ``tile_map._spawned_placement_positions``), not to the
        # state, so overworld placements, building-interior
        # placements, and dungeon-level placements don't collide on
        # identical (col, row) coordinates. See
        # :meth:`_spawn_placed_encounters`.

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

        # Dungeon entry action screen
        self.dungeon_action_active = False
        self.dungeon_action_cursor = 0        # 0=Enter, 1=Leave
        self.dungeon_action_info = {}         # {name, description, visited, quest_name}
        self.dungeon_action_entry_args = None # pre-computed entry params

        # Town/location entry action screen
        self.town_action_active = False
        self.town_action_cursor = 0           # 0=Enter, 1=Leave
        self.town_action_info = {}            # {name, description}

        # Building entry action screen
        self.building_action_active = False
        self.building_action_cursor = 0       # 0=Enter, 1=Leave
        self.building_action_info = {}        # {name, description}
        self.building_action_entry_args = None

        # Spawn point action screen
        self.spawn_action_active = False
        self.spawn_action_cursor = 0       # 0=Enter, 1=Leave
        self.spawn_action_info = {}        # name, description, tile_id
        self.spawn_action_pos = (0, 0)     # (col, row) of the spawn tile

        # Monster encounter action screen (roaming monsters)
        self.encounter_action_active = False
        self.encounter_action_cursor = 0   # 0=Engage, 1=Flee
        self.encounter_action_monster = None  # the contacted Monster object
        self.encounter_action_result = None   # None, "fled", "failed"
        self.encounter_result_timer = 0       # ms remaining for result msg

        # Destroyed spawn points
        self.destroyed_spawns = set()  # set of (col,row) tuples for destroyed spawn points

        # Spawn tile animation effects (list of dicts with col, row, timer)
        self._spawn_effects = []

        # Grace flag: skip one tile-event check after returning from a
        # town/dungeon so the player isn't immediately prompted to re-enter
        # the location they just left.
        self._exit_grace = False

        # ── Overworld interior state ──
        self._in_overworld_interior = False
        self._overworld_interior_stack = []
        self._overworld_interior_exit_positions = set()
        self._overworld_interior_links = {}  # {(col,row): interior_name}
        self._overworld_interior_name = ""
        self._overworld_interior_entry_grace = False
        # Stashed overworld state restored on exit
        self._stashed_overworld_tile_map = None
        self._stashed_overworld_monsters = None
        # NPCs spawned inside building interiors (quest items + guardians)
        self._building_interior_npcs = []
        self._building_combat_npc = None
        self._building_returning_from_combat = False
        self._building_name = ""  # the building name (not space name)

        # ── Overworld NPC dialogue (module quest givers) ──
        self.ow_npc_dialogue_active = False
        self.ow_npc_speaking = None
        self.ow_quest_dialogue_lines = []
        self.ow_quest_dialogue_index = 0
        self.ow_quest_choice_active = False
        self.ow_quest_choice_cursor = 0
        self.ow_quest_choices = []

        # ── Quest visual effects ──
        # List of active effects: {type, timer, duration, ...}
        self.quest_effects = []

    def reset_for_new_game(self):
        """Clear all transient state so a fresh game starts clean.

        The state object is created once and reused across sessions,
        so any flag that accumulates during play (interior nesting,
        stashed tile maps, dialogue overlays, quest effects) needs to
        be cleared explicitly when the player starts a new game.
        The previous bug: ``_in_overworld_interior`` stayed True after
        quitting from inside a building, then the renderer drew the
        new overworld with interior-darkness lighting.
        """
        # Interior nesting / stash
        self._in_overworld_interior = False
        self._overworld_interior_stack = []
        self._overworld_interior_exit_positions = set()
        self._overworld_interior_links = {}
        self._overworld_interior_name = ""
        self._overworld_interior_entry_grace = False
        self._stashed_overworld_tile_map = None
        self._stashed_overworld_monsters = None
        # Previously a player who started a new game after clearing a
        # lair kept the old destroyed-spawn memory, so the tile on the
        # fresh map was silently skipped.  A new game must start with a
        # clean slate.
        self.destroyed_spawns = set()
        for attr in ("_stashed_overworld_party_col",
                     "_stashed_overworld_party_row"):
            if hasattr(self, attr):
                delattr(self, attr)
        self._building_interior_npcs = []
        self._building_combat_npc = None
        self._building_returning_from_combat = False
        self._building_name = ""
        # Travel / action popup state
        self.building_action_active = False
        self.dungeon_action_active = False
        self.town_action_active = False
        self.spawn_action_active = False
        self._exit_grace = False
        # Dialogue + message overlays
        self.ow_npc_dialogue_active = False
        self.ow_npc_speaking = None
        self.ow_quest_dialogue_lines = []
        self.ow_quest_dialogue_index = 0
        self.ow_quest_choice_active = False
        self.ow_quest_choice_cursor = 0
        self.ow_quest_choices = []
        self.message = ""
        self.message_timer = 0
        self.move_cooldown = 0
        # Visual effects on the overworld surface
        self.quest_effects = []
        # Any inventory/party overlays provided by the shared mixin
        if hasattr(self, "_init_inventory_state"):
            self._init_inventory_state()
        # Unique-tile discovery readouts
        if hasattr(self, "unique_text"):
            self.unique_text = ""
        if hasattr(self, "unique_flash"):
            self.unique_flash = 0.0
        if hasattr(self, "unique_pos"):
            self.unique_pos = None

    def enter(self):
        self._apply_pending_combat_rewards()
        # Check quest kill progress (sets message if a step completed)
        quest_msg = self._check_quest_monster_kills()
        # Clean up building interior quest monster after combat
        if self._building_returning_from_combat and self._building_combat_npc:
            combat_state = self.game.states.get("combat")
            player_won = getattr(combat_state, "player_won", True)
            if player_won:
                npc = self._building_combat_npc
                if npc in self._building_interior_npcs:
                    self._building_interior_npcs.remove(npc)
            self._building_combat_npc = None
            self._building_returning_from_combat = False
        # Skip the first tile-event check so we don't immediately re-enter
        # the town/dungeon we just left.
        self._exit_grace = True
        if quest_msg:
            self.show_message(quest_msg, 4000)
        elif self.pending_combat_message:
            self.show_message(self.pending_combat_message, 2500)
            self.pending_combat_message = None
        elif not self.overworld_monsters and not self._in_overworld_interior:
            self.message = "Welcome, adventurers! Use arrow keys to explore."
            self.message_timer = 3000
            # Spawn initial orcs
            self._spawn_orcs()

        # Materialize designer-placed encounter markers every time we
        # enter the overworld. The helper is idempotent: placements
        # already represented by a live monster are skipped, so
        # repeated entries (e.g. returning from a town) don't stack.
        # Killed placements will respawn on re-entry, matching the
        # "acts like any other encounter" behaviour of roaming orcs.
        if not self._in_overworld_interior:
            self._spawn_placed_encounters()

    # ── Equipment management ─────────────────────────────────────

    # ── Orc spawning ──────────────────────────────────────────────

    def _spawn_orcs(self):
        """Top-up roaming orcs to _MAX_OVERWORLD_ORCS.

        Monsters are only spawned on walkable land tiles.  Water,
        mountains, and any other non-walkable tiles are excluded.

        Also prunes any existing monster that has somehow ended up on a
        non-walkable tile (safety net for movement edge-cases, map edits,
        or legacy state).

        When the DM-mode ``quest_monsters_only`` debug flag is on, no new
        roaming monsters are spawned — quest monsters are placed via
        :meth:`Game._spawn_quest_monsters_overworld` on a separate path
        and are unaffected.
        """
        if getattr(self.game, "quest_monsters_only", False):
            # Still prune any non-alive / off-map monsters so the list
            # stays healthy, but do not top up.  Use the monster's
            # own terrain check so sea creatures on land and land
            # creatures on water both get filtered out — a plain
            # ``is_walkable`` only catches the second case.
            self.overworld_monsters = [
                m for m in self.overworld_monsters
                if m.is_alive()
                and m._can_enter(m.col, m.row, self.game.tile_map)
            ]
            return
        tile_map = self.game.tile_map
        party = self.game.party

        # Keep only alive monsters standing on tiles their terrain
        # actually allows.  ``_can_enter`` returns False for a land
        # monster on water AND for a sea creature on land, so this
        # safety net handles both directions of misplacement (e.g.
        # designer-placed encounters that landed on the wrong
        # terrain, or post-edit map mutations).
        valid = []
        for m in self.overworld_monsters:
            if not m.is_alive():
                continue
            if not m._can_enter(m.col, m.row, tile_map):
                continue
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

                # Only spawn on walkable land tiles — skip water,
                # mountains, and any other non-walkable tile.
                if not tile_map.is_walkable(c, r):
                    continue
                tile_id = tile_map.get_tile(c, r)
                if tile_id == TILE_WATER:
                    continue  # water is non-walkable but guard anyway
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

        # Spawn tile monsters are handled separately in _try_spawn_tile_monsters()

    def _spawn_sea_encounter(self):
        """Spawn a terrain=\"sea\" encounter on water near the party.

        Called each step while the party is sailing.  Mirrors
        :meth:`_spawn_orcs` but targets water tiles and uses the sea
        encounter pool from ``encounters.json``.  Sea monsters already
        stay confined to water via :meth:`Monster._can_enter`, so the
        existing pursuit / bump-to-fight pipeline handles combat.
        """
        if getattr(self.game, "quest_monsters_only", False):
            return
        tile_map = self.game.tile_map
        party = self.game.party

        # Cap concurrent sea creatures to avoid flooding the water.
        sea_mons = [m for m in self.overworld_monsters
                    if m.is_alive() and getattr(m, "terrain", "land") == "sea"]
        if len(sea_mons) >= _MAX_OVERWORLD_ORCS:
            return

        for _attempt in range(60):
            c = party.col + random.randint(-_SPAWN_MAX_DIST, _SPAWN_MAX_DIST)
            r = party.row + random.randint(-_SPAWN_MAX_DIST, _SPAWN_MAX_DIST)
            dist = max(abs(c - party.col), abs(r - party.row))
            if dist < _SPAWN_MIN_DIST:
                continue
            if not (0 <= c < tile_map.width and 0 <= r < tile_map.height):
                continue
            # Only spawn on open water — skip boat markers and land.
            if tile_map.get_tile(c, r) != TILE_WATER:
                continue

            enc = create_encounter("overworld", terrain="sea")
            if enc is None:
                return  # no sea encounters defined — stop trying

            leader = create_monster(enc["monster_party_tile"])
            leader.encounter_template = {
                "name": enc["name"],
                "monster_names": [m.name for m in enc["monsters"]],
                "monster_party_tile": enc["monster_party_tile"],
            }
            leader.col = c
            leader.row = r
            self.overworld_monsters.append(leader)
            return

    def _spawn_placed_encounters(self):
        """Materialize designer-placed encounter templates as monsters.

        The map editor paints encounters by writing the template name
        into ``tile_map.tile_properties[(col,row)]["encounter"]``. At
        runtime we convert each placement into a "party leader"
        Monster at its painted position with ``encounter_template``
        attached, so the existing bump-to-fight / Attack-Run dialog
        pipeline (see :meth:`_show_encounter_action` and
        :meth:`_encounter_engage`) handles combat without any special
        casing.

        **Spawn-once semantics.** Every placement spawns at most once
        per session. The spawn-once set lives on the *tile_map*
        itself (as ``_spawned_placement_positions``) so the
        bookkeeping is scoped correctly: the overworld map has its
        own set, each building interior has its own, each dungeon
        level has its own. That avoids the (c,r) collision that
        would otherwise happen if an overworld placement and an
        interior placement shared the same coordinates. A defeated
        placement stays defeated even after leaving and re-entering
        the same interior or dungeon: dungeon levels are cached on
        the game (so the same tile_map carries its set across
        transitions), and building interiors hand the set back via
        ``game.building_interior_spawns`` keyed by interior name —
        the interior tile_map is rebuilt from JSON on each entry,
        but the set it points at is the same object.
        """
        from src.monster import find_encounter_template
        tile_map = self.game.tile_map
        tprops = getattr(tile_map, "tile_properties", None) or {}
        if not tprops:
            return
        # Stash the spawn-once set on the tile_map so it's scoped
        # correctly per-map and survives state re-entries.
        spawned = getattr(
            tile_map, "_spawned_placement_positions", None)
        if spawned is None:
            spawned = set()
            tile_map._spawned_placement_positions = spawned

        for pos_key, props in tprops.items():
            if not isinstance(props, dict):
                continue
            enc_name = props.get("encounter")
            if not enc_name:
                continue
            parts = pos_key.split(",")
            if len(parts) != 2:
                continue
            try:
                c, r = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            # Spawn-once gate: once materialised, never spawn again.
            if (c, r) in spawned:
                continue
            if not (0 <= c < tile_map.width
                    and 0 <= r < tile_map.height):
                continue
            tmpl = find_encounter_template(enc_name)
            if tmpl is None:
                # Unknown template — skip silently rather than crash;
                # designers can rename/re-paint to recover.
                continue
            # Pick the sprite monster. Prefer the template's party
            # tile; fall back to the first monster in the group.
            party_tile = (tmpl.get("monster_party_tile")
                          or (tmpl.get("monsters") or [""])[0])
            if not party_tile:
                continue
            mon = create_monster(party_tile)
            # Terrain check.  A designer-placed encounter at (c, r)
            # may sit on a tile the monster physically can't stand
            # on — most commonly a land creature on what's now an
            # ocean tile after procedural map gen.  Skip the spawn
            # rather than materialising a monster floating on water.
            # We don't auto-relocate because the placement
            # coordinates are author intent; designers can move
            # the marker in the editor if they want a different
            # location.
            if not mon._can_enter(c, r, tile_map):
                continue
            mon.col = c
            mon.row = r
            mon.encounter_template = {
                "name": tmpl.get("name", enc_name),
                "monster_names": list(tmpl.get("monsters") or []),
                "monster_party_tile": party_tile,
                # Forward custom rewards so combat code can honour
                # per-encounter XP and loot overrides.
                "xp_override": tmpl.get("xp_override"),
                "loot": tmpl.get("loot"),
            }
            mon._placement_pos = (c, r)
            self.overworld_monsters.append(mon)
            # Mark this placement as materialised — never respawn.
            spawned.add((c, r))

    def _spawn_from_spawn_tiles(self):
        """Spawn roaming monsters from nearby Monster Spawn tiles.

        Each spawn tile in range rolls independently using its own
        configured spawn_chance percentage — so a tile set to 8%
        has an 8% chance of producing a monster each step.

        Suppressed entirely when the DM-mode ``quest_monsters_only``
        debug flag is on.
        """
        if getattr(self.game, "quest_monsters_only", False):
            return
        from src.party import SPAWN_POINTS

        if not SPAWN_POINTS:
            return
        tile_map = self.game.tile_map
        party = self.game.party
        scan_dist = 10  # only check spawn tiles near the party

        for dr in range(-scan_dist, scan_dist + 1):
            for dc in range(-scan_dist, scan_dist + 1):
                c = party.col + dc
                r = party.row + dr
                if not (0 <= c < tile_map.width and 0 <= r < tile_map.height):
                    continue
                tid = tile_map.get_tile(c, r)
                if tid not in SPAWN_POINTS:
                    continue
                if (c, r) in self.destroyed_spawns:
                    continue

                sp = SPAWN_POINTS[tid]

                # ── Spawn chance: percentage chance per step ──
                chance = sp.get("spawn_chance", 20)
                if random.randint(1, 100) > chance:
                    continue

                # Count existing monsters near this spawn
                radius = sp.get("spawn_radius", 3)
                max_spawned = sp.get("max_spawned", 2)
                nearby = sum(1 for m in self.overworld_monsters
                             if abs(m.col - c) <= radius
                             and abs(m.row - r) <= radius)
                if nearby >= max_spawned:
                    continue

                # Pick a random monster from the spawn list
                monster_names = sp.get("spawn_monsters", [])
                if not monster_names:
                    continue
                chosen_name = random.choice(monster_names)

                # Find a valid position on or adjacent to the spawn tile.
                # Try the spawn tile itself first, then the 8 neighbours.
                spawn_offsets = [(0, 0)]
                for _od in [(-1, 0), (1, 0), (0, -1), (0, 1),
                            (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                    spawn_offsets.append(_od)
                random.shuffle(spawn_offsets)
                for _odc, _odr in spawn_offsets:
                    sc = c + _odc
                    sr = r + _odr
                    if not (0 <= sc < tile_map.width
                            and 0 <= sr < tile_map.height):
                        continue
                    if not tile_map.is_walkable(sc, sr):
                        continue
                    if sc == party.col and sr == party.row:
                        continue
                    # Don't spawn adjacent to the party — it would
                    # trigger an encounter before the player can see it
                    if abs(sc - party.col) + abs(sr - party.row) <= 1:
                        continue
                    if any(m.col == sc and m.row == sr
                           for m in self.overworld_monsters):
                        continue
                    try:
                        monster = create_monster(chosen_name)
                        monster.col = sc
                        monster.row = sr
                        # Set encounter template so combat uses
                        # the correct monster, not a random encounter
                        monster.encounter_template = {
                            "name": chosen_name,
                            "monster_names": [chosen_name],
                            "monster_party_tile": chosen_name,
                        }
                        self.overworld_monsters.append(monster)
                        # Track for spawn animation
                        self._spawn_effects.append({
                            "col": sc, "row": sr,
                            "src_col": c, "src_row": r,
                            "timer": 1.0,
                        })
                    except Exception:
                        pass
                    break

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

                # ── Town action screen input ──
                if self.town_action_active:
                    self._handle_town_action_input(event)
                    return

                # ── Dungeon action screen input ──
                if self.dungeon_action_active:
                    self._handle_dungeon_action_input(event)
                    return

                # ── Monster encounter action screen input ──
                if self.encounter_action_active:
                    self._handle_encounter_action_input(event)
                    return

                # ── Pick-lock / Knock dialog input (shared mixin) ──
                if self.door_interact_active:
                    self._handle_lock_interact_input(event)
                    return

                # ── Spawn action screen input ──
                if self.spawn_action_active:
                    self._handle_spawn_action_input(event)
                    return

                # ── Building action screen input ──
                if self.building_action_active:
                    self._handle_building_action_input(event)
                    return

                # ── Overworld NPC dialogue input ──
                if self.ow_npc_dialogue_active:
                    self._handle_ow_npc_dialogue_input(event)
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
                    # Return to title screen (where the player can save)
                    self.game.showing_title = True
                    self.game.title_cursor = 0
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
                if event.key == pygame.K_e:
                    self.game.change_state("examine")
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

        # If showing party, character detail, party inventory, NPC dialogue,
        # an action screen, the pick-lock dialog, or a pick-lock animation
        # is playing, block all other input (including movement).
        # The lock guards prevent bumping the door again before the
        # unlock animation finishes removing the ``locked`` property —
        # without them the same door re-opens the dialog and forces the
        # player to pick it a second time. Matches dungeon.py behaviour.
        if (self.showing_party or self.showing_char_detail is not None
                or self.showing_party_inv or self.ow_npc_dialogue_active
                or self.town_action_active or self.dungeon_action_active
                or self.building_action_active or self.spawn_action_active
                or self.encounter_action_active
                or self.door_interact_active or self.door_unlock_anim):
            return

        # ── Free-look / map-scroll mode (Shift + arrows) ──────
        # Holding Shift detaches the camera from the party so the
        # player can pan across the map and review previously
        # explored tiles under the fog-of-war mask. Panning does
        # NOT advance the turn counter. Releasing Shift snaps the
        # camera back to the party on the next frame (the main
        # loop calls camera.update() every frame — see game.run).
        mods = pygame.key.get_mods()
        shift_held = bool(mods & pygame.KMOD_SHIFT)
        if shift_held and not self.game.camera.free_look:
            self.game.camera.enter_free_look()
        elif not shift_held and self.game.camera.free_look:
            self.game.camera.exit_free_look()

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
        elif keys_pressed[pygame.K_DOWN] or (
                keys_pressed[pygame.K_s]
                and not ((pygame.key.get_mods()
                          & ~(pygame.KMOD_CAPS | pygame.KMOD_NUM))
                         & (pygame.KMOD_CTRL | pygame.KMOD_META
                            | getattr(pygame, "KMOD_GUI", 0)))):
            drow = 1

        # In free-look mode, arrow keys pan the camera instead of
        # moving the party and the turn counter does NOT advance.
        if shift_held:
            if dcol != 0 or drow != 0:
                self.game.camera.pan(dcol, drow)
                self.move_cooldown = MOVE_REPEAT_DELAY
            return

        if dcol != 0 or drow != 0:
            party = self.game.party
            target_col = party.col + dcol
            target_row = party.row + drow

            # Bump-to-interact: building interior NPCs
            if self._in_overworld_interior and self._building_interior_npcs:
                for bnpc in self._building_interior_npcs:
                    if bnpc.col == target_col and bnpc.row == target_row:
                        if bnpc.npc_type == "quest_monster":
                            self._start_building_quest_combat(bnpc)
                            self.move_cooldown = MOVE_REPEAT_DELAY
                            return
                        elif bnpc.npc_type == "quest_item":
                            self._collect_building_quest_item(bnpc)
                            self.move_cooldown = MOVE_REPEAT_DELAY
                            return
                        elif bnpc.npc_type == "module_quest_giver":
                            self._start_ow_npc_dialogue(bnpc)
                            self.move_cooldown = MOVE_REPEAT_DELAY
                            return
                        else:
                            # Regular NPC types (villager, shopkeep, etc.)
                            self._start_building_npc_dialogue(bnpc)
                            self.move_cooldown = MOVE_REPEAT_DELAY
                            return

            # Bump-to-talk: check if a quest NPC is on the target tile
            # Only check overworld quest NPCs when NOT inside a building
            # interior — their coordinates belong to the overworld map and
            # would otherwise collide with interior tile positions (e.g.
            # Lucian at overworld (14,5) matching a building interior cell).
            ow_npc = (self._get_ow_npc_at(target_col, target_row)
                       if not self._in_overworld_interior else None)
            if ow_npc:
                if getattr(ow_npc, "npc_type", "") == "quest_item":
                    self._collect_overworld_quest_item(ow_npc)
                else:
                    self._start_ow_npc_dialogue(ow_npc)
                self.move_cooldown = MOVE_REPEAT_DELAY
                return

            # Bump-to-fight: check if an orc is on the target tile.
            # While sailing, only sea creatures can be bump-attacked
            # directly. Moving toward a land creature from the boat
            # falls through to the boat handler, which disembarks the
            # party onto that land tile — after which normal contact
            # checks engage the creature on foot.
            orc = self._get_monster_at(target_col, target_row)
            if orc:
                on_boat = bool(getattr(self.game, "on_boat", False))
                if not on_boat or getattr(orc, "terrain", "land") == "sea":
                    self._show_encounter_action(orc)
                    self.move_cooldown = MOVE_REPEAT_DELAY
                    return

            # Locked tile (painted via the Attributes panel) — opens the
            # pick-lock dialog regardless of underlying walkability so a
            # lock on a normally-walkable tile still acts as a barrier.
            if self._try_open_locked(self.game.tile_map,
                                      target_col, target_row):
                self.move_cooldown = MOVE_REPEAT_DELAY
                return

            # Boat / sailing takes over movement when relevant. If the
            # handler returns True, it has already moved the party (or
            # blocked the step) and the outer pipeline should treat the
            # turn as consumed.
            boat_handled = self._try_boat_move(
                target_col, target_row, dcol, drow)
            if boat_handled is True:
                moved = True
            elif boat_handled is False:
                moved = False
            else:
                # Not a boat-related move — run the normal movement path.
                moved = party.try_move(dcol, drow, self.game.tile_map)

            if moved:
                self.move_cooldown = MOVE_REPEAT_DELAY
                party.clock.advance(5)
                self.game.tile_map.tick_cooldowns()
                self._check_tile_events()
                # Move orcs after party moves (not inside interiors)
                if not self._in_overworld_interior:
                    # Check contact BEFORE monsters move so the player
                    # only enters combat with monsters they could see as
                    # adjacent.  Previously both the party and monster
                    # moved in the same frame, making it look like combat
                    # triggered from 2+ tiles away.
                    self._check_monster_contact()
                    self._move_monsters()
                    self._move_overworld_npcs()
                    # Land-based encounter generators only run while
                    # the party is on foot — sailing swaps these out
                    # for sea encounters so the open water has its
                    # own threat pool and land creatures don't keep
                    # spawning unreachably on shore.
                    sailing = bool(getattr(self.game, "on_boat", False))
                    if not sailing:
                        # Occasionally respawn orcs that were killed
                        if random.random() < ORC_RESPAWN_CHANCE:
                            self._spawn_orcs()
                        # Check spawn tiles every step — the
                        # spawn_chance percentage is the per-step
                        # probability
                        self._spawn_from_spawn_tiles()
                    else:
                        # Roll for sea encounters while sailing so
                        # the open water isn't a safe empty lane.
                        if random.random() < ORC_RESPAWN_CHANCE:
                            self._spawn_sea_encounter()
                else:
                    # Inside a building interior — encounter-spawned
                    # monsters live in overworld_monsters (fresh list
                    # per interior, repopulated by _spawn_placed_
                    # encounters) and need the same pursue/wander AI
                    # and contact detection as the outer overworld,
                    # otherwise they just stand in place forever.
                    self._check_monster_contact()
                    self._move_monsters()
                    # Move building interior guardian NPCs
                    if self._building_interior_npcs:
                        self._move_building_interior_npcs()
                        self._check_building_interior_npc()
                # Tick Galadriel's Light step counter
                self._tick_galadriels_light()
                # Torches burn one charge per step everywhere, not
                # just in dungeons — uses the shared party-level
                # ticker so the mechanic stays consistent.
                self._tick_equipped_torch_with_message()
            else:
                self.move_cooldown = MOVE_REPEAT_DELAY
                self.show_message("Blocked!", 800)

    # ── Boat / sailing ───────────────────────────────────────────

    def _try_boat_move(self, target_col, target_row, dcol, drow):
        """Handle boat boarding, sailing, and disembarking.

        Returns:
            True  — this handler moved the party (treat the turn as
                    spent, do not call party.try_move afterwards)
            False — the move is boat-related but blocked (e.g. trying
                    to sail into a non-water, non-walkable tile)
            None  — not a boat-related move; caller should fall through
                    to the regular movement path
        """
        game = self.game
        tile_map = game.tile_map
        party = game.party

        if not (0 <= target_col < tile_map.width
                and 0 <= target_row < tile_map.height):
            return None  # out of bounds — fall through

        target_tile = tile_map.get_tile(target_col, target_row)

        # ── Boarding: party is on land and steps onto a boat tile ──
        if not game.on_boat and target_tile == TILE_BOAT:
            party.col = target_col
            party.row = target_row
            game.on_boat = True
            game.boat_anim_frame = 0
            game.boat_anim_accum = 0
            try:
                game.sfx.play("encounter")
            except Exception:
                pass
            self.show_message("You board the boat!", 1500)
            return True

        # ── Not on a boat — nothing to do for this handler. ──
        if not game.on_boat:
            return None

        # ── Sailing: already aboard, moving onto water ──
        if target_tile == TILE_WATER:
            # Move the boat marker: old tile reverts to water, new tile
            # becomes the boat. Party coordinates track the boat.
            tile_map.set_tile(party.col, party.row, TILE_WATER)
            tile_map.set_tile(target_col, target_row, TILE_BOAT)
            party.col = target_col
            party.row = target_row
            return True

        # ── Disembark: moving onto walkable land ──
        # The boat stays behind on its current water tile (already
        # TILE_BOAT) and the party steps off onto the land tile.
        if tile_map.is_walkable(target_col, target_row) \
                and target_tile != TILE_BOAT:
            party.col = target_col
            party.row = target_row
            game.on_boat = False
            game.boat_anim_frame = 0
            self.show_message("You disembark.", 1200)
            return True

        # ── Still aboard, trying to sail into a blocked tile ──
        # (mountain in the water, closed bridge, etc.) — treat as a
        # blocked move so the caller shows "Blocked!".
        return False

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

    def _tick_equipped_torch_with_message(self):
        """Consume one charge from the equipped torch and show a
        message if it burned out. Safe to call when no torch is
        equipped (no-ops)."""
        result = self.game.party.tick_equipped_torch()
        if result == "burned_out":
            self.show_message("Your torch has burned out!", 2500)

    # ── Overworld NPC helpers (module quest givers) ──────────────

    def _get_ow_npc_at(self, col, row):
        """Return the overworld quest NPC at (col, row), or None."""
        for npc in getattr(self.game, "overworld_quest_npcs", []):
            if npc.col == col and npc.row == row:
                return npc
        return None

    def _collect_overworld_quest_item(self, npc):
        """Pick up a quest collectible item on the overworld."""
        from src.quest_manager import collect_quest_item
        ow_npcs = getattr(self.game, "overworld_quest_npcs", [])
        if npc in ow_npcs:
            ow_npcs.remove(npc)
        msg = collect_quest_item(
            self.game,
            getattr(npc, "_quest_name", ""),
            getattr(npc, "_quest_step_idx", -1),
            npc.name)
        self.show_message(msg, 3000 if "complete" in msg.lower() else 2500)

    def _start_ow_npc_dialogue(self, npc):
        """Begin talking to an overworld quest NPC."""
        mqname = getattr(npc, "_module_quest_name", "")
        mq_states = getattr(self.game, "module_quest_states", {})
        mq_state = mq_states.get(mqname, {})
        status = mq_state.get("status", "available")

        self.ow_npc_dialogue_active = True
        self.ow_npc_speaking = npc

        if status == "available":
            # Offer the quest — append a dungeon hint line when any of
            # the quest steps take place inside a dungeon so the player
            # learns up front they'll be descending into one (and which
            # one it is) before accepting.
            from src.quest_manager import augment_quest_dialogue
            quest_defs = getattr(self.game, "_module_quest_defs", [])
            qdef = next(
                (q for q in quest_defs if q.get("name") == mqname),
                None)
            self.ow_quest_dialogue_lines = augment_quest_dialogue(
                npc.quest_dialogue, qdef)
            self.ow_quest_dialogue_index = 0
            if self.ow_quest_dialogue_lines:
                remaining = len(self.ow_quest_dialogue_lines) - 1
                hint = "  [ENTER] >" if remaining > 0 else "  [ENTER]"
                self.show_message(
                    f"{npc.name}: "
                    f"{self.ow_quest_dialogue_lines[0]}{hint}",
                    999999)
            else:
                self.show_message(
                    f"{npc.name}: I have a quest for you!  [ENTER]",
                    999999)
        elif status == "active":
            progress = mq_state.get("step_progress", [])
            done = sum(1 for p in progress if p)
            total = len(progress)
            self.show_message(
                f"{npc.name}: How's the quest going? "
                f"({done}/{total} steps done)  [ENTER]", 999999)
            self.ow_quest_dialogue_lines = []
        elif status == "completed":
            # Turn in quest — award rewards and play celebration
            quest_defs = getattr(self.game, "_module_quest_defs", [])
            qdef = None
            for q in quest_defs:
                if q.get("name") == mqname:
                    qdef = q
                    break
            reward_xp = qdef.get("reward_xp", 0) if qdef else 0
            reward_gold = qdef.get("reward_gold", 0) if qdef else 0
            reward_items = (qdef.get("reward_items", [])
                            if qdef else []) or []

            # Grant rewards
            if reward_xp:
                for m in self.game.party.members:
                    if m.is_alive():
                        m.exp += reward_xp
                        m.check_level_up()
            if reward_gold:
                self.game.party.gold += reward_gold
            # Item rewards — drop each one into the shared stash.
            for item_name in reward_items:
                try:
                    self.game.party.inv_add(item_name)
                except Exception:
                    pass

            # Build reward text for dialogue
            parts = []
            if reward_xp:
                parts.append(f"+{reward_xp} XP")
            if reward_gold:
                parts.append(f"+{reward_gold} Gold")
            if reward_items:
                if len(reward_items) == 1:
                    parts.append(f"+{reward_items[0]}")
                else:
                    parts.append(
                        f"+{len(reward_items)} items "
                        f"({', '.join(reward_items[:3])}"
                        + (f", +{len(reward_items)-3} more"
                           if len(reward_items) > 3 else "") + ")")
            reward_str = ", ".join(parts)
            if reward_str:
                self.show_message(
                    f"{npc.name}: Thank you, hero! "
                    f"Here is your reward: {reward_str}  [ENTER]",
                    999999)
            else:
                self.show_message(
                    f"{npc.name}: Thank you for completing the quest!"
                    f"  [ENTER]", 999999)

            # Quest complete visual effect
            self.quest_effects.append({
                "type": "quest_complete",
                "timer": 3000,
                "duration": 3000,
                "quest_name": mqname,
                "reward_xp": reward_xp,
                "reward_gold": reward_gold,
            })
            self.game.sfx.play("quest_complete")

            # Mark as turned in so rewards aren't given again
            mq_state["status"] = "turned_in"
            self.ow_quest_dialogue_lines = []

        elif status == "turned_in":
            self.show_message(
                f"{npc.name}: Thank you again, hero! "
                f"Your deeds will be remembered.  [ENTER]", 999999)
            self.ow_quest_dialogue_lines = []

    def _handle_ow_npc_dialogue_input(self, event):
        """Handle input while overworld NPC dialogue is active."""
        import pygame

        # Quest choice screen (accept / decline)
        if self.ow_quest_choice_active:
            if event.key in (pygame.K_UP, pygame.K_LEFT):
                self.ow_quest_choice_cursor = 0
            elif event.key in (pygame.K_DOWN, pygame.K_RIGHT):
                self.ow_quest_choice_cursor = 1
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._handle_ow_quest_choice()
            elif event.key == pygame.K_ESCAPE:
                # Decline on escape
                self.ow_quest_choice_cursor = 1
                self._handle_ow_quest_choice()
            return

        # Advancing dialogue lines — accept ANY key press
        if self.ow_quest_dialogue_lines:
            self.ow_quest_dialogue_index += 1
            if (self.ow_quest_dialogue_index
                    < len(self.ow_quest_dialogue_lines)):
                npc = self.ow_npc_speaking
                line = self.ow_quest_dialogue_lines[
                    self.ow_quest_dialogue_index]
                remaining = (len(self.ow_quest_dialogue_lines)
                             - self.ow_quest_dialogue_index - 1)
                hint = "  [ENTER] >" if remaining > 0 else "  [ENTER]"
                self.show_message(
                    f"{npc.name}: {line}{hint}", 999999)
                return
            else:
                # All dialogue shown — present choices if available
                npc = self.ow_npc_speaking
                if npc and npc.quest_choices:
                    self.ow_quest_choice_active = True
                    self.ow_quest_choices = list(npc.quest_choices)
                    self.ow_quest_choice_cursor = 0
                    return
        # No more lines / no choices — dismiss
        self._dismiss_ow_npc_dialogue()

    def _handle_ow_quest_choice(self):
        """Handle accept/decline on overworld quest offer."""
        npc = self.ow_npc_speaking
        if self.ow_quest_choice_cursor == 0:
            # Accept
            mqname = getattr(npc, "_module_quest_name", "")
            mq_states = getattr(self.game, "module_quest_states", {})
            if mqname in mq_states:
                mq_states[mqname]["status"] = "active"
            # Spawn quest monsters for any 'kill' steps
            if hasattr(self.game, "_spawn_quest_monsters"):
                self.game._spawn_quest_monsters(mqname)
            # Quest accepted visual effect
            self.quest_effects.append({
                "type": "quest_accepted",
                "timer": 2500,
                "duration": 2500,
                "col": npc.col,
                "row": npc.row,
                "quest_name": mqname,
            })
            self.game.sfx.play("quest_complete")
            self.show_message(
                f"{npc.name}: Wonderful! I'm counting on you. "
                f"Good luck!", 3000)
        else:
            # Decline
            self.show_message(
                f"{npc.name}: No worries. Come back if you change "
                f"your mind.", 3000)
        self.ow_quest_choice_active = False
        self.ow_quest_choices = []
        self.ow_quest_dialogue_lines = []
        self.ow_quest_dialogue_index = 0
        self.ow_npc_dialogue_active = False
        self.ow_npc_speaking = None

    def _dismiss_ow_npc_dialogue(self):
        """Close the overworld NPC dialogue."""
        self.ow_npc_dialogue_active = False
        self.ow_npc_speaking = None
        self.ow_quest_dialogue_lines = []
        self.ow_quest_dialogue_index = 0
        self.ow_quest_choice_active = False
        self.ow_quest_choices = []
        self.message = ""
        self.message_timer = 0

    def _check_quest_monster_kills(self):
        """After returning from combat, check if any killed monsters
        were quest targets and update step progress accordingly.

        Returns a message string if a step or quest was completed,
        otherwise None.
        """
        from src.quest_manager import check_quest_kills
        result_msg = check_quest_kills(self.game)
        if result_msg:
            self.quest_effects.append({
                "type": "step_complete",
                "timer": 2000,
                "duration": 2000,
                "text": result_msg,
            })
        return result_msg

    def _move_overworld_npcs(self):
        """Randomly wander overworld quest NPCs one step."""
        from src.settings import TILE_GRASS, TILE_PATH
        tmap = self.game.tile_map
        party = self.game.party
        npcs = getattr(self.game, "overworld_quest_npcs", [])
        if not npcs:
            return
        # Only move ~30% of the time so they don't zip around
        if random.random() > 0.3:
            return
        occupied = {(party.col, party.row)}
        for n in npcs:
            occupied.add((n.col, n.row))
        for mon in self.overworld_monsters:
            if mon.is_alive():
                occupied.add((mon.col, mon.row))
        for npc in npcs:
            # Quest collectible items never move
            if getattr(npc, "npc_type", "") == "quest_item":
                continue
            dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
            random.shuffle(dirs)
            for dc, dr in dirs:
                nc, nr = npc.col + dc, npc.row + dr
                if ((nc, nr) not in occupied
                        and 0 <= nc < tmap.width
                        and 0 <= nr < tmap.height
                        and tmap.get_tile(nc, nr) in (
                            TILE_GRASS, TILE_PATH)):
                    occupied.discard((npc.col, npc.row))
                    npc.col = nc
                    npc.row = nr
                    occupied.add((nc, nr))
                    break

    # ── Monster helpers ───────────────────────────────────────────

    def _get_monster_at(self, col, row):
        """Return the alive orc at (col, row), or None."""
        for mon in self.overworld_monsters:
            if mon.col == col and mon.row == row and mon.is_alive():
                return mon
        return None

    def _move_monsters(self):
        """Each alive orc wanders randomly, but pursues if within 6 tiles.

        Guardian monsters (tagged with ``_guardian_anchor``) stay leashed
        near their artifact and only intercept the party when it gets
        close to the anchor point.

        While a repel effect is active, monsters inside its radius flee
        *away* from the party instead of pursuing.
        """
        party = self.game.party
        alive = [m for m in self.overworld_monsters if m.is_alive()]
        occupied = {(m.col, m.row) for m in alive}
        occupied.add((party.col, party.row))

        repel = self.repel_effect  # may be None

        for mon in alive:
            occupied.discard((mon.col, mon.row))
            prev_col, prev_row = mon.col, mon.row
            cheb = max(abs(mon.col - party.col), abs(mon.row - party.row))

            anchor = getattr(mon, "_guardian_anchor", None)
            if anchor:
                # ── Guardian behaviour: stay near artifact, intercept ──
                leash = getattr(mon, "_guardian_leash", GUARDIAN_LEASH)
                ax, ay = anchor
                dist_party_to_anchor = (abs(party.col - ax)
                                        + abs(party.row - ay))
                # Intercept: pursue if party is within 8 tiles of artifact
                if dist_party_to_anchor <= GUARDIAN_INTERCEPT_RANGE_OVERWORLD and cheb <= 10:
                    # Move toward party but don't stray too far from anchor
                    self._guardian_move_toward(
                        mon, party.col, party.row,
                        ax, ay, leash, occupied)
                else:
                    # Drift back toward anchor if too far, else idle
                    dist_to_anchor = (abs(mon.col - ax)
                                      + abs(mon.row - ay))
                    if dist_to_anchor > leash:
                        mon.try_move_toward(
                            ax, ay, self.game.tile_map, occupied)
                    # Otherwise stay put — guardians don't wander
            elif repel and cheb <= repel["radius"]:
                # If repel effect is active and monster is within radius, flee
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
            # Safety: if a monster somehow landed on a non-walkable tile,
            # snap it back to its previous position.
            if not self.game.tile_map.is_walkable(mon.col, mon.row):
                mon.col, mon.row = prev_col, prev_row
            occupied.add((mon.col, mon.row))

        # Tick down the lingering repel effect (one step per party move)
        if repel:
            repel["steps_remaining"] -= 1
            if repel["steps_remaining"] <= 0:
                self.repel_effect = None

    def _guardian_move_toward(self, mon, target_col, target_row,
                              anchor_col, anchor_row, leash, occupied):
        """Move a guardian monster toward *target* without exceeding *leash*
        distance from the anchor (the artifact it protects).
        """
        from src.settings import TILE_GRASS, TILE_PATH
        tmap = self.game.tile_map

        # Try all four cardinal directions, prefer the one closest to target
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        best = None
        best_dist = abs(mon.col - target_col) + abs(mon.row - target_row)
        for dc, dr in dirs:
            nc, nr = mon.col + dc, mon.row + dr
            # Must stay within leash of anchor
            if (abs(nc - anchor_col) + abs(nr - anchor_row)) > leash:
                continue
            if (nc, nr) in occupied:
                continue
            if not (0 <= nc < tmap.width and 0 <= nr < tmap.height):
                continue
            if tmap.get_tile(nc, nr) not in (TILE_GRASS, TILE_PATH):
                continue
            d = abs(nc - target_col) + abs(nr - target_row)
            if d < best_dist:
                best_dist = d
                best = (nc, nr)
        if best:
            mon.col, mon.row = best

    def _check_monster_contact(self):
        """If a monster is adjacent to (or on top of) the party, show
        the encounter screen.

        Adjacency uses Chebyshev distance (``max(|dc|, |dr|) <= 1``)
        so diagonally-adjacent monsters count too.  Manhattan-only
        adjacency caused monsters that got stuck on a diagonal tile
        (because their cardinal path was blocked by water, trees, or
        another monster) to never trigger an encounter — the party
        would walk past them without ever seeing the dialog.

        While the party is aboard the boat, only sea creatures can
        initiate contact — a Wyvern standing on shore next to the
        boat can't reach the party through the water, so it shouldn't
        force an encounter.  The party can still deliberately attack
        land monsters by stepping off the boat onto their tile.
        """
        party = self.game.party
        on_boat = bool(getattr(self.game, "on_boat", False))
        for mon in self.overworld_monsters:
            if not mon.is_alive():
                continue
            # Skip land creatures while sailing — they can't board.
            if on_boat and getattr(mon, "terrain", "land") != "sea":
                continue
            if (max(abs(mon.col - party.col),
                    abs(mon.row - party.row)) <= 1):
                self._show_encounter_action(mon)
                return

    # ── Encounter action screen (roaming monsters) ───────────

    def _show_encounter_action(self, monster):
        """Show the encounter prompt for a roaming overworld monster."""
        self.encounter_action_monster = monster
        self.encounter_action_cursor = 0
        self.encounter_action_result = None
        self.encounter_result_timer = 0
        self.encounter_action_active = True

    def _handle_encounter_action_input(self, event):
        """Handle input for the monster encounter action screen."""
        # While showing a flee result message, consume any key to dismiss
        if self.encounter_action_result is not None:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                if self.encounter_action_result in ("fled", "fled_far"):
                    # Successful flee — push monster away by the
                    # distance determined by the saving throw
                    flee_dist = getattr(
                        self, '_encounter_flee_distance', 2)
                    mon = self.encounter_action_monster
                    if mon:
                        party = self.game.party
                        dx = mon.col - party.col
                        dy = mon.row - party.row
                        # Normalise direction (handle zero)
                        step_x = (1 if dx > 0 else -1 if dx < 0
                                  else (1 if dy == 0 else 0))
                        step_y = (1 if dy > 0 else -1 if dy < 0
                                  else (0 if dx != 0 else 1))
                        for _ in range(flee_dist):
                            nc = mon.col + step_x
                            nr = mon.row + step_y
                            if (0 <= nc < self.game.tile_map.width
                                    and 0 <= nr < self.game.tile_map.height
                                    and self.game.tile_map.is_walkable(
                                        nc, nr)):
                                mon.col, mon.row = nc, nr
                            else:
                                break
                    self.encounter_action_active = False
                    self._exit_grace = True
                else:
                    # Failed flee — enter combat
                    self._encounter_engage()
            return

        n_options = 2  # Engage, Flee
        if event.key in (pygame.K_UP, pygame.K_w):
            self.encounter_action_cursor = (
                self.encounter_action_cursor - 1) % n_options
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.encounter_action_cursor = (
                self.encounter_action_cursor + 1) % n_options
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.encounter_action_cursor == 0:
                self._encounter_engage()
            elif self.encounter_action_cursor == 1:
                self._encounter_flee()
        elif event.key == pygame.K_ESCAPE:
            # ESC = flee
            self._encounter_flee()

    def _encounter_engage(self):
        """Confirm engagement — start combat with the contacted monster."""
        mon = self.encounter_action_monster
        self.encounter_action_active = False
        if mon:
            self._start_orc_combat(mon)

    def _encounter_flee(self):
        """Attempt to flee using a DEX saving throw.

        Party average DEX modifier vs. monster effective DEX (derived from AC).
        Roll d20 + party_avg_dex_mod >= 10 + monster_dex_mod to escape.
        """
        import random as _rng
        party = self.game.party
        mon = self.encounter_action_monster

        # Party: average dex modifier of alive members
        alive = [m for m in party.members if m.is_alive()]
        if alive:
            avg_dex_mod = sum(m.dex_mod for m in alive) / len(alive)
        else:
            avg_dex_mod = 0

        # Monster: derive a rough dex modifier from AC
        # Base AC 10 implies +0 mod; each point above is roughly +1
        monster_dex_mod = max(0, (getattr(mon, 'ac', 10) - 10) // 2)

        roll = _rng.randint(1, 20)
        dc = 10 + monster_dex_mod
        total = roll + int(avg_dex_mod)

        if total >= dc:
            # Second saving throw determines escape distance:
            # Beat the DC again → 4 tiles, otherwise → 2 tiles
            dist_roll = _rng.randint(1, 20) + int(avg_dex_mod)
            if dist_roll >= dc:
                flee_dist = 4
                self.encounter_action_result = "fled_far"
            else:
                flee_dist = 2
                self.encounter_action_result = "fled"
            self._encounter_flee_distance = flee_dist
            self.encounter_result_timer = 1500
            self.game.sfx.play("chirp")
        else:
            self.encounter_action_result = "failed"
            self._encounter_flee_distance = 0
            self.encounter_result_timer = 1500
            self.game.sfx.play("hit")

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
        # Pass the terrain tile the party is standing on so the combat
        # arena can spawn appropriate obstacles (trees, rocks, etc.)
        terrain_tile = self.game.tile_map.get_tile(
            self.game.party.col, self.game.party.row)

        # Derive combat_location from the current context. When we're
        # inside a building interior, use the same space/building
        # string that quest kill-tracking and arena-style rendering
        # rely on — otherwise fall back to the open-world default.
        if self._in_overworld_interior:
            bld_name = self._building_name
            int_name = self._overworld_interior_name
            if bld_name and int_name and bld_name != int_name:
                combat_location = f"space:{bld_name}/{int_name}"
            else:
                combat_location = (
                    f"building:{bld_name or int_name}")
        else:
            combat_location = "overview"

        combat_state.start_combat(fighter, monsters,
                                  source_state="overworld",
                                  encounter_name=enc_name,
                                  map_monster_refs=[orc],
                                  terrain_tile=terrain_tile,
                                  combat_location=combat_location)
        self.game.change_state("combat")

    # ── Tile events ───────────────────────────────────────────────

    def _check_tile_events(self):
        """Check if the party stepped on a special tile."""
        # After returning from a town/dungeon, skip the first check so
        # the player isn't immediately prompted to re-enter.
        if self._exit_grace:
            self._exit_grace = False
            return

        # Don't re-trigger if an action screen is already active
        if (self.building_action_active or self.dungeon_action_active
                or self.town_action_active or self.spawn_action_active):
            return

        party = self.game.party

        # ── If inside an overworld interior, check exits and links ──
        if self._in_overworld_interior:
            # Placed ground item pickup (inside building interiors)
            _try_pickup_ground_item(
                self.game, self.game.tile_map,
                party.col, party.row,
                log_sink=self.game.game_log.append,
                msg_sink=self.show_message,
            )
            # Skip exit check on the first move after entering so the
            # player isn't immediately ejected when spawning on an exit.
            if self._overworld_interior_entry_grace:
                self._overworld_interior_entry_grace = False
            else:
                if (party.col, party.row) in self._overworld_interior_exit_positions:
                    self._exit_overworld_interior()
                    return
            # Interior-to-interior links
            interior_name = self._overworld_interior_links.get(
                (party.col, party.row))
            if interior_name:
                self._enter_overworld_interior(
                    interior_name, party.col, party.row,
                    building_name=self._building_name)
                return
            # Check tile link inside building interior
            int_props = self._get_interior_tile_props(
                party.col, party.row)
            if int_props.get("linked"):
                # Exit the interior first, then follow the link
                # from the overworld position where the building is.
                ow_col = getattr(self, '_stashed_overworld_party_col',
                                 party.col)
                ow_row = getattr(self, '_stashed_overworld_party_row',
                                 party.row)
                link_map = int_props.get("link_map", "")
                # Exit the interior, restore overworld state, then
                # follow the link directly (no action screen popup).
                self._exit_overworld_interior()
                self.game.party.col = ow_col
                self.game.party.row = ow_row
                self.game.camera.map_width = self.game.tile_map.width
                self.game.camera.map_height = self.game.tile_map.height
                self.game.camera.update(ow_col, ow_row)
                self._follow_tile_link(int_props, ow_col, ow_row,
                                       direct=True)
                return
            return  # no other tile events inside interiors

        pcol, prow = party.col, party.row
        tmap = self.game.tile_map

        # ── Placed ground item pickup (items editor → tile_properties) ──
        _try_pickup_ground_item(self.game, tmap, pcol, prow,
                                log_sink=self.game.game_log.append,
                                msg_sink=self.show_message)

        # ── Check tile link (universal linking system) ──
        # If the tile at the party's position has a link configured
        # in tile_properties, follow it to the target map.
        tile_props = self._get_overworld_tile_props(pcol, prow)
        if tile_props.get("linked"):
            self._follow_tile_link(tile_props, pcol, prow)
            return

        tile_id = tmap.get_tile(pcol, prow)

        if tile_id == TILE_TOWN:
            # Only trigger town entry if the module actually defines a
            # town at this position.  Placing a town *graphic* on the
            # overworld map is purely cosmetic until the designer
            # registers the town in the module editor.
            if (pcol, prow) in self.game.town_data_map:
                self._show_town_action()
                return

        elif tile_id in (TILE_DUNGEON, TILE_DUNGEON_CLEARED):
            # Link system removed — unlinked dungeon tiles treated as scenery
            # in custom modules. Base game shows dungeon action.
            if not self.game.module_manifest:
                self._show_dungeon_action(pcol, prow)
            return

        elif tile_id == TILE_CHEST:
            self._open_chest()
            # Restore the original tile that was under the chest
            pos = (pcol, prow)
            original = self.chest_under_tiles.pop(pos, TILE_GRASS)
            tmap.set_tile(pos[0], pos[1], original)
            return

        # Check for spawn tiles (any tile with interaction_type == "spawn")
        from src import settings as _settings
        tdef = _settings.TILE_DEFS.get(tile_id, {})
        if tdef.get("interaction_type") == "spawn" or tile_id == TILE_SPAWN:
            if (pcol, prow) not in self.destroyed_spawns:
                self._show_spawn_action(pcol, prow, tile_id)
            return

        # ── Unique tile check ──
        self._check_unique_tile()

    # ── Overworld interior entry / exit ──────────────────────

    def _enter_overworld_interior(self, interior_name, door_col, door_row,
                                     building_name=""):
        """Transition into an overworld interior (dungeon-style map)."""
        tmap = self.game.tile_map

        # If the target interior is already in the stack, unwind back to it
        # instead of nesting deeper (same pattern as town.py).
        stack = self._overworld_interior_stack
        for i in range(len(stack) - 1, -1, -1):
            if stack[i].get("name") == interior_name:
                while len(stack) > i + 1:
                    stack.pop()
                prev = stack.pop()
                self.game.tile_map = prev["tile_map"]
                self._overworld_interior_links = prev["interior_links"]
                self._overworld_interior_exit_positions = prev["exit_positions"]
                self.game.party.col = prev["col"]
                self.game.party.row = prev["row"]
                self._overworld_interior_name = prev.get("name", "")
                if not stack:
                    self._in_overworld_interior = False
                    # Restore overworld state
                    if self._stashed_overworld_tile_map is not None:
                        self.game.tile_map = self._stashed_overworld_tile_map
                        self._stashed_overworld_tile_map = None
                    if self._stashed_overworld_monsters is not None:
                        self.overworld_monsters = self._stashed_overworld_monsters
                        self._stashed_overworld_monsters = None
                self.game.camera.map_width = self.game.tile_map.width
                self.game.camera.map_height = self.game.tile_map.height
                self.game.camera.update(
                    self.game.party.col, self.game.party.row)
                self.show_message(
                    f"Returning to {interior_name}...", 1000)
                return

        # Find the interior definition from the overworld tile map's
        # interiors list (loaded from static_overworld.json).
        src_tmap = self._stashed_overworld_tile_map or tmap
        interiors = getattr(src_tmap, "overworld_interiors", [])
        interior = None
        for entry in interiors:
            if entry.get("name") == interior_name:
                interior = entry
                break
        if not interior or not interior.get("tiles"):
            self.show_message("Nothing here.", 1500)
            return

        # Push current state onto the interior stack.
        # ``source_map`` records where we came from so the destination
        # interior can find the correct back-link tile without searching.
        source_map_name = self._overworld_interior_name or "overworld"
        self._overworld_interior_stack.append({
            "col": door_col,
            "row": door_row,
            "source_map": source_map_name,
            "tile_map": self.game.tile_map,
            "interior_links": dict(self._overworld_interior_links),
            "exit_positions": set(self._overworld_interior_exit_positions),
            "name": self._overworld_interior_name,
        })

        # First time entering from the overworld — stash the overworld map
        if not self._in_overworld_interior:
            self._stashed_overworld_tile_map = tmap
            self._stashed_overworld_monsters = list(self.overworld_monsters)
            self.overworld_monsters = []  # no roaming orcs in interiors
            # Remember where the party was on the overworld so links
            # from inside interiors can return to the correct position.
            self._stashed_overworld_party_col = door_col
            self._stashed_overworld_party_row = door_row

        self._overworld_interior_name = interior_name
        self._in_overworld_interior = True
        self._overworld_interior_entry_grace = True

        # Build a tile map from the interior grid (dungeon tiles)
        from src.tile_map import TileMap
        from src.settings import TILE_VOID
        iw = interior.get("width", 14)
        ih = interior.get("height", 15)
        imap = TileMap(iw, ih, default_tile=TILE_VOID, oob_tile=TILE_VOID)

        for pos_key, td in interior.get("tiles", {}).items():
            parts = pos_key.split(",")
            c, r = int(parts[0]), int(parts[1])
            tid = td.get("tile_id")
            if tid is not None and 0 <= c < iw and 0 <= r < ih:
                imap.set_tile(c, r, tid)
                path = td.get("path")
                if path:
                    imap.sprite_overrides[(c, r)] = path

        # Store tile_properties on the interior map so links work at runtime
        imap.tile_properties = interior.get("tile_properties", {})

        # Restore the spawn-once memory for this interior so designer-
        # placed encounters that were already materialised (and likely
        # killed) on a previous visit stay gone. The interior tile_map
        # is rebuilt from JSON on every entry, so without this the
        # ``_spawned_placement_positions`` set would be empty each
        # time and dead monsters would silently respawn. The set is
        # held on the game (keyed by interior name) and shared by
        # reference, so ``_spawn_placed_encounters`` mutating it also
        # updates the cache.
        spawn_cache = getattr(self.game, "building_interior_spawns", None)
        if spawn_cache is None:
            spawn_cache = {}
            self.game.building_interior_spawns = spawn_cache
        imap._spawned_placement_positions = spawn_cache.setdefault(
            interior_name, set())

        self.game.tile_map = imap

        # Link system removed — initialize empty interior state
        self._overworld_interior_exit_positions = set()
        self._overworld_interior_links = {}
        exit_positions = []
        first_walkable = None
        entry_placed = False

        # ── Priority 1: BFS from center, fallback ──
        if not entry_placed:
            for pos_key, td in interior.get("tiles", {}).items():
                parts = pos_key.split(",")
                c, r = int(parts[0]), int(parts[1])
                tid = td.get("tile_id")
                if first_walkable is None and tid is not None:
                    from src.settings import TILE_DEFS
                    tdef = TILE_DEFS.get(tid, {})
                    if tdef.get("walkable", False):
                        first_walkable = (c, r)

        # BFS from exit tile to find nearest walkable non-exit tile for spawn
        if exit_positions and not entry_placed:
            from src.settings import TILE_DEFS as _TD
            ec, er = exit_positions[0]
            visited = set()
            queue = [(ec, er)]
            visited.add((ec, er))
            while queue and not entry_placed:
                cx, cy = queue.pop(0)
                for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                    nc, nr = cx + dc, cy + dr
                    if (nc, nr) in visited:
                        continue
                    visited.add((nc, nr))
                    if not (0 <= nc < iw and 0 <= nr < ih):
                        continue
                    ntid = imap.get_tile(nc, nr)
                    if _TD.get(ntid, {}).get("walkable", False):
                        if (nc, nr) not in self._overworld_interior_exit_positions:
                            self.game.party.col = nc
                            self.game.party.row = nr
                            entry_placed = True
                            break
                    queue.append((nc, nr))
            # Last resort: place on the exit tile itself
            if not entry_placed:
                self.game.party.col = ec
                self.game.party.row = er
                entry_placed = True

        if not entry_placed and first_walkable:
            self.game.party.col = first_walkable[0]
            self.game.party.row = first_walkable[1]
            entry_placed = True

        if not entry_placed:
            self.game.party.col = iw // 2
            self.game.party.row = ih // 2

        # Override with explicit target position from a tile link
        _tp = getattr(self, '_pending_link_target_pos', None)
        if _tp and _tp != (0, 0):
            self.game.party.col = _tp[0]
            self.game.party.row = _tp[1]
            self._pending_link_target_pos = None

        # Update camera
        self.game.camera.map_width = iw
        self.game.camera.map_height = ih
        self.game.camera.update(self.game.party.col, self.game.party.row)

        # Spawn data-defined NPCs from the interior definition first.
        self._building_interior_npcs = []
        self._build_building_interior_npcs(interior, imap)

        # Spawn quest items and guardians for this building interior.
        # Quest data can be keyed by building name ("building:X") or
        # by a specific space ("space:X/Y").
        self._building_name = building_name or interior_name
        quest_key_name = self._building_name
        self._spawn_building_quest_collect_items(
            quest_key_name, imap, space_name=interior_name)
        self._spawn_building_quest_monsters(
            quest_key_name, imap, space_name=interior_name)
        self._spawn_building_quest_givers(
            quest_key_name, interior_name, imap)

        # Materialize designer-placed encounter templates that live
        # on this interior's map. ``_spawn_placed_encounters`` scans
        # ``self.game.tile_map.tile_properties`` — which is now the
        # interior map — and adds party-leader monsters to
        # ``self.overworld_monsters``. That list was cleared to ``[]``
        # when we entered the interior, so the set is fresh per
        # interior, but the spawn-once bookkeeping on the state
        # itself still prevents a defeated placement from respawning
        # if the player exits this interior and re-enters (within
        # the same session).
        self._spawn_placed_encounters()

        self.show_message(f"Entering {interior_name}...", 1500)

    def _exit_overworld_interior(self):
        """Return from an overworld interior to the previous level."""
        stack = self._overworld_interior_stack
        if not stack:
            self._in_overworld_interior = False
            return
        prev = stack.pop()
        self.game.tile_map = prev["tile_map"]
        self.game.party.col = prev["col"]
        self.game.party.row = prev["row"]
        self._overworld_interior_exit_positions = prev.get(
            "exit_positions", set())
        self._overworld_interior_links = prev.get("interior_links", {})
        leaving_name = self._overworld_interior_name
        self._overworld_interior_name = prev.get("name", "")

        # If the stack is now empty, we're back on the overworld
        if not stack:
            self._in_overworld_interior = False
            # Restore the stashed overworld tile map
            if self._stashed_overworld_tile_map is not None:
                self.game.tile_map = self._stashed_overworld_tile_map
                self._stashed_overworld_tile_map = None
            if self._stashed_overworld_monsters is not None:
                self.overworld_monsters = self._stashed_overworld_monsters
                self._stashed_overworld_monsters = None

        self.game.camera.map_width = self.game.tile_map.width
        self.game.camera.map_height = self.game.tile_map.height
        self.game.camera.update(self.game.party.col, self.game.party.row)
        self._building_interior_npcs = []
        self._building_name = ""
        self._exit_grace = True  # brief grace period before next action
        self.show_message(f"Leaving {leaving_name}...", 1000)

    # ── Building interior quest spawning & interaction ─────────

    def _build_building_interior_npcs(self, interior_def, imap):
        """Create NPC objects from a building interior's ``npcs`` list.

        Reads an optional ``"npcs"`` array from the interior/space
        definition and appends :class:`NPC` objects to
        ``_building_interior_npcs``.
        """
        import random as _rng
        from src.town_generator import NPC

        npc_defs = interior_def.get("npcs")
        if not npc_defs:
            return

        iw, ih = imap.width, imap.height
        walkable = set()
        for wy in range(ih):
            for wx in range(iw):
                if imap.is_walkable(wx, wy):
                    walkable.add((wx, wy))
        # Remove exit tiles from candidates
        for pos in self._overworld_interior_exit_positions:
            walkable.discard(pos)
        walkable.discard((self.game.party.col, self.game.party.row))

        occupied = {(n.col, n.row) for n in self._building_interior_npcs}
        rng = _rng.Random(
            hash(interior_def.get("name", "")) & 0xFFFFFFFF)

        for nd in npc_defs:
            npc_name = nd.get("name", "Villager")
            dialogue = nd.get("dialogue", ["..."])
            if not dialogue:
                dialogue = ["..."]
            npc = NPC(
                col=nd.get("col", 0),
                row=nd.get("row", 0),
                name=npc_name,
                dialogue=dialogue,
                npc_type=nd.get("npc_type", "villager"),
                god_name=nd.get("god_name"),
                shop_type=nd.get("shop_type", "general"),
                sprite=nd.get("sprite") or None,
                quest_dialogue=nd.get("quest_dialogue"),
                quest_choices=nd.get("quest_choices"),
                quest_name=nd.get("quest_name"),
                artifact_name=nd.get("artifact_name"),
                hint_active=nd.get("hint_active"),
                text_complete=nd.get("text_complete"),
                innkeeper_quests=nd.get("innkeeper_quests", False),
            )
            npc.wander_range = nd.get("wander_range", 4)

            # If specified position is free, keep it; else pick random
            pos = (npc.col, npc.row)
            if pos in walkable and pos not in occupied:
                occupied.add(pos)
            else:
                free = list(walkable - occupied)
                if free:
                    nc, nr = rng.choice(free)
                    npc.col = nc
                    npc.row = nr
                    occupied.add((nc, nr))

            self._building_interior_npcs.append(npc)

    def _spawn_building_quest_collect_items(self, interior_name, imap,
                                               space_name=""):
        """Place collectible quest items inside a building interior."""
        import random as _rng
        from src.town_generator import NPC

        items_dict = getattr(self.game, "quest_collect_items", {})
        # Check both the generic building key and the specific space key.
        # e.g. "building:Abandoned Building" and
        #      "space:Abandoned Building/Basement"
        entries = list(items_dict.get(f"building:{interior_name}", []))
        if space_name:
            entries.extend(items_dict.get(
                f"space:{interior_name}/{space_name}", []))
        if not entries:
            return

        mq_states = getattr(self.game, "module_quest_states", {})

        walkable = []
        for wy in range(imap.height):
            for wx in range(imap.width):
                if imap.is_walkable(wx, wy):
                    walkable.append((wx, wy))

        occupied = set()
        # Exclude exit positions
        occupied.update(self._overworld_interior_exit_positions)
        rng = _rng.Random(hash(interior_name) & 0xFFFFFFFF)

        for entry in entries:
            qname = entry["quest_name"]
            step_idx = entry["step_idx"]
            item_name = entry["item_name"]
            item_sprite = entry.get("item_sprite", "")

            qstate = mq_states.get(qname, {})
            if qstate.get("status") != "active":
                continue
            progress = qstate.get("step_progress", [])
            if step_idx < len(progress) and progress[step_idx]:
                continue

            free = [p for p in walkable if p not in occupied]
            if not free:
                break
            col, row = rng.choice(free)
            occupied.add((col, row))

            npc = NPC(
                col=col, row=row,
                name=item_name,
                dialogue=[f"You found {item_name}!"],
                npc_type="quest_item",
            )
            npc._quest_name = qname
            npc._quest_step_idx = step_idx
            npc._item_sprite = item_sprite
            npc.quest_highlight = True
            self._building_interior_npcs.append(npc)

    def _spawn_building_quest_monsters(self, interior_name, imap,
                                          space_name=""):
        """Place quest monster NPCs inside a building interior."""
        import random as _rng
        from src.town_generator import NPC
        from src.monster import MONSTERS

        monsters_dict = getattr(self.game, "quest_interior_monsters", {})
        # Check both the generic building key and the specific space key.
        entries = list(monsters_dict.get(f"building:{interior_name}", []))
        if space_name:
            entries.extend(monsters_dict.get(
                f"space:{interior_name}/{space_name}", []))
        if not entries:
            return

        mq_states = getattr(self.game, "module_quest_states", {})

        walkable = []
        for wy in range(imap.height):
            for wx in range(imap.width):
                if imap.is_walkable(wx, wy):
                    walkable.append((wx, wy))

        occupied = {(n.col, n.row) for n in self._building_interior_npcs}
        occupied.update(self._overworld_interior_exit_positions)
        rng = _rng.Random(hash(interior_name + "_mon") & 0xFFFFFFFF)

        for entry in entries:
            qname = entry["quest_name"]
            step_idx = entry["step_idx"]
            monster_key = entry["monster_key"]
            count = entry.get("count", 1)
            is_guardian = entry.get("is_guardian", False)
            enc_name = entry.get("encounter_name", "")

            qstate = mq_states.get(qname, {})
            if qstate.get("status") != "active":
                continue
            progress = qstate.get("step_progress", [])
            if step_idx < len(progress) and progress[step_idx]:
                continue

            monster_info = MONSTERS.get(monster_key, {})
            display_name = monster_info.get(
                "name", monster_key.replace("_", " ").title())

            # Find the quest_item this guardian protects
            anchor_pos = None
            if is_guardian:
                for existing_npc in self._building_interior_npcs:
                    if (getattr(existing_npc, "npc_type", "") == "quest_item"
                            and getattr(existing_npc, "_quest_name", "") == qname
                            and getattr(existing_npc, "_quest_step_idx", -1) == step_idx):
                        anchor_pos = (existing_npc.col, existing_npc.row)
                        break

            for i in range(count):
                if anchor_pos:
                    ax, ay = anchor_pos
                    nearby = [(ax + dc, ay + dr)
                              for dc in range(-2, 3)
                              for dr in range(-2, 3)
                              if (dc, dr) != (0, 0)
                              and (ax + dc, ay + dr) in walkable
                              and (ax + dc, ay + dr) not in occupied]
                    if nearby:
                        col, row = rng.choice(nearby)
                    else:
                        free = [p for p in walkable if p not in occupied]
                        if not free:
                            break
                        col, row = rng.choice(free)
                else:
                    free = [p for p in walkable if p not in occupied]
                    if not free:
                        break
                    col, row = rng.choice(free)
                occupied.add((col, row))

                npc = NPC(
                    col=col, row=row,
                    name=display_name,
                    dialogue=["*growls menacingly*"],
                    npc_type="quest_monster",
                )
                npc._quest_name = qname
                npc._quest_step_idx = step_idx
                npc._monster_key = monster_key
                if enc_name:
                    npc._quest_encounter_name = enc_name
                npc.wander_range = NPC_WANDER_RANGE
                if is_guardian and anchor_pos:
                    npc._guardian_anchor = anchor_pos
                    npc._guardian_leash = GUARDIAN_LEASH
                self._building_interior_npcs.append(npc)

    def _spawn_building_quest_givers(self, building_name, space_name, imap):
        """Place quest giver NPCs inside a building interior.

        Matches quests whose giver_location is
        ``space:<building_name>/<space_name>``.
        """
        import random as _rng
        from src.town_generator import NPC

        quest_defs = getattr(self.game, "_module_quest_defs", [])
        if not quest_defs:
            return

        mq_states = getattr(self.game, "module_quest_states", {})

        # Match locations like "space:Mystery Shrine/Main Hall"
        loc_key = f"space:{building_name}/{space_name}"
        # Also match just the building name for simpler configs
        loc_key_bldg = f"space:{building_name}"

        walkable = []
        for wy in range(imap.height):
            for wx in range(imap.width):
                if imap.is_walkable(wx, wy):
                    walkable.append((wx, wy))

        occupied = {(n.col, n.row) for n in self._building_interior_npcs}
        occupied.update(self._overworld_interior_exit_positions)
        rng = _rng.Random(hash(building_name + space_name) & 0xFFFFFFFF)

        for qdef in quest_defs:
            qname = qdef.get("name", "")
            if not qname:
                continue
            loc = qdef.get("giver_location", "")
            if loc != loc_key and loc != loc_key_bldg:
                continue

            # Don't spawn if quest is fully turned in
            qstate = mq_states.get(qname, {})
            if qstate.get("status") == "turned_in":
                continue

            # Don't spawn if already present
            already = any(
                getattr(n, "_module_quest_name", "") == qname
                for n in self._building_interior_npcs
            )
            if already:
                continue

            npc_label = qdef.get("giver_npc", "") or qname
            sprite = qdef.get("giver_sprite", "") or None
            dialogue_text = qdef.get("giver_dialogue", "")
            if dialogue_text:
                lines = [s.strip() for s in dialogue_text.split("\n")
                         if s.strip()]
                if not lines:
                    lines = [dialogue_text]
            else:
                lines = [f"I have a quest for you: {qname}"]

            free = [p for p in walkable if p not in occupied]
            if not free:
                break
            col, row = rng.choice(free)
            occupied.add((col, row))

            npc = NPC(
                col=col, row=row,
                name=npc_label,
                dialogue=[
                    "Thank you for your help!",
                    "The quest awaits...",
                ],
                npc_type="module_quest_giver",
                quest_dialogue=lines,
                quest_choices=["Accept quest", "Not right now"],
                sprite=sprite,
            )
            npc._module_quest_name = qname
            npc.wander_range = NPC_WANDER_RANGE
            self._building_interior_npcs.append(npc)

    def _check_building_interior_npc(self):
        """Check if the party bumped into a building interior NPC."""
        party = self.game.party
        for npc in self._building_interior_npcs:
            if npc.col == party.col and npc.row == party.row:
                if npc.npc_type == "quest_monster":
                    self._start_building_quest_combat(npc)
                    return True
                elif npc.npc_type == "quest_item":
                    self._collect_building_quest_item(npc)
                    return True
        return False

    def _collect_building_quest_item(self, npc):
        """Pick up a quest collectible item inside a building interior."""
        from src.quest_manager import collect_quest_item
        if npc in self._building_interior_npcs:
            self._building_interior_npcs.remove(npc)
        msg = collect_quest_item(
            self.game,
            getattr(npc, "_quest_name", ""),
            getattr(npc, "_quest_step_idx", -1),
            npc.name)
        self.show_message(msg, 3000 if "complete" in msg.lower() else 2500)

    def _start_building_quest_combat(self, npc):
        """Initiate combat with a quest monster NPC inside a building."""
        from src.monster import create_monster, create_encounter_from_template

        monster_key = getattr(npc, "_monster_key", "skeleton")
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

        # Prefer the full encounter group when the NPC is tagged with a
        # quest encounter; otherwise fall back to a lone monster.
        enc_tag = getattr(npc, "_quest_encounter_name", "")
        enc = create_encounter_from_template(enc_tag) if enc_tag else None
        if enc:
            monsters = enc["monsters"]
            enc_name = enc["name"]
        else:
            monsters = [create_monster(monster_key)]
            enc_name = f"Quest: {npc.name}"

        self.game.sfx.play("encounter")
        terrain_tile = self.game.tile_map.get_tile(
            self.game.party.col, self.game.party.row)
        npc._is_quest_monster_npc = True
        self._building_combat_npc = npc
        self._building_returning_from_combat = True
        # Determine the combat location for quest kill tracking
        int_name = self._overworld_interior_name
        bld_name = self._building_name
        bld_loc = f"space:{bld_name}/{int_name}" \
            if bld_name and int_name and bld_name != int_name \
            else f"building:{bld_name or int_name}"
        combat_state.start_combat(
            fighter, monsters,
            source_state="overworld",
            encounter_name=enc_name,
            terrain_tile=terrain_tile,
            combat_location=bld_loc)
        self.game.change_state("combat")

    def _move_building_interior_npcs(self):
        """Move NPCs inside a building interior (guardians + wanderers)."""
        import random as _rng
        import time as _t

        party = self.game.party
        occupied = {(n.col, n.row) for n in self._building_interior_npcs}
        occupied.add((party.col, party.row))

        from src.town_generator import NPC as _NPCClass
        for npc in self._building_interior_npcs:
            # Random wandering for quest givers and non-guardian NPCs.
            # Quest items, quest monsters (guardians), and stationary
            # types (shopkeep, innkeeper, priest) stay in place.
            wr = getattr(npc, "wander_range", 0)
            stationary = getattr(_NPCClass, "STATIONARY_TYPES", set())
            if wr and npc.npc_type not in stationary and npc.npc_type != "quest_monster":
                if _rng.random() < 0.3:  # 30% chance each move
                    dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
                    _rng.shuffle(dirs)
                    for dc, dr in dirs:
                        nc, nr = npc.col + dc, npc.row + dr
                        if (nc, nr) in occupied:
                            continue
                        if not self.game.tile_map.is_walkable(nc, nr):
                            continue
                        occupied.discard((npc.col, npc.row))
                        npc.col, npc.row = nc, nr
                        occupied.add((nc, nr))
                        break
                continue

            if npc.npc_type != "quest_monster":
                continue

            anchor = getattr(npc, "_guardian_anchor", None)
            if not anchor:
                # Non-guardian quest monsters (e.g. goblins from kill
                # quests) wander randomly so they feel alive instead of
                # standing frozen in place.
                if _rng.random() < 0.3:
                    dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
                    _rng.shuffle(dirs)
                    for dc, dr in dirs:
                        nc, nr = npc.col + dc, npc.row + dr
                        if (nc, nr) in occupied:
                            continue
                        if not self.game.tile_map.is_walkable(nc, nr):
                            continue
                        occupied.discard((npc.col, npc.row))
                        npc.col, npc.row = nc, nr
                        occupied.add((nc, nr))
                        break
                continue

            leash = getattr(npc, "_guardian_leash", GUARDIAN_LEASH)
            ax, ay = anchor
            pcol, prow = party.col, party.row
            dist_party_to_anchor = abs(pcol - ax) + abs(prow - ay)

            # Guardian intercepts when party approaches artifact
            if dist_party_to_anchor <= GUARDIAN_INTERCEPT_RANGE_INTERIOR:
                # Move toward party but stay within leash of anchor
                best = None
                best_dist = abs(npc.col - pcol) + abs(npc.row - prow)
                for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                    nc, nr = npc.col + dc, npc.row + dr
                    if (nc, nr) in occupied and (nc, nr) != (npc.col, npc.row):
                        continue
                    if not self.game.tile_map.is_walkable(nc, nr):
                        continue
                    if abs(nc - ax) + abs(nr - ay) > leash:
                        continue
                    d = abs(nc - pcol) + abs(nr - prow)
                    if d < best_dist:
                        best_dist = d
                        best = (nc, nr)
                if best:
                    occupied.discard((npc.col, npc.row))
                    npc.col, npc.row = best
                    occupied.add(best)
            else:
                # Drift back to anchor if too far
                dist_to_anchor = abs(npc.col - ax) + abs(npc.row - ay)
                if dist_to_anchor > leash:
                    best = None
                    best_d = dist_to_anchor
                    for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                        nc, nr = npc.col + dc, npc.row + dr
                        if (nc, nr) in occupied:
                            continue
                        if not self.game.tile_map.is_walkable(nc, nr):
                            continue
                        d = abs(nc - ax) + abs(nr - ay)
                        if d < best_d:
                            best_d = d
                            best = (nc, nr)
                    if best:
                        occupied.discard((npc.col, npc.row))
                        npc.col, npc.row = best
                        occupied.add(best)

    def _start_building_npc_dialogue(self, npc):
        """Show dialogue for a regular NPC inside a building interior.

        Shows all dialogue lines sequentially; press Enter to advance.
        """
        lines = list(npc.dialogue) if npc.dialogue else ["..."]
        self.ow_npc_dialogue_active = True
        self.ow_npc_speaking = npc
        if len(lines) > 1:
            self.ow_quest_dialogue_lines = lines
            self.ow_quest_dialogue_index = 0
            remaining = len(lines) - 1
            hint = "  [ENTER] >" if remaining > 0 else "  [ENTER]"
            self.show_message(
                f"{npc.name}: {lines[0]}{hint}", 999999)
        else:
            self.ow_quest_dialogue_lines = []
            self.show_message(
                f"{npc.name}: {lines[0]}  [ENTER]", 999999)

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

    # ── Dungeon action screen ─────────────────────────────────

    # ── Town/location action screen ──────────────────────────────

    _TOWN_DESCRIPTIONS = {
        "Thornwall": "A sturdy frontier town nestled against the hills. Merchants, healers, and townsfolk go about their daily lives within its wooden walls.",
    }

    def _find_town_by_name(self, name):
        """Return the TownData whose name matches *name*, or None."""
        for td in self.game.town_data_map.values():
            if getattr(td, "name", None) == name:
                return td
        # Also check the default town_data (hub town)
        if (hasattr(self.game, "town_data")
                and self.game.town_data
                and getattr(self.game.town_data, "name", None) == name):
            return self.game.town_data
        return None

    def _find_module_dungeon_by_name(self, name):
        """Return the dungeon dict from dungeons.json whose name matches, or None."""
        import json, os
        mod_path = getattr(self.game, "active_module_path", "")
        if not mod_path:
            return None
        p = os.path.join(mod_path, "dungeons.json")
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r") as f:
                dungeons = json.load(f)
            if not isinstance(dungeons, list):
                return None
            for d in dungeons:
                if d.get("name") == name:
                    return d
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def _find_module_building_by_name(self, name):
        """Return the building dict from buildings.json whose name matches, or None."""
        import json, os
        mod_path = getattr(self.game, "active_module_path", "")
        if not mod_path:
            return None
        p = os.path.join(mod_path, "buildings.json")
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r") as f:
                buildings = json.load(f)
            if not isinstance(buildings, list):
                return None
            # Exact match first
            for b in buildings:
                if b.get("name") == name:
                    return b
            # Case-insensitive fallback
            name_lower = name.lower()
            for b in buildings:
                if b.get("name", "").lower() == name_lower:
                    return b
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[building lookup] Error reading {p}: {exc}")
        return None

    def _enter_module_dungeon(self, dungeon_def, pcol, prow):
        """Enter a module-defined dungeon (procedural or custom).

        For procedural mode: generates levels using generate_dungeon().
        For custom mode: converts the module's level data to DungeonData.
        """
        from src.dungeon_generator import generate_dungeon, DungeonData
        from src.tile_map import TileMap

        name = dungeon_def.get("name", "Dungeon")
        mode = dungeon_def.get("mode", "procedural")
        style = dungeon_def.get("dungeon_style", "cave")
        levels_data = dungeon_def.get("levels", [])

        dungeon_state = self.game.states["dungeon"]
        cache = self.game.dungeon_cache

        # Check cache first
        cached = cache.get((pcol, prow))
        if cached:
            if isinstance(cached, list) and len(cached) > 1:
                dungeon_state.enter_quest_dungeon(cached, pcol, prow)
            elif isinstance(cached, list) and len(cached) == 1:
                dungeon_state.enter_dungeon(cached[0], pcol, prow)
            else:
                dungeon_state.enter_dungeon(cached, pcol, prow)
            self.game.mark_dungeon_visited(pcol, prow)
            self.game.change_state("dungeon")
            return

        if mode == "procedural":
            # Map dungeon settings to generate_dungeon parameters.
            # Difficulty lives on the dungeon_generator so both call
            # sites (this one and save_load._regenerate_procedural)
            # stay in sync.
            from src.dungeon_generator import get_difficulty_profile
            size_map = {"small": (30, 20), "medium": (40, 30),
                        "large": (60, 40)}
            torch_map = {"none": "none", "sparse": "sparse",
                         "moderate": "medium", "abundant": "dense"}
            sz = size_map.get(
                dungeon_def.get("level_size", "medium"), (40, 30))
            td = torch_map.get(
                dungeon_def.get("torch_density", "moderate"), "medium")
            num_levels = max(1, int(dungeon_def.get("num_levels", 1)))
            doors = dungeon_def.get("locked_doors", "off") == "on"
            difficulty = dungeon_def.get("difficulty", "normal")

            gen_levels = []
            seed_base = hash((name, pcol, prow)) & 0xFFFFFFFF
            for li in range(num_levels):
                lname = f"{name} - Floor {li + 1}" if num_levels > 1 else name
                prof = get_difficulty_profile(difficulty, floor_idx=li)
                dd = generate_dungeon(
                    name=lname, width=sz[0], height=sz[1],
                    min_rooms=prof["min_rooms"],
                    max_rooms=prof["max_rooms"],
                    seed=seed_base + li,
                    place_stairs_down=(li < num_levels - 1),
                    place_overworld_exit=(
                        li == num_levels - 1 and num_levels > 1),
                    place_doors=doors,
                    torch_density=td,
                    encounter_min_level=prof["enc_min"],
                    encounter_max_level=prof["enc_max"],
                    random_encounter_chance=prof["enc_chance"],
                    # Per-monster difficulty tag filter: with this set,
                    # only monsters whose ``difficulty`` field matches
                    # (or is "any"/untagged) will spawn from random
                    # encounters.  Module-defined custom encounters
                    # bypass the filter — author intent always wins.
                    dungeon_difficulty=difficulty,
                    style=style)
                gen_levels.append(dd)

            cache[(pcol, prow)] = gen_levels
            if len(gen_levels) > 1:
                dungeon_state.enter_quest_dungeon(gen_levels, pcol, prow)
            else:
                dungeon_state.enter_dungeon(gen_levels[0], pcol, prow)
        else:
            # Custom mode: convert module level data to DungeonData
            if not levels_data:
                # No levels defined yet — generate a placeholder
                dd = generate_dungeon(name=name)
                cache[(pcol, prow)] = [dd]
                dungeon_state.enter_dungeon(dd, pcol, prow)
            else:
                gen_levels = []
                from src.settings import TILE_DEFS as _TD
                from src.settings import TILE_STAIRS, TILE_STAIRS_DOWN
                from src.settings import TILE_DWALL
                for lv in levels_data:
                    lname = lv.get("name", name)
                    lw = lv.get("width", 20)
                    lh = lv.get("height", 20)
                    ecol = lv.get("entry_col", 0)
                    erow = lv.get("entry_row", 0)
                    # Build a TileMap from sparse tile data.
                    # Default to dungeon wall so unset cells render
                    # as solid walls rather than overworld grass.
                    # oob_tile also walls so camera edge is clean.
                    tmap = TileMap(lw, lh, default_tile=TILE_DWALL,
                                  oob_tile=TILE_DWALL)
                    # Parse tiles and collect designer-placed links
                    for pos_key, td in lv.get("tiles", {}).items():
                        parts = pos_key.split(",")
                        if len(parts) == 2:
                            c, r = int(parts[0]), int(parts[1])
                            tile_id = (td.get("tile_id", 0)
                                       if isinstance(td, dict) else td)
                            if 0 <= c < lw and 0 <= r < lh:
                                tmap.set_tile(c, r, tile_id)

                    # ── Resolve entry point ──
                    # Find a walkable tile if the default isn't walkable.
                    if not _TD.get(tmap.get_tile(ecol, erow),
                                   {}).get("walkable", False):
                        for r in range(lh):
                            for c in range(lw):
                                if _TD.get(tmap.get_tile(c, r),
                                           {}).get("walkable", False):
                                    ecol, erow = c, r
                                    break
                            else:
                                continue
                            break

                    tmap._custom_mode = True

                    dd = DungeonData(
                        tile_map=tmap, rooms=[],
                        entry_col=ecol, entry_row=erow,
                        name=lname)

                    # ── Inject designer-placed encounters ──
                    import random as _rng
                    for enc_spec in lv.get("encounters", []):
                        mon_names = enc_spec.get("monsters", [])
                        if not mon_names:
                            # Legacy format
                            mid = enc_spec.get("monster_id", "")
                            cnt = max(1, int(enc_spec.get("count", 1)))
                            if mid:
                                mon_names = [mid] * cnt
                        if not mon_names:
                            continue
                        lead = mon_names[0]
                        monster = create_monster(lead)
                        placement = enc_spec.get("placement", "procedural")
                        if placement == "manual":
                            monster.col = int(enc_spec.get("col", ecol))
                            monster.row = int(enc_spec.get("row", erow))
                        else:
                            # Procedural: pick a random walkable tile
                            walkable = []
                            for _wr in range(lh):
                                for _wc in range(lw):
                                    if _TD.get(tmap.get_tile(_wc, _wr),
                                               {}).get("walkable", False):
                                        walkable.append((_wc, _wr))
                            if walkable:
                                mc, mr = _rng.choice(walkable)
                                monster.col, monster.row = mc, mr
                            else:
                                monster.col, monster.row = ecol, erow
                        ename = enc_spec.get("name", f"Encounter")
                        monster.encounter_template = {
                            "name": ename,
                            "monster_names": mon_names,
                            "monster_party_tile": lead,
                        }
                        dd.monsters.append(monster)

                    gen_levels.append(dd)
                cache[(pcol, prow)] = gen_levels
                if len(gen_levels) > 1:
                    dungeon_state.enter_quest_dungeon(
                        gen_levels, pcol, prow)
                else:
                    dungeon_state.enter_dungeon(
                        gen_levels[0], pcol, prow)

        self.game.mark_dungeon_visited(pcol, prow)
        self.game.change_state("dungeon")

    # ── Tile link system (universal) ─────────────────────────────

    def _get_interior_tile_props(self, col, row):
        """Return tile instance properties for (col, row) in the current
        interior map (building space, etc.).

        Reads directly from the active tile map's tile_properties,
        which is populated when the interior is entered.
        """
        props = getattr(self.game.tile_map, 'tile_properties', {})
        return props.get(f"{col},{row}", {})

    def _get_overworld_tile_props(self, col, row):
        """Return tile instance properties for (col, row) on the overworld.

        Reads from the tile_map's tile_properties dict (loaded from
        overview_map.json at startup).
        Returns empty dict if no properties are set.
        """
        props = getattr(self.game.tile_map, 'tile_properties', {})
        return props.get(f"{col},{row}", {})

    def _follow_tile_link(self, tile_props, pcol, prow, direct=False):
        """Follow a tile link to its target map and position.

        Simple dispatch: resolve the target map, switch to the right
        game state, place the party at the link's X/Y coordinates.

        If *direct* is False (overworld), shows an action screen for
        towns/dungeons.  If True (from inside a building/town), enters
        immediately.
        """
        link_map = tile_props.get("link_map", "")
        link_x = int(tile_props.get("link_x", 0))
        link_y = int(tile_props.get("link_y", 0))

        if not link_map:
            return

        # ── Overworld ──
        if link_map == "overworld":
            if link_x or link_y:
                self.game.party.col = link_x
                self.game.party.row = link_y
            self.game.camera.map_width = self.game.tile_map.width
            self.game.camera.map_height = self.game.tile_map.height
            self.game.camera.update(
                self.game.party.col, self.game.party.row)
            self._exit_grace = True
            return

        # ── Town ──
        if link_map.startswith("town:"):
            town_name = link_map[5:]
            td = self._find_town_by_name(town_name)
            if not td:
                return
            if (pcol, prow) not in self.game.town_data_map:
                self.game.town_data_map[(pcol, prow)] = td
            target_pos = (link_x, link_y) if (link_x or link_y) else None
            if direct:
                self._enter_town_direct(td, pcol, prow, target_pos)
            else:
                self._pending_link_target_pos = target_pos
                self._show_town_action()
            return

        # ── Town interior ──
        if link_map.startswith("interior:"):
            remainder = link_map[9:]
            town_name, interior_name = (remainder.split("/", 1)
                                        if "/" in remainder
                                        else ("", remainder))
            td = self._find_town_by_name(town_name) if town_name else None
            if not td:
                return
            if (pcol, prow) not in self.game.town_data_map:
                self.game.town_data_map[(pcol, prow)] = td
            target_pos = (link_x, link_y) if (link_x or link_y) else None
            self._enter_town_direct(td, pcol, prow, target_pos=None,
                                    auto_interior=interior_name,
                                    interior_pos=target_pos)
            return

        # ── Building / building space ──
        if link_map.startswith("building:"):
            parts = link_map[9:].split(":", 1)
            bldg_name = parts[0]
            sub_space = parts[1] if len(parts) > 1 else ""
            building_def = self._find_module_building_by_name(bldg_name)
            if not building_def or not building_def.get("spaces"):
                return
            if link_x or link_y:
                self._pending_link_target_pos = (link_x, link_y)
            if direct:
                self.building_action_entry_args = {
                    "building_def": building_def,
                    "col": pcol, "row": prow,
                    "sub_interior": sub_space,
                }
                self._enter_building_confirmed()
            else:
                self.building_action_info = {
                    "name": bldg_name,
                    "description": building_def.get("description", ""),
                }
                self.building_action_entry_args = {
                    "building_def": building_def,
                    "col": pcol, "row": prow,
                    "sub_interior": sub_space,
                }
                self.building_action_cursor = 0
                self.building_action_active = True
            return

        # ── Dungeon ──
        if link_map.startswith("dungeon:"):
            parts = link_map[8:].split(":", 1)
            dung_name = parts[0]
            dungeon_def = self._find_module_dungeon_by_name(dung_name)
            if not dungeon_def:
                return
            if direct:
                def _do():
                    self._enter_module_dungeon(dungeon_def, pcol, prow)
                self.game.start_loading_screen(
                    f"Entering {dung_name}", _do)
            else:
                self.dungeon_action_info = {
                    "name": dung_name,
                    "description": dungeon_def.get("description", ""),
                    "visited": self.game.is_dungeon_visited(pcol, prow),
                    "dungeon_def": dungeon_def,
                }
                self.dungeon_action_entry_args = {
                    "type": "module_dungeon",
                    "dungeon_def": dungeon_def,
                    "col": pcol, "row": prow,
                }
                self.dungeon_action_cursor = 0
                self.dungeon_action_active = True
            return

    def _enter_town_direct(self, td, pcol, prow, target_pos=None,
                           auto_interior=None, interior_pos=None):
        """Enter a town directly (no action screen).

        Places the party at *target_pos* in the town, or at the
        town's default entry point.  If *auto_interior* is set,
        immediately enters that interior and places the party at
        *interior_pos*.
        """
        self.game.town_data = td
        if (pcol, prow) not in self.game.town_data_map:
            self.game.town_data_map[(pcol, prow)] = td
        town_name = getattr(td, "name", "Town")

        def _do():
            ts = self.game.states["town"]
            if interior_pos:
                ts._pending_interior_target_pos = interior_pos
            ts.enter_town(td, pcol, prow,
                          target_pos=target_pos,
                          auto_interior=auto_interior)
            self.game.change_state("town")

        self.game.start_loading_screen(f"Entering {town_name}", _do)

    def _show_town_action(self):
        """Show the town entry action screen."""
        pcol, prow = self.game.party.col, self.game.party.row
        town_data = self.game.get_town_at(pcol, prow)
        name = town_data.name if town_data else "Town"
        # Use the user-defined description from TownData if available,
        # then fall back to hardcoded descriptions, then generic text.
        custom_desc = getattr(town_data, "description", "") if town_data else ""
        if custom_desc:
            desc = custom_desc
        else:
            desc = self._TOWN_DESCRIPTIONS.get(name,
                f"The town of {name} rises from the landscape. "
                "Smoke drifts from chimneys and voices carry on the wind.")

        self.town_action_info = {
            "name": name,
            "description": desc,
        }
        self.town_action_cursor = 0
        self.town_action_active = True

    def _handle_town_action_input(self, event):
        """Handle input for the town entry action screen."""
        if event.key in (pygame.K_UP, pygame.K_w):
            self.town_action_cursor = (self.town_action_cursor - 1) % 2
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.town_action_cursor = (self.town_action_cursor + 1) % 2
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.town_action_cursor == 0:
                self._enter_town_confirmed()
            else:
                self.town_action_active = False
        elif event.key == pygame.K_ESCAPE:
            self.town_action_active = False

    def _enter_town_confirmed(self):
        """Execute the actual town entry after the player confirms."""
        self.town_action_active = False
        pcol, prow = self.game.party.col, self.game.party.row
        town_data = self.game.get_town_at(pcol, prow)
        # Update game.town_data to the town being entered (for
        # downstream code that reads it, like victory messages)
        self.game.town_data = town_data

        # Use stashed target position from tile link if available
        _target_pos = getattr(self, '_pending_link_target_pos', None)
        self._pending_link_target_pos = None

        town_name = getattr(town_data, "name", None) or "Town"

        def _do_enter():
            town_state = self.game.states["town"]
            town_state.enter_town(town_data, pcol, prow,
                                  auto_interior=None,
                                  target_pos=_target_pos,
                                  preserve_exit=False)
            self.game.change_state("town")

        self.game.start_loading_screen(f"Entering {town_name}", _do_enter)

    # ── Dungeon action screen ─────────────────────────────────

    def _show_dungeon_action(self, pcol, prow):
        """Show the dungeon entry action screen instead of entering immediately."""
        visited = self.game.is_dungeon_visited(pcol, prow)
        cleared = False

        # Determine dungeon type and build info
        kd = self.game.get_key_dungeon(pcol, prow)
        quest = self.game.get_quest()
        hq = self.game.get_house_quest()

        if kd:
            if kd["status"] == "undiscovered":
                # Player hasn't accepted this quest yet — show a
                # generic name and description so quest details
                # aren't revealed prematurely.
                name = "Unknown Cave"
                desc = (
                    "A dark cave entrance leads deep underground. "
                    "The air smells of ancient stone and danger."
                )
                quest_name = None
                entry_type = "key_dungeon"
            elif kd["status"] == "completed":
                name = kd.get("name", "Key Dungeon")
                desc = kd.get("description") or (
                    "A dark cave entrance leads deep underground. "
                    "The air smells of ancient stone and danger."
                )
                cleared = True
                quest_name = f"{kd.get('key_name', 'Key')} (completed)"
                entry_type = "key_dungeon"
            else:
                name = kd.get("name", "Key Dungeon")
                # Use the dungeon's unique description if available
                desc = kd.get("description") or (
                    "A dark cave entrance leads deep underground. "
                    "The air smells of ancient stone and danger."
                )
                # Use the dungeon's unique quest objective if available
                quest_name = kd.get("quest_objective") or (
                    f"Retrieve the {kd.get('key_name', 'Key')}"
                )
                entry_type = "key_dungeon"
        elif (quest
                and pcol == quest.get("dungeon_col")
                and prow == quest.get("dungeon_row")):
            artifact = quest.get("artifact_name", "Shadow Crystal")
            name = quest.get("name", "The Shadow Crystal")
            desc = f"A foreboding passage descends into darkness. Somewhere below lies the {artifact}."
            if quest["status"] == "completed":
                cleared = True
                quest_name = f"{name} (completed)"
            else:
                quest_name = name
            entry_type = "quest"
        elif (hq
                and pcol == hq.get("dungeon_col")
                and prow == hq.get("dungeon_row")):
            name = "Elara's House"
            desc = "The old house sits quietly. The family heirloom is said to be hidden inside."
            if hq.get("status") == "completed":
                cleared = True
                quest_name = "Family Heirloom (completed)"
            else:
                quest_name = "Retrieve the Family Heirloom"
            entry_type = "house_quest"
        else:
            name = "The Depths"
            desc = "A yawning cave entrance beckons. Who knows what lurks in the darkness below."
            quest_name = None
            entry_type = "random"
            # A cleared random dungeon (TILE_DUNGEON_CLEARED with no quest)
            tile_id = self.game.tile_map.get_tile(pcol, prow)
            if tile_id == TILE_DUNGEON_CLEARED:
                cleared = True

        self.dungeon_action_info = {
            "name": name,
            "description": desc,
            "visited": visited,
            "cleared": cleared,
            "quest_name": quest_name,
        }
        self.dungeon_action_entry_args = {
            "type": entry_type,
            "col": pcol,
            "row": prow,
        }
        self.dungeon_action_cursor = 0
        self.dungeon_action_active = True

    def _handle_dungeon_action_input(self, event):
        """Handle input for the dungeon entry action screen."""
        if event.key in (pygame.K_UP, pygame.K_w):
            self.dungeon_action_cursor = (self.dungeon_action_cursor - 1) % 2
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.dungeon_action_cursor = (self.dungeon_action_cursor + 1) % 2
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.dungeon_action_cursor == 0:
                self._enter_dungeon_confirmed()
            else:
                self.dungeon_action_active = False
                self._exit_grace = True
        elif event.key == pygame.K_ESCAPE:
            self.dungeon_action_active = False
            self._exit_grace = True

    def _enter_dungeon_confirmed(self):
        """Execute the actual dungeon entry after the player confirms.

        Dungeons are persistent — once generated, their state (explored
        tiles, opened chests, triggered traps, killed monsters) is kept
        in ``game.dungeon_cache`` and reused on re-entry.
        """
        args = self.dungeon_action_entry_args
        if not args:
            self.dungeon_action_active = False
            return

        pcol, prow = args["col"], args["row"]
        entry_type = args["type"]
        dungeon_name = self.dungeon_action_info.get("name", "Dungeon")

        # For module dungeons, handle specially (they have their own
        # state-change logic inside _enter_module_dungeon).
        if entry_type == "module_dungeon":
            dungeon_def = args.get("dungeon_def")
            if dungeon_def:
                self.dungeon_action_active = False

                def _do_enter_module():
                    self._enter_module_dungeon(dungeon_def, pcol, prow)

                self.game.start_loading_screen(
                    f"Entering {dungeon_name}", _do_enter_module)
            else:
                self.dungeon_action_active = False
            return

        def _do_enter():
            dungeon_state = self.game.states["dungeon"]
            cache = self.game.dungeon_cache

            # Mark as visited
            self.game.mark_dungeon_visited(pcol, prow)

            if entry_type == "key_dungeon":
                kd = self.game.get_key_dungeon(pcol, prow)
                if kd:
                    if kd["status"] == "undiscovered":
                        for i, level in enumerate(kd["levels"]):
                            level.name = f"Unknown Cave - Floor {i + 1}"
                    dungeon_state.enter_quest_dungeon(kd["levels"], pcol, prow)
            elif entry_type == "quest":
                quest = self.game.get_quest()
                if quest:
                    dungeon_state.enter_quest_dungeon(quest["levels"], pcol, prow)
            elif entry_type == "house_quest":
                hq = self.game.get_house_quest()
                if hq:
                    dungeon_state.enter_quest_dungeon(hq["levels"], pcol, prow)
            else:
                cached = cache.get((pcol, prow))
                if cached:
                    dungeon_data = cached[0]
                else:
                    dungeon_data = generate_dungeon("The Depths")
                    cache[(pcol, prow)] = [dungeon_data]
                dungeon_state.enter_dungeon(dungeon_data, pcol, prow)

            self.game.change_state("dungeon")

        self.dungeon_action_active = False
        self.game.start_loading_screen(f"Entering {dungeon_name}", _do_enter)

    # ── Building action screen ─────────────────────────────────

    def _handle_building_action_input(self, event):
        """Handle input for the building entry action screen."""
        if event.key in (pygame.K_UP, pygame.K_w):
            self.building_action_cursor = (self.building_action_cursor - 1) % 2
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.building_action_cursor = (self.building_action_cursor + 1) % 2
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.building_action_cursor == 0:
                self._enter_building_confirmed()
            else:
                self.building_action_active = False
                self._exit_grace = True
        elif event.key == pygame.K_ESCAPE:
            self.building_action_active = False
            self._exit_grace = True

    def _enter_building_confirmed(self):
        """Execute the actual building entry after the player confirms."""
        self.building_action_active = False
        args = self.building_action_entry_args
        self.building_action_entry_args = {}
        if not args:
            return

        building_def = args["building_def"]
        pcol, prow = args["col"], args["row"]

        # Re-read building from disk to pick up any editor changes
        bname = building_def.get("name", "")
        fresh = self._find_module_building_by_name(bname)
        if fresh is not None:
            building_def = fresh

        spaces = building_def.get("spaces", [])
        if not spaces:
            return

        tmap = self.game.tile_map
        src_tmap = self._stashed_overworld_tile_map or tmap
        interiors = getattr(src_tmap, "overworld_interiors", [])

        # Always update building spaces with the latest data from
        # buildings.json so edits (e.g. adding a door) take effect
        # without needing a full restart.
        for sp in spaces:
            sp_name = sp.get("name", "")
            if not sp_name:
                continue
            new_entry = {
                "name": sp_name,
                "width": sp.get("width", 20),
                "height": sp.get("height", 20),
                "entry_col": sp.get("entry_col", 0),
                "entry_row": sp.get("entry_row", 0),
                "tiles": sp.get("tiles", {}),
                "npcs": sp.get("npcs", []),
                "tile_properties": sp.get("tile_properties", {}),
            }
            # Replace existing entry or append new one
            replaced = False
            for i, existing in enumerate(interiors):
                if existing.get("name") == sp_name:
                    interiors[i] = new_entry
                    replaced = True
                    break
            if not replaced:
                interiors.append(new_entry)
        src_tmap.overworld_interiors = interiors
        # Use the sub_interior if specified, otherwise default to
        # the first space in the building.
        sub = args.get("sub_interior", "")
        if sub:
            # Find the matching space by name
            entrance_name = sub
        else:
            entrance_name = spaces[0].get("name",
                                          building_def.get("name", ""))
        bldg_name = building_def.get("name", "")
        self._enter_overworld_interior(entrance_name, pcol, prow,
                                       building_name=bldg_name)

    def _activate_house_quest(self):
        """Activate the house quest when the party speaks to Elara."""
        hq = self.game.get_house_quest()
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
        self.game.set_house_quest({
            "name": "Family Heirloom",
            "status": "active",
            "dungeon_col": house_col,
            "dungeon_row": house_row,
            "levels": levels,
            "current_level": 0,
            "artifact_name": "Family Heirloom",
        })

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

        self.game.get_house_quest()["status"] = "completed"
        self.game.game_log.append(
            f"Quest complete! Elara rewards the party with {reward_gold} gold."
        )

    # ── Spawn point action screen ──────────────────────────────

    def _show_spawn_action(self, pcol, prow, tile_id):
        """Show the spawn point action screen."""
        from src.party import SPAWN_POINTS
        sp = SPAWN_POINTS.get(tile_id, {})
        self.spawn_action_info = {
            "name": sp.get("name", "Monster Lair"),
            "description": sp.get("description", "A creature's lair. Something dangerous lurks within."),
            "tile_id": tile_id,
        }
        self.spawn_action_pos = (pcol, prow)
        self.spawn_action_cursor = 0
        self.spawn_action_active = True

    def _handle_spawn_action_input(self, event):
        """Handle input for the spawn entry action screen."""
        if event.key in (pygame.K_UP, pygame.K_w):
            self.spawn_action_cursor = (self.spawn_action_cursor - 1) % 2
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.spawn_action_cursor = (self.spawn_action_cursor + 1) % 2
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.spawn_action_cursor == 0:
                self._enter_spawn_confirmed()
            else:
                self.spawn_action_active = False
                self._exit_grace = True
        elif event.key == pygame.K_ESCAPE:
            self.spawn_action_active = False
            self._exit_grace = True

    def _enter_spawn_confirmed(self):
        """Enter the monster spawn — trigger boss fight."""
        from src.party import SPAWN_POINTS
        from src.monster import create_monster

        tile_id = self.spawn_action_info.get("tile_id")
        sp = SPAWN_POINTS.get(tile_id, {})

        # Support new boss_monsters list with fallback to old boss_monster string
        boss_names = list(sp.get("boss_monsters", []))
        if not boss_names:
            old_boss = sp.get("boss_monster", "")
            if old_boss:
                boss_names = [old_boss]
        if not boss_names:
            # No boss defined — just close
            self.spawn_action_active = False
            self._exit_grace = True
            self.message = "The lair is empty."
            self.message_timer = 2000
            return

        # Create all boss monsters
        bosses = []
        for bname in boss_names:
            try:
                b = create_monster(bname)
                bosses.append(b)
            except Exception:
                pass
        if not bosses:
            self.spawn_action_active = False
            self._exit_grace = True
            return

        pcol, prow = self.spawn_action_pos
        for b in bosses:
            b.col = pcol
            b.row = prow

        # Find first alive fighter
        fighter = None
        for member in self.game.party.members:
            if member.is_alive():
                fighter = member
                break
        if not fighter:
            self.spawn_action_active = False
            return

        self.spawn_action_active = False
        self.game.sfx.play("encounter")

        # Store spawn info so we can destroy it on victory
        terrain_tile = self.game.tile_map.get_tile(pcol, prow)

        # Mark the first boss as the spawn boss sentinel for reward tracking
        bosses[0].is_spawn_boss = True
        bosses[0].spawn_tile_pos = (pcol, prow)
        bosses[0].spawn_tile_id = tile_id

        enc_label = ", ".join(boss_names)
        combat = self.game.states.get("combat")
        combat.start_combat(
            fighter, bosses,
            source_state="overworld",
            encounter_name=f"Boss: {enc_label}",
            map_monster_refs=[],
            terrain_tile=terrain_tile,
            combat_location="overview")
        self.game.change_state("combat")

    # ── Chest loot ─────────────────────────────────────────────

    def _open_chest(self):
        """Roll random loot from a chest: gold, an item, or both."""
        from src import data_registry as DR
        self.game.sfx.play("treasure")
        gold = random.randint(5, 30)
        self.game.party.gold += gold

        loot_table = DR.chest_loot()
        total_weight = sum(w for _, w in loot_table)
        roll = random.randint(1, total_weight)
        cumulative = 0
        chosen_item = None
        for item, weight in loot_table:
            cumulative += weight
            if roll <= cumulative:
                chosen_item = item
                break

        if chosen_item:
            self.game.party.inv_add(chosen_item)
            self.show_message(
                f"The party opened a treasure chest and found {gold} gold and {chosen_item}.", 2500)
        else:
            self.show_message(
                f"The party opened a treasure chest and found {gold} gold.", 2000)

    def update(self, dt):
        """Update timers."""
        # Check for pending spawn point destructions
        if hasattr(self.game, 'pending_spawn_destroys') and self.game.pending_spawn_destroys:
            for destroy in self.game.pending_spawn_destroys:
                pos = destroy['pos']
                self.destroyed_spawns.add(pos)
                # Replace spawn tile with grass
                self.game.tile_map.set_tile(pos[0], pos[1], TILE_GRASS)
            self.game.pending_spawn_destroys = []

        # Tick spawn effects
        for eff in self._spawn_effects:
            eff["timer"] -= dt
        self._spawn_effects = [e for e in self._spawn_effects
                               if e["timer"] > 0]

        dt_ms = dt * 1000  # convert seconds to ms

        # Pick-lock unlock animation (shared mixin).
        self._tick_lock_animation(dt_ms)

        # Tick encounter result display timer
        if self.encounter_result_timer > 0:
            self.encounter_result_timer -= dt_ms

        if self.message_timer > 0:
            self.message_timer -= dt_ms
            if self.message_timer <= 0:
                self.message = ""
                self.message_timer = 0

        if self.move_cooldown > 0:
            self.move_cooldown -= dt_ms
            if self.move_cooldown < 0:
                self.move_cooldown = 0

        # Tick boat sail animation while the party is aboard.
        # Flips the frame index every 350ms so the renderer can draw
        # a subtle bob/shift on the boat sprite.
        if getattr(self.game, "on_boat", False):
            self.game.boat_anim_accum += dt_ms
            if self.game.boat_anim_accum >= 350:
                self.game.boat_anim_accum = 0
                self.game.boat_anim_frame = 1 - self.game.boat_anim_frame

        # Tick use-item animation
        if self.use_item_anim and self.use_item_anim["timer"] > 0:
            self.use_item_anim["timer"] -= dt_ms
            if self.use_item_anim["timer"] <= 0:
                self.use_item_anim = None

        # Tick level-up animations
        self._update_level_up_queue(dt_ms)

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

        # Tick quest visual effects
        if self.quest_effects:
            for fx in self.quest_effects:
                fx["timer"] -= dt_ms
            self.quest_effects = [
                fx for fx in self.quest_effects if fx["timer"] > 0]

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
                brew_available=bool(self._has_alchemist()),
                tinker_available=self._can_tinker(),
                showing_tinker_list=self.showing_tinker_list,
                tinker_list_items=self.tinker_list_items,
                tinker_list_cursor=self.tinker_list_cursor,
                applying_poison_step=self.applying_poison_step,
                applying_poison_cursor=self.applying_poison_cursor,
                applying_poison_item=self.applying_poison_item,
                applying_poison_member=getattr(self, '_applying_poison_member', None))
            if self.use_item_anim:
                renderer.draw_use_item_animation(self.game.party, self.use_item_anim)
            if self.examining_item:
                renderer.draw_item_examine(self.examining_item, getattr(self, 'examining_durability', None))
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
                renderer.draw_item_examine(self.examining_item, getattr(self, 'examining_durability', None))
            return
        if self.showing_party:
            renderer.draw_party_screen_u3(self.game.party)
            return
        # Sync quest status onto NPC objects for renderer
        if self._in_overworld_interior:
            # Inside a building: only show building interior NPCs,
            # not overworld quest NPCs (whose coordinates are for the
            # overworld map and would appear at wrong positions).
            ow_npcs = list(self._building_interior_npcs)
        else:
            ow_npcs = getattr(self.game, "overworld_quest_npcs", [])
        mq_states = getattr(self.game, "module_quest_states", {})
        for npc in ow_npcs:
            mqn = getattr(npc, "_module_quest_name", "")
            npc._quest_status = mq_states.get(mqn, {}).get(
                "status", "available")

        # Building interior lighting — same model as town interiors.
        # Outside a building the flag is False and no visibility sets
        # are computed, so the overworld still follows normal outdoor
        # day/night rules. See src/states/town.py for the matching
        # block and src/interior_lighting.py for the algorithm.
        _ow_int = getattr(self, "_in_overworld_interior", False)
        _vis_tiles = None
        _exp_tiles = None
        if _ow_int:
            try:
                from src.interior_lighting import (
                    compute_visible_tiles, party_has_light,
                )
                tmap = self.game.tile_map
                if not hasattr(tmap, "_interior_light_cache"):
                    tmap._interior_light_cache = {}
                if not hasattr(tmap, "explored_tiles"):
                    tmap.explored_tiles = set()
                pcol = self.game.party.col
                prow = self.game.party.row
                _vis_tiles, tmap._interior_light_cache = compute_visible_tiles(
                    tmap, pcol, prow,
                    has_party_light=party_has_light(self.game.party),
                    light_cache=tmap._interior_light_cache,
                )
                # Safety + diagnostic — see src/states/town.py for
                # rationale.  If something's wrong, fall back to
                # fully lit rather than lock the player out.
                if (pcol, prow) not in _vis_tiles:
                    if not getattr(self, "_ow_int_fog_warned", False):
                        import sys
                        print(
                            f"[ow-interior-fog] WARNING: party "
                            f"({pcol},{prow}) not in visible set "
                            f"({len(_vis_tiles)} tiles). tile_map="
                            f"{tmap.width}x{tmap.height}. Disabling "
                            f"fog for this frame.",
                            file=sys.stderr,
                        )
                        self._ow_int_fog_warned = True
                    _vis_tiles = None
                    _exp_tiles = None
                else:
                    tmap.explored_tiles.update(_vis_tiles)
                    _exp_tiles = tmap.explored_tiles
            except Exception as e:
                if not getattr(self, "_ow_int_fog_warned", False):
                    import sys, traceback
                    print(f"[ow-interior-fog] ERROR: {e}", file=sys.stderr)
                    traceback.print_exc()
                    self._ow_int_fog_warned = True
                _vis_tiles = None
                _exp_tiles = None

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
            overworld_npcs=ow_npcs,
            quest_effects=self.quest_effects,
            interior_darkness=_ow_int,
            visible_tiles=_vis_tiles,
            explored_tiles=_exp_tiles,
            spawn_effects=self._spawn_effects,
        )
        # ── Overworld NPC quest choice overlay ──
        if self.ow_quest_choice_active:
            renderer.draw_ow_quest_choice(
                self.ow_quest_choices, self.ow_quest_choice_cursor)
        if self.town_action_active:
            renderer.draw_town_action_screen(
                self.town_action_info, self.town_action_cursor)
        if self.dungeon_action_active:
            renderer.draw_dungeon_action_screen(
                self.dungeon_action_info, self.dungeon_action_cursor)
        if self.building_action_active:
            renderer.draw_building_action_screen(
                self.building_action_info, self.building_action_cursor)
        if self.spawn_action_active:
            renderer.draw_spawn_action_screen(
                self.spawn_action_info, self.spawn_action_cursor)
        if self.encounter_action_active:
            renderer.draw_encounter_action_screen(
                self.encounter_action_monster,
                self.encounter_action_cursor,
                self.encounter_action_result)
        # Pick-lock dialog overlay — lock on any painted tile
        # (overworld or inside an overworld building interior).
        # The unlock animation is drawn separately because the dialog
        # closes *before* the animation plays (see
        # LockInteractionMixin._attempt_lock_pick).
        interact = self._get_door_interact_state()
        anim = self.door_unlock_anim
        if interact or anim:
            tile_map = self.game.tile_map
            ts = renderer._U3_OW_TS
            cols = renderer._U3_OW_COLS
            rows = renderer._U3_OW_ROWS
            off_c = max(0, min(self.game.party.col - cols // 2,
                               max(0, tile_map.width - cols)))
            off_r = max(0, min(self.game.party.row - rows // 2,
                               max(0, tile_map.height - rows)))
            if anim:
                renderer._u3_draw_door_unlock_anim(
                    anim, off_c, off_r, cols, rows, ts)
            if interact:
                renderer._u3_draw_door_interact(
                    interact, off_c, off_r, ts)
        if self.level_up_queue:
            renderer.draw_level_up_animation(self.level_up_queue[0])
        if self.quest_step_queue:
            renderer.draw_quest_step_animation(self.quest_step_queue[0])
        if self.showing_help:
            renderer.draw_overworld_help_overlay()
        if self.showing_log:
            renderer.draw_log_overlay(self.game.game_log, self.log_scroll)
