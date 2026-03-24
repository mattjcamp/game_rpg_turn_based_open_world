"""
Main Game class - the heart of the application.

Manages the game loop, state machine, and top-level resources.
"""

import json
import os
import random
import pygame

from src.editor_types import (
    FieldEntry,
    FeaturesRenderState, SpellEditorRS, ItemEditorRS,
    MonsterEditorRS, TileEditorRS, GalleryEditorRS,
    PixelEditorRS, MapEditorHubRS,
)
from src.features_editor import FeaturesEditor

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
                           delete_save, quick_save,
                           NUM_SAVE_SLOTS, QUICK_SAVE_SLOT,
                           load_config, save_config)
from src.module_loader import load_module_data


def _normalize_encounter(enc):
    """Return a list of monster names from an encounter dict.

    Supports both the new format ``{"monsters": [...]}`` and the
    legacy format ``{"monster": "X", "count": N}``.
    """
    if "monsters" in enc:
        return list(enc["monsters"])
    mon = enc.get("monster", "Giant Rat")
    cnt = max(1, int(enc.get("count", 1)))
    return [mon] * cnt


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
        self.start_level = max(1, min(10, self._config.get("start_level", 1)))

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

        # --- Game Features editor ---
        self.showing_features = False
        self._modules_from_features = False  # True when modules opened from features
        self.features_editor = FeaturesEditor(self)
        self._unsaved_dialog_active = False
        self._unsaved_dialog_save_cb = None    # callable: save then exit
        self._unsaved_dialog_discard_cb = None # callable: exit without saving

        # --- Title screen ---
        self.showing_title = True
        self.title_cursor = 0
        self.title_elapsed = 0.0        # for animations
        self._title_options_base = [
            {"label": "START NEW GAME", "action": self._title_new_game},
            {"label": "FORM PARTY", "action": self._title_form_party},
            {"label": "SAVE GAME", "action": self._title_save_game},
            {"label": "LOAD GAME", "action": self._title_load_game},
            {"label": "EDIT GAME", "action": self.features_editor.open_from_title},
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
        self._module_dirty = False           # True when module fields have unsaved edits
        self.module_edit_field = 0           # active field index
        self.module_edit_buffer = ""         # text being typed
        self.module_edit_fields = []         # [label, key, value, type, editable]
        self.module_edit_scroll = 0          # scroll offset for long field lists
        # ── Hierarchical navigation (edit existing modules) ──
        self.module_edit_level = 0           # 0=section browser, 1=field editor
        self.module_edit_sections = []       # list of section dicts
        self.module_edit_section_cursor = 0  # highlighted section
        self.module_edit_section_scroll = 0  # scroll for section list
        self.module_edit_nav_stack = []
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
        # Quick Save HUD flash
        self.quick_save_message = None
        self.quick_save_msg_timer = 0.0
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
            {"label": "START LEVEL",
             "value": self.start_level,
             "choices": list(range(1, 11)),
             "type": "choice", "action": self._cycle_start_level},
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
        else:
            # No active module — still refresh spell/item data from
            # default data/ so editor changes take effect immediately.
            from src.party import reload_module_data as _rp
            _rp()

        # ── Load overworld map ──
        # If the module has a static (custom) map, use it directly.
        # Otherwise fall back to procedural generation.
        overworld_cfg = None
        if self.module_manifest:
            overworld_cfg = self.module_manifest.get("_overworld_cfg")
        from src.tile_map import load_static_overworld
        static_map = None
        if self.active_module_path:
            static_map = load_static_overworld(self.active_module_path)
        if static_map is not None:
            self.tile_map = static_map
        else:
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

        # ── Apply debug / testing settings ──
        # Start level: use the higher of the global setting and the
        # per-module debug override so either source can boost the party.
        mod_start_level = 1
        if self.module_manifest:
            debug = self.module_manifest.get("debug", {})
            mod_start_level = max(1, min(10, int(debug.get("start_level", 1))))
            if debug.get("starter_kit", False):
                self._apply_debug_starter_kit()
        effective_level = max(self.start_level, mod_start_level)
        if effective_level > 1:
            self._apply_debug_start_level(effective_level)

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

    def _apply_debug_start_level(self, target_level):
        """Boost every party member to *target_level* by granting XP."""
        for m in self.party.members:
            template = m._load_class_template(m.char_class)
            race_info = m.race_info
            xp_per = race_info.get("exp_per_level",
                                   template["exp_per_level"])
            # check_level_up promotes while exp >= level * xp_per,
            # so to reach target_level we need (target_level - 1) * xp_per.
            needed = (target_level - 1) * xp_per
            if needed > m.exp:
                m.exp = needed
                m.check_level_up()
            # Fully heal after leveling
            m.hp = m.max_hp
            if hasattr(m, '_current_mp'):
                m._current_mp = m.max_mp

    def _apply_debug_starter_kit(self):
        """Give the party a set of useful items for testing."""
        kit = [
            ("Lockpick", 5),
            ("Camping Supplies", 3),
            ("Torch", 5),
            ("Healing Herb", 10),
            ("Antidote", 5),
            ("Healing Potion", 5),
            ("Arrows", 20),
            ("Bolts", 20),
        ]
        for item_name, count in kit:
            for _ in range(count):
                self.party.inv_add(item_name)
        # Give each member decent gear
        from src.party import WEAPONS, ARMORS
        weapon_upgrades = ["Long Sword", "Mace", "Dagger"]
        armor_upgrades = ["Chain", "Leather"]
        for m in self.party.members:
            # Equip best available weapon
            for w in weapon_upgrades:
                if w in WEAPONS:
                    m.equipped["right_hand"] = w
                    m._sync_legacy_fields()
                    break
            # Equip best available armor
            for a in armor_upgrades:
                if a in ARMORS:
                    m.equipped["body"] = a
                    m._sync_legacy_fields()
                    break

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
            dsz = kd.get("size", "medium")
            levels = generate_keys_dungeon(
                dnum, name=name,
                place_artifact=needs_artifact,
                module_levels=module_levels,
                kill_target=kt, kill_count=kc,
                torch_density=td,
                dungeon_size=dsz)
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
            custom_layout = tc.get("layout", "")
            if custom_layout:
                # Use a player-created layout from town_templates.json
                td = self._build_town_from_layout(
                    custom_layout, tname,
                    town_style=tc.get("style", "medieval"))
                if td is None:
                    # Layout not found — fall back to procedural
                    td = generate_town(
                        tname, seed=town_seed,
                        layout_index=town_ordinal,
                        has_key_dungeons=bool(self.key_dungeons),
                        innkeeper_quests=inn_quests,
                        gnome_machine=place_machine,
                        keys_needed=gnome_keys_needed,
                        town_config=tc)
            else:
                td = generate_town(
                    tname, seed=town_seed,
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

    def _build_town_from_layout(self, layout_name, town_name,
                                 town_style="medieval"):
        """Build a TownData from a custom layout in town_templates.json.

        Searches the loaded layouts list for *layout_name*, constructs a
        TileMap from its tile grid, extracts interior links, and finds the
        exit tile to set the entry position.

        Returns a TownData, or *None* if the layout isn't found.
        """
        from src.tile_map import TileMap
        from src.town_generator import TownData

        fe = self.features_editor
        layouts = fe.town_lists.get("layouts", [])
        if not layouts:
            fe.load_townlayouts()
            layouts = fe.town_lists.get("layouts", [])
        layout = None
        for l in layouts:
            if l["name"] == layout_name:
                layout = l
                break
        if layout is None:
            return None

        w = layout.get("width", 20)
        h = layout.get("height", 20)
        tiles_dict = layout.get("tiles", {})

        from src.settings import TILE_VOID, TILE_EXIT
        tm = TileMap(w, h, default_tile=TILE_VOID, oob_tile=TILE_VOID)
        interior_links = {}
        overworld_exits = set()
        entry_col, entry_row = 0, h - 1

        for key, td in tiles_dict.items():
            try:
                parts = key.split(",")
                col, row = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                continue
            tile_id = td.get("tile_id", 10)
            tm.set_tile(col, row, tile_id)
            path = td.get("path")
            if path:
                tm.sprite_overrides[(col, row)] = path
            if td.get("interior"):
                interior_links[(col, row)] = td["interior"]
            if td.get("to_overworld"):
                overworld_exits.add((col, row))
                if entry_col == 0 and entry_row == h - 1:
                    entry_col, entry_row = col, row
            if tile_id == TILE_EXIT:
                entry_col, entry_row = col, row

        return TownData(
            tile_map=tm,
            npcs=[],
            name=town_name,
            entry_col=entry_col,
            entry_row=entry_row,
            town_style=town_style,
            interior_links=interior_links,
            overworld_exits=overworld_exits,
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
        """Load available character tiles from the 'people' category
        in the tile manifest (data/tile_manifest.json)."""
        import os, json
        from src.tile_manifest import TileManifest
        project_root = os.path.dirname(os.path.dirname(__file__))
        manifest = TileManifest()
        manifest.load()
        self._cc_tiles = []  # list of {"name": ..., "file": ...}
        for name in manifest.names_in("people"):
            entry = manifest.get_entry_by_name("people", name)
            if entry and "path" in entry:
                abs_path = os.path.join(project_root, entry["path"])
                if os.path.isfile(abs_path):
                    # Use a display-friendly name: replace underscores,
                    # title-case, strip numbering suffixes
                    display = name.replace("_", " ").title()
                    self._cc_tiles.append({
                        "name": display,
                        "file": entry["path"],
                    })
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
            # No characters — Ctrl+N to create, or ESC/Enter/Space to return
            if self._is_new_shortcut(event):
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
        elif self._is_delete_shortcut(event):
            # Prompt delete confirmation
            if 0 <= self._fp_cursor < roster_len:
                self._fp_confirm_delete = True
        elif self._is_new_shortcut(event):
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
        """Return the slot number of the most recent save, or None.

        Checks all regular slots AND the Quick Save slot (0).
        """
        best_slot = None
        best_ts = -1
        # Include Quick Save slot (0) alongside regular slots
        for slot in [QUICK_SAVE_SLOT] + list(range(1, NUM_SAVE_SLOTS + 1)):
            info = get_save_info(slot)
            if info and info.get("timestamp", 0) > best_ts:
                best_ts = info["timestamp"]
                best_slot = slot
        return best_slot

    def _title_return_to_game(self):
        """Return to the active game, or load the most recent save."""
        if self._game_started:
            # Game already running — just dismiss the title screen.
            # Refresh overworld interiors & tile_links from disk in case the
            # module editor changed them since the game was started.
            self._refresh_overworld_interior_data()
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

    def _refresh_overworld_interior_data(self):
        """Reload overworld interiors & tile_links from static_overworld.json.

        Called when returning to a running game so that any changes made in
        the module editor (add/delete/rename interiors, re-link tiles) are
        picked up without requiring a full new-game restart.
        """
        import json, os
        if not self.active_module_path:
            return
        static_path = os.path.join(
            self.active_module_path, "static_overworld.json")
        if not os.path.isfile(static_path):
            return
        try:
            with open(static_path, "r") as fh:
                sdata = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        tmap = self.tile_map
        tmap.tile_links = sdata.get("tile_links", {})
        tmap.overworld_interiors = sdata.get("interiors", [])

    def _title_quit(self):
        """Quit the game."""
        pygame.event.post(pygame.event.Event(pygame.QUIT))

    # ── Map Editor hub (shared helpers) ──────────────────────────

    def _leave_modules(self):
        """Close modules screen, returning to features or title."""
        self.showing_modules = False
        if self._modules_from_features:
            self.showing_features = True
            self._modules_from_features = False
        else:
            self.showing_title = True

    def _title_modules(self):
        """Open the module browser from the title screen."""
        self._refresh_module_list()
        self.showing_title = False
        self.showing_modules = True
        self._modules_from_features = False
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

        # ── No modules: Ctrl+N to create, ESC to go back ──
        if not self.module_list:
            if self._is_new_shortcut(event):
                self._do_create_module()
            elif event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self._leave_modules()
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
            self._leave_modules()
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._enter_module_edit()
        elif event.key == pygame.K_ESCAPE:
            self._leave_modules()
        elif self._is_new_shortcut(event):
            self._do_create_module()
        elif self._is_delete_shortcut(event):
            selected = self.module_list[self.module_cursor]
            if selected["path"] == self.active_module_path:
                self.module_message = "Cannot delete the active module!"
                self.module_msg_timer = 2.0
            else:
                self.module_confirm_delete = True
                name = selected["name"]
                self.module_message = f'Delete "{name}"?  Y = Yes  N = No'

    def _do_create_module(self):
        """Open the edit overlay in 'create new module' mode."""
        self.module_edit_mode = True
        self.module_edit_is_new = True
        self.module_edit_level = 0
        self.module_edit_field = 0
        self.module_edit_scroll = 0
        # All fields are editable in create mode
        self.module_edit_fields = [
            ["Name", "name", "", "text", True],
            ["Author", "author", "", "text", True],
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
        """Enter edit mode for an existing module — Module Details only."""
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]

        self.module_edit_mode = True
        self.module_edit_is_new = False

        # ── Build section list — Module Details only ──
        sections = [
            {
                "label": "Module Details",
                "icon": ">",
                "fields": [
                    ["Name", "name", mod["name"], "text", True],
                    ["Author", "author", mod["author"], "text", True],
                    ["Description", "description",
                     mod.get("description", ""), "text", True],
                ],
            },
        ]

        self.module_edit_sections = sections
        self.module_edit_section_cursor = 0
        self.module_edit_section_scroll = 0
        self.module_edit_level = 0
        # Clear field-level state
        self.module_edit_fields = []
        self.module_edit_field = 0
        self.module_edit_buffer = ""
        self.module_edit_scroll = 0
        self.module_edit_nav_stack = []
        self._module_edit_folder_label = ""

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
        """Handle input while editing module."""
        # Intercept input when unsaved-changes dialog is showing
        if self._unsaved_dialog_active:
            self._handle_unsaved_dialog_input(event)
            return

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
            if self._module_dirty:
                def _save_and_exit():
                    self._leave_section_fields()
                    self._module_dirty = False
                def _discard_and_exit():
                    self.module_edit_level = 0
                    self._module_dirty = False
                self._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
            else:
                self._leave_section_fields()
            return
        if self._is_save_shortcut(event):
            if self.module_edit_fields:
                entry = self.module_edit_fields[self.module_edit_field]
                entry[2] = self.module_edit_buffer
            self._commit_module_edit()
            self._module_dirty = False
            return

        self._handle_field_editor_input(event)

    def _handle_section_browser_input(self, event):
        """Handle input at the section browser level (level 0)."""
        n = len(self.module_edit_sections)
        if event.key == pygame.K_ESCAPE:
            self._commit_module_edit()
            self.module_edit_mode = False
            self.module_edit_is_new = False
            self.module_message = None
            self._module_dirty = False
        elif event.key == pygame.K_UP:
            self.module_edit_section_cursor = (
                (self.module_edit_section_cursor - 1) % n)
            self._adjust_section_scroll()
        elif event.key == pygame.K_DOWN:
            self.module_edit_section_cursor = (
                (self.module_edit_section_cursor + 1) % n)
            self._adjust_section_scroll()
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            self._enter_section_fields()
        elif self._is_save_shortcut(event):
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

    def _enter_section_fields(self):
        """Enter field editing for the currently selected section."""
        sec = self.module_edit_sections[self.module_edit_section_cursor]
        if not sec.get("fields"):
            return
        self.module_edit_fields = sec["fields"]
        self.module_edit_field = 0
        self.module_edit_scroll = 0
        self.module_edit_level = 1
        self._module_dirty = False
        self.module_edit_field = self._next_editable_field(0)
        if self.module_edit_fields:
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]

    def _leave_section_fields(self):
        """Leave field editing, persist buffer, and return to level 0."""
        if self.module_edit_fields and self.module_edit_field < len(
                self.module_edit_fields):
            entry = self.module_edit_fields[self.module_edit_field]
            entry[2] = self.module_edit_buffer
        self.module_edit_level = 0
        self.module_edit_fields = []

    def _get_choices_for_field(self, key):
        """Return the list of valid choices for a choice-type field."""
        # Module editor only has text fields now (name, author, desc).
        # This method remains for any future choice fields.
        return []

    def _handle_field_editor_input(self, event):
        """Handle input at the field editor level (level 1)."""
        if not self.module_edit_fields:
            # Empty field list — only ESC to go back is meaningful.
            return
        field_entry = self.module_edit_fields[self.module_edit_field]
        field_type = field_entry[3] if len(field_entry) > 3 else "text"
        editable = field_entry[4] if len(field_entry) > 4 else True

        if event.key == pygame.K_UP:
            field_entry[2] = self.module_edit_buffer
            self._module_dirty = True
            self.module_edit_field = self._next_editable_field(-1)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()
        elif event.key == pygame.K_DOWN:
            field_entry[2] = self.module_edit_buffer
            self._module_dirty = True
            self.module_edit_field = self._next_editable_field(+1)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()
        elif not editable:
            return
        else:
            # text field
            if event.key == pygame.K_BACKSPACE:
                self.module_edit_buffer = self.module_edit_buffer[:-1]
                self._module_dirty = True
            elif event.unicode and event.unicode.isprintable():
                self.module_edit_buffer += event.unicode
                self._module_dirty = True

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
        elif self._is_save_shortcut(event):
            field_entry[2] = self.module_edit_buffer
            self._commit_module_edit()
        elif not editable:
            return
        elif event.key == pygame.K_BACKSPACE:
            self.module_edit_buffer = self.module_edit_buffer[:-1]
        elif event.unicode and event.unicode.isprintable():
            self.module_edit_buffer += event.unicode

    def _commit_module_edit(self):
        """Create a new module or save edits to an existing one."""
        # Persist any in-progress buffer before gathering
        if self.module_edit_level == 1 and self.module_edit_fields:
            entry = self.module_edit_fields[self.module_edit_field]
            entry[2] = self.module_edit_buffer

        # Gather all field values into a dict.
        values = {}
        if self.module_edit_is_new:
            sources = [self.module_edit_fields]
        else:
            sources = [s["fields"] for s in self.module_edit_sections
                       if s.get("fields")]
        for field_list in sources:
            for entry in field_list:
                key, value = entry[1], entry[2]
                values[key] = value

        if self.module_edit_is_new:
            # ── Create new module with defaults ──
            from src.module_loader import create_module
            path = create_module(
                name=values.get("name", "Untitled"),
                author=values.get("author", ""),
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
            # ── Update existing module (metadata only) ──
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

            # Write back
            try:
                with open(manifest_path, "w") as fh:
                    json.dump(data, fh, indent=2)
                ok = True
            except OSError:
                ok = False

            self.module_edit_mode = False
            self.module_edit_nav_stack = []
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

    def _cycle_start_level(self, direction=1):
        """Cycle the starting experience level (1-10) for new games."""
        opt = self.settings_options[4]  # START LEVEL entry
        choices = opt["choices"]
        cur_idx = choices.index(opt["value"]) if opt["value"] in choices else 0
        new_idx = (cur_idx + direction) % len(choices)
        new_val = choices[new_idx]
        opt["value"] = new_val
        self.start_level = new_val
        self._config["start_level"] = new_val
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

    def _do_quick_save(self):
        """Quick Save via Ctrl-S / Cmd-S shortcut.

        Saves to the dedicated Quick Save slot and shows a brief HUD
        message.  Blocked during combat and examine states.
        """
        ok = quick_save(self)
        if ok:
            self.quick_save_message = "Quick Save!"
            self.quick_save_msg_timer = 1.5
        else:
            # In combat or examine — show a brief "can't save" hint
            self.quick_save_message = "Cannot save here!"
            self.quick_save_msg_timer = 1.5

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
        label = "Quick Save" if slot == QUICK_SAVE_SLOT else f"Slot {slot}"
        if ok:
            self.save_load_message = f"{label} deleted."
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

    @staticmethod
    def _is_save_shortcut(event):
        """Return True if the event is Ctrl+S or Cmd+S (universal save)."""
        if event.key != pygame.K_s:
            return False
        return bool(event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))

    @staticmethod
    def _is_new_shortcut(event):
        """Return True if the event is Ctrl+N or Cmd+N (universal new)."""
        if event.key != pygame.K_n:
            return False
        return bool(event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))

    @staticmethod
    def _is_delete_shortcut(event):
        """Return True if the event is Ctrl+D or Cmd+D (universal delete)."""
        if event.key != pygame.K_d:
            return False
        return bool(event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))

    @staticmethod
    def _is_copy_shortcut(event):
        """Return True if the event is Ctrl+C or Cmd+C (universal copy/duplicate)."""
        if event.key != pygame.K_c:
            return False
        return bool(event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))

    def _show_unsaved_dialog(self, save_cb, discard_cb):
        """Show the 'unsaved changes' confirmation dialog.

        save_cb    — called when the player presses [S] (save & exit)
        discard_cb — called when the player presses [D] (discard & exit)
        Pressing [Escape] cancels and returns to the editor.
        """
        self._unsaved_dialog_active = True
        self._unsaved_dialog_save_cb = save_cb
        self._unsaved_dialog_discard_cb = discard_cb

    def _handle_unsaved_dialog_input(self, event):
        """Handle Enter/Escape input on the unsaved-changes overlay."""
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            # Save changes then exit
            cb = self._unsaved_dialog_save_cb
            self._unsaved_dialog_active = False
            if cb:
                cb()
        elif event.key == pygame.K_ESCAPE:
            # Discard changes and exit
            cb = self._unsaved_dialog_discard_cb
            self._unsaved_dialog_active = False
            self._module_dirty = False
            if cb:
                cb()

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

    # ────────────────────────────────────────────────────────────
    # Unified field editor — shared by all record-based editors
    # (spells, items, monsters, tiles).  Called from level 2
    # (spells/items/monsters) and level 3 (tiles).
    # ────────────────────────────────────────────────────────────
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
                slot = QUICK_SAVE_SLOT if self.save_load_cursor == 0 else self.save_load_cursor
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
        total_slots = 1 + NUM_SAVE_SLOTS  # Quick Save + regular slots
        if event.key == pygame.K_UP:
            self.save_load_cursor = (
                (self.save_load_cursor - 1) % total_slots)
        elif event.key == pygame.K_DOWN:
            self.save_load_cursor = (
                (self.save_load_cursor + 1) % total_slots)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            # Cursor 0 = Quick Save (slot 0), cursor 1-3 = regular slots 1-3
            slot = QUICK_SAVE_SLOT if self.save_load_cursor == 0 else self.save_load_cursor
            slot_label = "Quick Save" if slot == QUICK_SAVE_SLOT else f"Slot {slot}"
            if self.settings_mode == "save":
                ok = save_game(slot, self)
                if ok:
                    self.save_load_message = f"Game saved to {slot_label}!"
                else:
                    self.save_load_message = "Save failed!"
                self.save_load_msg_timer = 2.0
            else:
                ok = load_game(slot, self)
                if ok:
                    self._game_started = True
                    self.save_load_message = f"Loaded {slot_label}!"
                    self.save_load_msg_timer = 2.0
                else:
                    self.save_load_message = "No save in that slot!"
                    self.save_load_msg_timer = 2.0
                # If load succeeded from title or game over, close everything
                if self.save_load_message and "Loaded" in self.save_load_message:
                    if getattr(self, '_title_load_mode', False):
                        self._title_load_mode = False
                        self.showing_settings = False
                    elif getattr(self, '_game_over_load_mode', False):
                        self._game_over_load_mode = False
                        self.showing_settings = False
        elif self._is_delete_shortcut(event) and self.settings_mode == "load":
            # Only allow delete from the load screen
            slot = QUICK_SAVE_SLOT if self.save_load_cursor == 0 else self.save_load_cursor
            slot_label = "Quick Save" if slot == QUICK_SAVE_SLOT else f"Slot {slot}"
            info = get_save_info(slot)
            if info is not None:
                self.save_load_confirm_delete = True
                self.save_load_message = f"Delete {slot_label}?  Y = Yes  N = No"

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
            elif self.showing_features:
                for event in events:
                    self.features_editor.handle_input(event)
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
                    # Ctrl-S / Cmd-S: Quick Save
                    if (event.key == pygame.K_s
                            and (event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))):
                        self._do_quick_save()
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
            # Tick quick save HUD timer
            if self.quick_save_msg_timer > 0:
                self.quick_save_msg_timer -= dt
                if self.quick_save_msg_timer <= 0:
                    self.quick_save_message = None
            if (not self.showing_settings and not self.showing_title
                    and not self.showing_game_over
                    and not self.showing_char_create
                    and not self.showing_form_party
                    and not self.showing_modules
                    and not self.showing_features
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
            elif self.showing_features:
                self.renderer.draw_features_screen(
                    self.features_editor.get_render_state())
                if self._unsaved_dialog_active:
                    self.renderer.draw_unsaved_dialog()
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
                    edit_section_scroll=self.module_edit_section_scroll)
                if self._unsaved_dialog_active:
                    self.renderer.draw_unsaved_dialog()
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
                    # Build slot info list: Quick Save first, then regular slots
                    slot_infos = [get_save_info(QUICK_SAVE_SLOT)]
                    slot_infos += [get_save_info(i + 1)
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

            # ── Quick Save HUD overlay ──
            if self.quick_save_message:
                self.renderer.draw_quick_save_hud(self.quick_save_message)

            pygame.display.flip()

        pygame.quit()
