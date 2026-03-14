"""
Main Game class - the heart of the application.

Manages the game loop, state machine, and top-level resources.
"""

import os
import random
import pygame

from src.settings import SCREEN_WIDTH, SCREEN_HEIGHT, FPS, GAME_TITLE, COLOR_BLACK
from src.tile_map import create_test_map
from src.party import (create_default_party, _load_party_config,
                       save_roster, PartyMember, Party,
                       VALID_RACES, RACE_INFO)
from src.camera import Camera
from src.renderer import Renderer
from src.states.overworld import OverworldState
from src.states.town import TownState
from src.states.dungeon import DungeonState
from src.states.combat import CombatState
from src.states.examine import ExamineState
from src.town_generator import generate_town, generate_duskhollow
from src.music import MusicManager, SoundEffects, SOUNDTRACK_STYLES
from src.save_load import (save_game, load_game, get_save_info,
                           delete_save,
                           NUM_SAVE_SLOTS, load_config, save_config)
from src.module_loader import load_module_data


class Game:
    """
    Top-level game object.

    Owns the pygame display, clock, and manages the game state machine.
    """

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(GAME_TITLE)
        pygame.display.set_icon(self._generate_window_icon())
        self.clock = pygame.time.Clock()
        self.running = True

        # --- Create game world ---
        self.tile_map = create_test_map()

        # Party start position is defined in data/party.json
        self.party = create_default_party()

        # Camera follows the party
        self.camera = Camera(self.tile_map.width, self.tile_map.height)
        self.camera.update(self.party.col, self.party.row)

        # Renderer
        self.renderer = Renderer(self.screen)

        # --- Town data ---
        # Pre-generate the town so it persists across visits
        self.town_data = generate_town("Thornwall")  # default / current town
        self.town_data_map = {}  # {(col, row): TownData} for multi-town modules

        # --- Quest state ---
        # None when no quest active; dict when quest is in progress
        self.quest = None
        self.house_quest = None
        self._gnome_quest_accepted = False
        self.key_dungeons = {}
        self.keys_inserted = 0
        self.visited_dungeons = set()
        self.dungeon_cache = {}
        self.machine_col = None
        self.machine_row = None
        self.pending_combat_rewards = None
        self.pending_killed_monsters = []
        self.examined_tiles = {}

        # --- Darkness effect (Keys of Shadow module) ---
        self.darkness_active = False

        # --- Game log ---
        # Accumulates all messages from every state for the log overlay
        self.game_log = []

        # --- Load persistent player config ---
        self._config = load_config()
        self.smite_enabled = self._config.get("smite_enabled", False)
        self.start_with_equipment = self._config.get("start_with_equipment", True)

        # --- Music & Sound Effects ---
        saved_style = self._config.get("soundtrack_style", "Classic")
        if saved_style not in SOUNDTRACK_STYLES:
            saved_style = "Classic"
        self.music = MusicManager(style=saved_style)
        self.sfx = SoundEffects()
        if not self._config.get("music_enabled", True):
            self.music.toggle_mute()   # start muted if saved that way

        # --- Game-in-progress flag ---
        # True once the player has started or loaded a game.
        self._game_started = False

        # --- Title screen ---
        self.showing_title = True
        self.title_cursor = 0
        self.title_elapsed = 0.0        # for animations
        self._title_options_base = [
            {"label": "START NEW GAME", "action": self._title_new_game},
            {"label": "FORM PARTY", "action": self._title_form_party},
            {"label": "SAVE GAME", "action": self._title_save_game},
            {"label": "LOAD GAME", "action": self._title_load_game},
            {"label": "MODULES", "action": self._title_modules},
            {"label": "SETTINGS", "action": self._title_settings},
            {"label": "QUIT GAME", "action": self._title_quit},
        ]

        # --- Module selection screen ---
        self.showing_modules = False
        self.module_cursor = 0
        self.module_list = []  # populated when screen opens
        self.module_message = None           # feedback message
        self.module_msg_timer = 0.0          # seconds remaining
        self.module_confirm_delete = False   # Y/N delete confirmation
        self.module_edit_mode = False        # editing module metadata
        self.module_edit_is_new = False      # True = creating new module
        self.module_edit_field = 0           # active field index
        self.module_edit_buffer = ""         # text being typed
        self.module_edit_fields = []         # [label, key, value, type, editable]
        self.module_edit_scroll = 0          # scroll offset for long field lists
        # ── Hierarchical navigation (edit existing modules) ──
        self.module_edit_level = 0           # 0=section browser, 1=field editor
        self.module_edit_sections = []       # list of section dicts
        self.module_edit_section_cursor = 0  # highlighted section
        self.module_edit_section_scroll = 0  # scroll for section list
        # Navigation stack for nested section browsing (dungeon sub-sections)
        self.module_edit_nav_stack = []      # [(sections, cursor, scroll)]
        self.module_edit_dungeon_levels = {} # {dungeon_idx: [level_data]}
        self.module_edit_active_dung = -1    # which dungeon index is active
        self.module_edit_active_level = -1   # which level index (-1=props)
        self.module_edit_starting_loot = []  # [{item, count}]
        self.module_edit_in_loot = False     # True when editing loot fields
        from src.module_loader import get_default_module_path, scan_modules
        self.active_module_path = None
        self.active_module_name = "No Module"
        self.active_module_version = "0.0.0"
        self.module_manifest = None  # populated on new game start

        # Restore last-used module from config (if it still exists)
        saved_mod_path = self._config.get("active_module_path")
        if saved_mod_path and os.path.isdir(saved_mod_path):
            manifest_file = os.path.join(saved_mod_path, "module.json")
            if os.path.isfile(manifest_file):
                try:
                    import json as _json
                    with open(manifest_file, "r") as _f:
                        _manifest = _json.load(_f)
                    meta = _manifest.get("metadata", {})
                    self.active_module_path = saved_mod_path
                    self.active_module_name = meta.get(
                        "name", "Unknown Module")
                    self.active_module_version = meta.get(
                        "version", "1.0.0")
                except (OSError, ValueError):
                    pass  # fall through to default

        # If no valid saved module, pick the first available one
        if not self.active_module_path:
            default_path = get_default_module_path()
            if default_path:
                manifest_file = os.path.join(default_path, "module.json")
                try:
                    import json as _json
                    with open(manifest_file, "r") as _f:
                        _manifest = _json.load(_f)
                    meta = _manifest.get("metadata", {})
                    self.active_module_path = default_path
                    self.active_module_name = meta.get(
                        "name", "Unknown Module")
                    self.active_module_version = meta.get(
                        "version", "0.0.0")
                except (OSError, ValueError):
                    pass

        # --- Character creation screen ---
        self.showing_char_create = False
        self._cc_init()

        # --- Party formation screen ---
        self.showing_form_party = False
        self._fp_return_to_form_party = False
        self._fp_init()

        # --- Settings screen ---
        self.showing_settings = False
        self.settings_cursor = 0
        self.settings_mode = "main"      # "main", "save", "load"
        self.save_load_cursor = 0        # cursor within save/load slot list
        self.save_load_message = None    # feedback message ("Saved!", "Loaded!", etc.)
        self.save_load_msg_timer = 0.0   # seconds remaining for message display
        self.save_load_confirm_delete = False  # True while confirming a delete
        self.settings_options = [
            {"label": "MUSIC",
             "value": self._config.get("music_enabled", True),
             "type": "toggle", "action": self._toggle_music},
            {"label": "SOUNDTRACK",
             "value": self.music.style,
             "choices": SOUNDTRACK_STYLES,
             "type": "choice", "action": self._cycle_soundtrack},
            {"label": "SMITE (DEBUG)",
             "value": self._config.get("smite_enabled", False),
             "type": "toggle", "action": self._toggle_smite},
            {"label": "START WITH EQUIPMENT",
             "value": self._config.get("start_with_equipment", True),
             "type": "toggle", "action": self._toggle_start_equipment},
        ]

        # --- Quest log screen ---
        self.showing_quest_log = False
        self.quest_log_scroll = 0

        # --- Game Over screen ---
        self.showing_game_over = False
        self.game_over_cursor = 0
        self.game_over_elapsed = 0.0
        self.game_over_options = [
            {"label": "LOAD GAME", "action": self._game_over_load},
            {"label": "NEW GAME", "action": self._game_over_new},
        ]

        # Combat rewards (must be set before change_state triggers enter())
        self.pending_combat_rewards = None
        self.pending_killed_monsters = []
        # Examine tile persistence (must exist before examine state enter())
        self.examined_tiles = {}

        # --- State machine ---
        self.states = {
            "overworld": OverworldState(self),
            "town": TownState(self),
            "dungeon": DungeonState(self),
            "combat": CombatState(self),
            "examine": ExamineState(self),
        }
        self.current_state = None
        self.change_state("overworld")

        # Play title music (overrides the overworld music set by change_state)
        self.music.play("title")

    @property
    def title_options(self):
        """Build title menu options, adding RETURN TO GAME when applicable.

        Shows RETURN TO GAME if a game is actively in progress, OR if
        there is at least one save file the player can resume from.
        """
        if self._game_started or self._find_most_recent_save() is not None:
            return ([{"label": "RETURN TO GAME",
                       "action": self._title_return_to_game}]
                    + self._title_options_base)
        return self._title_options_base

    # ── Title screen actions ────────────────────────────────────

    def _title_new_game(self):
        """Start a fresh new game from the title screen.

        Loads all game data from the active module (with fallback to
        default data/ for any missing files), then initialises the party.

        If the player has already created characters and formed a party
        via the CREATE CHARACTER / FORM PARTY screens, those selections
        are preserved.  Only game-level state (position, gold, inventory,
        quests) is reset to defaults from party.json.

        Falls back to the full default party if no active members exist.
        """
        # ── Reset all per-game state so nothing leaks from a prior game ──
        self.darkness_active = False
        self.town_data = generate_town("Thornwall")  # safe default
        self.town_data_map = {}
        self._gnome_quest_accepted = False
        self.game_log = []
        self.dungeon_cache = {}  # clear persisted dungeon layouts

        # ── Load module data (items, races, monsters, etc.) ──
        if self.active_module_path:
            self.module_manifest = load_module_data(self.active_module_path)

        # ── Regenerate the overworld map from module config ──
        overworld_cfg = None
        if self.module_manifest:
            overworld_cfg = self.module_manifest.get("_overworld_cfg")
        self.tile_map = create_test_map(
            overworld_cfg=overworld_cfg,
            data_dir=self.active_module_path)
        self.camera = Camera(self.tile_map.width, self.tile_map.height)

        if self.party.members:
            # Player already formed a party — keep roster & active members,
            # but reset game-level state for a fresh start.
            cfg = _load_party_config()
            start = cfg.get("start_position", {})
            self.party.col = start.get("col", 14)
            self.party.row = start.get("row", 16)
            self.party.gold = cfg.get("gold", 100)

            # Module overworld may override the start position
            if overworld_cfg:
                mod_start = overworld_cfg.get("start_position")
                if mod_start:
                    self.party.col = mod_start.get("col", self.party.col)
                    self.party.row = mod_start.get("row", self.party.row)

            # Reset shared inventory to defaults
            self.party.shared_inventory = []
            for entry in cfg.get("inventory", []):
                item_name = entry["item"]
                charges = entry.get("charges")
                if charges is not None:
                    self.party.inv_add(item_name, charges=charges)
                else:
                    self.party.shared_inventory.append(item_name)

            # Reset party-level equipment and effects
            for slot in list(self.party.equipped.keys()):
                self.party.equipped[slot] = None
            for slot in self.party.EFFECT_SLOTS:
                self.party.effects[slot] = None

            # Reset each active member's HP to full and clear personal inv
            for m in self.party.members:
                m.hp = m.max_hp
                m.inventory = []

            # Strip equipment if starting without gear
            if not self.start_with_equipment:
                for m in self.party.roster:
                    m.equipped = {
                        "right_hand": "Club",
                        "left_hand": None,
                        "body": "Cloth",
                        "head": None,
                    }
                    m._sync_legacy_fields()
                    m.personal_inventory = []
                self.party.shared_inventory = []
                for _ in range(6):
                    self.party.shared_inventory.append("Rock")
        else:
            # No active party formed — use the default from party.json
            self.party = create_default_party(
                start_with_equipment=self.start_with_equipment)

            # Module overworld may override the start position
            if overworld_cfg:
                mod_start = overworld_cfg.get("start_position")
                if mod_start:
                    self.party.col = mod_start.get("col", self.party.col)
                    self.party.row = mod_start.get("row", self.party.row)

        # ── Set starting time from module config ──
        if self.module_manifest:
            start_time = self.module_manifest.get("settings", {}).get("start_time")
            if start_time:
                from src.game_time import GameClock
                self.party.clock = GameClock.from_date(
                    year=start_time.get("year", 1),
                    month=start_time.get("month", 1),
                    day=start_time.get("day", 1),
                    hour=start_time.get("hour", 12),
                    minute=start_time.get("minute", 0),
                )

        # ── Apply module-defined starting loot ──
        if self.module_manifest:
            starting_loot = self.module_manifest.get(
                "progression", {}).get("starting_loot", [])
            for loot_entry in starting_loot:
                item_name = loot_entry.get("item")
                count = max(1, int(loot_entry.get("count", 1)))
                if item_name:
                    for _ in range(count):
                        self.party.inv_add(item_name)

        self.quest = None
        self.house_quest = None
        self.examined_tiles = {}  # {(col, row): {"obstacles": {}, "ground_items": {}}}

        self.visited_dungeons = set()  # {(col, row)} — tracks which dungeon tiles the party has entered

        # Persistent dungeon cache: {(col,row): [DungeonData, ...]}
        # Stores generated dungeons so re-entry preserves state (explored
        # tiles, opened chests, triggered traps, killed monsters).
        self.dungeon_cache = {}

        # ── Module key-dungeon quests ──
        self.key_dungeons = {}  # {(col,row): {dungeon_number, name, key_name, ...}}
        self.keys_inserted = 0  # how many keys placed in the machine
        self.pending_combat_rewards = None  # set by combat victory, consumed by source state
        self.pending_killed_monsters = []   # monster names killed in last combat
        self.machine_col = None  # overworld position of the machine
        self.machine_row = None
        self.town_data_map = {}
        if self.module_manifest:
            mod_id = self.module_manifest.get(
                "metadata", {}).get("id", "")
            prog = self.module_manifest.get("progression", {})
            kd_list = prog.get("key_dungeons", [])
            if kd_list:
                self._init_key_dungeons(kd_list)
                if mod_id == "keys_of_shadow":
                    # Duskhollow is unique to Keys of Shadow
                    self.darkness_active = True
                    self.town_data = generate_duskhollow()
                else:
                    # Generate all towns from the manifest
                    self._init_module_towns()

        self._game_started = True
        self.showing_title = False
        self.change_state("overworld")
        self.camera.update(self.party.col, self.party.row)

    @staticmethod
    def _generate_window_icon():
        """Create a 32×32 procedural window icon — dark-fantasy crystal."""
        import math
        sz = 32
        icon = pygame.Surface((sz, sz), pygame.SRCALPHA)
        icon.fill((0, 0, 0, 0))
        cx, cy = sz // 2, sz // 2

        # Dark background circle
        pygame.draw.circle(icon, (15, 10, 30, 255), (cx, cy), 15)
        pygame.draw.circle(icon, (30, 20, 50, 255), (cx, cy), 13)

        # Glowing purple crystal (diamond shape)
        pts = [(cx, cy - 10), (cx + 7, cy), (cx, cy + 10), (cx - 7, cy)]
        pygame.draw.polygon(icon, (120, 50, 200), pts)
        # Crystal highlight
        inner = [(cx, cy - 6), (cx + 4, cy), (cx, cy + 6), (cx - 4, cy)]
        pygame.draw.polygon(icon, (170, 100, 255), inner)
        # Bright core
        pygame.draw.circle(icon, (220, 180, 255), (cx, cy), 2)

        # Glow aura
        for r in range(8, 15):
            a = max(0, 60 - (r - 8) * 8)
            glow = pygame.Surface((sz, sz), pygame.SRCALPHA)
            pygame.draw.circle(glow, (140, 80, 220, a), (cx, cy), r)
            icon.blit(glow, (0, 0))

        # Thin gold border ring
        pygame.draw.circle(icon, (200, 170, 60), (cx, cy), 15, 1)

        return icon

    def _init_key_dungeons(self, kd_list):
        """Set up key dungeon quest entries from the module manifest.

        Each key dungeon is stored in self.key_dungeons keyed by its
        overworld (col, row) position.  The dungeon levels are generated
        lazily on first entry.

        For the Keys of Shadow module, dungeons start as ``"active"``
        (the gnome quest acceptance gates visibility).  For all other
        modules, dungeons start as ``"undiscovered"`` — the quest
        objective is hidden until the town elder reveals them.
        """
        from src.dungeon_generator import generate_keys_dungeon

        overworld_cfg = self.module_manifest.get("_overworld_cfg", {})
        landmarks = {lm["id"]: lm for lm in overworld_cfg.get("landmarks", [])}

        # Determine starting status based on module
        mod_id = self.module_manifest.get("metadata", {}).get("id", "")
        initial_status = "active" if mod_id == "keys_of_shadow" else "undiscovered"

        # Find the machine landmark
        for lm in overworld_cfg.get("landmarks", []):
            if lm.get("type") == "machine":
                self.machine_col = lm["col"]
                self.machine_row = lm["row"]
                break

        for kd in kd_list:
            lm_id = kd.get("landmark_id", "")
            lm = landmarks.get(lm_id)
            if not lm:
                continue
            col, row = lm["col"], lm["row"]
            dnum = kd["dungeon_number"]
            name = kd.get("name", f"Key Dungeon {dnum}")
            key_name = kd.get("key_name", f"Key {dnum}")

            quest_type = kd.get("quest_type", "retrieve")
            module_levels = kd.get("levels") or None

            # Generate the multi-floor dungeon.
            # If the module defines levels with encounters, those
            # specs drive the floor count and monster placement.
            # Kill quests don't need an artifact tile — the portal
            # spawns when enough monsters are killed instead.
            # Gnome machine quests ARE retrieve quests (collect a key)
            # so they need an artifact tile.
            needs_artifact = (quest_type != "kill")
            kt = kd.get("kill_target", "") if quest_type == "kill" else None
            kc = int(kd.get("kill_count", 0)) if quest_type == "kill" else 0
            td = kd.get("torch_density", "medium")
            levels = generate_keys_dungeon(
                dnum, name=name,
                place_artifact=needs_artifact,
                module_levels=module_levels,
                kill_target=kt, kill_count=kc,
                torch_density=td)
            self.key_dungeons[(col, row)] = {
                "dungeon_number": dnum,
                "name": name,
                "key_name": key_name,
                "levels": levels,
                "current_level": 0,
                "status": initial_status,  # undiscovered → active → artifact_found → completed
                "dungeon_col": col,
                "dungeon_row": row,
                "artifact_name": key_name,
                "description": kd.get("description", ""),
                "quest_objective": kd.get("quest_objective", ""),
                "quest_hint": kd.get("quest_hint", ""),
                "quest_type": quest_type,
                "kill_target": kd.get("kill_target", ""),
                "kill_count": int(kd.get("kill_count", 0)),
                "kill_progress": 0,  # runtime kill counter
                "module_levels": module_levels,  # original specs
                "exit_portal": kd.get("exit_portal", True),
                "keys_needed": int(kd.get("keys_needed", 1)),
                "gnome_town": kd.get("gnome_town", ""),
            }

    def discover_key_dungeons(self, only_types=None, exclude_types=None):
        """Mark undiscovered key dungeons as active.

        Parameters
        ----------
        only_types : set or None
            If given, only reveal dungeons whose quest_type is in this set.
        exclude_types : set or None
            If given, skip dungeons whose quest_type is in this set.
        """
        for kd in self.key_dungeons.values():
            if kd["status"] != "undiscovered":
                continue
            qt = kd.get("quest_type", "retrieve")
            if only_types and qt not in only_types:
                continue
            if exclude_types and qt in exclude_types:
                continue
            kd["status"] = "active"
            # Restore proper floor names now that the quest is revealed
            dname = kd.get("name", "Key Dungeon")
            for i, level in enumerate(kd.get("levels", [])):
                level.name = f"{dname} - Floor {i + 1}"

    def _init_module_towns(self):
        """Generate towns for the active module and store in town_data_map.

        Reads town landmarks from the overworld config and generates a
        unique TownData for each (using a per-town seed so that layouts,
        NPCs, and dialogue vary).  The first town becomes
        ``self.town_data`` (the default / hub town).
        """
        overworld_cfg = self.module_manifest.get("_overworld_cfg", {})
        manifest_towns = self.module_manifest.get("world", {}).get("towns", [])
        # Build a quick lookup: town_id → town name and config
        town_names = {t["id"]: t["name"] for t in manifest_towns}
        town_configs = {t["id"]: t.get("town_config", {})
                        for t in manifest_towns}

        # Check if module enables innkeeper quests
        prog = self.module_manifest.get("progression", {})
        inn_quests = prog.get("innkeeper_quests", False)

        # Check if any quest uses gnome_machine type
        # (per-quest field, not module-level)
        has_gnome_machine = any(
            kd.get("quest_type") == "gnome_machine"
            for kd in self.key_dungeons.values())
        # Also check Keys of Shadow (always gnome machine)
        mod_id = self.module_manifest.get("metadata", {}).get("id", "")
        if mod_id == "keys_of_shadow":
            has_gnome_machine = True
        # Sum up keys_needed from all gnome_machine quests
        gnome_keys_needed = sum(
            kd.get("keys_needed", 1)
            for kd in self.key_dungeons.values()
            if kd.get("quest_type") == "gnome_machine")
        if mod_id == "keys_of_shadow":
            gnome_keys_needed = max(gnome_keys_needed,
                                    len(self.key_dungeons))
        # Determine which town the gnome machine should be placed in.
        # The user can choose via the "Gnome Town" quest field.
        # For KoS, it always goes in the first town.
        gnome_town_name = ""
        if has_gnome_machine and mod_id != "keys_of_shadow":
            for kd in self.key_dungeons.values():
                if kd.get("quest_type") == "gnome_machine":
                    gnome_town_name = kd.get("gnome_town", "")
                    if gnome_town_name:
                        break

        self.town_data_map = {}
        first_town = None
        town_ordinal = 0  # guarantees each town gets a different layout
        for i, lm in enumerate(overworld_cfg.get("landmarks", [])):
            if lm.get("type") != "town":
                continue
            tid = lm["id"]
            tname = town_names.get(tid, tid.replace("_", " ").title())
            col, row = lm["col"], lm["row"]
            # Unique seed per town so NPCs and dialogue vary
            town_seed = hash((tname, col, row, i)) & 0xFFFFFFFF
            # Place the gnome machine in the chosen town, or the first
            # town if none was explicitly chosen.
            if has_gnome_machine:
                if gnome_town_name:
                    place_machine = (tname == gnome_town_name)
                else:
                    place_machine = (first_town is None)
            else:
                place_machine = False
            tc = town_configs.get(tid, {})
            td = generate_town(tname, seed=town_seed,
                               layout_index=town_ordinal,
                               has_key_dungeons=bool(self.key_dungeons),
                               innkeeper_quests=inn_quests,
                               gnome_machine=place_machine,
                               keys_needed=gnome_keys_needed,
                               town_config=tc)
            town_ordinal += 1
            self.town_data_map[(col, row)] = td
            if first_town is None:
                first_town = td

        # Set the default town_data to the first town (hub)
        if first_town:
            self.town_data = first_town

        # Distribute non-gnome quests as individual NPCs across towns
        self._assign_quest_npcs()

    def _assign_quest_npcs(self):
        """Distribute non-gnome key dungeon quests across towns as NPCs.

        Each quest gets its own quest_giver NPC placed in a randomly
        chosen town.  The mapping is stored in
        ``self.quest_npc_assignments`` so it can be persisted across
        saves / town regeneration.
        """
        from src.town_generator import add_quest_giver_npc, _QUEST_GIVER_POOL

        # Collect non-gnome quests that need distributing
        quests_to_assign = []
        for pos_key, kd in self.key_dungeons.items():
            if kd.get("quest_type") == "gnome_machine":
                continue
            quests_to_assign.append((pos_key, kd))

        if not quests_to_assign or not self.town_data_map:
            self.quest_npc_assignments = {}
            return

        # Get list of town names / keys for round-robin assignment
        town_keys = list(self.town_data_map.keys())  # (col, row) list

        # Use a deterministic RNG seeded from the module for reproducibility
        mod_id = ""
        if self.module_manifest:
            mod_id = self.module_manifest.get("metadata", {}).get("id", "")
        assign_rng = random.Random(hash(mod_id + "_quest_npcs") & 0xFFFFFFFF)
        assign_rng.shuffle(town_keys)

        # If we already have saved assignments, use those instead
        if getattr(self, "quest_npc_assignments", None):
            assignments = self.quest_npc_assignments
        else:
            # Randomly assign each quest to any town independently.
            # Two quests may end up in the same town — that's fine.
            # Some towns may get no quest at all.
            assignments = {}
            available_names = list(_QUEST_GIVER_POOL)
            assign_rng.shuffle(available_names)
            for i, (pos_key, kd) in enumerate(quests_to_assign):
                town_key = assign_rng.choice(town_keys)
                td = self.town_data_map[town_key]
                dk_str = f"{pos_key[0]},{pos_key[1]}"
                npc_name = available_names[i % len(available_names)]
                assignments[dk_str] = {
                    "town_name": td.name,
                    "npc_name": npc_name,
                }
            self.quest_npc_assignments = assignments

        # Now inject quest_giver NPCs into the appropriate towns
        # Build town lookup by name
        town_by_name = {}
        for tk, td in self.town_data_map.items():
            town_by_name[td.name] = td

        name_idx = 0
        for pos_key, kd in quests_to_assign:
            dk_str = f"{pos_key[0]},{pos_key[1]}"
            info = assignments.get(dk_str)
            if not info:
                continue
            td = town_by_name.get(info["town_name"])
            if not td:
                # Town name mismatch (shouldn't happen) — put in first town
                td = next(iter(self.town_data_map.values()))
            seed = hash(dk_str) & 0xFFFFFFFF
            add_quest_giver_npc(
                td,
                quest_giver_name=info["npc_name"],
                dungeon_key_str=dk_str,
                dungeon_name=kd.get("name", "Unknown Dungeon"),
                quest_hint=kd.get("quest_hint", "Be careful."),
                quest_objective=kd.get("quest_objective", ""),
                quest_type=kd.get("quest_type", "retrieve"),
                seed=seed,
            )

    def discover_single_key_dungeon(self, dungeon_key_str):
        """Reveal a single key dungeon by its ``'col,row'`` string key."""
        parts = dungeon_key_str.split(",")
        if len(parts) != 2:
            return
        col, row = int(parts[0]), int(parts[1])
        kd = self.key_dungeons.get((col, row))
        if kd and kd["status"] == "undiscovered":
            kd["status"] = "active"
            dname = kd.get("name", "Key Dungeon")
            for i, level in enumerate(kd.get("levels", [])):
                level.name = f"{dname} - Floor {i + 1}"

    def get_town_at(self, col, row):
        """Return the TownData for the town landmark at (col, row), or the
        default town_data if no specific mapping exists."""
        return self.town_data_map.get((col, row), self.town_data)

    # ── Public accessors for game state ─────────────────────────
    # States should use these instead of reaching into internals.

    def is_dungeon_visited(self, col, row):
        """Return True if the dungeon at (col, row) has been entered before."""
        return (col, row) in self.visited_dungeons

    def mark_dungeon_visited(self, col, row):
        """Record that the dungeon at (col, row) has been entered."""
        self.visited_dungeons.add((col, row))

    def get_key_dungeons(self):
        """Return the full key-dungeon dict: {(col,row): info_dict}."""
        return self.key_dungeons

    def get_key_dungeon(self, col, row):
        """Return key-dungeon info at (col, row), or None."""
        return self.key_dungeons.get((col, row))

    def get_keys_inserted(self):
        """Return how many Keys of Shadow have been inserted."""
        return self.keys_inserted

    def insert_key(self):
        """Increment keys_inserted by one.  Returns the new count."""
        self.keys_inserted += 1
        return self.keys_inserted

    def get_total_keys(self):
        """Return the total number of keys needed for the gnome machine.

        For Keys of Shadow (all quests are gnome-style), this is the
        total number of key dungeons.  For custom modules, it counts
        only dungeons whose quest_type is ``"gnome_machine"``.  Falls
        back to all dungeons if none are explicitly gnome_machine.
        """
        gnome_count = sum(
            1 for kd in self.key_dungeons.values()
            if kd.get("quest_type") == "gnome_machine")
        return gnome_count if gnome_count else len(self.key_dungeons)

    def set_darkness(self, active):
        """Enable or disable the darkness overlay."""
        self.darkness_active = active

    def get_quest(self):
        """Return the active quest dict, or None."""
        return self.quest

    def set_quest(self, quest):
        """Set the active quest dict (or None to clear)."""
        self.quest = quest

    def get_house_quest(self):
        """Return the house quest dict, or None."""
        return self.house_quest

    def set_house_quest(self, quest):
        """Set the house quest dict (or None to clear)."""
        self.house_quest = quest

    def set_combat_rewards(self, rewards):
        """Store pending combat rewards (dict with xp, gold, etc.)."""
        self.pending_combat_rewards = rewards

    def consume_combat_rewards(self):
        """Return pending combat rewards and clear them."""
        rewards = self.pending_combat_rewards
        self.pending_combat_rewards = None
        return rewards

    def get_examined_tile(self, col, row):
        """Return saved examine data for (col, row), or None."""
        return self.examined_tiles.get((col, row))

    def save_examined_tile(self, col, row, data):
        """Store examine layout data for overworld tile (col, row)."""
        self.examined_tiles[(col, row)] = data

    def set_gnome_quest_accepted(self):
        """Mark the gnome quest as accepted."""
        self._gnome_quest_accepted = True

    def _build_quest_log(self):
        """Build a list of quest entries for the quest log screen.

        Each entry is a dict with:
            name:   str   — quest title
            status: str   — 'active', 'completed', etc.
            steps:  list  — [{description: str, done: bool}, ...]
        """
        quests = []

        # ── Innkeeper quest ──
        quest = self.quest
        if quest is not None:
            status = quest.get("status", "active")
            qtype = quest.get("quest_type", "retrieve")
            visited = (status in ("active", "artifact_found", "completed")
                       and self.is_dungeon_visited(
                           quest.get("dungeon_col", -1),
                           quest.get("dungeon_row", -1)))

            if qtype == "kill":
                kill_target = quest.get("kill_target", "Monster")
                kill_count = quest.get("kill_count", 1)
                kill_progress = quest.get("kill_progress", 0)
                steps = [
                    {"description": "Accept the quest from the innkeeper",
                     "done": True},
                    {"description": "Find and enter the quest dungeon",
                     "done": visited},
                    {"description": (
                        f"Defeat {kill_count} {kill_target}"
                        f" ({kill_progress}/{kill_count})"),
                     "done": status in ("artifact_found", "completed")},
                    {"description": "Report back to the innkeeper",
                     "done": status == "completed"},
                ]
            else:
                artifact = quest.get("artifact_name", "Shadow Crystal")
                steps = [
                    {"description": "Accept the quest from the innkeeper",
                     "done": True},
                    {"description": "Find and enter the quest dungeon",
                     "done": visited},
                    {"description": f"Retrieve the {artifact}",
                     "done": status in ("artifact_found", "completed")},
                    {"description": f"Return the {artifact} to the innkeeper",
                     "done": status == "completed"},
                ]
            quests.append({
                "name": quest.get("name", "The Shadow Crystal"),
                "status": status,
                "steps": steps,
            })

        # ── Key dungeon quests (one entry per dungeon) ──
        kd_map = self.key_dungeons
        if kd_map:
            gnome_accepted = self._gnome_quest_accepted
            inserted = self.keys_inserted

            # Check if any quest uses gnome_machine type
            is_gnome_machine = any(
                kd.get("quest_type") == "gnome_machine"
                for kd in kd_map.values())
            # Keys of Shadow is always gnome_machine style
            if self.module_manifest:
                mod_id = self.module_manifest.get(
                    "metadata", {}).get("id", "")
                if mod_id == "keys_of_shadow":
                    is_gnome_machine = True

            for pos, kd in kd_map.items():
                kd_status = kd.get("status", "undiscovered")
                if kd_status == "undiscovered":
                    continue  # don't show quests the player hasn't learned about
                key_name = kd.get("key_name", "Key")
                dname = kd.get("name", "Key Dungeon")
                qtype = kd.get("quest_type", "retrieve")

                # Per-quest return destination
                if qtype == "gnome_machine":
                    return_dest = "the Gnome"
                else:
                    return_dest = "the Elder"

                if qtype == "kill":
                    # Kill quest: track monster kills
                    kill_target = kd.get("kill_target", "Monster")
                    kill_count = kd.get("kill_count", 1)
                    kill_progress = kd.get("kill_progress", 0)
                    visited = (kd_status in ("active", "artifact_found",
                                             "completed")
                               and self.is_dungeon_visited(
                                   kd.get("dungeon_col", pos[0]),
                                   kd.get("dungeon_row", pos[1])))
                    steps = [
                        {"description": f"Enter {dname}",
                         "done": visited},
                        {"description": (
                            f"Defeat {kill_count} {kill_target}"
                            f" ({kill_progress}/{kill_count})"),
                         "done": kd_status in ("artifact_found",
                                               "completed")},
                        {"description": f"Report to {return_dest}",
                         "done": kd_status == "completed"},
                    ]
                    quest_title = f"{dname}: {kd.get('quest_objective', key_name)}"
                else:
                    # Retrieve / gnome_machine quest: find the artifact/key
                    steps = [
                        {"description": f"Enter {dname}",
                         "done": kd_status in ("active", "artifact_found",
                                               "completed")
                                 and self.is_dungeon_visited(
                                     kd.get("dungeon_col", pos[0]),
                                     kd.get("dungeon_row", pos[1]))},
                        {"description": f"Find the {key_name}",
                         "done": kd_status in ("artifact_found",
                                               "completed")},
                        {"description":
                            f"Bring the {key_name} to {return_dest}",
                         "done": kd_status == "completed"},
                    ]
                    quest_title = f"{dname}: {key_name}"

                quests.append({
                    "name": quest_title,
                    "status": kd_status,
                    "steps": steps,
                })

            # ── Final goal (Gnome Machine modules) ──
            # Show the meta-quest when the module uses gnome machine
            # quest style.  For elder modules, each dungeon quest is
            # handled individually — no separate end-goal needed.
            gnome_kds = [kd for kd in kd_map.values()
                         if kd.get("quest_type") == "gnome_machine"]
            if is_gnome_machine and (gnome_accepted or any(
                    kd.get("status") != "undiscovered"
                    for kd in gnome_kds)):
                total = len(gnome_kds) if gnome_kds else len(kd_map)
                all_done = inserted >= total
                quests.append({
                    "name": "Activate the Ancient Machine",
                    "status": "completed" if all_done else "active",
                    "steps": [
                        {"description": f"Collect all {total} keys ({inserted}/{total} delivered)",
                         "done": all_done},
                        {"description": "Insert all keys into the machine",
                         "done": all_done},
                    ],
                })

        if not quests:
            quests.append({
                "name": "No active quests",
                "status": "none",
                "steps": [{"description": "Explore the world and talk to NPCs to discover quests.", "done": False}],
            })

        return quests

    def _title_save_game(self):
        """Open the save screen from the title."""
        self.showing_title = False
        self.showing_settings = True
        self.settings_mode = "save"
        self.save_load_cursor = 0
        self.save_load_message = None
        self.settings_cursor = 0
        self._title_save_mode = True

    def _title_load_game(self):
        """Open the load screen from the title."""
        self.showing_title = False
        self.showing_settings = True
        self.settings_mode = "load"
        self.save_load_cursor = 0
        self.save_load_message = None
        self.settings_cursor = 0
        # Flag so we know to return to title if ESC from load
        self._title_load_mode = True

    # ── Game Over actions ────────────────────────────────────

    def trigger_game_over(self):
        """Show the game over screen (called by combat on total party wipe)."""
        self.showing_game_over = True
        self.game_over_cursor = 0
        self.game_over_elapsed = 0.0
        self.music.play("title")  # somber music

    def _game_over_load(self):
        """Open load screen from the game over screen."""
        self.showing_game_over = False
        self.showing_settings = True
        self.settings_mode = "load"
        self.save_load_cursor = 0
        self.save_load_message = None
        self._game_over_load_mode = True

    def _game_over_new(self):
        """Start a fresh game from the game over screen."""
        self.showing_game_over = False
        self._title_new_game()

    def _title_create_char(self):
        """Open the character creation screen from the title."""
        self.showing_title = False
        self.showing_char_create = True
        self._fp_return_to_form_party = False
        self._cc_init()

    # ── Character creation ─────────────────────────────────────

    def _cc_init(self):
        """Reset character creation state."""
        # Steps: name, race, gender, class, tile, stats, confirm
        self._cc_step = "name"
        self._cc_name = ""
        self._cc_race_cursor = 0
        self._cc_gender_cursor = 0
        self._cc_class_cursor = 0
        self._cc_tile_cursor = 0
        self._cc_stat_cursor = 0
        self._cc_confirm_cursor = 0
        self._cc_elapsed = 0.0
        self._cc_message = None
        self._cc_msg_timer = 0.0
        # Stats: 50 points to distribute, min 5 max 25 per stat
        self._cc_stats = {"strength": 10, "dexterity": 10,
                          "intelligence": 15, "wisdom": 15}
        self._cc_stat_names = ["strength", "dexterity",
                               "intelligence", "wisdom"]
        self._cc_points_total = 50
        # Load available classes from disk
        self._cc_load_classes()
        # Load available character tiles from config
        self._cc_load_tiles()

    def _cc_load_classes(self):
        """Discover available classes from data/classes/*.json."""
        import os, json
        classes_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "classes")
        self._cc_classes = []
        if os.path.isdir(classes_dir):
            for fn in sorted(os.listdir(classes_dir)):
                if fn.endswith(".json"):
                    name = fn[:-5].capitalize()
                    self._cc_classes.append(name)

    def _cc_load_tiles(self):
        """Load available character tiles from character_tiles.json."""
        import os, json
        project_root = os.path.dirname(os.path.dirname(__file__))
        # Try module directory first, then data/
        tiles_path = None
        if hasattr(self, 'active_module_path') and self.active_module_path:
            mod_path = os.path.join(self.active_module_path,
                                    "character_tiles.json")
            if os.path.isfile(mod_path):
                tiles_path = mod_path
        if tiles_path is None:
            tiles_path = os.path.join(project_root, "data",
                                      "character_tiles.json")
        self._cc_tiles = []  # list of {"name": ..., "file": ...}
        if os.path.isfile(tiles_path):
            try:
                with open(tiles_path, "r") as f:
                    data = json.load(f)
                for entry in data.get("tiles", []):
                    abs_path = os.path.join(project_root, entry["file"])
                    if os.path.isfile(abs_path):
                        self._cc_tiles.append({
                            "name": entry["name"],
                            "file": entry["file"],
                        })
            except (json.JSONDecodeError, OSError, KeyError):
                pass
        # If no tiles loaded, provide a minimal fallback
        if not self._cc_tiles:
            self._cc_tiles.append({"name": "Default", "file": ""})

    def _cc_selected_tile(self):
        """Return the file path for the currently selected tile."""
        if self._cc_tile_cursor < len(self._cc_tiles):
            return self._cc_tiles[self._cc_tile_cursor].get("file", "")
        return ""

    @property
    def _cc_points_spent(self):
        return sum(self._cc_stats.values())

    @property
    def _cc_points_remaining(self):
        return self._cc_points_total - self._cc_points_spent

    def _cc_selected_race(self):
        return VALID_RACES[self._cc_race_cursor]

    def _cc_selected_gender(self):
        return PartyMember.VALID_GENDERS[self._cc_gender_cursor]

    def _cc_selected_class(self):
        valid = getattr(self, '_cc_classes_filtered', None)
        if valid is None:
            valid = self._cc_valid_classes_for_race()
        if self._cc_class_cursor < len(valid):
            return valid[self._cc_class_cursor]
        return valid[0] if valid else "Fighter"

    def _cc_valid_classes_for_race(self):
        """Return list of class names valid for the selected race."""
        race = self._cc_selected_race().lower()
        valid = []
        for cls_name in self._cc_classes:
            allowed = PartyMember.allowed_races_for_class(cls_name)
            if allowed is None or race in allowed:
                valid.append(cls_name)
        return valid

    def _cc_finish(self):
        """Create the character and add to roster."""
        tile_file = self._cc_selected_tile()
        member = PartyMember(
            name=self._cc_name,
            char_class=self._cc_selected_class(),
            race=self._cc_selected_race(),
            gender=self._cc_selected_gender(),
            hp=20,
            strength=self._cc_stats["strength"],
            dexterity=self._cc_stats["dexterity"],
            intelligence=self._cc_stats["intelligence"],
            wisdom=self._cc_stats["wisdom"],
            sprite=tile_file if tile_file else None,
        )
        idx = self.party.add_to_roster(member)
        if idx < 0:
            self._cc_message = "Roster is full! (max 20)"
            self._cc_msg_timer = 2.0
            return
        # Persist the updated roster to data/party.json so the new
        # character is available across all future game sessions.
        save_roster(self.party)
        self._cc_message = f"{self._cc_name} joins the roster!"
        self._cc_msg_timer = 2.0
        self._cc_step = "done"

    def _handle_char_create_input(self, event):
        """Handle input on the character creation screen."""
        if event.type != pygame.KEYDOWN:
            return

        step = self._cc_step

        # Done step — any key returns to previous screen
        if step == "done":
            self._cc_exit()
            return

        # ESC goes back one step (or to title from name)
        if event.key == pygame.K_ESCAPE:
            if step == "name":
                self._cc_exit()
            elif step == "race":
                self._cc_step = "name"
            elif step == "gender":
                self._cc_step = "race"
            elif step == "class":
                self._cc_step = "gender"
            elif step == "tile":
                self._cc_step = "class"
            elif step == "stats":
                self._cc_step = "tile"
            elif step == "confirm":
                self._cc_step = "stats"
            return

        # ── Name entry ──
        if step == "name":
            if event.key == pygame.K_RETURN:
                if len(self._cc_name.strip()) > 0:
                    self._cc_step = "race"
            elif event.key == pygame.K_BACKSPACE:
                self._cc_name = self._cc_name[:-1]
            else:
                ch = event.unicode
                if ch and ch.isprintable() and len(self._cc_name) < 12:
                    self._cc_name += ch
            return

        # ── Race selection ──
        if step == "race":
            if event.key == pygame.K_UP:
                self._cc_race_cursor = (
                    self._cc_race_cursor - 1) % len(VALID_RACES)
            elif event.key == pygame.K_DOWN:
                self._cc_race_cursor = (
                    self._cc_race_cursor + 1) % len(VALID_RACES)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._cc_step = "gender"
            return

        # ── Gender selection ──
        if step == "gender":
            if event.key in (pygame.K_UP, pygame.K_DOWN):
                self._cc_gender_cursor = 1 - self._cc_gender_cursor
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                # Reset class cursor; filter classes for chosen race
                self._cc_class_cursor = 0
                self._cc_step = "class"
            return

        # ── Class selection ──
        if step == "class":
            valid = self._cc_valid_classes_for_race()
            if event.key == pygame.K_UP:
                self._cc_class_cursor = (
                    self._cc_class_cursor - 1) % len(valid)
            elif event.key == pygame.K_DOWN:
                self._cc_class_cursor = (
                    self._cc_class_cursor + 1) % len(valid)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                # Store selected class name from filtered list
                self._cc_classes_filtered = valid
                self._cc_tile_cursor = 0
                self._cc_step = "tile"
            return

        # ── Tile selection ──
        if step == "tile":
            tile_count = len(self._cc_tiles)
            if event.key == pygame.K_LEFT:
                self._cc_tile_cursor = (
                    self._cc_tile_cursor - 1) % tile_count
            elif event.key == pygame.K_RIGHT:
                self._cc_tile_cursor = (
                    self._cc_tile_cursor + 1) % tile_count
            elif event.key == pygame.K_UP:
                # Jump back by a row (6 tiles per row)
                self._cc_tile_cursor = (
                    self._cc_tile_cursor - 6) % tile_count
            elif event.key == pygame.K_DOWN:
                self._cc_tile_cursor = (
                    self._cc_tile_cursor + 6) % tile_count
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._cc_step = "stats"
                # Reset stats
                self._cc_stats = {"strength": 10, "dexterity": 10,
                                  "intelligence": 15, "wisdom": 15}
                self._cc_stat_cursor = 0
            return

        # ── Stat allocation ──
        if step == "stats":
            stat_key = self._cc_stat_names[self._cc_stat_cursor]
            if event.key == pygame.K_UP:
                self._cc_stat_cursor = (
                    self._cc_stat_cursor - 1) % 4
            elif event.key == pygame.K_DOWN:
                self._cc_stat_cursor = (
                    self._cc_stat_cursor + 1) % 4
            elif event.key == pygame.K_RIGHT:
                if (self._cc_stats[stat_key] < 25
                        and self._cc_points_remaining > 0):
                    self._cc_stats[stat_key] += 1
            elif event.key == pygame.K_LEFT:
                if self._cc_stats[stat_key] > 5:
                    self._cc_stats[stat_key] -= 1
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self._cc_points_remaining == 0:
                    self._cc_confirm_cursor = 0
                    self._cc_step = "confirm"
            return

        # ── Confirm ──
        if step == "confirm":
            if event.key in (pygame.K_UP, pygame.K_DOWN):
                self._cc_confirm_cursor = 1 - self._cc_confirm_cursor
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self._cc_confirm_cursor == 0:  # CREATE
                    self._cc_finish()
                else:  # CANCEL
                    self._cc_exit()
            return

    def _cc_exit(self):
        """Exit character creation, returning to form party or title."""
        self.showing_char_create = False
        if getattr(self, '_fp_return_to_form_party', False):
            self._fp_return_to_form_party = False
            self.showing_form_party = True
            self._fp_init()
        else:
            self.showing_title = True

    # ── Party formation ──────────────────────────────────────────

    def _title_form_party(self):
        """Open the party formation screen from the title."""
        self.showing_title = False
        self.showing_form_party = True
        self._fp_init()

    def _fp_init(self):
        """Reset party formation state."""
        self._fp_cursor = 0           # cursor in roster list
        self._fp_selected = set()     # set of roster indices currently selected
        self._fp_elapsed = 0.0
        self._fp_message = None
        self._fp_msg_timer = 0.0
        self._fp_scroll = 0           # scroll offset for long rosters
        self._fp_confirm_delete = False  # delete confirmation dialog
        # Pre-populate with current active party indices
        if hasattr(self, 'party') and self.party:
            self._fp_selected = set(self.party.active_indices)

    def _fp_toggle(self, idx):
        """Toggle a roster member in/out of the party selection."""
        if idx in self._fp_selected:
            self._fp_selected.discard(idx)
        else:
            if len(self._fp_selected) >= 4:
                self._fp_message = "Party is full! (max 4)"
                self._fp_msg_timer = 1.5
                return
            self._fp_selected.add(idx)

    def _fp_confirm(self):
        """Apply the selected roster members as the active party."""
        if len(self._fp_selected) == 0:
            self._fp_message = "Select at least 1 character!"
            self._fp_msg_timer = 1.5
            return
        indices = sorted(self._fp_selected)
        self.party.set_active_party(indices)
        # Persist active party selection so it's remembered across sessions.
        save_roster(self.party)
        self._fp_message = "Party formed!"
        self._fp_msg_timer = 1.5
        self.showing_form_party = False
        self.showing_title = True

    def _handle_form_party_input(self, event):
        """Handle input on the party formation screen."""
        if event.type != pygame.KEYDOWN:
            return

        # ── Delete confirmation dialog ──
        if self._fp_confirm_delete:
            if event.key == pygame.K_y:
                self._fp_do_delete()
            elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                self._fp_confirm_delete = False
            return

        roster_len = len(self.party.roster)
        if roster_len == 0:
            # No characters — C to create, or ESC/Enter/Space to return
            if event.key == pygame.K_c:
                self._fp_create_char()
            elif event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.showing_form_party = False
                self.showing_title = True
            return

        if event.key == pygame.K_ESCAPE:
            self.showing_form_party = False
            self.showing_title = True
        elif event.key == pygame.K_UP:
            self._fp_cursor = (self._fp_cursor - 1) % roster_len
            visible = 12
            if self._fp_cursor < self._fp_scroll:
                self._fp_scroll = self._fp_cursor
            elif self._fp_cursor >= self._fp_scroll + visible:
                self._fp_scroll = self._fp_cursor - visible + 1
        elif event.key == pygame.K_DOWN:
            self._fp_cursor = (self._fp_cursor + 1) % roster_len
            visible = 12
            if self._fp_cursor < self._fp_scroll:
                self._fp_scroll = self._fp_cursor
            elif self._fp_cursor >= self._fp_scroll + visible:
                self._fp_scroll = self._fp_cursor - visible + 1
        elif event.key == pygame.K_SPACE:
            self._fp_toggle(self._fp_cursor)
        elif event.key == pygame.K_RETURN:
            self._fp_confirm()
        elif event.key == pygame.K_d:
            # Prompt delete confirmation
            if 0 <= self._fp_cursor < roster_len:
                self._fp_confirm_delete = True
        elif event.key == pygame.K_c:
            self._fp_create_char()

    def _fp_create_char(self):
        """Open character creation from the form party screen."""
        self.showing_form_party = False
        self.showing_char_create = True
        self._fp_return_to_form_party = True  # flag to return here after
        self._cc_init()

    def _fp_do_delete(self):
        """Delete the character at the current cursor position."""
        self._fp_confirm_delete = False
        roster = self.party.roster
        idx = self._fp_cursor
        if not (0 <= idx < len(roster)):
            return
        name = roster[idx].name
        # Remove from selected set (adjust indices)
        new_selected = set()
        for si in self._fp_selected:
            if si == idx:
                continue  # removed
            elif si > idx:
                new_selected.add(si - 1)
            else:
                new_selected.add(si)
        self._fp_selected = new_selected
        # Remove from roster
        del roster[idx]
        # Also update active_indices on the party
        self.party.active_indices = sorted(self._fp_selected)
        self.party.members = [roster[i] for i in self.party.active_indices
                              if 0 <= i < len(roster)]
        # Adjust cursor
        if self._fp_cursor >= len(roster) and len(roster) > 0:
            self._fp_cursor = len(roster) - 1
        elif len(roster) == 0:
            self._fp_cursor = 0
        # Save to disk
        from src.party import save_roster
        save_roster(self.party)
        self._fp_message = f"{name} deleted."
        self._fp_msg_timer = 1.5

    def _title_settings(self):
        """Open settings from the title screen."""
        self.showing_title = False
        self.showing_settings = True
        self.settings_mode = "main"
        self.settings_cursor = 0
        self._title_settings_mode = True

    def _find_most_recent_save(self):
        """Return the slot number of the most recent save, or None."""
        best_slot = None
        best_ts = -1
        for slot in range(1, NUM_SAVE_SLOTS + 1):
            info = get_save_info(slot)
            if info and info.get("timestamp", 0) > best_ts:
                best_ts = info["timestamp"]
                best_slot = slot
        return best_slot

    def _title_return_to_game(self):
        """Return to the active game, or load the most recent save."""
        if self._game_started:
            # Game already running — just dismiss the title screen
            self.showing_title = False
            return

        # No game running — try to load the most recent save
        slot = self._find_most_recent_save()
        if slot is not None:
            ok = load_game(slot, self)
            if ok:
                self._game_started = True
                self.showing_title = False
                return

        # Shouldn't reach here (button hidden when no saves exist),
        # but fall back to just dismissing the title screen.
        self.showing_title = False

    def _title_quit(self):
        """Quit the game."""
        pygame.event.post(pygame.event.Event(pygame.QUIT))

    # ── Module selection ──────────────────────────────────────

    def _title_modules(self):
        """Open the module browser from the title screen."""
        self._refresh_module_list()
        self.showing_title = False
        self.showing_modules = True
        self.module_message = None
        self.module_msg_timer = 0.0
        self.module_confirm_delete = False
        self.module_edit_mode = False
        self.module_edit_is_new = False

    def _refresh_module_list(self):
        """Re-scan modules and restore cursor position."""
        from src.module_loader import scan_modules
        old_path = None
        if self.module_list and 0 <= self.module_cursor < len(self.module_list):
            old_path = self.module_list[self.module_cursor]["path"]
        self.module_list = scan_modules()
        self.module_cursor = 0
        # Try to re-select previously selected module
        target = old_path or self.active_module_path
        for i, mod in enumerate(self.module_list):
            if mod["path"] == target:
                self.module_cursor = i
                break

    def _handle_module_input(self, event):
        """Handle input on the module selection screen."""
        if event.type != pygame.KEYDOWN:
            return

        # ── Edit mode: typing metadata fields ──
        if self.module_edit_mode:
            self._handle_module_edit_input(event)
            return

        # ── Delete confirmation ──
        if self.module_confirm_delete:
            if event.key == pygame.K_y:
                self._do_delete_module()
            elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                self.module_confirm_delete = False
                self.module_message = None
            return

        # ── No modules: N to create, ESC to go back ──
        if not self.module_list:
            if event.key == pygame.K_n:
                self._do_create_module()
            elif event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.showing_modules = False
                self.showing_title = True
            return

        # ── Normal module browsing ──
        if event.key == pygame.K_UP:
            self.module_cursor = (
                (self.module_cursor - 1) % len(self.module_list))
        elif event.key == pygame.K_DOWN:
            self.module_cursor = (
                (self.module_cursor + 1) % len(self.module_list))
        elif event.key == pygame.K_s:
            selected = self.module_list[self.module_cursor]
            self._set_active_module(
                selected["path"], selected["name"], selected["version"])
            self.showing_modules = False
            self.showing_title = True
        elif event.key == pygame.K_ESCAPE:
            self.showing_modules = False
            self.showing_title = True
        elif event.key == pygame.K_n:
            self._do_create_module()
        elif event.key == pygame.K_d:
            selected = self.module_list[self.module_cursor]
            if selected["path"] == self.active_module_path:
                self.module_message = "Cannot delete the active module!"
                self.module_msg_timer = 2.0
            else:
                self.module_confirm_delete = True
                name = selected["name"]
                self.module_message = f'Delete "{name}"?  Y = Yes  N = No'
        elif event.key == pygame.K_e:
            self._enter_module_edit()

    def _do_create_module(self):
        """Open the edit overlay in 'create new module' mode."""
        self.module_edit_mode = True
        self.module_edit_is_new = True
        self.module_edit_level = 0
        self.module_edit_field = 0
        self.module_edit_scroll = 0
        # All fields are editable in create mode
        self.module_edit_fields = [
            ["DETAILS", "", "", "section", False],
            ["Name", "name", "New Module", "text", True],
            ["Author", "author", "Unknown", "text", True],
            ["Description", "description", "", "text", True],
            ["SETTINGS", "", "", "section", False],
            ["World Size", "world_size", "Medium", "choice", True],
            ["Towns", "num_towns", "1", "int", True],
            ["Quests", "num_quests", "1", "int", True],
            ["Season", "season", "Summer", "choice", True],
            ["Time of Day", "time_of_day", "Noon", "choice", True],
        ]
        # Skip to first editable field (past the section header)
        self.module_edit_field = self._next_editable_field(0)
        self.module_edit_buffer = \
            self.module_edit_fields[self.module_edit_field][2]

    def _do_delete_module(self):
        """Delete the currently selected module."""
        from src.module_loader import delete_module
        if not self.module_list:
            return
        selected = self.module_list[self.module_cursor]
        ok = delete_module(selected["path"])
        self.module_confirm_delete = False
        if ok:
            self.module_message = f'"{selected["name"]}" deleted.'
            self.module_msg_timer = 2.0
            self._refresh_module_list()
            if self.module_cursor >= len(self.module_list):
                self.module_cursor = max(0, len(self.module_list) - 1)
        else:
            self.module_message = "Delete failed!"
            self.module_msg_timer = 2.0

    def _enter_module_edit(self):
        """Enter edit mode for an existing module — hierarchical navigation."""
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]

        # Load current settings for display (read-only)
        from src.module_loader import get_module_settings
        mod_settings = get_module_settings(mod["path"]) or {
            "world_size": "Medium", "num_towns": 0, "num_quests": 0,
            "season": "Summer", "time_of_day": "Noon",
        }

        # Load full manifest so we can edit towns/dungeons/quests
        import json, os
        manifest_path = os.path.join(mod["path"], "module.json")
        try:
            with open(manifest_path, "r") as fh:
                manifest = json.load(fh)
        except (OSError, json.JSONDecodeError):
            manifest = {}

        self.module_edit_mode = True
        self.module_edit_is_new = False

        # ── Build section list for hierarchical navigation ──
        sections = []

        # 1) Module Details
        sections.append({
            "label": "Module Details",
            "icon": ">",
            "fields": [
                ["Name", "name", mod["name"], "text", True],
                ["Author", "author", mod["author"], "text", True],
                ["Description", "description",
                 mod.get("description", ""), "text", True],
            ],
        })

        # 2) Settings (read-only except innkeeper quests toggle)
        innkeeper_quests = manifest.get("progression", {}).get(
            "innkeeper_quests", False)
        sections.append({
            "label": "Settings",
            "icon": ">",
            "fields": [
                ["World Size", "world_size",
                 mod_settings["world_size"], "choice", False],
                ["Towns", "num_towns",
                 str(mod_settings["num_towns"]), "int", False],
                ["Quests", "num_quests",
                 str(mod_settings["num_quests"]), "int", False],
                ["Season", "season",
                 mod_settings["season"], "choice", False],
                ["Time of Day", "time_of_day",
                 mod_settings["time_of_day"], "choice", False],
                ["Innkeeper Quests", "innkeeper_quests",
                 "Yes" if innkeeper_quests else "No", "choice", True],
            ],
        })

        # 3) Towns folder
        from src.module_loader import (TOWN_SIZE_NAMES, TOWN_SIZE_KEYS,
                                       TOWN_STYLE_NAMES, TOWN_STYLE_KEYS,
                                       TOWN_BUILDING_KEYS,
                                       TOWN_BUILDING_NAMES,
                                       DEFAULT_TOWN_CONFIG)
        towns = manifest.get("world", {}).get("towns", [])
        town_children = []
        for i, town in enumerate(towns):
            tname = town.get("name", f"Town {i+1}")
            tc = town.get("town_config", {})
            # Resolve size display name
            tc_size = tc.get("size", DEFAULT_TOWN_CONFIG["size"])
            try:
                size_display = TOWN_SIZE_NAMES[
                    TOWN_SIZE_KEYS.index(tc_size)]
            except (ValueError, IndexError):
                size_display = "Medium"
            # Resolve style display name
            tc_style = tc.get("style", DEFAULT_TOWN_CONFIG["style"])
            try:
                style_display = TOWN_STYLE_NAMES[
                    TOWN_STYLE_KEYS.index(tc_style)]
            except (ValueError, IndexError):
                style_display = "Medieval"
            # Build fields
            fields = [
                ["Name", f"town_{i}_name", tname, "text", True],
                ["Description", f"town_{i}_desc",
                 town.get("description", ""), "text", True],
                ["Size", f"town_{i}_size", size_display, "choice", True],
                ["Style", f"town_{i}_style", style_display, "choice", True],
            ]
            # Add a Yes/No toggle for each optional building
            tc_buildings = tc.get("buildings",
                                  DEFAULT_TOWN_CONFIG["buildings"])
            for bkey, bname in zip(TOWN_BUILDING_KEYS,
                                   TOWN_BUILDING_NAMES):
                enabled = "Yes" if bkey in tc_buildings else "No"
                fields.append(
                    [bname, f"town_{i}_bldg_{bkey}", enabled,
                     "choice", True])
            town_children.append({
                "label": tname,
                "icon": "T",
                "fields": fields,
            })
        n_towns = len(towns)
        sections.append({
            "label": "Towns",
            "icon": "F",
            "folder": "towns",
            "children": town_children,
            "subtitle": (f"{n_towns} town{'s' if n_towns != 1 else ''}"
                         if n_towns else "none"),
        })

        # 4) Dungeons folder
        from src.module_loader import QUEST_TYPE_NAMES, QUEST_TYPE_KEYS
        dungeons = manifest.get("progression", {}).get(
            "key_dungeons", [])
        dungeon_children = []
        _TORCH_DENSITY_NAMES = {"high": "High", "medium": "Medium",
                                "low": "Low"}
        for i, dung in enumerate(dungeons):
            dname = dung.get("name", f"Dungeon {i+1}")
            n_levels = len(dung.get("levels", []))
            td_raw = dung.get("torch_density", "medium")
            td_display = _TORCH_DENSITY_NAMES.get(td_raw, "Medium")
            dungeon_children.append({
                "label": dname,
                "icon": "D",
                "dung_idx": i,
                "fields": [
                    ["Name", f"dung_{i}_name", dname, "text", True],
                    ["Description", f"dung_{i}_desc",
                     dung.get("description", ""), "text", True],
                    ["Torch Density", f"dung_{i}_tdensity",
                     td_display, "choice", True],
                ],
                "subtitle": (f"{n_levels} level{'s' if n_levels != 1 else ''}"
                             if n_levels > 0 else "no levels"),
            })
        n_dungeons = len(dungeons)
        sections.append({
            "label": "Dungeons",
            "icon": "F",
            "folder": "dungeons",
            "children": dungeon_children,
            "subtitle": (f"{n_dungeons} dungeon{'s' if n_dungeons != 1 else ''}"
                         if n_dungeons else "none"),
        })

        # 5) Quests folder
        town_name_list = [t.get("name", f"Town {j+1}")
                          for j, t in enumerate(towns)]
        self._module_edit_town_names = town_name_list
        quest_children = []
        for i, dung in enumerate(dungeons):
            dname = dung.get("name", f"Dungeon {i+1}")
            fields = self._quest_fields_for_type(
                i, dung, town_name_list)
            quest_children.append({
                "label": f"{dname} Quest",
                "icon": "Q",
                "quest_idx": i,
                "fields": fields,
            })
        n_quests = len(dungeons)
        sections.append({
            "label": "Quests",
            "icon": "F",
            "folder": "quests",
            "children": quest_children,
            "subtitle": (f"{n_quests} quest{'s' if n_quests != 1 else ''}"
                         if n_quests else "none"),
        })

        # 6) Starting Loot section
        starting_loot = manifest.get("progression", {}).get(
            "starting_loot", [])
        n_loot = len(starting_loot)
        sections.append({
            "label": "Starting Loot",
            "icon": "S",
            "is_loot": True,
            "fields": [],  # fields built dynamically when drilled into
            "subtitle": (f"{n_loot} item{'s' if n_loot != 1 else ''}"
                         if n_loot > 0 else "no items"),
        })

        # 7) Unique Tiles section
        unique_tiles_data = manifest.get("unique_tiles", {})
        n_utiles = len(unique_tiles_data)
        sections.append({
            "label": "Unique Tiles",
            "icon": "U",
            "is_unique_tiles": True,
            "fields": [],  # fields built dynamically when drilled into
            "subtitle": (f"{n_utiles} tile{'s' if n_utiles != 1 else ''}"
                         if n_utiles > 0 else "no tiles"),
        })

        self.module_edit_sections = sections
        self.module_edit_section_cursor = 0
        self.module_edit_section_scroll = 0
        self.module_edit_level = 0
        # Clear field-level state
        self.module_edit_fields = []
        self.module_edit_field = 0
        self.module_edit_buffer = ""
        self.module_edit_scroll = 0
        # Clear navigation stack and dungeon level data
        self.module_edit_nav_stack = []
        self._module_edit_folder_label = ""
        self.module_edit_active_dung = -1
        self.module_edit_active_level = -1
        # Starting loot data for editing
        self.module_edit_starting_loot = list(starting_loot)
        self.module_edit_in_loot = False
        # Unique tiles data for editing
        self.module_edit_unique_tiles = [
            {"id": tid, **tdef}
            for tid, tdef in unique_tiles_data.items()
        ]
        self.module_edit_in_unique_tiles = False
        # Store dungeon levels for editing
        self.module_edit_dungeon_levels = {}
        for i, dung in enumerate(dungeons):
            self.module_edit_dungeon_levels[i] = list(
                dung.get("levels", []))

    def _quest_fields_for_type(self, quest_idx, dung, town_name_list):
        """Return the field list for a quest section based on quest type.

        Only fields relevant to the selected quest type are shown:
        - Retrieve: Key/Artifact, Objective, Hint, Exit Portal
        - Kill: Kill Target, Kill Count, Exit Portal
        - Gnome Machine: Keys Needed, Gnome Town, Objective, Hint
        """
        from src.module_loader import QUEST_TYPE_NAMES, QUEST_TYPE_KEYS
        i = quest_idx
        qt_key = dung.get("quest_type", "retrieve")
        try:
            qt_display = QUEST_TYPE_NAMES[
                QUEST_TYPE_KEYS.index(qt_key)]
        except (ValueError, IndexError):
            qt_display = QUEST_TYPE_NAMES[0]

        fields = [
            ["Quest Type", f"quest_{i}_qtype",
             qt_display, "choice", True],
        ]
        if qt_key == "retrieve":
            fields += [
                ["Key / Artifact", f"quest_{i}_key",
                 dung.get("key_name", "Key"), "text", True],
                ["Objective", f"quest_{i}_obj",
                 dung.get("quest_objective", ""), "text", True],
                ["Hint", f"quest_{i}_hint",
                 dung.get("quest_hint", ""), "text", True],
                ["Exit Portal", f"quest_{i}_exitportal",
                 "Yes" if dung.get("exit_portal", True) else "No",
                 "choice", True],
            ]
        elif qt_key == "kill":
            fields += [
                ["Kill Target", f"quest_{i}_ktarget",
                 dung.get("kill_target", ""), "choice", True],
                ["Kill Count", f"quest_{i}_kcount",
                 str(dung.get("kill_count", 0)), "int", True],
                ["Objective", f"quest_{i}_obj",
                 dung.get("quest_objective", ""), "text", True],
                ["Hint", f"quest_{i}_hint",
                 dung.get("quest_hint", ""), "text", True],
                ["Exit Portal", f"quest_{i}_exitportal",
                 "Yes" if dung.get("exit_portal", True) else "No",
                 "choice", True],
            ]
        elif qt_key == "gnome_machine":
            # Determine current gnome town selection
            gnome_town = dung.get("gnome_town", "")
            if not gnome_town and town_name_list:
                gnome_town = town_name_list[0]
            fields += [
                ["Keys Needed", f"quest_{i}_keysneeded",
                 str(dung.get("keys_needed", 1)), "int", True],
                ["Gnome Town", f"quest_{i}_gnometown",
                 gnome_town, "choice", True],
                ["Key / Artifact", f"quest_{i}_key",
                 dung.get("key_name", "Key"), "text", True],
                ["Objective", f"quest_{i}_obj",
                 dung.get("quest_objective", ""), "text", True],
                ["Hint", f"quest_{i}_hint",
                 dung.get("quest_hint", ""), "text", True],
            ]
        return fields

    def _on_quest_type_changed(self, field_key):
        """Rebuild the quest section fields after the quest type is cycled.

        Preserves any shared field values (like Objective / Hint) from
        the old field list while switching to the appropriate set of
        fields for the newly selected quest type.
        """
        from src.module_loader import QUEST_TYPE_NAMES, QUEST_TYPE_KEYS
        # Parse quest index from the field key (quest_<i>_qtype)
        parts = field_key.split("_")
        try:
            quest_idx = int(parts[1])
        except (IndexError, ValueError):
            return
        # Map display name → internal key
        new_display = self.module_edit_buffer
        try:
            qt_key = QUEST_TYPE_KEYS[QUEST_TYPE_NAMES.index(new_display)]
        except (ValueError, IndexError):
            qt_key = "retrieve"
        # Collect current field values so we can carry over shared ones
        old_vals = {}
        for entry in self.module_edit_fields:
            old_vals[entry[1]] = entry[2]
        # Build a dummy dung dict from old values for the helper
        i = quest_idx
        dung = {
            "quest_type": qt_key,
            "key_name": old_vals.get(f"quest_{i}_key", "Key"),
            "kill_target": old_vals.get(f"quest_{i}_ktarget", ""),
            "kill_count": int(old_vals.get(f"quest_{i}_kcount", "0")
                              or "0"),
            "keys_needed": int(old_vals.get(f"quest_{i}_keysneeded", "1")
                               or "1"),
            "gnome_town": old_vals.get(f"quest_{i}_gnometown", ""),
            "quest_objective": old_vals.get(f"quest_{i}_obj", ""),
            "quest_hint": old_vals.get(f"quest_{i}_hint", ""),
            "exit_portal": old_vals.get(
                f"quest_{i}_exitportal", "Yes") == "Yes",
        }
        town_names = getattr(self, "_module_edit_town_names", [])
        new_fields = self._quest_fields_for_type(
            quest_idx, dung, town_names)
        # Replace the fields in both the active list and the section
        self.module_edit_fields[:] = new_fields
        # Also update the section object so commit gathers the right keys
        # (may be in current sections, folder children, or nav stack)
        def _update_quest_sec(sec_list):
            for sec in sec_list:
                if sec.get("quest_idx") == quest_idx:
                    sec["fields"] = new_fields
                    return True
                for child in sec.get("children", []):
                    if child.get("quest_idx") == quest_idx:
                        child["fields"] = new_fields
                        return True
            return False
        _update_quest_sec(self.module_edit_sections)
        for stack_entry in getattr(
                self, "module_edit_nav_stack", []):
            _update_quest_sec(stack_entry[0])
        # Reset cursor to the first field (Quest Type) and refresh buffer
        self.module_edit_field = 0
        self.module_edit_buffer = new_fields[0][2]

    def _enter_section_fields(self):
        """Drill into the selected section's fields for editing."""
        sec = self.module_edit_sections[self.module_edit_section_cursor]

        # ── Folder sections drill into child section list ──
        if sec.get("folder"):
            self._enter_folder(sec)
            return

        # ── Dungeon sections drill into a sub-section browser ──
        if sec.get("icon") == "D" and sec.get("dung_idx") is not None:
            dung_idx = sec["dung_idx"]
            self._enter_dungeon_sub(dung_idx)
            return

        # ── Level sections drill into encounter fields ──
        if sec.get("icon") == "L" and sec.get("level_idx") is not None:
            dung_idx = self.module_edit_active_dung
            level_idx = sec["level_idx"]
            self._enter_level_encounters(dung_idx, level_idx)
            return

        # ── Starting Loot section drills into loot field editor ──
        if sec.get("is_loot"):
            self._enter_loot_fields()
            return

        # ── Unique Tiles section drills into unique tile field editor ──
        if sec.get("is_unique_tiles"):
            self._enter_unique_tiles_fields()
            return

        # ── Properties and other sections: flat field editor ──
        self.module_edit_fields = sec["fields"]
        self.module_edit_field = 0
        self.module_edit_scroll = 0
        self.module_edit_level = 1
        # Find first editable field
        self.module_edit_field = self._next_editable_field(0)
        if self.module_edit_fields:
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]

    def _enter_folder(self, sec):
        """Push the current section list and show a folder's children."""
        self.module_edit_nav_stack.append((
            self.module_edit_sections,
            self.module_edit_section_cursor,
            self.module_edit_section_scroll,
            getattr(self, "_module_edit_folder_label", ""),
        ))
        self.module_edit_sections = list(sec.get("children", []))
        self.module_edit_section_cursor = 0
        self.module_edit_section_scroll = 0
        self.module_edit_level = 0
        # Store folder name for breadcrumb display
        self._module_edit_folder_label = sec.get("label", "")

    def _enter_dungeon_sub(self, dung_idx):
        """Push current section browser and show dungeon sub-sections."""
        # Push current state onto nav stack (with current folder label)
        self.module_edit_nav_stack.append((
            self.module_edit_sections,
            self.module_edit_section_cursor,
            self.module_edit_section_scroll,
            getattr(self, "_module_edit_folder_label", ""),
        ))
        # Remember dungeon name for breadcrumb
        sec = self.module_edit_sections[self.module_edit_section_cursor]
        self._module_edit_folder_label = sec.get("label", "Dungeon")
        self.module_edit_active_dung = dung_idx
        self._rebuild_dungeon_sub_sections(dung_idx)

    def _rebuild_dungeon_sub_sections(self, dung_idx):
        """Build the sub-section list for a dungeon (Properties + Levels)."""
        # Find the original dungeon section to get its property fields
        parent_sec = None
        for sec in self.module_edit_nav_stack[-1][0]:
            if sec.get("dung_idx") == dung_idx:
                parent_sec = sec
                break

        sub_sections = []
        # 1) Properties section
        sub_sections.append({
            "label": "Properties",
            "icon": ">",
            "fields": parent_sec["fields"] if parent_sec else [],
        })

        # 2) One section per dungeon level
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        for li, level in enumerate(levels):
            lname = level.get("name", f"Floor {li + 1}")
            enc_count = len(level.get("encounters", []))
            sub_sections.append({
                "label": lname,
                "icon": "L",
                "level_idx": li,
                "fields": [],  # built on drill-in
                "subtitle": f"{enc_count} encounter{'s' if enc_count != 1 else ''}",
            })

        # 3) [+] Add Level action
        sub_sections.append({
            "label": "[+] Add Level",
            "icon": "+",
            "fields": [],
            "action": "add_level",
        })

        self.module_edit_sections = sub_sections
        self.module_edit_section_cursor = 0
        self.module_edit_section_scroll = 0
        # Stay at level 0 (section browser)
        self.module_edit_level = 0

    def _enter_level_encounters(self, dung_idx, level_idx):
        """Drill into a dungeon level to edit its encounters."""
        self.module_edit_active_level = level_idx
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            return
        level = levels[level_idx]
        encounters = level.get("encounters", [])

        # Build field list for encounters
        fields = []
        # Level name
        fields.append(["Level Name", f"lvl_{level_idx}_name",
                        level.get("name", f"Floor {level_idx + 1}"),
                        "text", True])
        # Include random encounters toggle
        fields.append(["Random Encounters",
                        f"lvl_{level_idx}_randenc",
                        "Yes" if level.get("random_encounters", True)
                        else "No",
                        "choice", True])
        # Torch density per level
        _td_map = {"high": "High", "medium": "Medium", "low": "Low"}
        td_raw = level.get("torch_density", "medium")
        fields.append(["Torch Density",
                        f"lvl_{level_idx}_tdensity",
                        _td_map.get(td_raw, "Medium"),
                        "choice", True])

        for ei, enc in enumerate(encounters):
            # Section header for each encounter
            fields.append([f"-- Encounter {ei + 1} --",
                           f"lvl_{level_idx}_enc_{ei}_hdr",
                           "", "section", False])
            fields.append(["Monster", f"lvl_{level_idx}_enc_{ei}_mon",
                           enc.get("monster", "Giant Rat"),
                           "choice", True])
            fields.append(["Count", f"lvl_{level_idx}_enc_{ei}_cnt",
                           str(enc.get("count", 1)),
                           "int", True])

        self.module_edit_fields = fields
        self.module_edit_field = 0
        self.module_edit_scroll = 0
        self.module_edit_level = 1
        self.module_edit_field = self._next_editable_field(0)
        if self.module_edit_fields:
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]

    def _leave_section_fields(self):
        """Go back from field editing to the section browser."""
        # Persist any in-progress buffer back to the field
        if self.module_edit_fields:
            entry = self.module_edit_fields[self.module_edit_field]
            entry[2] = self.module_edit_buffer

        # If we were editing encounters, save them back to level data
        if self.module_edit_active_level >= 0:
            self._save_encounter_fields_to_level()
            self.module_edit_active_level = -1

        # If we were editing loot, save back to in-memory loot list
        if self.module_edit_in_loot:
            self._save_loot_fields()
            self.module_edit_in_loot = False

        # If we were editing unique tiles, save back to in-memory list
        if self.module_edit_in_unique_tiles:
            self._save_unique_tiles_fields()
            self.module_edit_in_unique_tiles = False

        self.module_edit_level = 0

    def _save_encounter_fields_to_level(self):
        """Persist encounter field edits back to the in-memory level data."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            return
        level = levels[level_idx]

        # Read back level name, random encounters flag, and torch density
        for entry in self.module_edit_fields:
            if entry[1] == f"lvl_{level_idx}_name":
                level["name"] = entry[2]
            elif entry[1] == f"lvl_{level_idx}_randenc":
                level["random_encounters"] = (entry[2] == "Yes")
            elif entry[1] == f"lvl_{level_idx}_tdensity":
                level["torch_density"] = entry[2].lower()

        # Read back encounters
        encounters = []
        ei = 0
        while True:
            mon_key = f"lvl_{level_idx}_enc_{ei}_mon"
            cnt_key = f"lvl_{level_idx}_enc_{ei}_cnt"
            mon_val = None
            cnt_val = None
            for entry in self.module_edit_fields:
                if entry[1] == mon_key:
                    mon_val = entry[2]
                elif entry[1] == cnt_key:
                    cnt_val = entry[2]
            if mon_val is None:
                break
            encounters.append({
                "monster": mon_val,
                "count": int(cnt_val) if cnt_val else 1,
            })
            ei += 1
        level["encounters"] = encounters

    def _leave_dungeon_sub(self):
        """Pop the nav stack to return from sub-sections or folder."""
        if self.module_edit_nav_stack:
            prev = self.module_edit_nav_stack.pop()
            self.module_edit_sections = prev[0]
            self.module_edit_section_cursor = prev[1]
            self.module_edit_section_scroll = prev[2]
            # Restore the breadcrumb label from the stack
            self._module_edit_folder_label = (
                prev[3] if len(prev) > 3 else "")
        else:
            self._module_edit_folder_label = ""
        self.module_edit_active_dung = -1
        self.module_edit_active_level = -1
        self.module_edit_level = 0

    def _add_dungeon_level(self):
        """Add a new level to the active dungeon."""
        dung_idx = self.module_edit_active_dung
        if dung_idx < 0:
            return
        levels = self.module_edit_dungeon_levels.setdefault(dung_idx, [])
        floor_num = len(levels) + 1
        levels.append({
            "name": f"Floor {floor_num}",
            "encounters": [{"monster": "Giant Rat", "count": 1}],
            "random_encounters": True,
        })
        # Rebuild sub-sections to show the new level
        self._rebuild_dungeon_sub_sections(dung_idx)
        # Move cursor to the newly added level
        # (it's the second-to-last entry, before [+] Add Level)
        self.module_edit_section_cursor = max(
            0, len(self.module_edit_sections) - 2)
        self._adjust_section_scroll()

    def _remove_dungeon_level(self, level_idx):
        """Remove a level from the active dungeon."""
        dung_idx = self.module_edit_active_dung
        if dung_idx < 0:
            return
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if 0 <= level_idx < len(levels):
            levels.pop(level_idx)
            # Rebuild sub-sections
            self._rebuild_dungeon_sub_sections(dung_idx)
            # Clamp cursor
            n = len(self.module_edit_sections)
            if self.module_edit_section_cursor >= n:
                self.module_edit_section_cursor = max(0, n - 1)
            self._adjust_section_scroll()

    def _add_encounter_to_level(self):
        """Add a new encounter to the active dungeon level."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        if dung_idx < 0 or level_idx < 0:
            return
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx >= len(levels):
            return
        # First save current field edits
        self._save_encounter_fields_to_level()
        # Add new encounter
        levels[level_idx].setdefault("encounters", []).append(
            {"monster": "Giant Rat", "count": 1})
        # Rebuild encounter fields
        self._enter_level_encounters(dung_idx, level_idx)
        # Move to last encounter's monster field
        if self.module_edit_fields:
            self.module_edit_field = max(
                0, len(self.module_edit_fields) - 2)
            self.module_edit_field = self._next_editable_field(0)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()

    def _remove_encounter_from_level(self):
        """Remove the currently selected encounter from the level."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        if dung_idx < 0 or level_idx < 0:
            return
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx >= len(levels):
            return
        level = levels[level_idx]
        encounters = level.get("encounters", [])
        if len(encounters) <= 1:
            return  # Keep at least one encounter

        # Figure out which encounter the cursor is on
        # Fields: [level_name, (hdr, mon, cnt) * N]
        # After level_name, groups of 3 per encounter
        cursor = self.module_edit_field
        if cursor <= 0:
            enc_idx = 0  # on level name — remove first
        else:
            enc_idx = (cursor - 1) // 3  # 3 fields per encounter
        enc_idx = min(enc_idx, len(encounters) - 1)

        # Save current edits first
        self._save_encounter_fields_to_level()
        # Remove the encounter
        encounters.pop(enc_idx)
        level["encounters"] = encounters
        # Rebuild encounter fields
        self._enter_level_encounters(dung_idx, level_idx)

    # ── Starting Loot editing ─────────────────────────────────────

    def _enter_loot_fields(self):
        """Build field list for editing starting loot items."""
        self.module_edit_in_loot = True
        loot = self.module_edit_starting_loot
        fields = []
        for li, entry in enumerate(loot):
            fields.append([f"-- Item {li + 1} --",
                           f"loot_{li}_hdr", "", "section", False])
            fields.append(["Item", f"loot_{li}_item",
                           entry.get("item", "Healing Herb"),
                           "choice", True])
            fields.append(["Qty", f"loot_{li}_qty",
                           str(entry.get("count", 1)),
                           "int", True])
        self.module_edit_fields = fields
        self.module_edit_field = 0
        self.module_edit_scroll = 0
        self.module_edit_level = 1
        self.module_edit_field = self._next_editable_field(0)
        if self.module_edit_fields:
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]

    def _save_loot_fields(self):
        """Persist loot field edits back to the in-memory loot list."""
        loot = []
        li = 0
        while True:
            item_key = f"loot_{li}_item"
            qty_key = f"loot_{li}_qty"
            item_val = None
            qty_val = None
            for entry in self.module_edit_fields:
                if entry[1] == item_key:
                    item_val = entry[2]
                elif entry[1] == qty_key:
                    qty_val = entry[2]
            if item_val is None:
                break
            loot.append({
                "item": item_val,
                "count": max(1, int(qty_val)) if qty_val else 1,
            })
            li += 1
        self.module_edit_starting_loot = loot

    def _add_loot_item(self):
        """Add a new item to the starting loot list."""
        # Save current field edits first
        if self.module_edit_fields:
            entry = self.module_edit_fields[self.module_edit_field]
            entry[2] = self.module_edit_buffer
        self._save_loot_fields()
        self.module_edit_starting_loot.append(
            {"item": "Healing Herb", "count": 1})
        self._enter_loot_fields()
        # Move cursor to the new item
        if self.module_edit_fields:
            self.module_edit_field = max(
                0, len(self.module_edit_fields) - 2)
            self.module_edit_field = self._next_editable_field(0)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()

    def _remove_loot_item(self):
        """Remove the currently selected loot item."""
        loot = self.module_edit_starting_loot
        if len(loot) <= 0:
            return  # Nothing to remove
        # Save current edits
        if self.module_edit_fields:
            entry = self.module_edit_fields[self.module_edit_field]
            entry[2] = self.module_edit_buffer
        self._save_loot_fields()
        loot = self.module_edit_starting_loot
        if not loot:
            return
        # Figure out which loot item the cursor is on
        # Fields: (hdr, item, qty) * N — groups of 3
        cursor = self.module_edit_field
        loot_idx = cursor // 3
        loot_idx = min(loot_idx, len(loot) - 1)
        loot.pop(loot_idx)
        self.module_edit_starting_loot = loot
        if loot:
            self._enter_loot_fields()
        else:
            # No items left — rebuild empty field list
            self.module_edit_fields = []
            self.module_edit_field = 0
            self.module_edit_buffer = ""

    # ── Unique Tiles editing ─────────────────────────────────────

    # Category and interact_type choice lists for the editor
    _UTILE_CATEGORIES = [
        "landmark", "portal", "secret", "lore", "npc", "hazard",
        "trap", "quest", "event", "rest", "dungeon_feature",
    ]
    _UTILE_INTERACT_TYPES = [
        "message", "heal", "restore_mp", "buff", "loot", "damage",
        "trap", "teleport", "enter_dungeon", "encounter", "dialogue",
        "quest_trigger", "sacrifice", "wish", "rest", "obstacle", "multi",
    ]
    _UTILE_BASE_TILES = [
        "grass", "forest", "sand", "path", "mountain",
        "dungeon_floor", "floor",
    ]

    def _enter_unique_tiles_fields(self):
        """Build field list for editing unique tiles."""
        self.module_edit_in_unique_tiles = True
        tiles = self.module_edit_unique_tiles
        fields = []
        for ti, utile in enumerate(tiles):
            tname = utile.get("name", f"Tile {ti+1}")
            fields.append([f"-- {tname} --",
                           f"utile_{ti}_hdr", "", "section", False])
            fields.append(["ID", f"utile_{ti}_id",
                           utile.get("id", ""), "text", True])
            fields.append(["Name", f"utile_{ti}_name",
                           tname, "text", True])
            fields.append(["Description", f"utile_{ti}_desc",
                           utile.get("description", ""), "text", True])
            fields.append(["Visible", f"utile_{ti}_visible",
                           "Yes" if utile.get("visible", False) else "No",
                           "choice", True])
            fields.append(["Walkable", f"utile_{ti}_walkable",
                           "Yes" if utile.get("walkable", True) else "No",
                           "choice", True])
            fields.append(["Base Tile", f"utile_{ti}_basetile",
                           utile.get("base_tile", "grass"),
                           "choice", True])
            fields.append(["Category", f"utile_{ti}_category",
                           utile.get("category", "landmark"),
                           "choice", True])
            fields.append(["Interact Type", f"utile_{ti}_interact",
                           utile.get("interact_type", "message"),
                           "choice", True])
            fields.append(["Interact Text", f"utile_{ti}_itext",
                           utile.get("interact_text", ""), "text", True])
        self.module_edit_fields = fields
        self.module_edit_field = 0
        self.module_edit_scroll = 0
        self.module_edit_level = 1
        self.module_edit_field = self._next_editable_field(0)
        if self.module_edit_fields:
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]

    def _save_unique_tiles_fields(self):
        """Persist unique tile field edits back to in-memory list."""
        tiles = []
        ti = 0
        while True:
            id_key = f"utile_{ti}_id"
            id_val = None
            vals = {}
            for entry in self.module_edit_fields:
                k = entry[1]
                if k == id_key:
                    id_val = entry[2]
                elif k.startswith(f"utile_{ti}_"):
                    suffix = k[len(f"utile_{ti}_"):]
                    vals[suffix] = entry[2]
            if id_val is None:
                break
            tiles.append({
                "id": id_val,
                "name": vals.get("name", ""),
                "description": vals.get("desc", ""),
                "visible": vals.get("visible", "No") == "Yes",
                "walkable": vals.get("walkable", "Yes") == "Yes",
                "base_tile": vals.get("basetile", "grass"),
                "category": vals.get("category", "landmark"),
                "interact_type": vals.get("interact", "message"),
                "interact_text": vals.get("itext", ""),
                "interact_data": {},
            })
            ti += 1
        self.module_edit_unique_tiles = tiles

    def _add_unique_tile(self):
        """Add a new unique tile to the list."""
        if self.module_edit_fields:
            entry = self.module_edit_fields[self.module_edit_field]
            entry[2] = self.module_edit_buffer
        self._save_unique_tiles_fields()
        n = len(self.module_edit_unique_tiles)
        self.module_edit_unique_tiles.append({
            "id": f"new_tile_{n + 1}",
            "name": f"New Tile {n + 1}",
            "description": "A mysterious feature.",
            "visible": False,
            "walkable": True,
            "base_tile": "grass",
            "category": "lore",
            "interact_type": "message",
            "interact_text": "You notice something unusual here.",
            "interact_data": {},
        })
        self._enter_unique_tiles_fields()
        # Move cursor to the new tile
        if self.module_edit_fields:
            # Jump to the last tile's first editable field (ID)
            self.module_edit_field = max(
                0, len(self.module_edit_fields) - 9)
            self.module_edit_field = self._next_editable_field(0)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()

    def _remove_unique_tile(self):
        """Remove the currently selected unique tile."""
        tiles = self.module_edit_unique_tiles
        if not tiles:
            return
        if self.module_edit_fields:
            entry = self.module_edit_fields[self.module_edit_field]
            entry[2] = self.module_edit_buffer
        self._save_unique_tiles_fields()
        tiles = self.module_edit_unique_tiles
        if not tiles:
            return
        # Each tile uses 10 fields (hdr + 9 editable)
        cursor = self.module_edit_field
        tile_idx = cursor // 10
        tile_idx = min(tile_idx, len(tiles) - 1)
        tiles.pop(tile_idx)
        self.module_edit_unique_tiles = tiles
        if tiles:
            self._enter_unique_tiles_fields()
        else:
            self.module_edit_fields = []
            self.module_edit_field = 0
            self.module_edit_buffer = ""

    def _next_editable_field(self, direction):
        """Move to the next editable field in the given direction (+1/-1).

        Skips read-only fields.  Wraps around.  If no editable field
        exists in that direction, stays put.  direction=0 finds the
        first editable field from the current position forward.
        """
        n = len(self.module_edit_fields)
        if n == 0:
            return 0
        step = direction if direction != 0 else 1
        start = self.module_edit_field
        # When direction is 0, check the current field first
        if direction == 0 and self.module_edit_fields[start][4]:
            return start
        for _ in range(n):
            candidate = (start + step) % n
            if self.module_edit_fields[candidate][4]:  # editable?
                return candidate
            start = candidate
        return self.module_edit_field  # nothing editable found

    def _adjust_module_edit_scroll(self):
        """Auto-scroll the edit form to keep the active field visible."""
        CHARS_PER_LINE = 49
        y = 0
        field_h = 0
        for i, entry in enumerate(self.module_edit_fields):
            field_type = entry[3] if len(entry) > 3 else "text"
            val = entry[2] or ""
            if field_type == "text" and len(val) > CHARS_PER_LINE:
                nlines = min(4, max(1,
                    (len(val) + CHARS_PER_LINE - 1) // CHARS_PER_LINE))
                extra = (nlines - 1) * 16
            else:
                extra = 0
            h = 18 + 28 + extra
            if i == self.module_edit_field:
                field_h = h
                break
            y += h
        visible_height = 480
        if y < self.module_edit_scroll:
            self.module_edit_scroll = max(0, y - 10)
        elif y + field_h + 10 > self.module_edit_scroll + visible_height:
            self.module_edit_scroll = y + field_h + 10 - visible_height

    def _handle_module_edit_input(self, event):
        """Handle input while editing module (hierarchical navigation)."""
        # ── Create-new mode uses flat field list (no hierarchy) ──
        if self.module_edit_is_new:
            self._handle_module_edit_input_flat(event)
            return

        # ── Level 0: section browser ──
        if self.module_edit_level == 0:
            self._handle_section_browser_input(event)
            return

        # ── Level 1: field editor within a section ──
        if event.key == pygame.K_ESCAPE:
            self._leave_section_fields()
            return
        if (event.key == pygame.K_s
                and event.mod & pygame.KMOD_CTRL):
            # Save from within field editor
            if self.module_edit_fields:
                entry = self.module_edit_fields[self.module_edit_field]
                entry[2] = self.module_edit_buffer
            self._commit_module_edit()
            return
        # Encounter add/remove (only when editing a dungeon level)
        if self.module_edit_active_level >= 0:
            if (event.key == pygame.K_a
                    and event.mod & pygame.KMOD_CTRL):
                self._add_encounter_to_level()
                return
            if event.key == pygame.K_DELETE:
                self._remove_encounter_from_level()
                return
        # Loot add/remove (only when editing starting loot)
        if self.module_edit_in_loot:
            if (event.key == pygame.K_a
                    and event.mod & pygame.KMOD_CTRL):
                self._add_loot_item()
                return
            if event.key == pygame.K_DELETE:
                self._remove_loot_item()
                return
        # Unique tile add/remove
        if self.module_edit_in_unique_tiles:
            if (event.key == pygame.K_a
                    and event.mod & pygame.KMOD_CTRL):
                self._add_unique_tile()
                return
            if event.key == pygame.K_DELETE:
                self._remove_unique_tile()
                return

        self._handle_field_editor_input(event)

    def _handle_section_browser_input(self, event):
        """Handle input at the section browser level (level 0)."""
        n = len(self.module_edit_sections)
        if event.key == pygame.K_ESCAPE:
            # If in a dungeon sub-browser, pop back up
            if self.module_edit_nav_stack:
                self._leave_dungeon_sub()
            else:
                self.module_edit_mode = False
                self.module_edit_is_new = False
                self.module_message = None
        elif event.key == pygame.K_LEFT:
            # Left also goes back from sub-browser
            if self.module_edit_nav_stack:
                self._leave_dungeon_sub()
        elif event.key == pygame.K_UP:
            self.module_edit_section_cursor = (
                (self.module_edit_section_cursor - 1) % n)
            self._adjust_section_scroll()
        elif event.key == pygame.K_DOWN:
            self.module_edit_section_cursor = (
                (self.module_edit_section_cursor + 1) % n)
            self._adjust_section_scroll()
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            sec = self.module_edit_sections[
                self.module_edit_section_cursor]
            # Handle action sections
            action = sec.get("action")
            if action == "add_level":
                self._add_dungeon_level()
            elif action == "remove_level":
                pass  # handled by 'd' key
            else:
                self._enter_section_fields()
        elif event.key == pygame.K_a:
            # 'A' to add a level (in dungeon sub) or encounter (in level)
            if (self.module_edit_nav_stack
                    and self.module_edit_active_dung >= 0):
                self._add_dungeon_level()
        elif event.key in (pygame.K_d, pygame.K_DELETE):
            # 'D' or Delete to remove current level
            if (self.module_edit_nav_stack
                    and self.module_edit_active_dung >= 0):
                sec = self.module_edit_sections[
                    self.module_edit_section_cursor]
                if sec.get("icon") == "L" and sec.get(
                        "level_idx") is not None:
                    self._remove_dungeon_level(sec["level_idx"])
        elif (event.key == pygame.K_s
              and event.mod & pygame.KMOD_CTRL):
            self._commit_module_edit()

    def _adjust_section_scroll(self):
        """Keep the section cursor visible in the section list."""
        row_h = 36
        visible_height = 480
        max_visible = visible_height // row_h
        cursor = self.module_edit_section_cursor
        if cursor < self.module_edit_section_scroll:
            self.module_edit_section_scroll = cursor
        elif cursor >= self.module_edit_section_scroll + max_visible:
            self.module_edit_section_scroll = cursor - max_visible + 1

    def _get_choices_for_field(self, key):
        """Return the list of valid choices for a choice-type field."""
        from src.module_loader import (WORLD_SIZE_NAMES,
                                       SEASON_NAMES,
                                       TIME_OF_DAY_NAMES,
                                       QUEST_TYPE_NAMES,
                                       KILL_QUEST_MONSTERS,
                                       ENCOUNTER_MONSTERS)
        if key == "world_size":
            return WORLD_SIZE_NAMES
        elif key == "season":
            return SEASON_NAMES
        elif key == "time_of_day":
            return TIME_OF_DAY_NAMES
        elif key.endswith("_qtype"):
            return QUEST_TYPE_NAMES
        elif key.endswith("_ktarget"):
            return [""] + KILL_QUEST_MONSTERS
        elif key.endswith("_mon"):
            return ENCOUNTER_MONSTERS
        elif key.endswith("_gnometown"):
            return getattr(self, "_module_edit_town_names", []) or ["(none)"]
        elif key.endswith("_tdensity"):
            return ["High", "Medium", "Low"]
        elif key.endswith("_exitportal"):
            return ["Yes", "No"]
        elif key == "innkeeper_quests":
            return ["Yes", "No"]
        elif key.endswith("_size") and key.startswith("town_"):
            from src.module_loader import TOWN_SIZE_NAMES
            return TOWN_SIZE_NAMES
        elif key.endswith("_style") and key.startswith("town_"):
            from src.module_loader import TOWN_STYLE_NAMES
            return TOWN_STYLE_NAMES
        elif "_bldg_" in key and key.startswith("town_"):
            return ["Yes", "No"]
        elif key.endswith("_randenc"):
            return ["Yes", "No"]
        elif key.endswith("_item") and key.startswith("loot_"):
            from src.module_loader import LOOT_ITEMS
            return LOOT_ITEMS
        # Unique tile choices
        elif key.endswith("_visible") and key.startswith("utile_"):
            return ["Yes", "No"]
        elif key.endswith("_walkable") and key.startswith("utile_"):
            return ["Yes", "No"]
        elif key.endswith("_basetile") and key.startswith("utile_"):
            return self._UTILE_BASE_TILES
        elif key.endswith("_category") and key.startswith("utile_"):
            return self._UTILE_CATEGORIES
        elif key.endswith("_interact") and key.startswith("utile_"):
            return self._UTILE_INTERACT_TYPES
        # No match

        return []

    def _handle_field_editor_input(self, event):
        """Handle input at the field editor level (level 1)."""
        if not self.module_edit_fields:
            # Empty field list (e.g. loot with no items) —
            # only ESC to go back is meaningful here.
            return
        field_entry = self.module_edit_fields[self.module_edit_field]
        field_type = field_entry[3] if len(field_entry) > 3 else "text"
        editable = field_entry[4] if len(field_entry) > 4 else True

        if event.key == pygame.K_UP:
            field_entry[2] = self.module_edit_buffer
            self.module_edit_field = self._next_editable_field(-1)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()
        elif event.key == pygame.K_DOWN:
            field_entry[2] = self.module_edit_buffer
            self.module_edit_field = self._next_editable_field(+1)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()
        elif not editable:
            return
        elif field_type == "choice":
            choices = self._get_choices_for_field(field_entry[1])
            if not choices:
                choices = [self.module_edit_buffer]
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                try:
                    idx = choices.index(self.module_edit_buffer)
                except ValueError:
                    idx = 0
                if event.key == pygame.K_RIGHT:
                    idx = (idx + 1) % len(choices)
                else:
                    idx = (idx - 1) % len(choices)
                self.module_edit_buffer = choices[idx]
                # When quest type changes, rebuild the field list
                if field_entry[1].endswith("_qtype"):
                    self._on_quest_type_changed(field_entry[1])
        elif field_type == "int":
            if event.key == pygame.K_BACKSPACE:
                self.module_edit_buffer = self.module_edit_buffer[:-1]
            elif event.key == pygame.K_LEFT:
                val = max(0, int(self.module_edit_buffer or "0") - 1)
                self.module_edit_buffer = str(val)
            elif event.key == pygame.K_RIGHT:
                val = int(self.module_edit_buffer or "0") + 1
                self.module_edit_buffer = str(val)
            elif event.unicode and event.unicode.isdigit():
                self.module_edit_buffer += event.unicode
        else:
            # text field
            if event.key == pygame.K_BACKSPACE:
                self.module_edit_buffer = self.module_edit_buffer[:-1]
            elif event.unicode and event.unicode.isprintable():
                self.module_edit_buffer += event.unicode

    def _handle_module_edit_input_flat(self, event):
        """Handle input for the flat create-new-module form."""
        if event.key == pygame.K_ESCAPE:
            self.module_edit_mode = False
            self.module_edit_is_new = False
            self.module_message = None
            return

        field_entry = self.module_edit_fields[self.module_edit_field]
        field_type = field_entry[3] if len(field_entry) > 3 else "text"
        editable = field_entry[4] if len(field_entry) > 4 else True

        if event.key == pygame.K_UP:
            field_entry[2] = self.module_edit_buffer
            self.module_edit_field = self._next_editable_field(-1)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()
        elif event.key == pygame.K_DOWN:
            field_entry[2] = self.module_edit_buffer
            self.module_edit_field = self._next_editable_field(+1)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()
        elif (event.key == pygame.K_s
              and event.mod & pygame.KMOD_CTRL):
            field_entry[2] = self.module_edit_buffer
            self._commit_module_edit()
        elif not editable:
            return
        elif field_type == "choice":
            choices = self._get_choices_for_field(field_entry[1])
            if not choices:
                choices = [self.module_edit_buffer]
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                try:
                    idx = choices.index(self.module_edit_buffer)
                except ValueError:
                    idx = 0
                if event.key == pygame.K_RIGHT:
                    idx = (idx + 1) % len(choices)
                else:
                    idx = (idx - 1) % len(choices)
                self.module_edit_buffer = choices[idx]
        elif field_type == "int":
            if event.key == pygame.K_BACKSPACE:
                self.module_edit_buffer = self.module_edit_buffer[:-1]
            elif event.key == pygame.K_LEFT:
                val = max(0, int(self.module_edit_buffer or "0") - 1)
                self.module_edit_buffer = str(val)
            elif event.key == pygame.K_RIGHT:
                val = int(self.module_edit_buffer or "0") + 1
                self.module_edit_buffer = str(val)
            elif event.unicode and event.unicode.isdigit():
                self.module_edit_buffer += event.unicode
        else:
            if event.key == pygame.K_BACKSPACE:
                self.module_edit_buffer = self.module_edit_buffer[:-1]
            elif event.unicode and event.unicode.isprintable():
                self.module_edit_buffer += event.unicode

    def _commit_module_edit(self):
        """Create a new module or save edits to an existing one."""
        # Persist any in-progress buffer before gathering
        if self.module_edit_level == 1 and self.module_edit_fields:
            entry = self.module_edit_fields[self.module_edit_field]
            entry[2] = self.module_edit_buffer
            # If editing encounters, save back to level data
            if self.module_edit_active_level >= 0:
                self._save_encounter_fields_to_level()
            # If editing loot, save back to in-memory loot list
            if self.module_edit_in_loot:
                self._save_loot_fields()
            # If editing unique tiles, save back to in-memory list
            if self.module_edit_in_unique_tiles:
                self._save_unique_tiles_fields()

        # Gather all field values into a dict.
        # For create-new, fields live in self.module_edit_fields.
        # For existing modules, fields are spread across ALL sections
        # including those on the nav stack.
        values = {}
        if self.module_edit_is_new:
            sources = [self.module_edit_fields]
        else:
            # Collect from nav stack (parent sections) + current sections
            all_sections = []
            for stack_entry in self.module_edit_nav_stack:
                all_sections.extend(stack_entry[0])
            all_sections.extend(self.module_edit_sections)
            # Flatten: also include children of folder sections
            expanded = []
            for s in all_sections:
                expanded.append(s)
                if s.get("children"):
                    expanded.extend(s["children"])
            sources = [s["fields"] for s in expanded
                       if s.get("fields")]
        for field_list in sources:
            for entry in field_list:
                key, value = entry[1], entry[2]
                if key in ("num_towns", "num_quests"):
                    values[key] = int(value) if value else 0
                else:
                    values[key] = value

        if self.module_edit_is_new:
            # ── Create new module with all settings ──
            from src.module_loader import create_module
            path = create_module(
                name=values.get("name", "New Module"),
                author=values.get("author", "Unknown"),
                description=values.get("description", ""),
                world_size=values.get("world_size", "Medium"),
                num_towns=values.get("num_towns", 1),
                num_quests=values.get("num_quests", 1),
                season=values.get("season", "Summer"),
                time_of_day=values.get("time_of_day", "Noon"),
            )
            self.module_edit_mode = False
            self.module_edit_is_new = False
            self._refresh_module_list()
            # Select the newly created module as the active module
            for i, mod in enumerate(self.module_list):
                if mod["path"] == path:
                    self.module_cursor = i
                    self._set_active_module(
                        mod["path"], mod["name"], mod["version"])
                    break
            self.module_message = "Module created and selected!"
            self.module_msg_timer = 2.0
        else:
            # ── Update existing module (full content) ──
            import json, os
            if not self.module_list:
                self.module_edit_mode = False
                return
            mod = self.module_list[self.module_cursor]
            manifest_path = os.path.join(mod["path"], "module.json")
            try:
                with open(manifest_path, "r") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                self.module_edit_mode = False
                self.module_message = "Update failed!"
                self.module_msg_timer = 2.0
                return

            # ── Metadata fields ──
            meta = data.setdefault("metadata", {})
            for key in ("name", "author", "description"):
                if key in values:
                    meta[key] = values[key]

            # ── Innkeeper quests toggle ──
            if "innkeeper_quests" in values:
                prog = data.setdefault("progression", {})
                prog["innkeeper_quests"] = (
                    values["innkeeper_quests"] == "Yes")

            # ── Town fields (town_<i>_<field>) ──
            from src.module_loader import (TOWN_SIZE_NAMES, TOWN_SIZE_KEYS,
                                           TOWN_STYLE_NAMES,
                                           TOWN_STYLE_KEYS,
                                           TOWN_BUILDING_KEYS)
            towns = data.get("world", {}).get("towns", [])
            town_field_map = {
                "name": "name",
                "desc": "description",
            }
            for key, val in values.items():
                if not key.startswith("town_"):
                    continue
                parts = key.split("_", 2)   # town, <i>, <field>
                if len(parts) < 3:
                    continue
                try:
                    idx = int(parts[1])
                except ValueError:
                    continue
                suffix = parts[2]
                if not (0 <= idx < len(towns)):
                    continue
                json_key = town_field_map.get(suffix)
                if json_key:
                    towns[idx][json_key] = val
                elif suffix == "size":
                    # Convert display name to key
                    tc = towns[idx].setdefault("town_config", {})
                    try:
                        si = TOWN_SIZE_NAMES.index(val)
                        tc["size"] = TOWN_SIZE_KEYS[si]
                    except (ValueError, IndexError):
                        tc["size"] = "medium"
                elif suffix == "style":
                    tc = towns[idx].setdefault("town_config", {})
                    try:
                        si = TOWN_STYLE_NAMES.index(val)
                        tc["style"] = TOWN_STYLE_KEYS[si]
                    except (ValueError, IndexError):
                        tc["style"] = "medieval"
                elif suffix.startswith("bldg_"):
                    bldg_key = suffix[5:]  # strip "bldg_"
                    if bldg_key in TOWN_BUILDING_KEYS:
                        tc = towns[idx].setdefault("town_config", {})
                        blist = tc.setdefault("buildings", [])
                        if val == "Yes" and bldg_key not in blist:
                            blist.append(bldg_key)
                        elif val == "No" and bldg_key in blist:
                            blist.remove(bldg_key)

            # ── Dungeon fields (dung_<i>_<field>) ──
            from src.module_loader import QUEST_TYPE_NAMES, QUEST_TYPE_KEYS
            dungeons = data.get("progression", {}).get(
                "key_dungeons", [])
            dung_field_map = {
                "name": "name",
                "desc": "description",
                "tdensity": "torch_density",
            }
            for key, val in values.items():
                if not key.startswith("dung_"):
                    continue
                parts = key.split("_", 2)   # dung, <i>, <field>
                if len(parts) < 3:
                    continue
                try:
                    idx = int(parts[1])
                except ValueError:
                    continue
                suffix = parts[2]
                json_key = dung_field_map.get(suffix)
                if json_key and 0 <= idx < len(dungeons):
                    # Torch density: convert display name to key
                    if suffix == "tdensity":
                        val = val.lower()
                    dungeons[idx][json_key] = val

            # ── Quest fields (quest_<i>_<field>) ──
            quest_field_map = {
                "key": "key_name",
                "obj": "quest_objective",
                "hint": "quest_hint",
                "ktarget": "kill_target",
            }
            for key, val in values.items():
                if not key.startswith("quest_"):
                    continue
                parts = key.split("_", 2)   # quest, <i>, <field>
                if len(parts) < 3:
                    continue
                try:
                    idx = int(parts[1])
                except ValueError:
                    continue
                suffix = parts[2]
                if suffix == "qtype":
                    try:
                        qi = QUEST_TYPE_NAMES.index(val)
                        if 0 <= idx < len(dungeons):
                            dungeons[idx]["quest_type"] = \
                                QUEST_TYPE_KEYS[qi]
                    except (ValueError, IndexError):
                        if 0 <= idx < len(dungeons):
                            dungeons[idx]["quest_type"] = "retrieve"
                elif suffix == "kcount":
                    if 0 <= idx < len(dungeons):
                        dungeons[idx]["kill_count"] = \
                            int(val) if val else 0
                elif suffix == "keysneeded":
                    if 0 <= idx < len(dungeons):
                        kn = int(val) if val else 1
                        dungeons[idx]["keys_needed"] = \
                            max(1, min(8, kn))
                elif suffix == "exitportal":
                    if 0 <= idx < len(dungeons):
                        dungeons[idx]["exit_portal"] = \
                            (val == "Yes")
                elif suffix == "gnometown":
                    if 0 <= idx < len(dungeons):
                        dungeons[idx]["gnome_town"] = val
                else:
                    json_key = quest_field_map.get(suffix)
                    if json_key and 0 <= idx < len(dungeons):
                        dungeons[idx][json_key] = val

            # ── Dungeon levels and encounters ──
            for dung_idx, levels_data in \
                    self.module_edit_dungeon_levels.items():
                if 0 <= dung_idx < len(dungeons):
                    dungeons[dung_idx]["levels"] = levels_data

            # ── Starting loot ──
            prog = data.setdefault("progression", {})
            if self.module_edit_starting_loot:
                prog["starting_loot"] = self.module_edit_starting_loot
            else:
                prog.pop("starting_loot", None)

            # ── Unique tiles ──
            ut_dict = {}
            for utile in self.module_edit_unique_tiles:
                tid = utile.get("id", "")
                if not tid:
                    continue
                ut_dict[tid] = {
                    "name": utile.get("name", ""),
                    "description": utile.get("description", ""),
                    "tile": None,
                    "visible": utile.get("visible", False),
                    "walkable": utile.get("walkable", True),
                    "base_tile": utile.get("base_tile", "grass"),
                    "category": utile.get("category", "landmark"),
                    "interact_type": utile.get("interact_type", "message"),
                    "interact_text": utile.get("interact_text", ""),
                    "interact_data": utile.get("interact_data", {}),
                }
            if ut_dict:
                data["unique_tiles"] = ut_dict
            else:
                data.pop("unique_tiles", None)

            # Write back
            try:
                with open(manifest_path, "w") as fh:
                    json.dump(data, fh, indent=2)
                ok = True
            except OSError:
                ok = False

            self.module_edit_mode = False
            self.module_edit_nav_stack = []
            self.module_edit_active_dung = -1
            self.module_edit_active_level = -1
            self.module_edit_in_loot = False
            self.module_edit_in_unique_tiles = False
            if ok:
                self.module_message = "Module updated!"
                self.module_msg_timer = 2.0
                self._refresh_module_list()
            else:
                self.module_message = "Update failed!"
                self.module_msg_timer = 2.0

    # ── Module / settings helpers ────────────────────────────────

    def _set_active_module(self, path, name, version):
        """Set the active module and persist the choice to config."""
        self.active_module_path = path
        self.active_module_name = name
        self.active_module_version = version
        self._config["active_module_path"] = path
        save_config(self._config)

    # ── Music / settings helpers ────────────────────────────────

    def _toggle_music(self):
        """Toggle music on/off, sync settings display, and persist."""
        muted = self.music.toggle_mute()
        self.settings_options[0]["value"] = not muted
        self._config["music_enabled"] = not muted
        save_config(self._config)

    def _cycle_soundtrack(self, direction=1):
        """Cycle through available soundtrack styles and apply immediately.

        direction: +1 for next, -1 for previous.
        """
        opt = self.settings_options[1]  # SOUNDTRACK entry
        choices = opt["choices"]
        cur_idx = choices.index(opt["value"]) if opt["value"] in choices else 0
        new_idx = (cur_idx + direction) % len(choices)
        new_style = choices[new_idx]
        opt["value"] = new_style
        self.music.set_style(new_style)
        self._config["soundtrack_style"] = new_style
        save_config(self._config)

    def _toggle_smite(self):
        """Toggle the Smite debug action in combat menus."""
        self.smite_enabled = not self.smite_enabled
        self.settings_options[2]["value"] = self.smite_enabled
        self._config["smite_enabled"] = self.smite_enabled
        save_config(self._config)

    def _toggle_start_equipment(self):
        """Toggle whether new games start with full equipment or minimal gear."""
        self.start_with_equipment = not self.start_with_equipment
        self.settings_options[3]["value"] = self.start_with_equipment
        self._config["start_with_equipment"] = self.start_with_equipment
        save_config(self._config)

    def _open_save_screen(self):
        """Switch settings view to the save-slot picker."""
        self.settings_mode = "save"
        self.save_load_cursor = 0
        self.save_load_message = None
        self.save_load_confirm_delete = False

    def _open_load_screen(self):
        """Switch settings view to the load-slot picker."""
        self.settings_mode = "load"
        self.save_load_cursor = 0
        self.save_load_message = None
        self.save_load_confirm_delete = False

    def _do_save(self, slot):
        """Save game to the given slot and show feedback."""
        ok = save_game(slot, self)
        if ok:
            self.save_load_message = f"Game saved to Slot {slot}!"
        else:
            self.save_load_message = "Save failed!"
        self.save_load_msg_timer = 2.0

    def _do_load(self, slot):
        """Load game from the given slot and show feedback."""
        ok = load_game(slot, self)
        if ok:
            self._game_started = True
            self.save_load_message = f"Loaded Slot {slot}!"
            self.save_load_msg_timer = 2.0
            # Close settings after a successful load
        else:
            self.save_load_message = "No save in that slot!"
            self.save_load_msg_timer = 2.0

    def _do_delete_save(self, slot):
        """Delete a save from the given slot and show feedback."""
        ok = delete_save(slot)
        if ok:
            self.save_load_message = f"Slot {slot} deleted."
        else:
            self.save_load_message = "Nothing to delete!"
        self.save_load_msg_timer = 2.0
        self.save_load_confirm_delete = False

    def _handle_game_over_input(self, event):
        """Handle input on the game over screen."""
        if event.type != pygame.KEYDOWN:
            return
        # Ignore input during the initial fade-in (first 2 seconds)
        if self.game_over_elapsed < 2.0:
            return
        if event.key == pygame.K_UP:
            self.game_over_cursor = (
                (self.game_over_cursor - 1) % len(self.game_over_options))
        elif event.key == pygame.K_DOWN:
            self.game_over_cursor = (
                (self.game_over_cursor + 1) % len(self.game_over_options))
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.game_over_options[self.game_over_cursor]["action"]()

    def change_state(self, state_name):
        """Switch to a different game state."""
        if self.current_state:
            self.current_state.exit()
        self.current_state = self.states[state_name]
        self.current_state.enter()
        # Switch music to match the new state
        self.music.play(state_name)

    # ── Input handlers ──────────────────────────────────────────

    def _handle_title_input(self, event):
        """Handle input on the title screen."""
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_UP:
            self.title_cursor = (
                (self.title_cursor - 1) % len(self.title_options))
        elif event.key == pygame.K_DOWN:
            self.title_cursor = (
                (self.title_cursor + 1) % len(self.title_options))
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.title_options[self.title_cursor]["action"]()

    def _handle_settings_input(self, event):
        """Handle input while the settings screen is open."""
        if event.type != pygame.KEYDOWN:
            return

        # --- Save/Load sub-screen ---
        if self.settings_mode in ("save", "load"):
            self._handle_save_load_input(event)
            return

        # --- Main settings ---
        if event.key in (pygame.K_m, pygame.K_ESCAPE):
            self.showing_settings = False
            self.settings_mode = "main"
            # Return to title screen if we came from there
            if getattr(self, '_title_settings_mode', False):
                self._title_settings_mode = False
                self.showing_title = True
                self.music.play("title")
        elif event.key == pygame.K_UP:
            self.settings_cursor = (
                (self.settings_cursor - 1) % len(self.settings_options))
        elif event.key == pygame.K_DOWN:
            self.settings_cursor = (
                (self.settings_cursor + 1) % len(self.settings_options))
        elif event.key == pygame.K_LEFT:
            opt = self.settings_options[self.settings_cursor]
            if opt["type"] == "choice":
                opt["action"](direction=-1)
        elif event.key == pygame.K_RIGHT:
            opt = self.settings_options[self.settings_cursor]
            if opt["type"] == "choice":
                opt["action"](direction=1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            opt = self.settings_options[self.settings_cursor]
            if opt["type"] == "toggle":
                opt["action"]()
            elif opt["type"] == "choice":
                opt["action"](direction=1)
            elif opt["type"] == "action":
                opt["action"]()

    def _handle_save_load_input(self, event):
        """Handle input in the save/load slot picker."""
        # ── Delete confirmation sub-state ──
        if self.save_load_confirm_delete:
            if event.key == pygame.K_y:
                slot = self.save_load_cursor + 1
                self._do_delete_save(slot)
            elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                self.save_load_confirm_delete = False
                self.save_load_message = None
            return

        if event.key == pygame.K_ESCAPE:
            # If we came from the title screen save/load option, go back to title
            if getattr(self, '_title_load_mode', False):
                self._title_load_mode = False
                self.showing_settings = False
                self.showing_title = True
                self.music.play("title")
            elif getattr(self, '_title_save_mode', False):
                self._title_save_mode = False
                self.showing_settings = False
                self.showing_title = True
                self.music.play("title")
            # If we came from the game over screen, go back to game over
            elif getattr(self, '_game_over_load_mode', False):
                self._game_over_load_mode = False
                self.showing_settings = False
                self.showing_game_over = True
            else:
                self.settings_mode = "main"
            self.save_load_message = None
            return
        if event.key == pygame.K_UP:
            self.save_load_cursor = (
                (self.save_load_cursor - 1) % NUM_SAVE_SLOTS)
        elif event.key == pygame.K_DOWN:
            self.save_load_cursor = (
                (self.save_load_cursor + 1) % NUM_SAVE_SLOTS)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            slot = self.save_load_cursor + 1  # 1-based
            if self.settings_mode == "save":
                self._do_save(slot)
            else:
                self._do_load(slot)
                # If load succeeded from title or game over, close everything
                if self.save_load_message and "Loaded" in self.save_load_message:
                    if getattr(self, '_title_load_mode', False):
                        self._title_load_mode = False
                        self.showing_settings = False
                    elif getattr(self, '_game_over_load_mode', False):
                        self._game_over_load_mode = False
                        self.showing_settings = False
        elif event.key == pygame.K_d and self.settings_mode == "load":
            # Only allow delete from the load screen
            slot = self.save_load_cursor + 1
            info = get_save_info(slot)
            if info is not None:
                self.save_load_confirm_delete = True
                self.save_load_message = f"Delete Slot {slot}?  Y = Yes  N = No"

    def run(self):
        """Main game loop."""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # delta time in seconds

            # --- Events ---
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    self.running = False

            if self.showing_title:
                # Title screen intercepts all input
                for event in events:
                    self._handle_title_input(event)
                self.title_elapsed += dt
            elif self.showing_char_create:
                for event in events:
                    self._handle_char_create_input(event)
                self._cc_elapsed += dt
                if self._cc_msg_timer > 0:
                    self._cc_msg_timer -= dt
                    if self._cc_msg_timer <= 0:
                        self._cc_message = None
            elif self.showing_form_party:
                for event in events:
                    self._handle_form_party_input(event)
                self._fp_elapsed += dt
                if self._fp_msg_timer > 0:
                    self._fp_msg_timer -= dt
                    if self._fp_msg_timer <= 0:
                        self._fp_message = None
            elif self.showing_modules:
                for event in events:
                    self._handle_module_input(event)
                # Tick module message timer
                if self.module_msg_timer > 0:
                    self.module_msg_timer -= dt
                    if self.module_msg_timer <= 0:
                        self.module_message = None
            elif self.showing_game_over:
                for event in events:
                    self._handle_game_over_input(event)
                self.game_over_elapsed += dt
            elif self.showing_quest_log:
                for event in events:
                    if event.type != pygame.KEYDOWN:
                        continue
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        self.showing_quest_log = False
                    elif event.key == pygame.K_UP:
                        self.quest_log_scroll = max(0, self.quest_log_scroll - 1)
                    elif event.key == pygame.K_DOWN:
                        self.quest_log_scroll += 1
            elif self.showing_settings:
                # Settings screen intercepts all input
                for event in events:
                    self._handle_settings_input(event)
                # Tick feedback message timer
                if self.save_load_msg_timer > 0:
                    self.save_load_msg_timer -= dt
                    if self.save_load_msg_timer <= 0:
                        self.save_load_message = None
            else:
                # Check for M key to open settings, 1-4 for character sheets
                for event in events:
                    if event.type != pygame.KEYDOWN:
                        continue
                    if event.key == pygame.K_q and not self.showing_quest_log:
                        self.showing_quest_log = True
                        self.quest_log_scroll = 0
                        break
                    if event.key == pygame.K_m:
                        self.showing_title = True
                        self.title_cursor = 0
                        self.music.play("title")
                        break
                    # 1-4 opens/switches character sheet if the state supports it
                    num = {pygame.K_1: 0, pygame.K_2: 1,
                           pygame.K_3: 2, pygame.K_4: 3}.get(event.key)
                    if num is not None:
                        state = self.current_state
                        if (hasattr(state, 'showing_char_detail')
                                and not getattr(state, 'showing_party_inv', False)
                                and not getattr(state, 'char_action_menu', False)
                                and num < len(self.party.members)):
                            state.showing_char_detail = num
                            state.char_sheet_cursor = 0
                            state.char_action_menu = False
                            state.examining_item = None
                            break

                # --- Input ---
                if not self.showing_settings:
                    keys_pressed = pygame.key.get_pressed()
                    self.current_state.handle_input(events, keys_pressed)

            # --- Update ---
            self.music.update(dt)
            if (not self.showing_settings and not self.showing_title
                    and not self.showing_game_over
                    and not self.showing_char_create
                    and not self.showing_form_party
                    and not self.showing_modules
                    and not self.showing_quest_log):
                self.current_state.update(dt)
                self.camera.update(self.party.col, self.party.row)

            # --- Draw ---
            self.screen.fill(COLOR_BLACK)
            if self.showing_title:
                mod_info = f"Module: {self.active_module_name} v{self.active_module_version}"
                self.renderer.draw_title_screen(
                    self.title_options, self.title_cursor,
                    self.title_elapsed, module_info=mod_info)
            elif self.showing_char_create:
                self.renderer.draw_char_create_screen(self)
            elif self.showing_form_party:
                self.renderer.draw_form_party_screen(self)
            elif self.showing_modules:
                self.renderer.draw_module_screen(
                    self.module_list, self.module_cursor,
                    self.active_module_path,
                    message=self.module_message,
                    confirm_delete=self.module_confirm_delete,
                    edit_mode=self.module_edit_mode,
                    edit_is_new=self.module_edit_is_new,
                    edit_field=self.module_edit_field,
                    edit_fields=self.module_edit_fields,
                    edit_buffer=self.module_edit_buffer,
                    edit_scroll=self.module_edit_scroll,
                    edit_level=self.module_edit_level,
                    edit_sections=self.module_edit_sections,
                    edit_section_cursor=self.module_edit_section_cursor,
                    edit_section_scroll=self.module_edit_section_scroll,
                    edit_nav_depth=len(self.module_edit_nav_stack),
                    edit_nav_label=getattr(
                        self, "_module_edit_folder_label", ""),
                    edit_in_encounters=(
                        self.module_edit_active_level >= 0
                        or self.module_edit_in_loot),
                    edit_in_dungeon_sub=(
                        self.module_edit_active_dung >= 0))
            elif self.showing_game_over:
                self.renderer.draw_game_over_screen(
                    self.game_over_options, self.game_over_cursor,
                    self.game_over_elapsed)
            elif self.showing_quest_log:
                quest_data = self._build_quest_log()
                self.renderer.draw_quest_screen(
                    quest_data, self.quest_log_scroll)
            elif self.showing_settings:
                if self.settings_mode in ("save", "load"):
                    # Build slot info list for the renderer
                    slot_infos = [get_save_info(i + 1)
                                  for i in range(NUM_SAVE_SLOTS)]
                    self.renderer.draw_save_load_screen(
                        mode=self.settings_mode,
                        slot_infos=slot_infos,
                        cursor=self.save_load_cursor,
                        message=self.save_load_message,
                        confirm_delete=self.save_load_confirm_delete)
                else:
                    self.renderer.draw_settings_screen(
                        self.settings_options, self.settings_cursor)
            else:
                self.current_state.draw(self.renderer)
            pygame.display.flip()

        pygame.quit()
