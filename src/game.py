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
from src.town_generator import generate_town
from src.music import SoundEffects, MusicManager
from src.save_load import (save_game, load_game, get_save_info,
                           delete_save, quick_save,
                           NUM_SAVE_SLOTS, QUICK_SAVE_SLOT,
                           load_config, save_config)
from src.module_loader import load_module_data
from src.module_editor_town import ModuleTownEditorMixin
from src.module_editor_dungeon import ModuleDungeonEditorMixin
from src.module_editor_building import ModuleBuildingEditorMixin
from src.module_editor_quest import ModuleQuestEditorMixin


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


class Game(ModuleTownEditorMixin, ModuleDungeonEditorMixin,
           ModuleBuildingEditorMixin, ModuleQuestEditorMixin):
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

        # Camera follows the party.
        # Viewport dims match the renderer's map area (30x20 tiles;
        # the bottom ~96px of the screen is reserved for the HUD), so
        # free-look panning (Shift + arrows) clamps to exactly what
        # the renderer will display.
        self.camera = Camera(
            self.tile_map.width, self.tile_map.height,
            viewport_cols=30, viewport_rows=20,
        )
        self.camera.update(self.party.col, self.party.row)

        # Renderer
        self.renderer = Renderer(self.screen)
        # Give the renderer a back-reference to the Game so it can read
        # transient UI state (e.g. party.on_boat for sail animation)
        # without plumbing every flag through every draw call.
        self.renderer.game = self
        # Give the renderer a back-reference to the camera so its
        # map-drawing methods pick up free-look pan offsets instead
        # of always re-centering on the party.
        self.renderer.camera = self.camera

        # --- Town data ---
        # Pre-generate the town so it persists across visits
        self.town_data = generate_town("Thornwall")  # default / current town
        self.town_data_map = {}  # {(col, row): TownData} for multi-town modules

        # --- Quest state ---
        # None when no quest active; dict when quest is in progress
        self.quest = None
        self.house_quest = None
        self.key_dungeons = {}
        self.visited_dungeons = set()
        # Module quest system - user-created quests from quests.json
        self.module_quest_states = {}  # {quest_name: {status, step_progress}}
        self.overworld_quest_npcs = []  # NPC objects placed on the overview map
        self.quest_spawned_monsters = {}  # {quest_name: [monster_obj, ...]}
        self.quest_interior_monsters = {}  # {location_key: [{monster_key, ...}]}
        self.quest_dungeon_monsters = {}   # {dungeon_name: [{monster_key, ...}]}
        self.quest_collect_items = {}      # {location_key: [{item_info, ...}]}
        self.dungeon_cache = {}
        self.pending_combat_rewards = None
        self.pending_killed_monsters = []
        self.pending_combat_location = ""
        self.examined_tiles = {}

        # --- Boat / sailing state ---
        # on_boat: party is currently aboard the boat (allows water crossing)
        # boat_anim_frame: toggles 0/1 for sail animation while sailing
        # boat_anim_accum: accumulator (ms) advancing the animation timer
        self.on_boat = False
        self.boat_anim_frame = 0
        self.boat_anim_accum = 0

        # --- Darkness effect (Keys of Shadow module) ---
        self.darkness_active = False

        # --- Game log ---
        # Accumulates all messages from every state for the log overlay
        self.game_log = []

        # --- Load persistent player config ---
        self._config = load_config()
        self.dm_mode = self._config.get("dm_mode", False)
        self.smite_enabled = self._config.get("smite_enabled", False)
        self.start_with_equipment = self._config.get("start_with_equipment", True)
        self.start_level = max(1, min(10, self._config.get("start_level", 1)))
        # DM-mode-only debug toggle: when on, roaming overworld monsters
        # (orcs and spawn-tile monsters) are not spawned, and procedurally
        # generated dungeons skip their random per-room encounters. Quest
        # monsters and module-defined custom encounters are unaffected.
        # Only has an effect while dm_mode is on.
        self.quest_monsters_only = bool(
            self._config.get("quest_monsters_only", False)) and self.dm_mode
        # Keep the dungeon generator's debug switch aligned with the config.
        from src.dungeon_generator import set_quest_monsters_only_debug
        set_quest_monsters_only_debug(self.quest_monsters_only)

        # --- Sound Effects ---
        self.sfx = SoundEffects()
        self.sfx.muted = self._config.get("sfx_muted", False)

        # --- Background Music ---
        soundtrack_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "soundtrack")
        self.music = MusicManager(
            base_path=soundtrack_path,
            volume=self._config.get("music_volume", 0.5))
        self.music.muted = self._config.get("music_muted", False)

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
            {"label": "SETTINGS", "action": self._title_settings},
            {"label": "QUIT GAME", "action": self._title_quit},
        ]
        self._title_dm_option = {
            "label": "EDIT GAME",
            "action": self.features_editor.open_from_title,
        }
        self._rebuild_title_options()

        # --- Intro screen (shown between title and gameplay on new game) ---
        self.showing_intro = False
        self._intro_elapsed = 0.0
        self._intro_module_name = ""
        self._intro_module_desc = ""
        self._intro_fading_out = False   # True once player presses key
        self._intro_fade_elapsed = 0.0   # seconds since fade-out began

        # --- Loading screen (fade-to-black transition between areas) ---
        self._loading_screen_active = False
        self._loading_screen_phase = "idle"   # idle / fade_out / hold / fade_in
        self._loading_screen_elapsed = 0.0
        self._loading_screen_label = ""       # e.g. "Entering Riverdale"
        self._loading_screen_callback = None  # called once at start of hold
        self._loading_screen_callback_fired = False
        # Timing (seconds)
        self._loading_fade_out_dur = 0.6    # screen goes dark
        self._loading_hold_dur = 0.5        # stay dark while assets load
        self._loading_fade_in_dur = 0.6     # new area fades in

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
        # ── Overview Map in module ──
        self._mod_overview_map = None  # dict: map_config + tiles (or None)
        self._mod_overview_picking = False  # True when showing template picker
        self._mod_overview_pick_list = []   # list of overview template dicts
        self._mod_overview_pick_cursor = 0
        self._mod_overview_pick_scroll = 0
        self._mod_overview_generate_mode = False   # True when editing dims
        self._mod_overview_gen_fields = []          # [width_str, height_str]
        self._mod_overview_gen_field = 0            # 0=width, 1=height
        self._mod_overview_gen_buffer = ""          # current field buffer
        self._mod_overview_children = []    # [Settings, Edit Map]
        self._mod_overview_child_cursor = 0
        self._mod_overview_level = 0        # 0=children, 1=settings fields
        from src.module_loader import get_default_module_path, scan_modules
        self.active_module_path = None
        self.active_module_name = "No Module"
        self.active_module_version = "0.0.0"
        self.module_manifest = None  # populated on new game start

        # ── Town Editor (within module) ──
        self._mod_town_list = []          # list of town dicts for current module
        self._mod_town_cursor = 0
        self._mod_town_scroll = 0
        self._mod_town_sub_cursor = 0     # 0=Settings, 1=Townspeople, 2=Edit Map
        self._mod_town_sub_items = ["Settings", "Townspeople", "Enclosures",
                                    "Edit Map"]
        # Settings fields
        self._mod_town_fields = []        # list of FieldEntry for settings
        self._mod_town_field = 0
        self._mod_town_buffer = ""
        self._mod_town_field_scroll = 0
        # Townspeople (NPC list)
        self._mod_town_npc_list = []
        self._mod_town_npc_cursor = 0
        self._mod_town_npc_scroll = 0
        # NPC field editor
        self._mod_town_npc_fields = []
        self._mod_town_npc_field = 0
        self._mod_town_npc_buffer = ""
        self._mod_town_npc_field_scroll = 0
        self._mod_town_npc_choice_map = {}
        # Town map generation overlays
        self._mod_town_gen_mode = None        # None, "pick_template", "generate"
        self._mod_town_gen_pick_list = []     # list of layout templates
        self._mod_town_gen_pick_cursor = 0
        self._mod_town_gen_pick_scroll = 0
        # Generate form
        self._mod_town_gen_field = 0          # active field in generate form
        self._mod_town_gen_size_idx = 1       # 0=small, 1=medium, 2=large
        self._mod_town_gen_style_idx = 0      # index into styles
        self._MOD_TOWN_SIZES = ["small", "medium", "large"]
        self._MOD_TOWN_STYLES = ["medieval", "desert", "coastal",
                                  "forest", "mountain"]
        # Enclosures (interior instances for this town)
        self._mod_town_enclosures = []        # list of interior dicts
        self._mod_town_enc_cursor = 0
        self._mod_town_enc_scroll = 0
        # Enclosure import picker
        self._mod_town_enc_picking = False     # True when picker overlay shown
        self._mod_town_enc_pick_list = []      # list of me_enclosure templates
        self._mod_town_enc_pick_cursor = 0
        self._mod_town_enc_pick_scroll = 0
        # Enclosure naming overlay (for generate)
        self._mod_town_enc_naming = False
        self._mod_town_enc_name_buf = ""
        self._mod_town_enc_template = None     # template being instantiated
        # Enclosure sub-screen (Townspeople | Edit Map)
        self._mod_town_enc_edit_mode = 0  # 0=list, 1=sub-screen, 2=npc list, 3=npc field editor
        self._mod_town_enc_sub_cursor = 0
        self._mod_town_enc_sub_items = ["Townspeople", "Edit Map"]
        # Enclosure NPC list (parallel to town NPC state)
        self._mod_town_enc_npc_list = []
        self._mod_town_enc_npc_cursor = 0
        self._mod_town_enc_npc_scroll = 0
        # Enclosure NPC field editor
        self._mod_town_enc_npc_fields = []
        self._mod_town_enc_npc_field = 0
        self._mod_town_enc_npc_buffer = ""
        self._mod_town_enc_npc_field_scroll = 0
        self._mod_town_enc_npc_choice_map = {}
        self._mod_town_enc_npc_sprite_name_to_file = {}
        # Map editor
        self._mod_town_editor_active = False
        self._mod_town_map_editor_state = None
        self._mod_town_map_editor_handler = None
        # Naming overlay
        self._mod_town_naming = False
        self._mod_town_name_buf = ""
        self._mod_town_naming_is_new = False
        # Save flash
        self._mod_town_save_flash = 0.0

        # ── Dungeon Editor (within module) ──
        self._mod_dungeon_list = []          # list of dungeon dicts
        self._mod_dungeon_cursor = 0
        self._mod_dungeon_scroll = 0
        # Dungeon sub-screen: 0=Settings, 1=Levels
        self._mod_dungeon_sub_cursor = 0
        self._mod_dungeon_sub_items = ["Settings", "Levels"]
        # Settings fields
        self._mod_dungeon_fields = []
        self._mod_dungeon_field = 0
        self._mod_dungeon_buffer = ""
        self._mod_dungeon_field_scroll = 0
        self._mod_dungeon_choice_map = {}  # populated by _mod_dungeon_build_settings_fields
        # Level list (within a dungeon)
        self._mod_dungeon_level_list = []
        self._mod_dungeon_level_cursor = 0
        self._mod_dungeon_level_scroll = 0
        # Level sub-screen: 0=Edit Map, 1=Encounters
        self._mod_dungeon_level_sub_cursor = 0
        self._mod_dungeon_level_sub_items = ["Edit Map", "Encounters"]
        # Encounters list (within a level)
        self._mod_dungeon_encounter_list = []
        self._mod_dungeon_encounter_cursor = 0
        self._mod_dungeon_encounter_scroll = 0
        # Encounter editor (custom screen with monster list)
        self._mod_dungeon_encounter_fields = []       # legacy compat
        self._mod_dungeon_encounter_field = 0         # legacy compat
        self._mod_dungeon_encounter_buffer = ""        # legacy compat
        self._mod_dungeon_encounter_field_scroll = 0   # legacy compat
        self._mod_dungeon_enc_cursor = 0
        self._mod_dungeon_enc_editing = False
        self._mod_dungeon_enc_buffer = ""
        self._mod_dungeon_enc_monster_cursor = 0
        # Encounter placement on map (overlay within edit_level 13)
        self._mod_dungeon_enc_placing = False
        self._mod_dungeon_enc_place_col = 0
        self._mod_dungeon_enc_place_row = 0
        # Monster picker (overlay within edit_level 13)
        self._mod_dungeon_enc_picker_active = False
        self._mod_dungeon_enc_picker_monsters = []
        self._mod_dungeon_enc_picker_cursor = 0
        self._mod_dungeon_enc_picker_scroll = 0
        # Map editor
        self._mod_dungeon_editor_active = False
        self._mod_dungeon_map_editor_state = None
        self._mod_dungeon_map_editor_handler = None
        # Naming overlay (shared for dungeon + level naming)
        self._mod_dungeon_naming = False
        self._mod_dungeon_name_buf = ""
        self._mod_dungeon_naming_is_new = False
        self._mod_dungeon_naming_target = ""   # "dungeon" or "level"
        # Save flash
        self._mod_dungeon_save_flash = 0.0

        # ── Building Editor (within module) ──
        self._mod_building_list = []          # list of building dicts
        self._mod_building_cursor = 0
        self._mod_building_scroll = 0
        # Building sub-screen: 0=Settings, 1=Spaces
        self._mod_building_sub_cursor = 0
        self._mod_building_sub_items = ["Settings", "Spaces"]
        # Settings fields
        self._mod_building_fields = []
        self._mod_building_field = 0
        self._mod_building_buffer = ""
        self._mod_building_field_scroll = 0
        self._mod_building_choice_map = {}
        # Space list (within a building)
        self._mod_building_space_list = []
        self._mod_building_space_cursor = 0
        self._mod_building_space_scroll = 0
        # Space sub-screen: Townspeople | Edit Map | Encounters |
        # Auto-Populate Encounters | Import Template
        self._mod_building_space_sub_cursor = 0
        self._mod_building_space_sub_items = [
            "Townspeople", "Edit Map", "Encounters",
            "Auto-Populate Encounters", "Import Template"]
        # Difficulty picker overlay state (auto-populate)
        self._mod_building_diff_picking = False
        self._mod_building_diff_cursor = 1  # default: "normal"
        self._mod_building_auto_pop_msg = ""
        # Building space NPC edit mode (sub-state within level 17)
        self._mod_building_space_npc_edit_mode = 0  # 0=off, 1=npc list, 2=npc field editor
        # Building space NPC list
        self._mod_building_space_npc_list = []
        self._mod_building_space_npc_cursor = 0
        self._mod_building_space_npc_scroll = 0
        # Building space NPC field editor
        self._mod_building_space_npc_fields = []
        self._mod_building_space_npc_field = 0
        self._mod_building_space_npc_buffer = ""
        self._mod_building_space_npc_field_scroll = 0
        self._mod_building_space_npc_choice_map = {}
        self._mod_building_space_npc_sprite_name_to_file = {}
        # Encounters list (within a space)
        self._mod_building_encounter_list = []
        self._mod_building_encounter_cursor = 0
        self._mod_building_encounter_scroll = 0
        # Encounter field editor
        self._mod_building_encounter_fields = []
        self._mod_building_encounter_field = 0
        self._mod_building_encounter_buffer = ""
        self._mod_building_encounter_field_scroll = 0
        # Map editor
        self._mod_building_editor_active = False
        self._mod_building_map_editor_state = None
        self._mod_building_map_editor_handler = None
        # Naming overlay (shared for building + space naming)
        self._mod_building_naming = False
        self._mod_building_name_buf = ""
        self._mod_building_naming_is_new = False
        self._mod_building_naming_target = ""   # "building" or "space"
        # Enclosure template picker (for importing into building spaces)
        self._mod_building_enc_picking = False
        self._mod_building_enc_pick_list = []
        self._mod_building_enc_pick_cursor = 0
        self._mod_building_enc_pick_scroll = 0
        self._mod_building_importing_to_space = False
        # Save flash
        self._mod_building_save_flash = 0.0

        # ── Quest Editor (within module) ──
        self._mod_quest_list = []             # list of quest dicts
        self._mod_quest_cursor = 0
        self._mod_quest_scroll = 0
        # Quest sub-screen: 0=Settings, 1=Quest Steps
        self._mod_quest_sub_cursor = 0
        self._mod_quest_sub_items = ["Settings", "Quest Steps"]
        # Settings fields
        self._mod_quest_fields = []
        self._mod_quest_field = 0
        self._mod_quest_buffer = ""
        self._mod_quest_field_scroll = 0
        self._mod_quest_choice_map = {}        # populated by build_settings_fields
        self._mod_quest_sprite_name_to_file = {}  # display name -> file path
        self._mod_quest_step_choice_map = {}   # populated by build_step_fields
        # Step list (within a quest)
        self._mod_quest_step_list = []
        self._mod_quest_step_cursor = 0
        self._mod_quest_step_scroll = 0
        # Step field editor
        self._mod_quest_step_fields = []
        self._mod_quest_step_field = 0
        self._mod_quest_step_buffer = ""
        self._mod_quest_step_field_scroll = 0
        # Naming overlay (shared for quest + step naming)
        self._mod_quest_naming = False
        self._mod_quest_name_buf = ""
        self._mod_quest_naming_is_new = False
        self._mod_quest_naming_target = ""   # "quest" or "step"
        # Save flash
        self._mod_quest_save_flash = 0.0
        # Reward-items picker overlay (quest settings screen)
        self._mod_quest_item_picker_active = False
        self._mod_quest_item_picker_cursor = 0
        self._mod_quest_item_picker_scroll = 0
        self._mod_quest_item_picker_list = None  # lazy-loaded

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
        self.settings_options = []
        self._rebuild_settings_options()

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
        self.pending_combat_location = ""
        # Examine tile persistence (must exist before examine state enter())
        self.examined_tiles = {}
        # Boat / sailing state
        self.on_boat = False
        self.boat_anim_frame = 0
        self.boat_anim_accum = 0

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

    @property
    def title_options(self):
        """Build title menu options dynamically.

        Adds RETURN TO GAME at the top when a game is in progress or a
        save exists.  Inserts EDIT GAME before SETTINGS when Dungeon
        Master mode is enabled.
        """
        opts = list(self._title_options_base)
        if self.dm_mode:
            # Insert EDIT GAME before SETTINGS
            settings_idx = next(
                (i for i, o in enumerate(opts) if o["label"] == "SETTINGS"),
                len(opts) - 1)
            opts.insert(settings_idx, self._title_dm_option)
        if self._game_started or self._find_most_recent_save() is not None:
            opts = ([{"label": "RETURN TO GAME",
                       "action": self._title_return_to_game}]
                    + opts)
        return opts

    # ── Title screen actions ────────────────────────────────────

    def _rebuild_title_options(self):
        """Clamp the title cursor after DM mode changes.

        The title_options property builds the list dynamically, so this
        just ensures the cursor stays in range.
        """
        if hasattr(self, 'title_cursor'):
            self.title_cursor = min(self.title_cursor,
                                    len(self.title_options) - 1)

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
        self.module_quest_states = {}
        self.overworld_quest_npcs = []
        self.quest_spawned_monsters = {}
        self.quest_interior_monsters = {}
        self.quest_dungeon_monsters = {}
        self.quest_collect_items = {}
        self.game_log = []
        self.dungeon_cache = {}  # clear persisted dungeon layouts

        # ── Scrub per-state overlays (interior darkness, shop/temple
        # overlays, dungeon torch timers, etc.) — the state objects are
        # cached on self.states and reused across games, so any flag
        # still set from a prior session will bleed into the new game
        # (e.g. overworld drawn with interior darkness on a fresh map).
        for _st_name in ("overworld", "town", "dungeon"):
            _st = self.states.get(_st_name) if hasattr(self, "states") else None
            if _st is not None and hasattr(_st, "reset_for_new_game"):
                try:
                    _st.reset_for_new_game()
                except Exception:
                    # Don't let a buggy reset stop the new game — log
                    # and move on so the player isn't stuck on title.
                    import logging
                    logging.getLogger(__name__).exception(
                        "reset_for_new_game failed for %s", _st_name)

        # ── Load module data (items, races, monsters, etc.) ──
        if self.active_module_path:
            self.module_manifest = load_module_data(self.active_module_path)
        else:
            # No active module - still refresh spell/item data from
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
        self.camera = Camera(
            self.tile_map.width, self.tile_map.height,
            viewport_cols=30, viewport_rows=20,
        )
        # Re-wire the renderer's camera reference since we just
        # replaced the camera instance.
        if getattr(self, "renderer", None) is not None:
            self.renderer.camera = self.camera

        # ── Validate bidirectional links ──
        if self.active_module_path:
            from src.tile_map import validate_module_links
            validate_module_links(self.active_module_path)


        if self.party.members:
            # Player already formed a party - keep roster & active members,
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
            # Reset the Galadriel's Light step counter + last-day tracker
            # so the lantern's dungeon-light bonus from the prior game
            # doesn't bleed into the new one.
            if hasattr(self.party, "galadriels_light_steps"):
                self.party.galadriels_light_steps = 0
            if hasattr(self.party, "last_galadriels_light_day"):
                self.party.last_galadriels_light_day = -1

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
            # No active party formed - use the default from party.json
            self.party = create_default_party(
                start_with_equipment=self.start_with_equipment)

            # Module overworld may override the start position
            if overworld_cfg:
                mod_start = overworld_cfg.get("start_position")
                if mod_start:
                    self.party.col = mod_start.get("col", self.party.col)
                    self.party.row = mod_start.get("row", self.party.row)

        # ── Overview map party_start overrides everything ──
        if self.active_module_path:
            _ov_path = os.path.join(
                self.active_module_path, "overview_map.json")
            if os.path.isfile(_ov_path):
                try:
                    with open(_ov_path, "r") as _fh:
                        _ov_data = json.load(_fh)
                except (OSError, json.JSONDecodeError):
                    _ov_data = {}
                _ps = _ov_data.get("party_start")
                if _ps:
                    self.party.col = _ps.get("col", self.party.col)
                    self.party.row = _ps.get("row", self.party.row)

        # ── Clamp start position to map bounds & find walkable tile ──
        from src.settings import TILE_WATER, TILE_MOUNTAIN
        mw, mh = self.tile_map.width, self.tile_map.height
        self.party.col = max(0, min(mw - 1, self.party.col))
        self.party.row = max(0, min(mh - 1, self.party.row))
        # If the clamped position is not walkable, search outward
        NON_WALKABLE = {TILE_WATER, TILE_MOUNTAIN}
        if self.tile_map.get_tile(self.party.col, self.party.row) in NON_WALKABLE:
            found = False
            for radius in range(1, max(mw, mh)):
                if found:
                    break
                for dr in range(-radius, radius + 1):
                    for dc in range(-radius, radius + 1):
                        c, r = self.party.col + dc, self.party.row + dr
                        if (0 <= c < mw and 0 <= r < mh
                                and self.tile_map.get_tile(c, r)
                                not in NON_WALKABLE):
                            self.party.col, self.party.row = c, r
                            found = True
                            break
                    if found:
                        break

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

        self.visited_dungeons = set()  # {(col, row)} - tracks which dungeon tiles the party has entered

        # Persistent dungeon cache: {(col,row): [DungeonData, ...]}
        # Stores generated dungeons so re-entry preserves state (explored
        # tiles, opened chests, triggered traps, killed monsters).
        self.dungeon_cache = {}

        # ── Module key-dungeon quests ──
        self.key_dungeons = {}  # {(col,row): {dungeon_number, name, key_name, ...}}
        self.pending_combat_rewards = None  # set by combat victory, consumed by source state
        self.pending_killed_monsters = []   # monster names killed in last combat
        self.pending_combat_location = ""   # where the combat took place
        self.town_data_map = {}
        if self.module_manifest:
            prog = self.module_manifest.get("progression", {})
            kd_list = prog.get("key_dungeons", [])
            if kd_list:
                self._init_key_dungeons(kd_list)
            # Generate all towns from the manifest
            self._init_module_towns()

        # Inject module quest giver NPCs into towns
        self._inject_module_quest_npcs()

        self._game_started = True
        self.showing_title = False

        # Show a dramatic intro screen with the module name and lore
        # before dropping the player into the overworld.
        meta = {}
        if self.module_manifest:
            meta = self.module_manifest.get("metadata", {})
        mod_name = meta.get("name", self.active_module_name or "")
        mod_desc = meta.get("description", "")
        if mod_name or mod_desc:
            self._intro_module_name = mod_name
            self._intro_module_desc = mod_desc
            self._intro_elapsed = 0.0
            self.showing_intro = True
        else:
            # No module metadata — skip straight to game
            self.change_state("overworld")
            self.camera.update(self.party.col, self.party.row)

    @staticmethod
    def _generate_window_icon():
        """Create a 32×32 procedural window icon - dark-fantasy crystal."""
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

        Dungeons start as ``"undiscovered"`` - the quest objective is
        hidden until the town elder reveals them.
        """
        from src.dungeon_generator import generate_keys_dungeon

        overworld_cfg = self.module_manifest.get("_overworld_cfg", {})
        landmarks = {lm["id"]: lm for lm in overworld_cfg.get("landmarks", [])}

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
            # Kill quests don't need an artifact tile - the portal
            # spawns when enough monsters are killed instead.
            needs_artifact = (quest_type != "kill")
            kt = kd.get("kill_target", "") if quest_type == "kill" else None
            kc = int(kd.get("kill_count", 0)) if quest_type == "kill" else 0
            td = kd.get("torch_density", "medium")
            dsz = kd.get("size", "medium")
            locked = kd.get("locked_doors", "off") == "on"
            levels = generate_keys_dungeon(
                dnum, name=name,
                place_artifact=needs_artifact,
                module_levels=module_levels,
                kill_target=kt, kill_count=kc,
                torch_density=td,
                dungeon_size=dsz,
                place_doors=locked)
            self.key_dungeons[(col, row)] = {
                "dungeon_number": dnum,
                "name": name,
                "key_name": key_name,
                "levels": levels,
                "current_level": 0,
                "status": "undiscovered",  # undiscovered → active → artifact_found → completed
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

        self.town_data_map = {}
        first_town = None
        town_ordinal = 0  # guarantees each town gets a different layout

        # Pre-load towns.json so landmark towns can use user-edited tile
        # data instead of layout templates or procedural generation.
        if self.active_module_path:
            self._load_module_towns(self.active_module_path)
        _towns_json_by_name = {
            t.get("name", ""): t
            for t in getattr(self, "_mod_town_list", [])
            if t.get("name")
        }

        for i, lm in enumerate(overworld_cfg.get("landmarks", [])):
            if lm.get("type") != "town":
                continue
            tid = lm["id"]
            tname = town_names.get(tid, tid.replace("_", " ").title())
            col, row = lm["col"], lm["row"]
            # Unique seed per town so NPCs and dialogue vary
            town_seed = hash((tname, col, row, i)) & 0xFFFFFFFF
            tc = town_configs.get(tid, {})
            # Prefer user-edited town from towns.json over layout
            # templates or procedural generation - this is the map the
            # player actually designed in the town editor.
            td = None
            if tname in _towns_json_by_name:
                td = self._build_town_from_towns_json(
                    _towns_json_by_name[tname])
            if td is None:
                custom_layout = tc.get("layout", "")
                if custom_layout:
                    # Use a player-created layout from town_templates.json
                    td = self._build_town_from_layout(
                        custom_layout, tname,
                        town_style=tc.get("style", "medieval"))
                if td is None:
                    # Layout not found - fall back to procedural
                    td = generate_town(
                        tname, seed=town_seed,
                        layout_index=town_ordinal,
                        has_key_dungeons=bool(self.key_dungeons),
                        innkeeper_quests=inn_quests,
                        town_config=tc)
            town_ordinal += 1
            self.town_data_map[(col, row)] = td
            if first_town is None:
                first_town = td

        # ── Register maps from tile_properties links ──
        # Tiles on the overview map can link to towns, buildings, or
        # dungeons via the tile_properties system.  Register any linked
        # towns/dungeons that aren't already in the data maps.
        tile_props = getattr(self.tile_map, 'tile_properties', {})
        for pos_key, props in tile_props.items():
            if not props.get("linked"):
                continue
            link_map = props.get("link_map", "")
            if not link_map:
                continue
            parts = pos_key.split(",")
            if len(parts) != 2:
                continue
            col, row = int(parts[0]), int(parts[1])
            if (col, row) in self.town_data_map:
                continue  # already registered

            # Town links
            if link_map.startswith("town:"):
                town_name = link_map[5:]
                if town_name in _towns_json_by_name:
                    td = self._build_town_from_towns_json(
                        _towns_json_by_name[town_name])
                    if td is not None:
                        self.town_data_map[(col, row)] = td
                        if first_town is None:
                            first_town = td

        # ── Overlay custom data from towns.json ──
        # If the user added enclosures to a town via the editor,
        # overlay those onto the matching TownData.
        # This handles cases where a town was generated procedurally
        # from a landmark but the user later added custom content.
        for town_def in getattr(self, "_mod_town_list", []):
            tname = town_def.get("name", "")
            if not tname:
                continue
            custom_interiors = town_def.get("interiors", [])
            if not custom_interiors:
                continue
            # Apply to every TownData with matching name
            for td_obj in self.town_data_map.values():
                if getattr(td_obj, "name", "") != tname:
                    continue
                if custom_interiors:
                    td_obj.interiors = custom_interiors

        # Set the default town_data to the first town (hub)
        if first_town:
            self.town_data = first_town

        # Distribute key dungeon quests as individual NPCs across towns
        self._assign_quest_npcs()

    def _assign_quest_npcs(self):
        """Distribute key dungeon quests across towns as NPCs.

        Each quest gets its own quest_giver NPC placed in a randomly
        chosen town.  The mapping is stored in
        ``self.quest_npc_assignments`` so it can be persisted across
        saves / town regeneration.
        """
        from src.town_generator import add_quest_giver_npc, _QUEST_GIVER_POOL

        # Collect quests that need distributing
        quests_to_assign = list(self.key_dungeons.items())

        if not quests_to_assign or not self.town_data_map:
            self.quest_npc_assignments = {}
            return

        # Only assign quest NPCs to procedurally generated towns.
        # User-created towns (custom=True, loaded from towns.json) have
        # hand-placed NPCs and should not receive auto-injected content.
        town_keys = [
            k for k, td in self.town_data_map.items()
            if not getattr(td, "custom", False)
        ]
        if not town_keys:
            self.quest_npc_assignments = {}
            return

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
            # Two quests may end up in the same town - that's fine.
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
                # Town name mismatch (shouldn't happen) - put in first town
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

    def _inject_module_quest_npcs(self):
        """Load quests.json and inject quest-giver NPCs into runtime maps.

        For each quest that has a ``giver_location`` set, creates an NPC
        of type ``module_quest_giver`` in the matching town.  Also
        initialises ``module_quest_states`` for quests that haven't been
        tracked yet.
        """
        import json
        import os
        from src.town_generator import NPC

        if not self.active_module_path:
            return
        p = os.path.join(self.active_module_path, "quests.json")
        if not os.path.isfile(p):
            return
        try:
            with open(p, "r") as f:
                quest_list = json.load(f)
            if not isinstance(quest_list, list):
                return
        except (OSError, json.JSONDecodeError):
            return

        # Store the raw definitions for dialogue / step lookups
        self._module_quest_defs = quest_list
        # Overworld quest NPCs (placed on the overview map)
        if not hasattr(self, "overworld_quest_npcs"):
            self.overworld_quest_npcs = []

        # Build town lookup by name (for matching giver_location)
        town_by_name = {}
        for _tk, td in self.town_data_map.items():
            town_by_name[getattr(td, "name", "")] = td

        for qdef in quest_list:
            qname = qdef.get("name", "")
            if not qname:
                continue
            loc = qdef.get("giver_location", "")
            sprite = qdef.get("giver_sprite", "") or None
            dialogue_text = qdef.get("giver_dialogue", "")
            npc_label = qdef.get("giver_npc", "") or qname

            # Initialise quest state if new
            if qname not in self.module_quest_states:
                steps = qdef.get("steps", [])
                self.module_quest_states[qname] = {
                    "status": "available",  # available → active → completed
                    "step_progress": [False] * len(steps),
                }

            # Build dialogue lines (shared by both town and overworld)
            if dialogue_text:
                lines = [s.strip() for s in dialogue_text.split("\n")
                         if s.strip()]
                if not lines:
                    lines = [dialogue_text]
            else:
                lines = [f"I have a quest for you: {qname}"]

            # Parse location to find the target TownData or overworld
            target_td = None
            is_overworld = False
            if loc.startswith("town:"):
                town_name = loc[5:]
                target_td = town_by_name.get(town_name)
            elif loc.startswith("building:") or loc.startswith("space:"):
                # For building/space locations we'd need interior map
                # injection - skip for now, only towns supported
                pass
            elif loc.startswith("dungeon:"):
                # Dungeon interior - skip for now
                pass
            elif loc == "Overview Map" or loc == "overview":
                is_overworld = True

            if is_overworld:
                # ── Place NPC on the overworld map ──
                already = any(
                    getattr(n, "_module_quest_name", "") == qname
                    for n in self.overworld_quest_npcs
                )
                if already:
                    continue

                # If designer set explicit giver_col / giver_row, use
                # those directly; otherwise fall back to the ring search
                # near the party's starting position.
                explicit_col = qdef.get("giver_col")
                explicit_row = qdef.get("giver_row")

                from src.settings import TILE_GRASS, TILE_PATH
                tmap = self.tile_map
                party_col = self.party.col
                party_row = self.party.row
                occupied = {(n.col, n.row)
                            for n in self.overworld_quest_npcs}
                occupied.add((party_col, party_row))

                placed = None
                if (explicit_col is not None and explicit_row is not None
                        and isinstance(explicit_col, int)
                        and isinstance(explicit_row, int)):
                    placed = (explicit_col, explicit_row)
                else:
                    # Ring-based search near the party start
                    _r = __import__("random").Random(
                        hash(qname) & 0xFFFFFFFF)
                    for ring in range(3, 20):
                        candidates = []
                        for dc in range(-ring, ring + 1):
                            for dr in range(-ring, ring + 1):
                                if max(abs(dc), abs(dr)) != ring:
                                    continue
                                c, r = party_col + dc, party_row + dr
                                if (0 <= c < tmap.width
                                        and 0 <= r < tmap.height
                                        and tmap.get_tile(c, r) in (
                                            TILE_GRASS, TILE_PATH)
                                        and (c, r) not in occupied):
                                    candidates.append((c, r))
                        if candidates:
                            placed = _r.choice(candidates)
                            break
                if placed is None:
                    placed = (party_col + 4, party_row + 4)
                col, row = placed
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
                self.overworld_quest_npcs.append(npc)
                continue

            if target_td is None:
                continue

            # ── Place NPC inside a town ──
            # Check if this NPC was already injected (avoid duplicates on
            # repeated calls, e.g. after loading a save)
            already = any(
                getattr(n, "_module_quest_name", "") == qname
                for n in target_td.npcs
            )
            if already:
                continue

            tmap = target_td.tile_map
            occupied = {(n.col, n.row) for n in target_td.npcs}
            occupied.add((target_td.entry_col, target_td.entry_row))

            # If the designer set explicit giver_col / giver_row in the
            # quest editor, honor them.  Coordinates are interpreted in
            # the town's interior coordinate space (the playable region
            # inside the walls), with (0, 0) being the top-left interior
            # tile.  This matches what the user sees in the editor.
            explicit_col = qdef.get("giver_col")
            explicit_row = qdef.get("giver_row")
            placed = None
            if (isinstance(explicit_col, int)
                    and isinstance(explicit_row, int)):
                # Translate interior-relative coords to absolute tile
                # coords using the town's interior origin if available.
                ix = getattr(target_td, "interior_origin_x", None)
                iy = getattr(target_td, "interior_origin_y", None)
                if ix is None or iy is None:
                    # Fall back to absolute coords if interior origin
                    # isn't tracked on this town.
                    abs_col, abs_row = explicit_col, explicit_row
                else:
                    abs_col = ix + explicit_col
                    abs_row = iy + explicit_row
                if (0 <= abs_col < tmap.width
                        and 0 <= abs_row < tmap.height
                        and tmap.is_walkable(abs_col, abs_row)):
                    placed = (abs_col, abs_row)

            if placed is None:
                # Find an open walkable tile in the town's largest
                # connected region.  Custom towns may have the entry door
                # walled off from the interior (the player passes through
                # it during the transition), so a plain BFS from the
                # entry can fail.  Instead, find ALL walkable connected
                # components and use the one that contains the entry tile
                # (the playable interior) — falling back to the largest
                # component if the entry isn't walkable.
                from collections import deque
                visited = set()
                best_component = []
                entry_component = []
                entry_pos = (target_td.entry_col, target_td.entry_row)
                for sy in range(tmap.height):
                    for sx in range(tmap.width):
                        if ((sx, sy) in visited
                                or not tmap.is_walkable(sx, sy)):
                            continue
                        # BFS to find this connected component
                        component = []
                        queue = deque([(sx, sy)])
                        visited.add((sx, sy))
                        while queue:
                            cx, cy = queue.popleft()
                            component.append((cx, cy))
                            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                                nx, ny = cx + dx, cy + dy
                                if ((nx, ny) not in visited
                                        and 0 <= nx < tmap.width
                                        and 0 <= ny < tmap.height
                                        and tmap.is_walkable(nx, ny)):
                                    visited.add((nx, ny))
                                    queue.append((nx, ny))
                        if entry_pos in component:
                            entry_component = component
                        if len(component) > len(best_component):
                            best_component = component

                # Prefer the component containing the entry tile so the
                # quest giver is always in the same playable area as the
                # player.  Fall back to the largest component otherwise.
                preferred = entry_component or best_component
                all_floor = [p for p in preferred if p not in occupied]

                if all_floor:
                    if occupied:
                        def _min_dist(pos):
                            return min(abs(pos[0] - ox) + abs(pos[1] - oy)
                                       for ox, oy in occupied)
                        all_floor.sort(key=_min_dist, reverse=True)
                        top_n = max(1, len(all_floor) // 4)
                        import random as _rng
                        _r = _rng.Random(hash(qname) & 0xFFFFFFFF)
                        placed = _r.choice(all_floor[:top_n])
                    else:
                        import random as _rng
                        _r = _rng.Random(hash(qname) & 0xFFFFFFFF)
                        placed = _r.choice(all_floor)
            if placed is None:
                placed = (target_td.entry_col, target_td.entry_row)

            col, row = placed

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
            npc.wander_range = 4  # wander around like other NPCs
            target_td.npcs.append(npc)

    # ── Quest monster spawning ─────────────────────────────────────

    def _resolve_monster_key(self, monster_display):
        """Convert a display name like 'Fire Wolf' to a MONSTERS dict key."""
        from src.monster import MONSTERS
        if not monster_display or monster_display == "(none)":
            return None
        monster_key = monster_display.lower().replace(" ", "_")
        if monster_key not in MONSTERS:
            for k in MONSTERS:
                if k.replace("_", " ").title() == monster_display:
                    monster_key = k
                    break
        if monster_key not in MONSTERS:
            return None
        return monster_key

    def _resolve_quest_encounter(self, encounter_display):
        """Resolve a quest step's encounter name to (template, rep_key).

        ``template`` is the raw encounters.json dict (with ``monsters``
        and ``monster_party_tile``), or ``None`` if the name is unknown.
        ``rep_key`` is the MONSTERS key to use for the representative
        quest-marker NPC on the map — preferring ``monster_party_tile``
        so the sprite matches how the encounter is normally shown, and
        falling back to the first monster in the list.
        """
        from src.monster import find_encounter_template
        if not encounter_display or encounter_display == "(none)":
            return (None, None)
        tmpl = find_encounter_template(encounter_display)
        if tmpl is None:
            return (None, None)
        rep_name = tmpl.get("monster_party_tile") or ""
        if not rep_name:
            mons = tmpl.get("monsters") or []
            rep_name = mons[0] if mons else ""
        rep_key = self._resolve_monster_key(rep_name) if rep_name else None
        return (tmpl, rep_key)

    def _parse_spawn_location(self, spawn_loc):
        """Parse a spawn_location string into (type, name) tuple.

        Returns e.g. ("overview", ""), ("interior", "General Shop"),
        ("dungeon", "Dank Place"), ("town", "New York").
        """
        if not spawn_loc or spawn_loc in ("overview", "Overview Map"):
            return ("overview", "")
        if spawn_loc.startswith("interior:"):
            rest = spawn_loc[len("interior:"):]
            if "/" in rest:
                _town_name, interior_name = rest.split("/", 1)
            else:
                interior_name = rest
            return ("interior", interior_name)
        if spawn_loc.startswith("dungeon:"):
            return ("dungeon", spawn_loc[len("dungeon:"):])
        if spawn_loc.startswith("town:"):
            return ("town", spawn_loc[5:])
        if spawn_loc.startswith("building:"):
            return ("building", spawn_loc[len("building:"):])
        if spawn_loc.startswith("space:"):
            # Format: "space:BuildingName/SpaceName"
            # Returns ("space", "BuildingName/SpaceName") so items
            # are placed only in the specific space, not all spaces.
            return ("space", spawn_loc[len("space:"):])
        return ("overview", "")

    def _spawn_quest_monsters(self, quest_name):
        """Spawn monsters and collect items for quest steps when quest is accepted.

        For 'kill' steps: creates Monster objects at the specified location.
        For 'collect' steps: registers the collectible item (and optional
        guardian monster) to appear at the specified location.
        """
        import random as _rng
        from src.monster import create_monster, MONSTERS
        from src.settings import TILE_GRASS, TILE_PATH, TILE_FLOOR

        if not hasattr(self, "quest_spawned_monsters"):
            self.quest_spawned_monsters = {}
        if not hasattr(self, "quest_collect_items"):
            self.quest_collect_items = {}  # {location_key: [{item info}]}

        quest_defs = getattr(self, "_module_quest_defs", [])
        qdef = None
        for q in quest_defs:
            if q.get("name") == quest_name:
                qdef = q
                break
        if not qdef:
            return

        steps = qdef.get("steps", [])
        spawned = []

        for step_idx, step in enumerate(steps):
            step_type = step.get("step_type", "")
            spawn_loc = step.get("spawn_location", "")
            loc_type, loc_name = self._parse_spawn_location(spawn_loc)

            if step_type == "kill":
                enc_name = step.get("encounter", "")
                tmpl, monster_key = self._resolve_quest_encounter(enc_name)
                if not monster_key:
                    continue
                target_count = max(1, step.get("target_count", 1))

                if loc_type == "overview":
                    self._spawn_quest_monsters_overworld(
                        quest_name, step_idx, monster_key,
                        target_count, spawned,
                        encounter_name=enc_name)
                elif loc_type == "town":
                    self._spawn_quest_monsters_town(
                        quest_name, step_idx, monster_key,
                        target_count, loc_name, spawned,
                        encounter_name=enc_name)
                elif loc_type == "interior":
                    self._register_quest_interior_monster(
                        quest_name, step_idx, monster_key,
                        target_count, loc_name,
                        encounter_name=enc_name)
                elif loc_type == "dungeon":
                    self._register_quest_dungeon_monster(
                        quest_name, step_idx, monster_key,
                        target_count, loc_name,
                        encounter_name=enc_name)
                elif loc_type == "building":
                    # Register under building key for deferred spawning
                    self._register_quest_interior_monster(
                        quest_name, step_idx, monster_key,
                        target_count, loc_name,
                        key_prefix="building",
                        encounter_name=enc_name)
                elif loc_type == "space":
                    # "space:BuildingName/SpaceName" → register under
                    # the building name so it spawns in that building,
                    # but use a space-specific key for finer matching.
                    self._register_quest_interior_monster(
                        quest_name, step_idx, monster_key,
                        target_count, loc_name,
                        key_prefix="space",
                        encounter_name=enc_name)

            elif step_type == "collect":
                collect_item = step.get("collect_item", "")
                if not collect_item or collect_item == "(none)":
                    continue
                has_guardian = step.get("has_guardian", "no") == "yes"
                guardian_key = None
                guardian_encounter_name = ""
                if has_guardian:
                    guardian_encounter_name = step.get(
                        "guardian_encounter", "")
                    _gtmpl, guardian_key = self._resolve_quest_encounter(
                        guardian_encounter_name)

                # Look up the artifact tile sprite for this item
                artifact_sprite = ""
                self._mod_quest_load_artifact_tiles()
                artifact_sprites = getattr(
                    self, "_mod_quest_artifact_sprites", {})
                artifact_sprite = artifact_sprites.get(collect_item, "")

                # Build the collect item registration
                item_info = {
                    "quest_name": quest_name,
                    "step_idx": step_idx,
                    "item_name": collect_item,
                    "item_sprite": artifact_sprite,
                    "has_guardian": has_guardian,
                    "guardian_key": guardian_key,
                    "target_count": max(1, step.get("target_count", 1)),
                }

                # Register at the appropriate location
                if loc_type == "interior":
                    loc_key = f"interior:{loc_name}"
                elif loc_type == "dungeon":
                    loc_key = f"dungeon:{loc_name}"
                elif loc_type == "town":
                    loc_key = f"town:{loc_name}"
                elif loc_type == "building":
                    loc_key = f"building:{loc_name}"
                elif loc_type == "space":
                    loc_key = f"space:{loc_name}"
                else:
                    loc_key = "overview"

                if loc_key not in self.quest_collect_items:
                    self.quest_collect_items[loc_key] = []
                self.quest_collect_items[loc_key].append(item_info)

                # Spawn the collect item and guardian at the location.
                # Guardians are anchored near the item they protect.
                if loc_type == "overview":
                    item_pos = self._spawn_quest_collect_overworld(
                        item_info, spawned)
                    if guardian_key:
                        self._spawn_quest_monsters_overworld(
                            quest_name, step_idx, guardian_key,
                            1, spawned, guardian_anchor=item_pos,
                            encounter_name=guardian_encounter_name)
                elif loc_type == "town":
                    self._register_quest_town_collect(
                        item_info, loc_name)
                    if guardian_key:
                        self._spawn_quest_monsters_town(
                            quest_name, step_idx, guardian_key,
                            1, loc_name, spawned,
                            encounter_name=guardian_encounter_name)
                elif loc_type == "interior":
                    # Store guardian anchor info for deferred spawning
                    if guardian_key:
                        self._register_quest_interior_monster(
                            quest_name, step_idx, guardian_key,
                            1, loc_name, is_guardian=True,
                            encounter_name=guardian_encounter_name)
                elif loc_type == "dungeon":
                    # Guardian for dungeon collect items is spawned by
                    # _inject_quest_dungeon_collect_items directly next
                    # to the artifact, so no separate registration needed.
                    pass
                elif loc_type == "building":
                    # Register guardian for deferred spawning in building
                    if guardian_key:
                        self._register_quest_interior_monster(
                            quest_name, step_idx, guardian_key,
                            1, loc_name, is_guardian=True,
                            key_prefix="building",
                            encounter_name=guardian_encounter_name)
                elif loc_type == "space":
                    # Register guardian for deferred spawning in a
                    # specific building space.
                    if guardian_key:
                        self._register_quest_interior_monster(
                            quest_name, step_idx, guardian_key,
                            1, loc_name, is_guardian=True,
                            key_prefix="space",
                            encounter_name=guardian_encounter_name)

        self.quest_spawned_monsters[quest_name] = spawned

    def _spawn_quest_monsters_overworld(self, quest_name, step_idx,
                                         monster_key, count, spawned,
                                         guardian_anchor=None,
                                         encounter_name=""):
        """Place quest monsters on the overworld near the party.

        If *guardian_anchor* is a ``(col, row)`` tuple the monsters are
        placed near that position instead of the party and are tagged as
        guardians so the movement AI keeps them leashed to the artifact.

        If *encounter_name* is given, the spawned monster's
        ``encounter_template`` uses the full monster list from that
        encounter so combat pits the party against the whole group.
        """
        import random as _rng
        from src.monster import create_monster, find_encounter_template
        from src.settings import TILE_GRASS, TILE_PATH

        # Resolve the encounter template once so each spawn uses the
        # same monster list / party-tile identity.
        enc_tmpl = find_encounter_template(encounter_name) \
            if encounter_name else None
        if enc_tmpl:
            enc_monster_names = list(enc_tmpl.get("monsters", []))
            enc_party_tile = (
                enc_tmpl.get("monster_party_tile") or monster_key)
            display_enc_name = enc_tmpl.get("name", encounter_name)
        else:
            enc_monster_names = [monster_key]
            enc_party_tile = monster_key
            display_enc_name = ""

        party = self.party
        ow_state = self.states.get("overworld")
        if not ow_state:
            return

        # Use the stashed overworld tile map if we're inside an interior,
        # since self.tile_map may be the interior's small map.
        stashed_tmap = getattr(ow_state, "_stashed_overworld_tile_map", None)
        tmap = stashed_tmap or self.tile_map

        # When inside an interior, monsters must go into the stashed
        # list so they appear on the overworld when the player exits
        # (the live overworld_monsters list is empty during interiors).
        stashed_monsters = getattr(
            ow_state, "_stashed_overworld_monsters", None)
        if stashed_tmap and stashed_monsters is not None:
            monster_list = stashed_monsters
        else:
            monster_list = ow_state.overworld_monsters

        occupied = {(m.col, m.row) for m in monster_list}

        # If inside an interior, use the stashed overworld position
        # (the door tile) instead of the party's interior coordinates.
        stack = getattr(ow_state, "_overworld_interior_stack", [])
        if stack:
            ow_col = stack[0].get("col", party.col)
            ow_row = stack[0].get("row", party.row)
        else:
            ow_col, ow_row = party.col, party.row
        occupied.add((ow_col, ow_row))

        rng = _rng.Random(hash((quest_name, step_idx)) & 0xFFFFFFFF)

        # If this is a guardian, place near the artifact instead of party
        anchor_col, anchor_row = (
            guardian_anchor if guardian_anchor else
            (ow_col, ow_row))

        for i in range(count):
            mon = create_monster(monster_key)
            # Tag monster for quest tracking
            mon._quest_name = quest_name
            mon._quest_step_idx = step_idx
            if encounter_name:
                mon._quest_encounter_name = encounter_name

            # Tag as guardian with anchor position
            if guardian_anchor:
                mon._guardian_anchor = guardian_anchor
                mon._guardian_leash = 4  # max tiles from artifact

            # Build the encounter template once per monster so combat
            # pulls the full group (not just the representative).
            enc_display = display_enc_name or f"Quest: {mon.name}"
            enc_template = {
                "name": enc_display,
                "monster_names": list(enc_monster_names),
                "monster_party_tile": enc_party_tile,
            }

            # Place near the anchor point (artifact or party)
            placed = False
            start_ring = 1 if guardian_anchor else 5
            for ring in range(start_ring, 25):
                candidates = []
                for dc in range(-ring, ring + 1):
                    for dr in range(-ring, ring + 1):
                        if max(abs(dc), abs(dr)) != ring:
                            continue
                        c, r = anchor_col + dc, anchor_row + dr
                        if (0 <= c < tmap.width
                                and 0 <= r < tmap.height
                                and tmap.get_tile(c, r) in (
                                    TILE_GRASS, TILE_PATH)
                                and (c, r) not in occupied):
                            candidates.append((c, r))
                if candidates:
                    col, row = rng.choice(candidates)
                    mon.col = col
                    mon.row = row
                    mon.encounter_template = enc_template
                    monster_list.append(mon)
                    occupied.add((col, row))
                    spawned.append(mon)
                    placed = True
                    break
            if not placed:
                # Fallback: place near anchor
                mon.col = anchor_col + 1 + i
                mon.row = anchor_row + 1
                if guardian_anchor:
                    mon._guardian_anchor = guardian_anchor
                    mon._guardian_leash = 4
                mon.encounter_template = enc_template
                monster_list.append(mon)
                spawned.append(mon)

    def _spawn_quest_collect_overworld(self, item_info, spawned):
        """Place a quest collectible item on the overworld near the party.

        Returns ``(col, row)`` of the placed item, or ``None``.
        """
        import random as _rng
        from src.town_generator import NPC
        from src.settings import TILE_GRASS, TILE_PATH

        tmap = self.tile_map
        party = self.party
        ow_npcs = getattr(self, "overworld_quest_npcs", [])

        occupied = set()
        for npc in ow_npcs:
            occupied.add((npc.col, npc.row))
        occupied.add((party.col, party.row))

        quest_name = item_info["quest_name"]
        step_idx = item_info["step_idx"]
        item_name = item_info["item_name"]
        item_sprite = item_info.get("item_sprite", "")

        rng = _rng.Random(
            hash((quest_name, step_idx, item_name)) & 0xFFFFFFFF)

        placed_pos = None
        for ring in range(3, 20):
            candidates = []
            for dc in range(-ring, ring + 1):
                for dr in range(-ring, ring + 1):
                    if max(abs(dc), abs(dr)) != ring:
                        continue
                    c, r = party.col + dc, party.row + dr
                    if (0 <= c < tmap.width
                            and 0 <= r < tmap.height
                            and tmap.get_tile(c, r) in (
                                TILE_GRASS, TILE_PATH)
                            and (c, r) not in occupied):
                        candidates.append((c, r))
            if candidates:
                col, row = rng.choice(candidates)
                npc = NPC(
                    col=col, row=row,
                    name=item_name,
                    dialogue=[f"You found {item_name}!"],
                    npc_type="quest_item",
                )
                npc._quest_name = quest_name
                npc._quest_step_idx = step_idx
                npc._item_sprite = item_sprite
                npc.quest_highlight = True
                ow_npcs.append(npc)
                occupied.add((col, row))
                placed_pos = (col, row)
                break
        if not placed_pos:
            # Fallback
            col, row = party.col + 5, party.row + 3
            npc = NPC(
                col=col, row=row,
                name=item_name,
                dialogue=[f"You found {item_name}!"],
                npc_type="quest_item",
            )
            npc._quest_name = quest_name
            npc._quest_step_idx = step_idx
            npc._item_sprite = item_sprite
            npc.quest_highlight = True
            ow_npcs.append(npc)
            placed_pos = (col, row)

        return placed_pos

    def _register_quest_town_collect(self, item_info, town_name):
        """Register a collect item to spawn when the player enters a town."""
        loc_key = f"town:{town_name}"
        if loc_key not in self.quest_collect_items:
            self.quest_collect_items[loc_key] = []
        # Already added in the main loop; this is a no-op placeholder
        # for future town-level collect spawning.
        pass

    def _spawn_quest_monsters_town(self, quest_name, step_idx,
                                    monster_key, count, town_name,
                                    spawned, encounter_name=""):
        """Place quest monsters in a specific town."""
        # Register them so they appear when the player enters the town.
        # The town state will read quest_interior_monsters and spawn
        # monster NPCs at runtime.
        if not hasattr(self, "quest_interior_monsters"):
            self.quest_interior_monsters = {}
        key = f"town:{town_name}"
        if key not in self.quest_interior_monsters:
            self.quest_interior_monsters[key] = []
        self.quest_interior_monsters[key].append({
            "monster_key": monster_key,
            "quest_name": quest_name,
            "step_idx": step_idx,
            "count": count,
            "encounter_name": encounter_name,
        })

    def _register_quest_interior_monster(self, quest_name, step_idx,
                                          monster_key, count,
                                          interior_name,
                                          is_guardian=False,
                                          key_prefix="interior",
                                          encounter_name=""):
        """Register quest monsters to spawn when the player enters an interior."""
        if not hasattr(self, "quest_interior_monsters"):
            self.quest_interior_monsters = {}
        key = f"{key_prefix}:{interior_name}"
        if key not in self.quest_interior_monsters:
            self.quest_interior_monsters[key] = []
        self.quest_interior_monsters[key].append({
            "monster_key": monster_key,
            "quest_name": quest_name,
            "step_idx": step_idx,
            "count": count,
            "is_guardian": is_guardian,
            "encounter_name": encounter_name,
        })

    def _register_quest_dungeon_monster(self, quest_name, step_idx,
                                         monster_key, count,
                                         dungeon_name,
                                         is_guardian=False,
                                         encounter_name=""):
        """Register quest monsters to spawn when the player enters a dungeon."""
        if not hasattr(self, "quest_dungeon_monsters"):
            self.quest_dungeon_monsters = {}
        key = dungeon_name
        if key not in self.quest_dungeon_monsters:
            self.quest_dungeon_monsters[key] = []
        self.quest_dungeon_monsters[key].append({
            "monster_key": monster_key,
            "quest_name": quest_name,
            "step_idx": step_idx,
            "count": count,
            "is_guardian": is_guardian,
            "encounter_name": encounter_name,
        })

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
            if tile_id == TILE_EXIT:
                entry_col, entry_row = col, row

        return TownData(
            tile_map=tm,
            npcs=[],
            name=town_name,
            entry_col=entry_col,
            entry_row=entry_row,
            town_style=town_style,
        )

    def _build_town_from_towns_json(self, town_def):
        """Build a TownData from a towns.json entry (user-created town).

        The town_def dict comes from the module's towns.json and contains
        a sparse tile grid, NPC definitions, entry position, and style.
        Returns a TownData, or *None* on failure.
        """
        from src.tile_map import TileMap
        from src.town_generator import TownData, NPC
        from src.settings import TILE_VOID, TILE_EXIT

        name = town_def.get("name", "Town")
        w = town_def.get("width", 20)
        h = town_def.get("height", 20)
        tiles_dict = town_def.get("tiles", {})
        if not tiles_dict:
            return None

        tm = TileMap(w, h, default_tile=TILE_VOID, oob_tile=TILE_VOID)
        entry_col = town_def.get("entry_col", w // 2)
        entry_row = town_def.get("entry_row", h - 1)

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
            if tile_id == TILE_EXIT:
                # Mark exit positions for NPC placement avoidance
                pass

        # Build NPC objects from the town definition
        npcs = []
        for nd in town_def.get("npcs", []):
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
            )
            npc.wander_range = nd.get("wander_range", 4)
            npcs.append(npc)

        # Distribute NPCs so none share a tile.  Collect all walkable
        # floor positions, then assign each NPC a unique random spot.
        import random as _rng
        walkable = set()
        for wy in range(h):
            for wx in range(w):
                if tm.is_walkable(wx, wy):
                    walkable.add((wx, wy))
        # Remove the entry tile
        walkable.discard((entry_col, entry_row))

        occupied = set()
        rng = _rng.Random(hash(name) & 0xFFFFFFFF)
        for npc in npcs:
            # If the NPC's current position is free, keep it
            pos = (npc.col, npc.row)
            if pos in walkable and pos not in occupied:
                occupied.add(pos)
                continue
            # Otherwise pick a random free walkable tile
            free = list(walkable - occupied)
            if free:
                nc, nr = rng.choice(free)
                npc.col = nc
                npc.row = nr
                npc.home_col = nc
                npc.home_row = nr
                occupied.add((nc, nr))


        td = TownData(
            tile_map=tm,
            npcs=npcs,
            name=name,
            entry_col=entry_col,
            entry_row=entry_row,
            town_style=town_def.get("town_style", "medieval"),
            custom=True,
            interiors=town_def.get("interiors", []),
            description=town_def.get("description", ""),
        )
        # Load per-tile instance properties (links, etc.)
        tp = town_def.get("tile_properties", {})
        td.tile_properties = tp
        td.tile_map.tile_properties = tp
        return td

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

    def _build_quest_log(self):
        """Build a list of quest entries for the quest log screen.

        Each entry is a dict with:
            name:   str   - quest title
            status: str   - 'active', 'completed', etc.
            steps:  list  - [{description: str, done: bool}, ...]
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
            for pos, kd in kd_map.items():
                kd_status = kd.get("status", "undiscovered")
                if kd_status == "undiscovered":
                    continue  # don't show quests the player hasn't learned about
                key_name = kd.get("key_name", "Key")
                dname = kd.get("name", "Key Dungeon")
                qtype = kd.get("quest_type", "retrieve")

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
                    # Retrieve quest: find the artifact/key
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

        # ── Module quests (user-created via the quest editor) ──
        for qdef in getattr(self, "_module_quest_defs", []):
            qname = qdef.get("name", "")
            if not qname:
                continue
            mq_state = self.module_quest_states.get(qname, {})
            status = mq_state.get("status", "available")
            if status == "available":
                continue  # don't show unaccepted quests
            step_progress = mq_state.get("step_progress", [])
            steps = []
            for i, sdef in enumerate(qdef.get("steps", [])):
                done = step_progress[i] if i < len(step_progress) else False
                desc = sdef.get("description", f"Step {i + 1}")
                stype = sdef.get("step_type", "")
                if stype:
                    desc = f"[{stype.title()}] {desc}"
                steps.append({"description": desc, "done": done})
            # Add a final "return to quest giver" step
            giver = qdef.get("giver_npc", "") or qname
            steps.append({
                "description": f"Return to {giver} for reward",
                "done": status == "turned_in",
            })
            if not steps:
                steps = [{"description": qdef.get("description", qname),
                           "done": status in ("completed", "turned_in")}]
            display_status = status
            if status == "turned_in":
                display_status = "completed"
            quests.append({
                "name": qname,
                "status": display_status,
                "steps": steps,
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

        # Done step - any key returns to previous screen
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
            # No characters - Ctrl+N to create, or ESC/Enter/Space to return
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
            # Game already running - just dismiss the title screen.
            # Refresh overworld interiors from disk in case the
            # module editor changed them since the game was started.
            self._refresh_overworld_interior_data()
            # Clear dungeon cache so edited dungeon layouts are rebuilt
            # with the latest level data on next entry.
            self.dungeon_cache = {}
            self.showing_title = False
            return

        # No game running - try to load the most recent save
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
        """Reload overworld interiors from disk.

        Called when returning to a running game so that any changes made in
        the module editor (add/delete/rename interiors) are
        picked up without requiring a full new-game restart.

        Checks two sources in priority order:
          1. static_overworld.json  (full static overworld format)
          2. overview_map.json      (module editor overview map format)
        """
        import json, os
        if not self.active_module_path:
            return

        sdata = None

        # ── 1. Try static_overworld.json ──
        static_path = os.path.join(
            self.active_module_path, "static_overworld.json")
        if os.path.isfile(static_path):
            try:
                with open(static_path, "r") as fh:
                    sdata = json.load(fh)
            except (OSError, json.JSONDecodeError):
                pass

        # ── 2. Fall back to overview_map.json ──
        if sdata is None:
            overview_path = os.path.join(
                self.active_module_path, "overview_map.json")
            if os.path.isfile(overview_path):
                try:
                    with open(overview_path, "r") as fh:
                        sdata = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    pass

        if sdata is None:
            return

        # If the player is inside an overworld interior, the current
        # tile_map is the interior map.  Update the stashed overworld
        # map instead.
        ow_state = self.states.get("overworld")
        stashed = (getattr(ow_state, "_stashed_overworld_tile_map", None)
                   if ow_state else None)
        tmap = stashed if stashed is not None else self.tile_map

        tmap.overworld_interiors = sdata.get("interiors", [])

        # Re-validate links after editor changes
        from src.tile_map import validate_module_links
        validate_module_links(self.active_module_path)

        # If the overview map tiles were also updated, refresh them
        # so the player sees the latest map layout.
        tiles = sdata.get("tiles")
        if tiles and isinstance(tiles, list):
            mc = sdata.get("map_config", {})
            new_w = mc.get("width", 0) or (len(tiles[0]) if tiles else 0)
            new_h = mc.get("height", 0) or len(tiles)
            if new_w == tmap.width and new_h == tmap.height:
                tmap.tiles = tiles

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
        """Enter edit mode for an existing module - Module Details only."""
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]

        self.module_edit_mode = True
        self.module_edit_is_new = False

        # ── Load overview map for this module (if it exists) ──
        self._mod_overview_map = self._load_module_overview_map(
            mod["path"])

        # ── Build section list ──
        has_map = self._mod_overview_map is not None
        overview_sub = ("Map assigned" if has_map
                        else "No map - choose a template")
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
            {
                "label": "Overview Map",
                "icon": "M",
                "subtitle": overview_sub,
                "_overview_map": True,
            },
            {
                "label": "Towns",
                "icon": "T",
                "subtitle": "",
                "_towns": True,
            },
            {
                "label": "Dungeons",
                "icon": "D",
                "subtitle": "",
                "_dungeons": True,
            },
            {
                "label": "Buildings",
                "icon": "B",
                "subtitle": "",
                "_buildings": True,
            },
            {
                "label": "Quests",
                "icon": "Q",
                "subtitle": "",
                "_quests": True,
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

        # ── Pre-load all module data so _mod_module_maps is available ──
        # This ensures the link manager's map selection list is populated
        # regardless of which sub-editor the user opens first.
        self._load_module_towns(mod["path"])
        self._load_module_dungeons(mod["path"])
        self._load_module_buildings(mod["path"])
        self._build_module_maps()

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

        # ── Level 2: overview map children browser ──
        if self.module_edit_level == 2:
            self._handle_overview_map_input(event)
            return

        # ── Level 3: overview map settings fields ──
        if self.module_edit_level == 3:
            self._handle_overview_settings_input(event)
            return

        # ── Levels 4-7: Town editor ──
        if self.module_edit_level in (4, 5, 6, 7):
            self._handle_town_edit_input(event)
            return

        # ── Levels 8-13: Dungeon editor ──
        if self.module_edit_level in (8, 9, 10, 11, 12, 13):
            self._handle_dungeon_edit_input(event)
            return

        # ── Levels 14-19: Building editor ──
        if self.module_edit_level in (14, 15, 16, 17, 18, 19):
            self._handle_building_edit_input(event)
            return

        # ── Levels 20-23: Quest editor ──
        if self.module_edit_level in (20, 21, 22, 23):
            self._handle_quest_edit_input(event)
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

        # ── Overview Map section: special handling ──
        if sec.get("_overview_map"):
            self._enter_overview_map_section()
            return

        # ── Towns section: special handling ──
        if sec.get("_towns"):
            self._enter_towns_section()
            return

        # ── Dungeons section: special handling ──
        if sec.get("_dungeons"):
            self._enter_dungeons_section()
            return

        # ── Buildings section: special handling ──
        if sec.get("_buildings"):
            self._enter_buildings_section()
            return

        # ── Quests section: special handling ──
        if sec.get("_quests"):
            self._enter_quests_section()
            return

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
            # Empty field list - only ESC to go back is meaningful.
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

    # ── Overview Map in Module ─────────────────────────────────

    def _load_module_overview_map(self, mod_path):
        """Load overview_map.json from a module directory, or None."""
        import json, os
        p = os.path.join(mod_path, "overview_map.json")
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def _save_module_overview_map(self):
        """Persist the current overview map data to the active module."""
        import json, os
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]
        p = os.path.join(mod["path"], "overview_map.json")
        try:
            with open(p, "w") as f:
                json.dump(self._mod_overview_map, f, indent=2)
        except OSError:
            pass

    def _enter_overview_map_section(self):
        """Handle entering the Overview Map section.

        If no map has been assigned yet, show a template picker so the
        player can choose a starting template.  Otherwise, show the
        two children: Settings and Edit Map.
        """
        if self._mod_overview_map is None:
            # ── Show template picker ──
            self._mod_overview_picking = True
            self._mod_overview_pick_cursor = 0
            self._mod_overview_pick_scroll = 0
            self._mod_overview_generate_mode = False
            self.module_edit_level = 2  # route input to overview handler
            # Load overview templates from map_templates.json
            fe = self.features_editor
            saved = fe.load_map_templates()
            raw = saved.get("me_overview", [])
            # Append a special "Generate Map" entry
            generate_entry = {
                "_generate": True,
                "label": "Generate Map",
                "subtitle": "Procedurally generate a new map",
            }
            self._mod_overview_pick_list = raw + [generate_entry]
        else:
            # ── Show children: Settings / Edit Map ──
            self._open_overview_map_children()

    def _open_overview_map_children(self):
        """Set up the children view for an assigned overview map."""
        mc = self._mod_overview_map.get("map_config", {})
        w = mc.get("width", 16)
        h = mc.get("height", 12)
        self._mod_overview_children = [
            {"label": "Settings", "_overview_settings": True},
            {"label": "Edit Map", "_overview_edit_map": True},
            {"label": "Change Template", "_overview_change": True},
        ]
        self._mod_overview_child_cursor = 0
        self._mod_overview_level = 0
        self.module_edit_level = 2  # special level for overview map

    def _pick_overview_template(self, idx):
        """Copy the selected template into the module as its overview map."""
        import copy
        if idx < 0 or idx >= len(self._mod_overview_pick_list):
            return
        tmpl = self._mod_overview_pick_list[idx]
        # Deep copy so the module's map is independent
        self._mod_overview_map = copy.deepcopy(tmpl)
        self._save_module_overview_map()

        # Update the section subtitle
        for sec in self.module_edit_sections:
            if sec.get("_overview_map"):
                sec["subtitle"] = "Map assigned"
                break

        # Close picker and open children
        self._mod_overview_picking = False
        self._open_overview_map_children()

    def _build_module_maps(self):
        """Build the module_maps list for the link manager.

        Collects all map addresses (overworld, towns, buildings, dungeons)
        from the currently loaded module data.  Stores the result on
        ``self._mod_module_maps`` so all sub-editors can share it.
        """
        module_maps = [("overworld", "Overworld")]
        for t in getattr(self, '_mod_town_list', []):
            tname = t.get("name", "")
            if tname:
                module_maps.append((f"town:{tname}", f"Town: {tname}"))
        for b in getattr(self, '_mod_building_list', []):
            bname = b.get("name", "")
            if bname:
                for sp in b.get("spaces", []):
                    spname = sp.get("name", "")
                    if spname:
                        module_maps.append(
                            (f"building:{bname}:{spname}",
                             f"Building: {bname} / {spname}"))
        for d in getattr(self, '_mod_dungeon_list', []):
            dname = d.get("name", "")
            if dname:
                for lv in d.get("levels", []):
                    lvname = lv.get("name", "")
                    if lvname:
                        module_maps.append(
                            (f"dungeon:{dname}:{lvname}",
                             f"Dungeon: {dname} / {lvname}"))
        self._mod_module_maps = module_maps
        return module_maps

    @staticmethod
    def _picker_max_visible():
        """Rows the enclosure template picker overlay actually draws.

        Kept in sync with ``Renderer._draw_building_enc_picker`` /
        ``_draw_town_enc_picker`` so the cursor-driven scroll window
        never desynchronises from the visible row count. Without this,
        templates past the visible rows get clipped off the bottom of
        the ADD SPACE dialog (the bug reported for Dungeon 4).

        Renderer constants:
            panel_h = SCREEN_HEIGHT - 130
            pad=12   (outer padding)
            row_h=40 (per-entry height)
            title_area=42 (title + margin)
            footer=80 (controls hint + margin)
        """
        from src.settings import SCREEN_HEIGHT
        panel_h = SCREEN_HEIGHT - 130
        content_h = panel_h - 12 * 2 - 42 - 80
        # Conservative floor so tiny screens still work.
        return max(4, content_h // 40)

    def _build_map_hierarchy(self):
        """Build the map hierarchy tree for the tile link picker.

        Returns a list of (map_id, display_label, indent_level) tuples
        representing the full module map tree:
          Overview Map
            Towns → Town Interiors
            Buildings → Building Spaces
            Dungeons → Dungeon Levels
        """
        # Ensure all module data is loaded so the hierarchy is complete
        mod_path = None
        if self.module_list and self.module_cursor < len(self.module_list):
            mod_path = self.module_list[self.module_cursor].get("path")
        elif self.active_module_path:
            mod_path = self.active_module_path
        if mod_path:
            if not getattr(self, '_mod_town_list', []):
                self._load_module_towns(mod_path)
            if not getattr(self, '_mod_building_list', []):
                self._load_module_buildings(mod_path)
            if not getattr(self, '_mod_dungeon_list', []):
                self._load_module_dungeons(mod_path)

        hierarchy = [("overworld", "Overview Map", 0)]

        # Towns and their interiors
        for town in getattr(self, '_mod_town_list', []):
            tname = town.get("name", "")
            if not tname:
                continue
            hierarchy.append((f"town:{tname}", f"Town: {tname}", 0))
            for interior in town.get("interiors", []):
                iname = interior.get("name", "")
                if iname:
                    hierarchy.append(
                        (f"interior:{tname}/{iname}", iname, 1))

        # Buildings and their spaces
        for bldg in getattr(self, '_mod_building_list', []):
            bname = bldg.get("name", "")
            if not bname:
                continue
            hierarchy.append((f"building:{bname}", f"Building: {bname}", 0))
            for space in bldg.get("spaces", []):
                sname = space.get("name", "")
                if sname:
                    hierarchy.append(
                        (f"building:{bname}:{sname}", sname, 1))

        # Dungeons and their levels
        for dung in getattr(self, '_mod_dungeon_list', []):
            dname = dung.get("name", "")
            if not dname:
                continue
            hierarchy.append((f"dungeon:{dname}", f"Dungeon: {dname}", 0))
            for level in dung.get("levels", []):
                lname = level.get("name", "")
                if lname:
                    hierarchy.append(
                        (f"dungeon:{dname}:{lname}", lname, 1))

        return hierarchy

    def _launch_module_overview_editor(self):
        """Launch the shared map editor for the module's overview map."""
        if self._mod_overview_map is None:
            return

        from src.map_editor import (
            MapEditorConfig, MapEditorState, MapEditorInputHandler,
            build_overworld_brushes,
            STORAGE_DENSE, GRID_FIXED, GRID_SCROLLABLE,
        )

        mc = self._mod_overview_map.get("map_config", {})
        w = mc.get("width", 16)
        h = mc.get("height", 12)
        tiles = self._mod_overview_map.get("tiles")

        fe = self.features_editor

        # Load all templates for stamp brush folders
        saved_all = fe.load_map_templates()

        brushes = build_overworld_brushes(
            fe.TILE_CONTEXT,
            all_templates=saved_all,
        )

        # If tiles are missing, create a default grid
        if (tiles is None or len(tiles) != h
                or not all(len(row) == w for row in tiles)):
            tiles = [[0] * w for _ in range(h)]
            self._mod_overview_map["tiles"] = tiles

        # ── Build interior list from module towns, dungeons, etc. ──
        # Each entry is {"name": str, "type": str} so the picker can
        # display available link targets.  Sub-interiors (town
        # interiors, building spaces) are included with a
        # "sub_interior" key so the overworld can link directly to
        # a specific room inside a town or building.
        interior_list = []
        mod = self.module_list[self.module_cursor]
        self._load_module_towns(mod["path"])
        for town in self._mod_town_list:
            tname = town.get("name", "")
            if tname:
                interior_list.append({
                    "name": tname,
                    "type": "town",
                })
                # Add each town interior as a linkable sub-target
                for sub in town.get("interiors", []):
                    sname = sub.get("name", "")
                    if sname:
                        interior_list.append({
                            "name": tname,
                            "type": "town",
                            "sub_interior": sname,
                        })
        self._load_module_dungeons(mod["path"])
        for dng in self._mod_dungeon_list:
            dname = dng.get("name", "")
            if dname:
                interior_list.append({
                    "name": dname,
                    "type": "dungeon",
                })
        self._load_module_buildings(mod["path"])
        for bldg in self._mod_building_list:
            bname = bldg.get("name", "")
            if bname:
                interior_list.append({
                    "name": bname,
                    "type": "building",
                })
                # Add each building space as a linkable sub-target
                for space in bldg.get("spaces", []):
                    spname = space.get("name", "")
                    if spname and spname != bname:
                        interior_list.append({
                            "name": bname,
                            "type": "building",
                            "sub_interior": spname,
                        })

        # ── Build module maps list ──
        module_maps = self._build_module_maps()

        # ── Load existing party start position ──
        party_start = self._mod_overview_map.get("party_start")

        def _on_save(st):
            self._mod_overview_map["tiles"] = st.tiles
            self._mod_overview_map["party_start"] = st.party_start
            self._mod_overview_map["tile_properties"] = st.tile_properties
            self._save_module_overview_map()

        def _on_exit(st):
            self._mod_overview_map["tiles"] = st.tiles
            self._mod_overview_map["party_start"] = st.party_start
            self._mod_overview_map["tile_properties"] = st.tile_properties
            self._save_module_overview_map()
            self.showing_features = False
            self.showing_modules = True
            self.module_edit_mode = True
            self._mod_map_editor_state = None

        config = MapEditorConfig(
            title=self._mod_overview_map.get("label", "Overview Map"),
            storage=STORAGE_DENSE,
            grid_type=GRID_SCROLLABLE,
            width=w,
            height=h,
            brushes=brushes,
            tile_context="overworld",
            supports_replace=True,
            supports_party_start=True,
            on_save=_on_save,
            on_exit=_on_exit,
            map_hierarchy=self._build_map_hierarchy(),
        )

        state = MapEditorState(config, tiles=tiles,
                               interior_list=interior_list,
                               party_start=party_start)
        # Restore per-tile instance properties from saved data
        saved_props = self._mod_overview_map.get("tile_properties", {})
        if saved_props:
            state.tile_properties = dict(saved_props)
        handler = MapEditorInputHandler(
            state, is_save_shortcut=self._is_save_shortcut)

        self._mod_map_editor_state = state
        self._mod_map_editor_handler = handler
        # Switch to showing the map editor
        self.module_edit_mode = False
        self.showing_modules = False
        self.showing_features = True
        fe.active_editor = "mod_overview_map"
        fe.level = 1  # renderer requires level >= 1 for editor views

    def _handle_overview_map_input(self, event):
        """Handle input for the Overview Map section (level 2).

        Dispatches between: template picker overlay, children browser
        (Settings / Edit Map), and settings field editor.
        """
        import pygame

        # ── Template picker overlay ──
        if self._mod_overview_picking:
            self._handle_overview_template_picker(event)
            return

        # ── Children browser ──
        children = self._mod_overview_children
        n = len(children)
        if not n:
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 0
            return

        if event.key == pygame.K_ESCAPE:
            self.module_edit_level = 0
            return
        if event.key == pygame.K_UP:
            self._mod_overview_child_cursor = (
                (self._mod_overview_child_cursor - 1) % n)
        elif event.key == pygame.K_DOWN:
            self._mod_overview_child_cursor = (
                (self._mod_overview_child_cursor + 1) % n)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            child = children[self._mod_overview_child_cursor]
            if child.get("_overview_settings"):
                # Build settings fields for the overview map
                mc = self._mod_overview_map.get("map_config", {})
                self.module_edit_fields = [
                    ["Label", "label",
                     self._mod_overview_map.get("label", ""),
                     "text", True],
                ]
                self.module_edit_field = 0
                self.module_edit_scroll = 0
                self.module_edit_buffer = self.module_edit_fields[0][2]
                self._mod_overview_level = 1
                self.module_edit_level = 3  # settings field editing
            elif child.get("_overview_edit_map"):
                self._launch_module_overview_editor()
            elif child.get("_overview_change"):
                # Re-open the template picker (replaces current map)
                self._mod_overview_picking = True
                self._mod_overview_pick_cursor = 0
                self._mod_overview_pick_scroll = 0
                self._mod_overview_generate_mode = False
                fe = self.features_editor
                saved = fe.load_map_templates()
                raw = saved.get("me_overview", [])
                generate_entry = {
                    "_generate": True,
                    "label": "Generate Map",
                    "subtitle": "Procedurally generate a new map",
                }
                self._mod_overview_pick_list = raw + [generate_entry]

    def _handle_overview_template_picker(self, event):
        """Handle input for the template picker overlay."""
        import pygame
        templates = self._mod_overview_pick_list
        n = len(templates)

        # ── Generate mode: editing width/height fields ──
        if self._mod_overview_generate_mode:
            self._handle_generate_fields_input(event)
            return

        if event.key == pygame.K_ESCAPE:
            self._mod_overview_picking = False
            self.module_edit_level = 0
            return
        if not n:
            return
        if event.key == pygame.K_UP:
            self._mod_overview_pick_cursor = (
                (self._mod_overview_pick_cursor - 1) % n)
        elif event.key == pygame.K_DOWN:
            self._mod_overview_pick_cursor = (
                (self._mod_overview_pick_cursor + 1) % n)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            selected = templates[self._mod_overview_pick_cursor]
            if selected.get("_generate"):
                # Enter generate mode with default dimensions
                self._mod_overview_generate_mode = True
                self._mod_overview_gen_fields = ["40", "30"]
                self._mod_overview_gen_field = 0
                self._mod_overview_gen_buffer = "40"
            else:
                self._pick_overview_template(self._mod_overview_pick_cursor)

    def _handle_generate_fields_input(self, event):
        """Handle input when editing generate-map dimension fields."""
        import pygame

        if event.key == pygame.K_ESCAPE:
            # Leave generate mode, return to picker list
            self._mod_overview_generate_mode = False
            return

        if event.key == pygame.K_UP or event.key == pygame.K_DOWN:
            # Save buffer, switch field
            self._mod_overview_gen_fields[
                self._mod_overview_gen_field] = self._mod_overview_gen_buffer
            self._mod_overview_gen_field = (
                1 - self._mod_overview_gen_field)
            self._mod_overview_gen_buffer = self._mod_overview_gen_fields[
                self._mod_overview_gen_field]
            return

        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            # Commit buffer and generate
            self._mod_overview_gen_fields[
                self._mod_overview_gen_field] = self._mod_overview_gen_buffer
            self._generate_overview_map()
            return

        # Text editing for dimension values
        if event.key == pygame.K_BACKSPACE:
            self._mod_overview_gen_buffer = \
                self._mod_overview_gen_buffer[:-1]
        elif event.unicode and event.unicode.isdigit():
            if len(self._mod_overview_gen_buffer) < 4:
                self._mod_overview_gen_buffer += event.unicode

    def _generate_overview_map(self):
        """Procedurally generate an overview map and save to module."""
        from src.tile_map import create_test_map
        import random

        # Parse dimensions with sensible defaults and bounds
        try:
            w = max(10, min(200, int(self._mod_overview_gen_fields[0])))
        except (ValueError, IndexError):
            w = 40
        try:
            h = max(10, min(200, int(self._mod_overview_gen_fields[1])))
        except (ValueError, IndexError):
            h = 30

        # Build a minimal overworld config with the requested dimensions
        overworld_cfg = {"size": {"width": w, "height": h}}

        # Generate the map
        seed = random.randint(0, 2 ** 31)
        tmap = create_test_map(seed=seed, overworld_cfg=overworld_cfg)

        # Build overview map dict matching the template format
        from src.map_editor import STORAGE_DENSE, GRID_FIXED
        self._mod_overview_map = {
            "label": "Generated Overworld",
            "map_config": {
                "storage": STORAGE_DENSE,
                "grid_type": GRID_FIXED,
                "tile_context": "overworld",
                "width": tmap.width,
                "height": tmap.height,
            },
            "tiles": tmap.tiles,
        }
        self._save_module_overview_map()

        # Update section subtitle
        for sec in self.module_edit_sections:
            if sec.get("_overview_map"):
                sec["subtitle"] = "Map assigned"
                break

        # Close picker and open children
        self._mod_overview_picking = False
        self._mod_overview_generate_mode = False
        self._open_overview_map_children()

    def _handle_overview_settings_input(self, event):
        """Handle input when editing overview map settings (level 3)."""
        import pygame

        if event.key == pygame.K_ESCAPE:
            # Commit buffer and apply settings
            if self.module_edit_fields:
                entry = self.module_edit_fields[self.module_edit_field]
                entry[2] = self.module_edit_buffer
            self._apply_overview_settings()
            self.module_edit_level = 2
            self.module_edit_fields = []
            return
        if self._is_save_shortcut(event):
            if self.module_edit_fields:
                entry = self.module_edit_fields[self.module_edit_field]
                entry[2] = self.module_edit_buffer
            self._apply_overview_settings()
            return
        self._handle_field_editor_input(event)

    def _apply_overview_settings(self):
        """Apply edited settings back to the overview map data."""
        if self._mod_overview_map is None:
            return
        for entry in self.module_edit_fields:
            key, val = entry[1], entry[2]
            if key == "label":
                self._mod_overview_map["label"] = val
            elif key in ("width", "height"):
                try:
                    self._mod_overview_map.setdefault(
                        "map_config", {})[key] = int(val)
                except ValueError:
                    pass
        self._save_module_overview_map()

    # ── Town Editor (within Module) ─────────────────────────────

    def _enter_towns_section(self):
        """Enter the Towns section from the module section browser.

        Loads the town list for the current module and switches to
        level 4 (town list browser).
        """
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]
        self._load_module_towns(mod["path"])
        # Update section subtitle
        for sec in self.module_edit_sections:
            if sec.get("_towns"):
                n = len(self._mod_town_list)
                sec["subtitle"] = f"{n} town{'s' if n != 1 else ''}"
                break
        self.module_edit_level = 4

    def _load_module_towns(self, mod_path):
        """Load towns.json from a module directory."""
        import json, os
        self._mod_town_list = []
        self._mod_town_cursor = 0
        self._mod_town_scroll = 0
        p = os.path.join(mod_path, "towns.json")
        if not os.path.isfile(p):
            return
        try:
            with open(p, "r") as f:
                data = json.load(f)
            self._mod_town_list = data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            pass

    def _save_module_towns(self):
        """Persist the current town list to the active module."""
        import json, os
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]
        p = os.path.join(mod["path"], "towns.json")
        try:
            with open(p, "w") as f:
                json.dump(self._mod_town_list, f, indent=2)
        except OSError:
            pass

    def _handle_mod_town_enc_list_input(self, event):
        """Handle input for the enclosure list (level 6, sub_cursor 2)."""
        import pygame

        # ── Import picker overlay ──
        if self._mod_town_enc_picking:
            self._handle_mod_town_enc_picker_input(event)
            return

        # ── Naming overlay (after picking template) ──
        if self._mod_town_enc_naming:
            self._handle_mod_town_enc_naming_input(event)
            return

        n = len(self._mod_town_enclosures)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self._mod_town_save_enclosures()
            self.module_edit_level = 5
            return

        # Import from template (Ctrl+N)
        if self._is_new_shortcut(event):
            self._mod_town_open_enc_picker()
            return

        # Delete enclosure (Ctrl+D)
        if self._is_delete_shortcut(event) and n > 0:
            self._mod_town_delete_enclosure()
            return

        # Save (Ctrl+S)
        if self._is_save_shortcut(event):
            self._mod_town_save_enclosures()
            self._save_module_towns()
            self._mod_town_save_flash = 1.5
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_town_enc_cursor = (
                self._mod_town_enc_cursor - 1) % n
            self._mod_town_enc_scroll = fe._adjust_scroll_generic(
                self._mod_town_enc_cursor, self._mod_town_enc_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_town_enc_cursor = (
                self._mod_town_enc_cursor + 1) % n
            self._mod_town_enc_scroll = fe._adjust_scroll_generic(
                self._mod_town_enc_cursor, self._mod_town_enc_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            # Open enclosure sub-screen (Townspeople | Edit Map)
            self._mod_town_enc_sub_cursor = 0
            self._mod_town_enc_edit_mode = 1

    def _handle_mod_town_enc_picker_input(self, event):
        """Handle input for the enclosure template import picker."""
        import pygame
        templates = self._mod_town_enc_pick_list
        n = len(templates)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE:
            self._mod_town_enc_picking = False
            return

        if not n:
            return

        # Match the renderer's actual row count so templates past row N
        # scroll into view correctly (the picker overlay shows ~11 rows).
        max_vis = self._picker_max_visible()

        if event.key == pygame.K_UP:
            self._mod_town_enc_pick_cursor = (
                self._mod_town_enc_pick_cursor - 1) % n
            self._mod_town_enc_pick_scroll = fe._adjust_scroll_generic(
                self._mod_town_enc_pick_cursor,
                self._mod_town_enc_pick_scroll,
                max_visible=max_vis)
        elif event.key == pygame.K_DOWN:
            self._mod_town_enc_pick_cursor = (
                self._mod_town_enc_pick_cursor + 1) % n
            self._mod_town_enc_pick_scroll = fe._adjust_scroll_generic(
                self._mod_town_enc_pick_cursor,
                self._mod_town_enc_pick_scroll,
                max_visible=max_vis)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            # Select template → show naming overlay to generate instance
            template = templates[self._mod_town_enc_pick_cursor]
            self._mod_town_enc_template = template
            self._mod_town_enc_naming = True
            if template.get("_blank"):
                self._mod_town_enc_name_buf = "New Enclosure"
            else:
                self._mod_town_enc_name_buf = template.get("label", "Interior")
            self._mod_town_enc_picking = False

    def _handle_mod_town_enc_naming_input(self, event):
        """Handle naming input after selecting a template to generate."""
        import pygame
        if event.key == pygame.K_ESCAPE:
            self._mod_town_enc_naming = False
            self._mod_town_enc_template = None
            return
        if event.key == pygame.K_RETURN:
            name = self._mod_town_enc_name_buf.strip()
            if name and self._mod_town_enc_template:
                self._mod_town_generate_enclosure(
                    name, self._mod_town_enc_template)
            self._mod_town_enc_naming = False
            self._mod_town_enc_template = None
            return
        if event.key == pygame.K_BACKSPACE:
            self._mod_town_enc_name_buf = self._mod_town_enc_name_buf[:-1]
            return
        if event.unicode and event.unicode.isprintable():
            self._mod_town_enc_name_buf += event.unicode

    # ── Dungeon editor ─────────────────────────────────────────
    #
    # Navigation hierarchy:
    #   Level 8  – Dungeon list browser
    #   Level 9  – Dungeon sub-screen   (Settings | Levels)
    #   Level 10 – Settings fields  OR  Level list
    #   Level 11 – Level sub-screen     (Edit Map | Encounters)
    #   Level 12 – Encounter list
    #   Level 13 – Encounter field editor
    #

    def _enter_dungeons_section(self):
        """Enter the Dungeons section from the module section browser."""
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]
        self._load_module_dungeons(mod["path"])
        for sec in self.module_edit_sections:
            if sec.get("_dungeons"):
                n = len(self._mod_dungeon_list)
                sec["subtitle"] = f"{n} dungeon{'s' if n != 1 else ''}"
                break
        self.module_edit_level = 8

    # ── Load / save ──

    def _load_module_dungeons(self, mod_path):
        """Load dungeons.json from a module directory."""
        import json, os
        self._mod_dungeon_list = []
        self._mod_dungeon_cursor = 0
        self._mod_dungeon_scroll = 0
        p = os.path.join(mod_path, "dungeons.json")
        if not os.path.isfile(p):
            return
        try:
            with open(p, "r") as f:
                data = json.load(f)
            self._mod_dungeon_list = data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            pass

    def _save_module_dungeons(self):
        """Persist the current dungeon list to the active module."""
        import json, os
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]
        p = os.path.join(mod["path"], "dungeons.json")
        try:
            with open(p, "w") as f:
                json.dump(self._mod_dungeon_list, f, indent=2)
        except OSError:
            pass

    # ── Dungeon-level helpers ──

    def _handle_mod_dungeon_sub_input(self, event):
        """Handle dungeon sub-screen (level 9): Settings | [Levels]."""
        import pygame
        self._mod_dungeon_refresh_sub_items()
        n = len(self._mod_dungeon_sub_items)
        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self.module_edit_level = 8
            return
        if event.key == pygame.K_UP:
            self._mod_dungeon_sub_cursor = (
                self._mod_dungeon_sub_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self._mod_dungeon_sub_cursor = (
                self._mod_dungeon_sub_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            if self._mod_dungeon_sub_cursor == 0:
                self._mod_dungeon_build_settings_fields()
                self.module_edit_level = 10
            elif self._mod_dungeon_sub_cursor == 1:
                self._mod_dungeon_load_levels()
                self.module_edit_level = 10

    def _handle_mod_dungeon_settings_field_input(self, event):
        """Handle dungeon settings field editing (level 10, sub 0).

        Supports text, int, and choice field types.  Choice fields
        cycle with Left/Right arrows instead of accepting typed text.
        """
        import pygame
        fields = self._mod_dungeon_fields
        n = len(fields)
        fe = self.features_editor
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 9
            return

        current_field = fields[self._mod_dungeon_field]
        is_choice = current_field.field_type == "choice"

        # ── Save text before leaving the field ──
        def _commit_text():
            if current_field.editable and not is_choice:
                current_field.value = self._mod_dungeon_buffer

        if self._is_save_shortcut(event):
            _commit_text()
            self._mod_dungeon_save_settings_fields()
            self._save_module_dungeons()
            self._mod_dungeon_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            _commit_text()
            self._mod_dungeon_save_settings_fields()
            self.module_edit_level = 9
            return

        # ── Left/Right: cycle choice fields ──
        if is_choice and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            direction = -1 if event.key == pygame.K_LEFT else 1
            self._mod_dungeon_cycle_choice(direction)
            return

        # ── Up/Down: navigate between fields ──
        if event.key == pygame.K_UP:
            _commit_text()
            self._mod_dungeon_field = fe._next_editable_generic(
                fields, (self._mod_dungeon_field - 1) % n)
            nf = fields[self._mod_dungeon_field]
            self._mod_dungeon_buffer = nf.value
            self._mod_dungeon_field_scroll = fe._adjust_field_scroll_generic(
                self._mod_dungeon_field, self._mod_dungeon_field_scroll)
        elif event.key == pygame.K_DOWN:
            _commit_text()
            self._mod_dungeon_field = fe._next_editable_generic(
                fields, (self._mod_dungeon_field + 1) % n)
            nf = fields[self._mod_dungeon_field]
            self._mod_dungeon_buffer = nf.value
            self._mod_dungeon_field_scroll = fe._adjust_field_scroll_generic(
                self._mod_dungeon_field, self._mod_dungeon_field_scroll)
        elif not is_choice:
            # Text/int typing
            if event.key == pygame.K_BACKSPACE:
                self._mod_dungeon_buffer = self._mod_dungeon_buffer[:-1]
            elif event.unicode and event.unicode.isprintable():
                self._mod_dungeon_buffer += event.unicode

    def _handle_mod_dungeon_level_list_input(self, event):
        """Handle level list browsing (level 10, sub 1)."""
        import pygame

        # Naming overlay for levels
        if self._mod_dungeon_naming:
            self._handle_mod_dungeon_naming_input(event)
            return

        n = len(self._mod_dungeon_level_list)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self._save_module_dungeons()
            self.module_edit_level = 9
            return
        if self._is_new_shortcut(event):
            self._mod_dungeon_naming = True
            self._mod_dungeon_naming_is_new = True
            self._mod_dungeon_naming_target = "level"
            idx = len(self._mod_dungeon_level_list) + 1
            self._mod_dungeon_name_buf = f"Level {idx}"
            return
        if self._is_delete_shortcut(event) and n > 0:
            self._mod_dungeon_delete_level()
            return
        if self._is_save_shortcut(event):
            self._save_module_dungeons()
            self._mod_dungeon_save_flash = 1.5
            return
        if event.key == pygame.K_F2 and n > 0:
            level = self._mod_dungeon_get_current_level()
            if level:
                self._mod_dungeon_naming = True
                self._mod_dungeon_naming_is_new = False
                self._mod_dungeon_naming_target = "level"
                self._mod_dungeon_name_buf = level.get("name", "")
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_dungeon_level_cursor = (
                self._mod_dungeon_level_cursor - 1) % n
            self._mod_dungeon_level_scroll = fe._adjust_scroll_generic(
                self._mod_dungeon_level_cursor,
                self._mod_dungeon_level_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_dungeon_level_cursor = (
                self._mod_dungeon_level_cursor + 1) % n
            self._mod_dungeon_level_scroll = fe._adjust_scroll_generic(
                self._mod_dungeon_level_cursor,
                self._mod_dungeon_level_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_dungeon_level_sub_cursor = 0
            self.module_edit_level = 11

    def _handle_mod_dungeon_level_sub_input(self, event):
        """Handle level sub-screen (level 11): Edit Map | Encounters."""
        import pygame
        n = len(self._mod_dungeon_level_sub_items)
        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self.module_edit_level = 10
            return
        if event.key == pygame.K_UP:
            self._mod_dungeon_level_sub_cursor = (
                self._mod_dungeon_level_sub_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self._mod_dungeon_level_sub_cursor = (
                self._mod_dungeon_level_sub_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            if self._mod_dungeon_level_sub_cursor == 0:
                self._mod_dungeon_launch_map_editor()
            elif self._mod_dungeon_level_sub_cursor == 1:
                self._mod_dungeon_load_encounters()
                self.module_edit_level = 12

    def _handle_mod_dungeon_encounter_list_input(self, event):
        """Handle encounter list (level 12)."""
        import pygame
        n = len(self._mod_dungeon_encounter_list)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self._mod_dungeon_save_encounters()
            self.module_edit_level = 11
            return
        if self._is_new_shortcut(event):
            self._mod_dungeon_add_encounter()
            return
        if self._is_delete_shortcut(event) and n > 0:
            self._mod_dungeon_delete_encounter()
            return
        if self._is_save_shortcut(event):
            self._mod_dungeon_save_encounters()
            self._save_module_dungeons()
            self._mod_dungeon_save_flash = 1.5
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_dungeon_encounter_cursor = (
                self._mod_dungeon_encounter_cursor - 1) % n
            self._mod_dungeon_encounter_scroll = fe._adjust_scroll_generic(
                self._mod_dungeon_encounter_cursor,
                self._mod_dungeon_encounter_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_dungeon_encounter_cursor = (
                self._mod_dungeon_encounter_cursor + 1) % n
            self._mod_dungeon_encounter_scroll = fe._adjust_scroll_generic(
                self._mod_dungeon_encounter_cursor,
                self._mod_dungeon_encounter_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_dungeon_open_encounter_editor()
            self.module_edit_level = 13

    def _handle_mod_dungeon_encounter_field_input(self, event):
        """Handle encounter editor (level 13) — custom screen with monster list."""
        import pygame
        if not (0 <= self._mod_dungeon_encounter_cursor < len(
                self._mod_dungeon_encounter_list)):
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 12
            return

        rows = self._mod_dungeon_get_enc_rows()
        n = len(rows)
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 12
            return

        cur = self._mod_dungeon_enc_cursor
        if cur >= n:
            cur = n - 1
            self._mod_dungeon_enc_cursor = cur
        row = rows[cur]

        # ── Save shortcut ──
        if self._is_save_shortcut(event):
            if self._mod_dungeon_enc_editing and row["type"] in (
                    "name", "col", "row"):
                self._mod_dungeon_save_enc_field(
                    row, self._mod_dungeon_enc_buffer)
                self._mod_dungeon_enc_editing = False
            self._mod_dungeon_save_encounters()
            self._save_module_dungeons()
            self._mod_dungeon_save_flash = 1.5
            return

        # ── Escape ──
        if event.key == pygame.K_ESCAPE:
            if self._mod_dungeon_enc_editing:
                self._mod_dungeon_save_enc_field(
                    row, self._mod_dungeon_enc_buffer)
                self._mod_dungeon_enc_editing = False
            else:
                self._mod_dungeon_save_encounters()
                self.module_edit_level = 12
            return

        # ── Navigation ──
        if event.key == pygame.K_UP:
            if self._mod_dungeon_enc_editing:
                self._mod_dungeon_save_enc_field(
                    row, self._mod_dungeon_enc_buffer)
                self._mod_dungeon_enc_editing = False
            new_cur = cur - 1
            while new_cur >= 0 and rows[new_cur]["type"] == "section":
                new_cur -= 1
            if new_cur >= 0:
                self._mod_dungeon_enc_cursor = new_cur
            return

        if event.key == pygame.K_DOWN:
            if self._mod_dungeon_enc_editing:
                self._mod_dungeon_save_enc_field(
                    row, self._mod_dungeon_enc_buffer)
                self._mod_dungeon_enc_editing = False
            new_cur = cur + 1
            while new_cur < n and rows[new_cur]["type"] == "section":
                new_cur += 1
            if new_cur < n:
                self._mod_dungeon_enc_cursor = new_cur
            return

        # ── Enter / toggle / start editing ──
        if event.key == pygame.K_RETURN:
            if row["type"] == "position":
                # Toggle between procedural and manual placement
                enc = self._mod_dungeon_encounter_list[
                    self._mod_dungeon_encounter_cursor]
                if enc.get("placement", "procedural") == "procedural":
                    enc["placement"] = "manual"
                else:
                    self._mod_dungeon_enc_clear_position()
                return
            if row["type"] == "place_on_map":
                self._mod_dungeon_enc_open_placement()
                return
            if row["type"] == "name":
                if not self._mod_dungeon_enc_editing:
                    self._mod_dungeon_enc_editing = True
                    self._mod_dungeon_enc_buffer = str(row["value"])
                else:
                    self._mod_dungeon_save_enc_field(
                        row, self._mod_dungeon_enc_buffer)
                    self._mod_dungeon_enc_editing = False
                return
            return

        # ── Cmd+N: Add monster ──
        if self._is_new_shortcut(event) and not self._mod_dungeon_enc_editing:
            self._mod_dungeon_open_monster_picker()
            self._mod_dungeon_enc_picker_active = True
            return

        # ── Cmd+D: Delete selected monster ──
        if self._is_delete_shortcut(event) and not self._mod_dungeon_enc_editing:
            if row["type"] == "monster":
                self._mod_dungeon_enc_remove_monster()
                new_rows = self._mod_dungeon_get_enc_rows()
                if self._mod_dungeon_enc_cursor >= len(new_rows):
                    self._mod_dungeon_enc_cursor = max(0, len(new_rows) - 1)
            return

        # ── Text editing ──
        if self._mod_dungeon_enc_editing:
            if event.key == pygame.K_BACKSPACE:
                self._mod_dungeon_enc_buffer = (
                    self._mod_dungeon_enc_buffer[:-1])
            elif event.unicode and event.unicode.isprintable():
                self._mod_dungeon_enc_buffer += event.unicode

    def _handle_mod_dungeon_enc_placement_input(self, event):
        """Handle encounter placement on the level map."""
        import pygame
        level = self._mod_dungeon_get_current_level()
        if not level:
            self._mod_dungeon_enc_placing = False
            return
        w = level.get("width", 20)
        h = level.get("height", 20)

        if event.key == pygame.K_ESCAPE:
            self._mod_dungeon_enc_placing = False
            return

        # Navigation
        if event.key == pygame.K_UP:
            self._mod_dungeon_enc_place_row = max(
                0, self._mod_dungeon_enc_place_row - 1)
        elif event.key == pygame.K_DOWN:
            self._mod_dungeon_enc_place_row = min(
                h - 1, self._mod_dungeon_enc_place_row + 1)
        elif event.key == pygame.K_LEFT:
            self._mod_dungeon_enc_place_col = max(
                0, self._mod_dungeon_enc_place_col - 1)
        elif event.key == pygame.K_RIGHT:
            self._mod_dungeon_enc_place_col = min(
                w - 1, self._mod_dungeon_enc_place_col + 1)

        # Enter/Space: place encounter at cursor
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._mod_dungeon_enc_set_position(
                self._mod_dungeon_enc_place_col,
                self._mod_dungeon_enc_place_row)
            self._mod_dungeon_enc_placing = False

        # X: remove placement (set back to random)
        elif event.key == pygame.K_x:
            self._mod_dungeon_enc_clear_position()
            self._mod_dungeon_enc_placing = False

    def _handle_mod_dungeon_monster_picker_input(self, event):
        """Handle monster picker overlay — choose a monster to add."""
        import pygame
        monsters = self._mod_dungeon_enc_picker_monsters
        n = len(monsters)

        if event.key == pygame.K_ESCAPE:
            self._mod_dungeon_enc_picker_active = False
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_dungeon_enc_picker_cursor = (
                self._mod_dungeon_enc_picker_cursor - 1) % n
            if self._mod_dungeon_enc_picker_cursor < self._mod_dungeon_enc_picker_scroll:
                self._mod_dungeon_enc_picker_scroll = self._mod_dungeon_enc_picker_cursor
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_dungeon_enc_picker_cursor = (
                self._mod_dungeon_enc_picker_cursor + 1) % n
            if self._mod_dungeon_enc_picker_cursor >= self._mod_dungeon_enc_picker_scroll + 10:
                self._mod_dungeon_enc_picker_scroll = (
                    self._mod_dungeon_enc_picker_cursor - 9)
        elif event.key == pygame.K_RETURN and n > 0:
            name = monsters[self._mod_dungeon_enc_picker_cursor]
            self._mod_dungeon_enc_add_monster(name)
            self._mod_dungeon_enc_picker_active = False
            return

    # ══════════════════════════════════════════════════════════
    # ── Building Editor Methods ────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def _enter_buildings_section(self):
        """Enter the Buildings section from the module section browser."""
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]
        self._load_module_buildings(mod["path"])
        for sec in self.module_edit_sections:
            if sec.get("_buildings"):
                n = len(self._mod_building_list)
                sec["subtitle"] = f"{n} building{'s' if n != 1 else ''}"
                break
        self.module_edit_level = 14

    # ── Load / save ──

    def _load_module_buildings(self, mod_path):
        """Load buildings.json from a module directory."""
        import json, os
        self._mod_building_list = []
        self._mod_building_cursor = 0
        self._mod_building_scroll = 0
        p = os.path.join(mod_path, "buildings.json")
        if not os.path.isfile(p):
            return
        try:
            with open(p, "r") as f:
                data = json.load(f)
            self._mod_building_list = data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            pass

    def _save_module_buildings(self):
        """Persist the current building list to the active module."""
        import json, os
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]
        p = os.path.join(mod["path"], "buildings.json")
        try:
            with open(p, "w") as f:
                json.dump(self._mod_building_list, f, indent=2)
        except OSError:
            pass

    # ── Building-level helpers ──

    def _handle_building_edit_input(self, event):
        """Dispatch building editor input based on module_edit_level.

        Levels:
        14 = building list browser
        15 = building sub-screen (Settings / Spaces)
        16 = settings fields OR space list
        17 = space sub-screen (Edit Map / Encounters)
        18 = encounter list
        19 = encounter field editor
        """
        import pygame

        # ── Map editor active (takes over everything) ──
        if self._mod_building_editor_active:
            if self._mod_building_map_editor_handler:
                result = self._mod_building_map_editor_handler.handle(event)
                if result == "exit":
                    self._mod_building_editor_active = False
                    self._mod_building_map_editor_state = None
                    self._mod_building_map_editor_handler = None
            return

        if self.module_edit_level == 19:
            self._handle_mod_building_encounter_field_input(event)
            return
        if self.module_edit_level == 18:
            self._handle_mod_building_encounter_list_input(event)
            return
        if self.module_edit_level == 17:
            self._handle_mod_building_space_sub_input(event)
            return
        if self.module_edit_level == 16:
            if self._mod_building_sub_cursor == 0:
                self._handle_mod_building_settings_field_input(event)
            elif self._mod_building_sub_cursor == 1:
                self._handle_mod_building_space_list_input(event)
            return
        if self.module_edit_level == 15:
            self._handle_mod_building_sub_input(event)
            return

        # ── Level 14: Building list ──
        if self._mod_building_naming:
            self._handle_mod_building_naming_input(event)
            return

        layouts = self._mod_building_list
        n = len(layouts)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE:
            self._save_module_buildings()
            self.module_edit_level = 0
            return
        if self._is_new_shortcut(event):
            self._mod_building_naming = True
            self._mod_building_naming_is_new = True
            self._mod_building_naming_target = "building"
            self._mod_building_name_buf = ""
            return
        if self._is_delete_shortcut(event) and n > 0:
            layouts.pop(self._mod_building_cursor)
            n -= 1
            if n == 0:
                self._mod_building_cursor = 0
            elif self._mod_building_cursor >= n:
                self._mod_building_cursor = n - 1
            self._save_module_buildings()
            return
        if self._is_save_shortcut(event):
            self._save_module_buildings()
            self._mod_building_save_flash = 1.5
            return
        if event.key == pygame.K_F2 and n > 0:
            building = self._mod_building_get_current()
            if building:
                self._mod_building_naming = True
                self._mod_building_naming_is_new = False
                self._mod_building_naming_target = "building"
                self._mod_building_name_buf = building.get("name", "")
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_building_cursor = (self._mod_building_cursor - 1) % n
            self._mod_building_scroll = fe._adjust_scroll_generic(
                self._mod_building_cursor, self._mod_building_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_building_cursor = (self._mod_building_cursor + 1) % n
            self._mod_building_scroll = fe._adjust_scroll_generic(
                self._mod_building_cursor, self._mod_building_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_building_sub_cursor = 0
            self.module_edit_level = 15

    def _handle_mod_building_naming_input(self, event):
        """Handle text input while naming/renaming a building or space."""
        import pygame
        if event.key == pygame.K_ESCAPE:
            self._mod_building_naming = False
            return
        if event.key == pygame.K_RETURN:
            name = self._mod_building_name_buf.strip()
            if name:
                target = self._mod_building_naming_target
                if target == "building":
                    if self._mod_building_naming_is_new:
                        self._mod_building_add_new(name)
                    else:
                        building = self._mod_building_get_current()
                        if building:
                            building["name"] = name
                            self._save_module_buildings()
                elif target == "space_from_template":
                    template = getattr(self, "_mod_building_enc_template", None)
                    if template and template.get("_blank"):
                        self._mod_building_add_space(name)
                    elif template:
                        self._mod_building_generate_space_from_template(
                            name, template)
                    else:
                        self._mod_building_add_space(name)
                    self._mod_building_enc_template = None
                elif target == "space":
                    if self._mod_building_naming_is_new:
                        self._mod_building_add_space(name)
                    else:
                        space = self._mod_building_get_current_space()
                        if space:
                            space["name"] = name
                            self._save_module_buildings()
            self._mod_building_naming = False
            return
        if event.key == pygame.K_BACKSPACE:
            self._mod_building_name_buf = self._mod_building_name_buf[:-1]
            return
        if event.unicode and event.unicode.isprintable():
            self._mod_building_name_buf += event.unicode

    def _handle_mod_building_sub_input(self, event):
        """Handle building sub-screen (level 15): Settings | Spaces."""
        import pygame
        n = len(self._mod_building_sub_items)
        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self.module_edit_level = 14
            return
        if event.key == pygame.K_UP:
            self._mod_building_sub_cursor = (
                self._mod_building_sub_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self._mod_building_sub_cursor = (
                self._mod_building_sub_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            if self._mod_building_sub_cursor == 0:
                self._mod_building_build_settings_fields()
                self.module_edit_level = 16
            elif self._mod_building_sub_cursor == 1:
                self._mod_building_load_spaces()
                self.module_edit_level = 16

    def _handle_mod_building_settings_field_input(self, event):
        """Handle building settings field editing (level 16, sub 0)."""
        import pygame
        fields = self._mod_building_fields
        n = len(fields)
        fe = self.features_editor
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 15
            return

        current_field = fields[self._mod_building_field]
        is_choice = current_field.field_type == "choice"

        def _commit_text():
            if current_field.editable and not is_choice:
                current_field.value = self._mod_building_buffer

        if self._is_save_shortcut(event):
            _commit_text()
            self._mod_building_save_settings_fields()
            self._save_module_buildings()
            self._mod_building_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            _commit_text()
            self._mod_building_save_settings_fields()
            self.module_edit_level = 15
            return

        if is_choice and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            direction = -1 if event.key == pygame.K_LEFT else 1
            self._mod_building_cycle_choice(direction)
            return

        if event.key == pygame.K_UP:
            _commit_text()
            self._mod_building_field = fe._next_editable_generic(
                fields, (self._mod_building_field - 1) % n)
            nf = fields[self._mod_building_field]
            self._mod_building_buffer = nf.value
            self._mod_building_field_scroll = fe._adjust_field_scroll_generic(
                self._mod_building_field, self._mod_building_field_scroll)
        elif event.key == pygame.K_DOWN:
            _commit_text()
            self._mod_building_field = fe._next_editable_generic(
                fields, (self._mod_building_field + 1) % n)
            nf = fields[self._mod_building_field]
            self._mod_building_buffer = nf.value
            self._mod_building_field_scroll = fe._adjust_field_scroll_generic(
                self._mod_building_field, self._mod_building_field_scroll)
        elif not is_choice:
            if event.key == pygame.K_BACKSPACE:
                self._mod_building_buffer = self._mod_building_buffer[:-1]
            elif event.unicode and event.unicode.isprintable():
                self._mod_building_buffer += event.unicode

    def _handle_mod_building_space_list_input(self, event):
        """Handle space list browsing (level 16, sub 1)."""
        import pygame

        # Intercept enclosure template picker overlay
        if self._mod_building_enc_picking:
            self._handle_mod_building_enc_picker_input(event)
            return

        if self._mod_building_naming:
            self._handle_mod_building_naming_input(event)
            return

        n = len(self._mod_building_space_list)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self._save_module_buildings()
            self.module_edit_level = 15
            return
        if self._is_new_shortcut(event):
            # Open template picker instead of blank naming
            self._mod_building_open_enc_picker()
            return
        if self._is_delete_shortcut(event) and n > 0:
            self._mod_building_delete_space()
            return
        if self._is_save_shortcut(event):
            self._save_module_buildings()
            self._mod_building_save_flash = 1.5
            return
        if event.key == pygame.K_F2 and n > 0:
            space = self._mod_building_get_current_space()
            if space:
                self._mod_building_naming = True
                self._mod_building_naming_is_new = False
                self._mod_building_naming_target = "space"
                self._mod_building_name_buf = space.get("name", "")
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_building_space_cursor = (
                self._mod_building_space_cursor - 1) % n
            self._mod_building_space_scroll = fe._adjust_scroll_generic(
                self._mod_building_space_cursor,
                self._mod_building_space_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_building_space_cursor = (
                self._mod_building_space_cursor + 1) % n
            self._mod_building_space_scroll = fe._adjust_scroll_generic(
                self._mod_building_space_cursor,
                self._mod_building_space_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_building_space_sub_cursor = 0
            self.module_edit_level = 17

    def _handle_mod_building_enc_picker_input(self, event):
        """Handle enclosure template picker for building spaces."""
        import pygame
        templates = self._mod_building_enc_pick_list
        n = len(templates)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE:
            self._mod_building_enc_picking = False
            self._mod_building_importing_to_space = False
            return

        if not n:
            return

        # Keep the scroll window in sync with what the renderer draws.
        # Renderer layout (see Renderer._draw_building_enc_picker):
        #   pad=12, row_h=40, title+margin=42, footer gap=80.
        # max_vis = (rh - pad*2 - 42 - 80) / row_h
        # where rh is the module editor panel height (SCREEN_HEIGHT-130).
        max_vis = self._picker_max_visible()

        if event.key == pygame.K_UP:
            self._mod_building_enc_pick_cursor = (
                self._mod_building_enc_pick_cursor - 1) % n
            self._mod_building_enc_pick_scroll = fe._adjust_scroll_generic(
                self._mod_building_enc_pick_cursor,
                self._mod_building_enc_pick_scroll,
                max_visible=max_vis)
        elif event.key == pygame.K_DOWN:
            self._mod_building_enc_pick_cursor = (
                self._mod_building_enc_pick_cursor + 1) % n
            self._mod_building_enc_pick_scroll = fe._adjust_scroll_generic(
                self._mod_building_enc_pick_cursor,
                self._mod_building_enc_pick_scroll,
                max_visible=max_vis)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            template = templates[self._mod_building_enc_pick_cursor]
            if self._mod_building_importing_to_space:
                # Apply template to current space directly
                self._mod_building_apply_template_to_space(template)
                self._mod_building_enc_picking = False
                self._mod_building_importing_to_space = False
                self._mod_building_save_flash = 1.5
            else:
                # Select template → show naming overlay for new space
                self._mod_building_enc_template = template
                self._mod_building_enc_picking = False
                self._mod_building_naming = True
                self._mod_building_naming_is_new = True
                self._mod_building_naming_target = "space_from_template"
                if template.get("_blank"):
                    idx = len(self._mod_building_space_list) + 1
                    self._mod_building_name_buf = f"Room {idx}"
                else:
                    self._mod_building_name_buf = template.get(
                        "label", "Room")

    def _handle_mod_building_diff_picker_input(self, event):
        """Handle input for the auto-populate difficulty picker overlay.

        Up/Down: select tier. Enter: run auto-populate and close.
        Esc: cancel without doing anything.
        """
        import pygame
        options = self._BUILDING_DIFFICULTY_OPTIONS
        n = len(options)

        if event.key == pygame.K_ESCAPE:
            self._mod_building_diff_picking = False
            self._mod_building_auto_pop_msg = ""
            return
        if event.key == pygame.K_UP:
            self._mod_building_diff_cursor = (
                self._mod_building_diff_cursor - 1) % n
            return
        if event.key == pygame.K_DOWN:
            self._mod_building_diff_cursor = (
                self._mod_building_diff_cursor + 1) % n
            return
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            difficulty = options[self._mod_building_diff_cursor]
            self._mod_building_auto_populate_encounters(difficulty)
            # Close the picker — the confirmation message lives on
            # the space sub-screen for a moment via save_flash.
            self._mod_building_diff_picking = False
            return

    def _handle_mod_building_space_sub_input(self, event):
        """Handle space sub-screen (level 17): Townspeople | Edit Map | Encounters | Auto-Populate | Import Template."""
        import pygame

        # Intercept the difficulty picker (auto-populate encounters)
        # before any other overlay so it captures all input while open.
        if self._mod_building_diff_picking:
            self._handle_mod_building_diff_picker_input(event)
            return

        # Intercept enclosure template picker overlay
        if self._mod_building_enc_picking:
            self._handle_mod_building_enc_picker_input(event)
            return

        # Dispatch to NPC sub-editors via edit mode (stays at level 17)
        if self._mod_building_space_npc_edit_mode == 2:
            self._handle_mod_building_space_npc_field_input(event)
            return
        if self._mod_building_space_npc_edit_mode == 1:
            self._handle_mod_building_space_npc_list_input(event)
            return

        n = len(self._mod_building_space_sub_items)
        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self._mod_building_space_npc_edit_mode = 0
            self.module_edit_level = 16
            return
        if event.key == pygame.K_UP:
            self._mod_building_space_sub_cursor = (
                self._mod_building_space_sub_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self._mod_building_space_sub_cursor = (
                self._mod_building_space_sub_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
            if self._mod_building_space_sub_cursor == 0:
                self._mod_building_space_load_npcs()
                self._mod_building_space_npc_edit_mode = 1
            elif self._mod_building_space_sub_cursor == 1:
                self._mod_building_launch_map_editor()
            elif self._mod_building_space_sub_cursor == 2:
                self._mod_building_load_encounters()
                self.module_edit_level = 18
            elif self._mod_building_space_sub_cursor == 3:
                # Auto-Populate Encounters — opens difficulty picker.
                self._mod_building_open_difficulty_picker()
            elif self._mod_building_space_sub_cursor == 4:
                self._mod_building_open_space_template_picker()

    def _handle_mod_building_encounter_list_input(self, event):
        """Handle encounter list (level 18)."""
        import pygame
        n = len(self._mod_building_encounter_list)
        fe = self.features_editor

        if event.key == pygame.K_ESCAPE or event.key == pygame.K_LEFT:
            self._mod_building_save_encounters()
            self.module_edit_level = 17
            return
        if self._is_new_shortcut(event):
            self._mod_building_add_encounter()
            return
        if self._is_delete_shortcut(event) and n > 0:
            self._mod_building_delete_encounter()
            return
        if self._is_save_shortcut(event):
            self._mod_building_save_encounters()
            self._save_module_buildings()
            self._mod_building_save_flash = 1.5
            return

        if event.key == pygame.K_UP and n > 0:
            self._mod_building_encounter_cursor = (
                self._mod_building_encounter_cursor - 1) % n
            self._mod_building_encounter_scroll = fe._adjust_scroll_generic(
                self._mod_building_encounter_cursor,
                self._mod_building_encounter_scroll)
        elif event.key == pygame.K_DOWN and n > 0:
            self._mod_building_encounter_cursor = (
                self._mod_building_encounter_cursor + 1) % n
            self._mod_building_encounter_scroll = fe._adjust_scroll_generic(
                self._mod_building_encounter_cursor,
                self._mod_building_encounter_scroll)
        elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
            self._mod_building_build_encounter_fields()
            self.module_edit_level = 19

    def _handle_mod_building_encounter_field_input(self, event):
        """Handle encounter field editing (level 19)."""
        import pygame
        fields = self._mod_building_encounter_fields
        n = len(fields)
        fe = self.features_editor
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 18
            return

        if self._is_save_shortcut(event):
            f = fields[self._mod_building_encounter_field]
            if f.editable:
                f.value = self._mod_building_encounter_buffer
            self._mod_building_save_encounter_fields()
            self._mod_building_save_encounters()
            self._save_module_buildings()
            self._mod_building_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            f = fields[self._mod_building_encounter_field]
            if f.editable:
                f.value = self._mod_building_encounter_buffer
            self._mod_building_save_encounter_fields()
            self._mod_building_save_encounters()
            self.module_edit_level = 18
            return

        if event.key == pygame.K_UP:
            f = fields[self._mod_building_encounter_field]
            if f.editable:
                f.value = self._mod_building_encounter_buffer
            self._mod_building_encounter_field = fe._next_editable_generic(
                fields, (self._mod_building_encounter_field - 1) % n)
            self._mod_building_encounter_buffer = fields[
                self._mod_building_encounter_field].value
            self._mod_building_encounter_field_scroll = (
                fe._adjust_field_scroll_generic(
                    self._mod_building_encounter_field,
                    self._mod_building_encounter_field_scroll))
        elif event.key == pygame.K_DOWN:
            f = fields[self._mod_building_encounter_field]
            if f.editable:
                f.value = self._mod_building_encounter_buffer
            self._mod_building_encounter_field = fe._next_editable_generic(
                fields, (self._mod_building_encounter_field + 1) % n)
            self._mod_building_encounter_buffer = fields[
                self._mod_building_encounter_field].value
            self._mod_building_encounter_field_scroll = (
                fe._adjust_field_scroll_generic(
                    self._mod_building_encounter_field,
                    self._mod_building_encounter_field_scroll))
        elif event.key == pygame.K_BACKSPACE:
            self._mod_building_encounter_buffer = (
                self._mod_building_encounter_buffer[:-1])
        elif event.key and event.unicode and event.unicode.isprintable():
            self._mod_building_encounter_buffer += event.unicode

    # ── Quest Editor ─────────────────────────────────────────────

    def _enter_quests_section(self):
        """Enter the Quests section from the module section browser.

        Also pre-loads towns, dungeons, and buildings so the location
        picker can reference all available maps.
        """
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]
        self._load_module_quests(mod["path"])
        # Pre-load other module data for location picker
        self._load_module_towns(mod["path"])
        self._load_module_dungeons(mod["path"])
        self._load_module_buildings(mod["path"])
        # Reset cached monster / encounter names so they reload fresh
        self._mod_quest_monster_names = None
        self._mod_quest_encounter_names = None
        # Clear any open picker overlay + its cached item list.
        self._mod_quest_item_picker_active = False
        self._mod_quest_item_picker_list = None
        # Update section subtitle
        for sec in self.module_edit_sections:
            if sec.get("_quests"):
                n = len(self._mod_quest_list)
                sec["subtitle"] = f"{n} quest{'s' if n != 1 else ''}"
                break
        self.module_edit_level = 20

    def _load_module_quests(self, mod_path):
        """Load quests.json from a module directory."""
        import json, os
        self._mod_quest_list = []
        self._mod_quest_cursor = 0
        self._mod_quest_scroll = 0
        p = os.path.join(mod_path, "quests.json")
        if not os.path.isfile(p):
            return
        try:
            with open(p, "r") as f:
                data = json.load(f)
            self._mod_quest_list = data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            pass

    def _save_module_quests(self):
        """Persist the current quest list to the active module."""
        import json, os
        if not self.module_list:
            return
        mod = self.module_list[self.module_cursor]
        p = os.path.join(mod["path"], "quests.json")
        try:
            with open(p, "w") as f:
                json.dump(self._mod_quest_list, f, indent=2)
        except OSError:
            pass

    def _handle_mod_quest_step_field_input(self, event):
        """Handle input for step field editing (level 23)."""
        import pygame
        fields = self._mod_quest_step_fields
        n = len(fields)
        fe = self.features_editor
        if n == 0:
            if event.key == pygame.K_ESCAPE:
                self.module_edit_level = 22
            return

        current_field = fields[self._mod_quest_step_field]

        if self._is_save_shortcut(event):
            if current_field.editable and current_field.field_type != "choice":
                current_field.value = self._mod_quest_step_buffer
            self._mod_quest_save_step_fields()
            self._mod_quest_save_steps()
            self._save_module_quests()
            self._mod_quest_save_flash = 1.5
            return

        if event.key == pygame.K_ESCAPE:
            if current_field.editable and current_field.field_type != "choice":
                current_field.value = self._mod_quest_step_buffer
            self._mod_quest_save_step_fields()
            self._mod_quest_save_steps()
            self.module_edit_level = 22
            return

        if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            if current_field.field_type == "choice":
                direction = -1 if event.key == pygame.K_LEFT else 1
                self._mod_quest_step_cycle_choice(direction)
                return

        if event.key == pygame.K_UP:
            if current_field.editable and current_field.field_type != "choice":
                current_field.value = self._mod_quest_step_buffer
            self._mod_quest_step_field = fe._next_editable_generic(
                fields, (self._mod_quest_step_field - 1) % n)
            nf = fields[self._mod_quest_step_field]
            self._mod_quest_step_buffer = (
                nf.value if nf.field_type != "choice" else "")
            self._mod_quest_step_field_scroll = (
                fe._adjust_field_scroll_generic(
                    self._mod_quest_step_field,
                    self._mod_quest_step_field_scroll))
        elif event.key == pygame.K_DOWN:
            if current_field.editable and current_field.field_type != "choice":
                current_field.value = self._mod_quest_step_buffer
            self._mod_quest_step_field = fe._next_editable_generic(
                fields, (self._mod_quest_step_field + 1) % n)
            nf = fields[self._mod_quest_step_field]
            self._mod_quest_step_buffer = (
                nf.value if nf.field_type != "choice" else "")
            self._mod_quest_step_field_scroll = (
                fe._adjust_field_scroll_generic(
                    self._mod_quest_step_field,
                    self._mod_quest_step_field_scroll))
        elif current_field.field_type == "choice":
            # Don't allow typing on choice fields
            pass
        elif event.key == pygame.K_BACKSPACE:
            self._mod_quest_step_buffer = (
                self._mod_quest_step_buffer[:-1])
        elif event.key and event.unicode and event.unicode.isprintable():
            self._mod_quest_step_buffer += event.unicode

    # ── Module / settings helpers ────────────────────────────────

    def _set_active_module(self, path, name, version):
        """Set the active module and persist the choice to config."""
        self.active_module_path = path
        self.active_module_name = name
        self.active_module_version = version
        self._config["active_module_path"] = path
        save_config(self._config)

    # ── Settings helpers ─────────────────────────────────────────

    def _rebuild_settings_options(self):
        """(Re)build ``self.settings_options`` based on current mode.

        The first four entries are always present.  DM-mode-only debug
        toggles (e.g. QUEST MONSTERS ONLY) are appended only while
        ``self.dm_mode`` is True so they stay hidden from normal players.
        Indices 0–3 remain stable so the existing index-based updates
        in the audio and DM-mode handlers keep working.
        """
        opts = [
            {"label": "MUSIC VOLUME",
             "value": self._format_volume(self.music.volume),
             "type": "choice", "action": self._change_music_volume},
            {"label": "MUSIC",
             "value": not self.music.muted,
             "type": "toggle", "action": self._toggle_music_mute},
            {"label": "SFX",
             "value": not self.sfx.muted,
             "type": "toggle", "action": self._toggle_sfx_mute},
            {"label": "DUNGEON MASTER MODE",
             "value": self.dm_mode,
             "type": "toggle", "action": self._toggle_dm_mode},
        ]
        if self.dm_mode:
            opts.append({
                "label": "QUEST MONSTERS ONLY",
                "value": self.quest_monsters_only,
                "type": "toggle",
                "action": self._toggle_quest_monsters_only,
            })
        self.settings_options = opts
        # Keep cursor in range if the list shrank (e.g. DM mode turned off
        # while the cursor was on the DM-only row).
        if self.settings_cursor >= len(self.settings_options):
            self.settings_cursor = max(0, len(self.settings_options) - 1)

    def _toggle_dm_mode(self):
        """Toggle Dungeon Master mode on/off.

        When DM mode is on, Smite is available in combat, the Edit Game
        option appears on the title screen, and DM-only debug toggles
        appear in Settings.  Turning DM mode off clears those debug
        toggles so normal play is never affected by a leftover flag.
        """
        self.dm_mode = not self.dm_mode
        self._config["dm_mode"] = self.dm_mode
        # Smite tracks DM mode
        self.smite_enabled = self.dm_mode
        self._config["smite_enabled"] = self.dm_mode
        # Debug toggles are DM-only — clear when leaving DM mode so they
        # can't silently alter normal play.
        if not self.dm_mode and self.quest_monsters_only:
            self.quest_monsters_only = False
            self._config["quest_monsters_only"] = False
            from src.dungeon_generator import set_quest_monsters_only_debug
            set_quest_monsters_only_debug(False)
        # Rebuild menus that change shape with DM mode.
        self._rebuild_settings_options()
        self._rebuild_title_options()
        save_config(self._config)

    def _toggle_quest_monsters_only(self):
        """DM-mode debug: suppress free-roaming overworld monsters and
        random dungeon encounters. Quest monsters and module-defined
        custom encounters still spawn.  Only meaningful while
        ``self.dm_mode`` is True (the option is only shown in that case)."""
        self.quest_monsters_only = not self.quest_monsters_only
        self._config["quest_monsters_only"] = self.quest_monsters_only
        # Keep the dungeon generator's switch in sync.
        from src.dungeon_generator import set_quest_monsters_only_debug
        set_quest_monsters_only_debug(self.quest_monsters_only)
        # Update the settings row's displayed value (last entry when DM
        # mode is on — which it must be for this toggle to exist).
        for opt in self.settings_options:
            if opt.get("label") == "QUEST MONSTERS ONLY":
                opt["value"] = self.quest_monsters_only
                break
        save_config(self._config)

    # ── Audio settings helpers ────────────────────────────────────

    @staticmethod
    def _format_volume(vol):
        """Format a 0.0–1.0 volume as a percentage string."""
        return f"{int(round(vol * 100))}%"

    def _change_music_volume(self, direction=1):
        """Adjust music volume in 10% steps."""
        step = 0.1 * direction
        new_vol = max(0.0, min(1.0, round(self.music.volume + step, 2)))
        self.music.volume = new_vol
        # Update the settings display
        self.settings_options[0]["value"] = self._format_volume(new_vol)
        # Persist
        self._config["music_volume"] = new_vol
        save_config(self._config)

    def _toggle_music_mute(self):
        """Toggle background music mute on/off."""
        self.music.muted = not self.music.muted
        self.settings_options[1]["value"] = not self.music.muted
        self._config["music_muted"] = self.music.muted
        save_config(self._config)

    def _toggle_sfx_mute(self):
        """Toggle sound effects mute on/off."""
        self.sfx.muted = not self.sfx.muted
        self.settings_options[2]["value"] = not self.sfx.muted
        self._config["sfx_muted"] = self.sfx.muted
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
            # In combat or examine - show a brief "can't save" hint
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
        # Start area-appropriate background music
        self.music.play_area(state_name)

    def start_loading_screen(self, label, callback):
        """Begin a fade-out → hold → fade-in loading transition.

        *label* is shown on screen (e.g. "Entering Riverdale").
        *callback* is invoked once at the start of the hold phase —
        it should perform the actual state change / heavy loading.
        """
        self._loading_screen_active = True
        self._loading_screen_phase = "fade_out"
        self._loading_screen_elapsed = 0.0
        self._loading_screen_label = label
        self._loading_screen_callback = callback
        self._loading_screen_callback_fired = False

    # ── Input handlers ──────────────────────────────────────────

    # Modifier mask: Ctrl and Cmd (GUI/Meta) - the actual "command" keys.
    # Filter out Caps Lock and Num Lock which can cause false positives.
    _SAVE_MOD_MASK = (pygame.KMOD_CTRL
                      | pygame.KMOD_META
                      | getattr(pygame, "KMOD_GUI", 0))

    @staticmethod
    def _is_save_shortcut(event):
        """Return True if the event is Ctrl+S or Cmd+S (universal save)."""
        if event.key != pygame.K_s:
            return False
        # Strip out Caps Lock / Num Lock - only test command modifiers
        mods = event.mod & ~(pygame.KMOD_CAPS | pygame.KMOD_NUM)
        return bool(mods & Game._SAVE_MOD_MASK)

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

        save_cb    - called when the player presses [S] (save & exit)
        discard_cb - called when the player presses [D] (discard & exit)
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
    # Unified field editor - shared by all record-based editors
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
            elif getattr(self, '_title_save_mode', False):
                self._title_save_mode = False
                self.showing_settings = False
                self.showing_title = True
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
                # Advance background music playlist when a track ends
                self.music.handle_event(event)

            # --- Loading screen transition (overrides all other screens) ---
            if self._loading_screen_active:
                self._loading_screen_elapsed += dt
                phase = self._loading_screen_phase

                if phase == "fade_out":
                    if self._loading_screen_elapsed >= self._loading_fade_out_dur:
                        self._loading_screen_phase = "hold"
                        self._loading_screen_elapsed = 0.0
                elif phase == "hold":
                    if not self._loading_screen_callback_fired:
                        self._loading_screen_callback_fired = True
                        if self._loading_screen_callback:
                            self._loading_screen_callback()
                    if self._loading_screen_elapsed >= self._loading_hold_dur:
                        self._loading_screen_phase = "fade_in"
                        self._loading_screen_elapsed = 0.0
                elif phase == "fade_in":
                    if self._loading_screen_elapsed >= self._loading_fade_in_dur:
                        self._loading_screen_active = False
                        self._loading_screen_phase = "idle"

                # Draw: current state underneath, then loading overlay
                self.current_state.draw(self.renderer)
                self.renderer.draw_loading_screen(
                    self._loading_screen_label,
                    self._loading_screen_phase,
                    self._loading_screen_elapsed,
                    self._loading_fade_out_dur,
                    self._loading_hold_dur,
                    self._loading_fade_in_dur,
                )
                pygame.display.flip()
                continue

            if self.showing_intro:
                # Intro screen — dramatic module name / description
                self._intro_elapsed += dt
                if self._intro_fading_out:
                    # Crossfade: advance fade timer, update overworld underneath
                    self._intro_fade_elapsed += dt
                    fade_duration = 1.5
                    if self._intro_fade_elapsed >= fade_duration:
                        # Fade complete — hand off fully to overworld
                        self.showing_intro = False
                        self._intro_fading_out = False
                    else:
                        # Keep overworld state ticking while we fade
                        self.current_state.update(dt)
                        self.camera.update(
                            self.party.col, self.party.row)
                else:
                    for event in events:
                        if event.type == pygame.KEYDOWN:
                            # Allow skip only after the text has faded in
                            if self._intro_elapsed > 2.0:
                                # Start fade-out and activate overworld underneath
                                self._intro_fading_out = True
                                self._intro_fade_elapsed = 0.0
                                self.change_state("overworld")
                                self.camera.update(
                                    self.party.col, self.party.row)
            elif self.showing_title:
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
                # Tick town save flash
                if self._mod_town_save_flash > 0:
                    self._mod_town_save_flash -= dt
                    if self._mod_town_save_flash < 0:
                        self._mod_town_save_flash = 0
                # Tick dungeon save flash
                if self._mod_dungeon_save_flash > 0:
                    self._mod_dungeon_save_flash -= dt
                    if self._mod_dungeon_save_flash < 0:
                        self._mod_dungeon_save_flash = 0
                # Tick building save flash
                if self._mod_building_save_flash > 0:
                    self._mod_building_save_flash -= dt
                    if self._mod_building_save_flash < 0:
                        self._mod_building_save_flash = 0
                # Tick quest save flash
                if self._mod_quest_save_flash > 0:
                    self._mod_quest_save_flash -= dt
                    if self._mod_quest_save_flash < 0:
                        self._mod_quest_save_flash = 0
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
                        break
                    # Ctrl-S / Cmd-S: Quick Save
                    if self._is_save_shortcut(event):
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
            # Tick quick save HUD timer
            if self.quick_save_msg_timer > 0:
                self.quick_save_msg_timer -= dt
                if self.quick_save_msg_timer <= 0:
                    self.quick_save_message = None
            if (not self.showing_settings and not self.showing_title
                    and not self.showing_intro
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
            if self.showing_intro:
                if self._intro_fading_out:
                    # Draw overworld underneath first
                    self.current_state.draw(self.renderer)
                    # Then overlay the intro with decreasing opacity
                    fade_progress = min(1.0,
                        self._intro_fade_elapsed / 1.5)
                    self.renderer.draw_intro_screen(
                        self._intro_module_name,
                        self._intro_module_desc,
                        self._intro_elapsed,
                        fade_out=fade_progress)
                else:
                    self.renderer.draw_intro_screen(
                        self._intro_module_name,
                        self._intro_module_desc,
                        self._intro_elapsed)
            elif self.showing_title:
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
                    edit_section_scroll=self.module_edit_section_scroll,
                    overview_picking=getattr(self, '_mod_overview_picking', False),
                    overview_pick_list=getattr(self, '_mod_overview_pick_list', []),
                    overview_pick_cursor=getattr(self, '_mod_overview_pick_cursor', 0),
                    overview_pick_scroll=getattr(self, '_mod_overview_pick_scroll', 0),
                    overview_generate_mode=getattr(self, '_mod_overview_generate_mode', False),
                    overview_gen_fields=getattr(self, '_mod_overview_gen_fields', []),
                    overview_gen_field=getattr(self, '_mod_overview_gen_field', 0),
                    overview_gen_buffer=getattr(self, '_mod_overview_gen_buffer', ""),
                    overview_children=getattr(self, '_mod_overview_children', []),
                    overview_child_cursor=getattr(self, '_mod_overview_child_cursor', 0),
                    overview_editor_state=getattr(self, '_mod_map_editor_state', None),
                    town_data={
                        "towns": self._mod_town_list,
                        "cursor": self._mod_town_cursor,
                        "scroll": self._mod_town_scroll,
                        "sub_cursor": self._mod_town_sub_cursor,
                        "sub_items": self._mod_town_sub_items,
                        "fields": self._mod_town_fields,
                        "field_cursor": self._mod_town_field,
                        "field_buffer": self._mod_town_buffer,
                        "field_scroll": self._mod_town_field_scroll,
                        "npc_list": self._mod_town_npc_list,
                        "npc_cursor": self._mod_town_npc_cursor,
                        "npc_scroll": self._mod_town_npc_scroll,
                        "npc_fields": self._mod_town_npc_fields,
                        "npc_field_cursor": self._mod_town_npc_field,
                        "npc_field_buffer": self._mod_town_npc_buffer,
                        "npc_field_scroll": self._mod_town_npc_field_scroll,
                        "npc_sprite_map": getattr(self, "_mod_town_npc_sprite_name_to_file", {}),
                        "editor_active": self._mod_town_editor_active,
                        "editor_data": self._mod_town_map_editor_state,
                        "naming": self._mod_town_naming,
                        "name_buf": self._mod_town_name_buf,
                        "naming_is_new": self._mod_town_naming_is_new,
                        "save_flash": self._mod_town_save_flash,
                        "level": max(0, self.module_edit_level - 4),
                        "enclosures": self._mod_town_enclosures,
                        "enc_cursor": self._mod_town_enc_cursor,
                        "enc_scroll": self._mod_town_enc_scroll,
                        "enc_picking": self._mod_town_enc_picking,
                        "enc_pick_list": self._mod_town_enc_pick_list,
                        "enc_pick_cursor": self._mod_town_enc_pick_cursor,
                        "enc_pick_scroll": self._mod_town_enc_pick_scroll,
                        "enc_naming": self._mod_town_enc_naming,
                        "enc_name_buf": self._mod_town_enc_name_buf,
                        "enc_edit_mode": self._mod_town_enc_edit_mode,
                        "enc_sub_cursor": self._mod_town_enc_sub_cursor,
                        "enc_sub_items": self._mod_town_enc_sub_items,
                        "enc_npc_list": self._mod_town_enc_npc_list,
                        "enc_npc_cursor": self._mod_town_enc_npc_cursor,
                        "enc_npc_scroll": self._mod_town_enc_npc_scroll,
                        "enc_npc_fields": self._mod_town_enc_npc_fields,
                        "enc_npc_field_cursor": self._mod_town_enc_npc_field,
                        "enc_npc_field_buffer": self._mod_town_enc_npc_buffer,
                        "enc_npc_field_scroll": self._mod_town_enc_npc_field_scroll,
                        "enc_npc_sprite_map": getattr(self, "_mod_town_enc_npc_sprite_name_to_file", {}),
                        "gen_mode": self._mod_town_gen_mode,
                        "gen_pick_list": self._mod_town_gen_pick_list,
                        "gen_pick_cursor": self._mod_town_gen_pick_cursor,
                        "gen_pick_scroll": self._mod_town_gen_pick_scroll,
                        "gen_field": self._mod_town_gen_field,
                        "gen_size_idx": self._mod_town_gen_size_idx,
                        "gen_style_idx": self._mod_town_gen_style_idx,
                        "gen_sizes": self._MOD_TOWN_SIZES,
                        "gen_styles": self._MOD_TOWN_STYLES,
                    },
                    dungeon_data={
                        "dungeons": self._mod_dungeon_list,
                        "cursor": self._mod_dungeon_cursor,
                        "scroll": self._mod_dungeon_scroll,
                        "sub_cursor": self._mod_dungeon_sub_cursor,
                        "sub_items": self._mod_dungeon_sub_items,
                        "fields": self._mod_dungeon_fields,
                        "field_cursor": self._mod_dungeon_field,
                        "field_buffer": self._mod_dungeon_buffer,
                        "field_scroll": self._mod_dungeon_field_scroll,
                        "level_list": self._mod_dungeon_level_list,
                        "level_cursor": self._mod_dungeon_level_cursor,
                        "level_scroll": self._mod_dungeon_level_scroll,
                        "level_sub_cursor": self._mod_dungeon_level_sub_cursor,
                        "level_sub_items": self._mod_dungeon_level_sub_items,
                        "encounter_list": self._mod_dungeon_encounter_list,
                        "encounter_cursor": self._mod_dungeon_encounter_cursor,
                        "encounter_scroll": self._mod_dungeon_encounter_scroll,
                        "encounter_fields": self._mod_dungeon_encounter_fields,
                        "encounter_field_cursor": self._mod_dungeon_encounter_field,
                        "encounter_field_buffer": self._mod_dungeon_encounter_buffer,
                        "encounter_field_scroll": self._mod_dungeon_encounter_field_scroll,
                        "enc_cursor": self._mod_dungeon_enc_cursor,
                        "enc_editing": self._mod_dungeon_enc_editing,
                        "enc_buffer": self._mod_dungeon_enc_buffer,
                        "enc_encounter_list": self._mod_dungeon_encounter_list,
                        "enc_encounter_cursor": self._mod_dungeon_encounter_cursor,
                        "enc_picker_active": self._mod_dungeon_enc_picker_active,
                        "enc_picker_monsters": self._mod_dungeon_enc_picker_monsters,
                        "enc_picker_cursor": self._mod_dungeon_enc_picker_cursor,
                        "enc_picker_scroll": self._mod_dungeon_enc_picker_scroll,
                        "enc_placing": self._mod_dungeon_enc_placing,
                        "enc_place_col": self._mod_dungeon_enc_place_col,
                        "enc_place_row": self._mod_dungeon_enc_place_row,
                        "enc_level_data": self._mod_dungeon_get_current_level(),
                        "editor_active": self._mod_dungeon_editor_active,
                        "editor_data": self._mod_dungeon_map_editor_state,
                        "naming": self._mod_dungeon_naming,
                        "name_buf": self._mod_dungeon_name_buf,
                        "naming_is_new": self._mod_dungeon_naming_is_new,
                        "naming_target": self._mod_dungeon_naming_target,
                        "save_flash": self._mod_dungeon_save_flash,
                        "level": max(0, self.module_edit_level - 8),
                    },
                    building_data={
                        "buildings": self._mod_building_list,
                        "cursor": self._mod_building_cursor,
                        "scroll": self._mod_building_scroll,
                        "sub_cursor": self._mod_building_sub_cursor,
                        "sub_items": self._mod_building_sub_items,
                        "fields": self._mod_building_fields,
                        "field_cursor": self._mod_building_field,
                        "field_buffer": self._mod_building_buffer,
                        "field_scroll": self._mod_building_field_scroll,
                        "space_list": self._mod_building_space_list,
                        "space_cursor": self._mod_building_space_cursor,
                        "space_scroll": self._mod_building_space_scroll,
                        "space_sub_cursor": self._mod_building_space_sub_cursor,
                        "space_sub_items": self._mod_building_space_sub_items,
                        "encounter_list": self._mod_building_encounter_list,
                        "encounter_cursor": self._mod_building_encounter_cursor,
                        "encounter_scroll": self._mod_building_encounter_scroll,
                        "encounter_fields": self._mod_building_encounter_fields,
                        "encounter_field_cursor": self._mod_building_encounter_field,
                        "encounter_field_buffer": self._mod_building_encounter_buffer,
                        "encounter_field_scroll": self._mod_building_encounter_field_scroll,
                        "editor_active": self._mod_building_editor_active,
                        "editor_data": self._mod_building_map_editor_state,
                        "naming": self._mod_building_naming,
                        "name_buf": self._mod_building_name_buf,
                        "naming_is_new": self._mod_building_naming_is_new,
                        "naming_target": self._mod_building_naming_target,
                        "enc_picking": self._mod_building_enc_picking,
                        "enc_importing": self._mod_building_importing_to_space,
                        "enc_pick_list": self._mod_building_enc_pick_list,
                        "enc_pick_cursor": self._mod_building_enc_pick_cursor,
                        "enc_pick_scroll": self._mod_building_enc_pick_scroll,
                        "diff_picking": self._mod_building_diff_picking,
                        "diff_cursor": self._mod_building_diff_cursor,
                        "diff_options": self._BUILDING_DIFFICULTY_OPTIONS,
                        "auto_pop_msg": self._mod_building_auto_pop_msg,
                        "space_npc_edit_mode": self._mod_building_space_npc_edit_mode,
                        "space_npc_list": self._mod_building_space_npc_list,
                        "space_npc_cursor": self._mod_building_space_npc_cursor,
                        "space_npc_scroll": self._mod_building_space_npc_scroll,
                        "space_npc_fields": self._mod_building_space_npc_fields,
                        "space_npc_field_cursor": self._mod_building_space_npc_field,
                        "space_npc_field_buffer": self._mod_building_space_npc_buffer,
                        "space_npc_field_scroll": self._mod_building_space_npc_field_scroll,
                        "space_npc_sprite_map": getattr(self, "_mod_building_space_npc_sprite_name_to_file", {}),
                        "save_flash": self._mod_building_save_flash,
                        "level": max(0, self.module_edit_level - 14),
                    },
                    quest_data={
                        "quests": self._mod_quest_list,
                        "cursor": self._mod_quest_cursor,
                        "scroll": self._mod_quest_scroll,
                        "sub_cursor": self._mod_quest_sub_cursor,
                        "sub_items": self._mod_quest_sub_items,
                        "fields": self._mod_quest_fields,
                        "field_cursor": self._mod_quest_field,
                        "field_buffer": self._mod_quest_buffer,
                        "field_scroll": self._mod_quest_field_scroll,
                        "step_list": self._mod_quest_step_list,
                        "step_cursor": self._mod_quest_step_cursor,
                        "step_scroll": self._mod_quest_step_scroll,
                        "step_fields": self._mod_quest_step_fields,
                        "step_field_cursor": self._mod_quest_step_field,
                        "step_field_buffer": self._mod_quest_step_buffer,
                        "step_field_scroll": self._mod_quest_step_field_scroll,
                        "naming": self._mod_quest_naming,
                        "name_buf": self._mod_quest_name_buf,
                        "naming_is_new": self._mod_quest_naming_is_new,
                        "naming_target": self._mod_quest_naming_target,
                        "save_flash": self._mod_quest_save_flash,
                        "level": max(0, self.module_edit_level - 20),
                        "sprite_map": getattr(self, "_mod_quest_sprite_name_to_file", {}),
                        "monster_tile_map": getattr(self, "_mod_quest_monster_tiles", {}),
                        "encounter_tile_map": getattr(self, "_mod_quest_encounter_tiles", {}),
                        "artifact_sprite_map": getattr(self, "_mod_quest_artifact_sprites", {}),
                        # Reward-items picker overlay state
                        "item_picker_active": self._mod_quest_item_picker_active,
                        "item_picker_cursor": self._mod_quest_item_picker_cursor,
                        "item_picker_scroll": self._mod_quest_item_picker_scroll,
                        "item_picker_list": self._mod_quest_item_picker_list or [],
                        "reward_items": (
                            self._mod_quest_get_current().get("reward_items", [])
                            if self._mod_quest_get_current() else []),
                    })
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
