"""
Main Game class - the heart of the application.

Manages the game loop, state machine, and top-level resources.
"""

import json
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

        # --- Title screen ---
        self.showing_title = True
        self.title_cursor = 0
        self.title_elapsed = 0.0        # for animations
        self._title_options_base = [
            {"label": "START NEW GAME", "action": self._title_new_game},
            {"label": "FORM PARTY", "action": self._title_form_party},
            {"label": "SAVE GAME", "action": self._title_save_game},
            {"label": "LOAD GAME", "action": self._title_load_game},
            {"label": "EDIT GAME FEATURES", "action": self._title_features},
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
        self.module_edit_active_enc = -1     # which encounter index
        self._editing_level_settings = False # True when in level settings
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

        # --- Game Features editor ---
        self.showing_features = False
        self._feat_cursor = 0        # top-level category cursor
        self._feat_categories = [
            {"label": "Modules", "icon": "M"},
            {"label": "Spells", "icon": "S"},
            {"label": "Items", "icon": "I"},
            {"label": "Monsters", "icon": "X"},
            {"label": "Tile Types", "icon": "T"},
            {"label": "Tile Gallery", "icon": "G"},
            {"label": "Reusable Features", "icon": "F"},
            {"label": "Town Layouts", "icon": "L"},
        ]
        self._modules_from_features = False  # True when modules opened from features
        # Spell editor state
        self._feat_spell_list = []   # list of spell dicts loaded from JSON
        self._feat_spell_cursor = 0  # which spell is highlighted
        self._feat_spell_scroll = 0
        self._feat_spell_editing = False   # True when editing spell fields
        self._feat_spell_field = 0         # active field index
        self._feat_spell_fields = []       # [label, key, value, type, editable]
        self._feat_spell_buffer = ""       # text being typed
        self._feat_spell_scroll_f = 0      # field list scroll
        # Spell folder navigation (3-tier: casting_type → level → spells)
        self._feat_spell_nav = 0           # 0=casting types, 1=levels, 2=spells
        self._feat_spell_ctype_cursor = 0  # cursor within casting type list
        self._feat_spell_level_cursor = 0  # cursor within level list
        self._feat_spell_level_scroll = 0
        self._feat_spell_sel_ctype = None  # selected casting type string
        self._feat_spell_sel_level = None  # selected level number
        self._feat_spell_filtered = []     # indices into _feat_spell_list
        self._feat_spell_filter_pos = 0    # cursor position within filtered
        self._feat_level = 0  # 0=categories, 1=list, 2=field editor
        # Which editor is active: "spells", "items", "monsters", "tiles"
        self._feat_active_editor = None

        # Items editor state (mirrors spell editor pattern)
        self._feat_item_list = []        # list of (name, section, data) tuples
        self._feat_item_cursor = 0
        self._feat_item_scroll = 0
        self._feat_item_editing = False
        self._feat_item_field = 0
        self._feat_item_fields = []
        self._feat_item_buffer = ""
        self._feat_item_scroll_f = 0

        # Monsters editor state
        self._feat_mon_list = []         # list of (name, data) tuples
        self._feat_mon_cursor = 0
        self._feat_mon_scroll = 0
        self._feat_mon_editing = False
        self._feat_mon_field = 0
        self._feat_mon_fields = []
        self._feat_mon_buffer = ""
        self._feat_mon_scroll_f = 0

        # Tile Types editor state — sub-folder hierarchy
        self._feat_tile_list = []        # all tiles (flat)
        self._feat_tile_folders = []     # folder dicts: name, label, count
        self._feat_tile_folder_cursor = 0
        self._feat_tile_folder_scroll = 0
        self._feat_tile_folder_tiles = []  # tiles in current folder
        self._feat_tile_cursor = 0
        self._feat_tile_scroll = 0
        self._feat_tile_editing = False
        self._feat_tile_field = 0
        self._feat_tile_fields = []
        self._feat_tile_buffer = ""
        self._feat_tile_scroll_f = 0
        self._feat_tile_in_folder = False  # True when browsing inside a folder

        # Classification of tile IDs into context folders
        self._TILE_CONTEXT = {
            0: "overworld", 1: "overworld", 2: "overworld",
            3: "overworld", 4: "overworld", 5: "overworld",
            6: "overworld", 7: "overworld", 8: "overworld",
            9: "overworld",
            10: "town", 11: "town", 12: "town", 13: "town",
            14: "town", 35: "town",
            30: "town", 31: "town",
            20: "dungeon", 21: "dungeon", 22: "dungeon",
            23: "dungeon", 24: "dungeon", 25: "dungeon",
            26: "dungeon", 27: "dungeon", 28: "dungeon",
            29: "dungeon",
            32: "dungeon", 33: "dungeon", 34: "dungeon",
        }
        self._TILE_FOLDER_ORDER = [
            {"name": "overworld", "label": "Overworld"},
            {"name": "town", "label": "Town"},
            {"name": "dungeon", "label": "Dungeon"},
            {"name": "battle", "label": "Battle Screen"},
            {"name": "examine", "label": "Examine Screen"},
        ]

        # Restore user-created / edited tile defs from disk so the
        # rest of the game (town rendering etc.) sees them at startup.
        self._feat_restore_tile_defs_from_disk()

        # Tile Gallery — 3-level folder hierarchy
        # Level 1: category folders, Level 2: sprites, Level 3: tag editor
        self._feat_gallery_list = []         # unique sprite entries (for saving)
        self._feat_gallery_cat_list = []     # categories with counts
        self._feat_gallery_cat_cursor = 0    # which category folder
        self._feat_gallery_cat_scroll = 0
        self._feat_gallery_sprites = []      # sprites for current category
        self._feat_gallery_spr_cursor = 0    # which sprite in category
        self._feat_gallery_spr_scroll = 0
        self._feat_gallery_tag_cursor = 0    # which tag row in editor
        self._feat_gallery_all_cats = [
            "overworld", "town", "dungeon", "people",
            "monsters", "objects", "unique_tiles",
            "items", "spells", "unassigned",
        ]
        self._feat_gallery_naming = False     # True when typing a new name
        self._feat_gallery_name_buf = ""      # text buffer for renaming
        self._feat_gallery_detail_cursor = 0  # 0=Name, 1=Categories, 2=Edit Pixels
        # Pixel editor state (Level 5)
        self._feat_pxedit_pixels = None      # 2D list of (r,g,b,a) tuples
        self._feat_pxedit_cx = 0             # cursor x on canvas
        self._feat_pxedit_cy = 0             # cursor y on canvas
        self._feat_pxedit_color_idx = 0      # selected palette index
        self._feat_pxedit_focus = "canvas"   # "canvas" or "palette"
        self._feat_pxedit_w = 32             # canvas width
        self._feat_pxedit_h = 32             # canvas height
        self._feat_pxedit_path = ""          # file path for saving
        self._feat_pxedit_undo_stack = []    # list of pixel snapshots for undo
        # Color replace mode
        self._feat_pxedit_replacing = False  # True when in replace mode
        self._feat_pxedit_replace_src_color = (0, 0, 0, 255)  # actual RGBA from canvas
        self._feat_pxedit_replace_dst = 0   # target palette index ("to")
        self._feat_pxedit_replace_sel = "dst"  # which selector is active ("src" or "dst")

        # Unsaved-changes confirmation dialog
        # When a player presses ESC on an editor with unsaved changes,
        # this flag activates and the pending callback stores what to
        # do on "save" vs "discard".
        self._unsaved_dialog_active = False
        self._unsaved_dialog_save_cb = None    # callable: save then exit
        self._unsaved_dialog_discard_cb = None # callable: exit without saving
        self._feat_dirty = False               # True when editor has unsaved changes

        # Town editor state — restructured for new hierarchy
        # Per-sub-editor lists stored by key
        self._feat_town_lists = {
            "layouts": [], "features": [], "interiors": [],
        }
        self._feat_townlayout_cursor = 0
        self._feat_townlayout_scroll = 0
        self._feat_townlayout_editing = False  # True when in grid painter
        self._feat_townlayout_cx = 0          # cursor col in grid
        self._feat_townlayout_cy = 0          # cursor row in grid
        self._feat_townlayout_brush_idx = 0   # index into brush palette
        self._feat_townlayout_brushes = None  # built lazily from manifest
        self._feat_townlayout_naming = False   # True when typing a name
        self._feat_townlayout_name_buf = ""    # text buffer for naming
        # New state for town editor hierarchy
        self._feat_town_active_sub = None     # None (town list), "nodes" (3-node selection),
                                               # "details" (editing details), "interiors" (interior list)
        self._feat_town_selected_idx = 0      # index into layouts[] for the currently selected town
        self._feat_town_node_cursor = 0       # 0=Details, 1=Interiors, 2=Layout
        self._feat_town_detail_editing = False  # True when editing name/desc
        self._feat_town_desc_buf = ""         # text buffer for description
        # Tile replace mode (opened with R in the grid painter)
        self._feat_townlayout_replacing = False    # True when replace overlay is open
        self._feat_townlayout_replace_src_tile = None  # tile_id of source tile under cursor
        self._feat_townlayout_replace_src_name = ""    # display name of source tile
        self._feat_townlayout_replace_src_empty = False  # True when replacing empty cells
        self._feat_townlayout_replace_dst_idx = 0      # brush index for destination
        # Town picker overlay (shown when copying interior to pick parent)
        self._feat_town_picker_active = False
        self._feat_town_picker_cursor = 0
        # Interior-link picker (opened with I in the grid painter)
        self._feat_interior_picking = False    # True when picker overlay is open
        self._feat_interior_pick_cursor = 0    # cursor in the picker list
        self._feat_interior_pick_scroll = 0    # scroll offset for the list

        # Reusable Features editor state
        self._feat_rfeat_lists = {
            "town": [], "dungeon": [], "overworld": [],
        }
        self._feat_rfeat_folders = []       # folder dicts with name/label/count
        self._feat_rfeat_folder_cursor = 0
        self._feat_rfeat_folder_scroll = 0
        self._feat_rfeat_in_folder = False
        self._feat_rfeat_cursor = 0
        self._feat_rfeat_scroll = 0
        self._feat_rfeat_current_ctx = "town"  # which folder we're in
        self._feat_rfeat_editing = False     # True when in grid painter
        self._feat_rfeat_cx = 0
        self._feat_rfeat_cy = 0
        self._feat_rfeat_brush_idx = 0
        self._feat_rfeat_brushes = None
        self._feat_rfeat_naming = False
        self._feat_rfeat_name_buf = ""

        self._feat_pxedit_palette = [
            (0, 0, 0, 255),        # Black
            (255, 255, 255, 255),  # White
            (200, 50, 50, 255),    # Red
            (50, 160, 50, 255),    # Green
            (50, 80, 200, 255),    # Blue
            (255, 200, 60, 255),   # Gold
            (255, 140, 40, 255),   # Orange
            (160, 80, 200, 255),   # Purple
            (100, 200, 200, 255),  # Cyan
            (180, 130, 60, 255),   # Brown
            (140, 100, 40, 255),   # Dark Brown
            (180, 190, 200, 255),  # Steel
            (120, 130, 140, 255),  # Dark Steel
            (60, 55, 65, 255),     # Dark Gray
            (130, 130, 130, 255),  # Gray
            (200, 200, 200, 255),  # Light Gray
            (34, 139, 34, 255),    # Forest Green
            (30, 90, 180, 255),    # Ocean Blue
            (210, 190, 130, 255),  # Sand
            (80, 0, 0, 255),       # Dark Red
            (0, 80, 0, 255),       # Dark Green
            (255, 220, 180, 255),  # Skin
            (220, 180, 140, 255),  # Parchment
            (0, 0, 0, 0),          # Transparent
        ]

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

    # ── Game Features editor ──────────────────────────────────

    def _title_features(self):
        """Open the Game Features editor from the title screen."""
        self.showing_title = False
        self.showing_features = True
        self._feat_level = 0
        self._feat_cursor = 0
        self._feat_spell_editing = False

    def _feat_open_modules(self):
        """Open the module browser from within the features editor."""
        self._refresh_module_list()
        self.showing_features = False
        self.showing_modules = True
        self._modules_from_features = True
        self.module_message = None
        self.module_msg_timer = 0.0
        self.module_confirm_delete = False
        self.module_edit_mode = False
        self.module_edit_is_new = False

    def _feat_spells_path(self):
        """Return the path to the spells.json file that the game
        actually uses — module directory first, then default data/."""
        if self.active_module_path:
            mod_path = os.path.join(self.active_module_path,
                                    "spells.json")
            if os.path.isfile(mod_path):
                return mod_path
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "spells.json")

    def _feat_load_spells(self):
        """Load spells from the active spells.json into the editor."""
        import json
        path = self._feat_spells_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
            spells = data.get("spells", [])
        except (OSError, ValueError):
            spells = []
        # Sort: sorcerer first, then priest/cleric, each by level
        from src import data_registry as DR
        type_order = DR.casting_type_sort_order()
        spells.sort(key=lambda s: (
            type_order.get(s.get("casting_type", "sorcerer"), 2),
            s.get("min_level", 1),
            s.get("name", ""),
        ))
        self._feat_spell_list = spells
        self._feat_spell_cursor = 0
        self._feat_spell_scroll = 0
        # Reset folder navigation to top level
        self._feat_spell_nav = 0
        self._feat_spell_ctype_cursor = 0
        self._feat_spell_level_cursor = 0
        self._feat_spell_level_scroll = 0
        self._feat_spell_sel_ctype = None
        self._feat_spell_sel_level = None
        self._feat_spell_filtered = []

    def _feat_spell_casting_types(self):
        """Return sorted list of distinct casting types in the spell list."""
        from src import data_registry as DR
        order = DR.casting_type_sort_order()
        seen = {}
        for s in self._feat_spell_list:
            ct = s.get("casting_type", "sorcerer")
            if ct not in seen:
                seen[ct] = order.get(ct, 99)
        return sorted(seen.keys(), key=lambda c: seen[c])

    def _feat_spell_levels_for_ctype(self, ctype):
        """Return sorted list of (level, count) for a casting type."""
        from collections import Counter
        counts = Counter()
        for s in self._feat_spell_list:
            if s.get("casting_type", "sorcerer") == ctype:
                counts[s.get("min_level", 1)] += 1
        return sorted(counts.items())

    def _feat_spell_filter(self, ctype, level):
        """Build filtered index list for a casting type + level.

        Resets cursor and scroll to 0.  Callers may adjust cursor
        afterwards if they need to restore a position.
        """
        self._feat_spell_filtered = [
            i for i, s in enumerate(self._feat_spell_list)
            if s.get("casting_type", "sorcerer") == ctype
            and s.get("min_level", 1) == level
        ]
        self._feat_spell_cursor = min(
            self._feat_spell_filter_pos,
            max(0, len(self._feat_spell_filtered) - 1))
        self._feat_spell_scroll = 0

    def _feat_save_spells(self):
        """Write current spell list back to the active spells.json
        and refresh the in-memory spell registry so changes are
        immediately available in gameplay."""
        import json
        path = self._feat_spells_path()
        data = {"spells": self._feat_spell_list}
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            return False
        # Refresh the runtime spell registry used by combat/casting.
        # Pass the active module directory so _load_spells_config
        # reads from the correct location.
        try:
            from src.party import reload_module_data as _reload
            _reload(self.active_module_path)
        except Exception:
            pass
        return True

    @staticmethod
    def _feat_default_classes(casting_type):
        """Return the default allowable_classes for a casting type."""
        from src import data_registry as DR
        return DR.classes_for_casting_type(casting_type)

    def _feat_build_spell_fields(self, spell):
        """Build the editable field list for a single spell."""
        # Choice lists for spell fields
        from src import data_registry as DR
        casting_types = DR.all_casting_types()
        effect_types = DR.all_effect_types()
        targeting_types = DR.all_targeting_types()
        usable_in_opts = DR.all_usable_locations()
        all_classes = DR.caster_class_names()

        ev = spell.get("effect_value", {})
        dice = ev.get("dice", "")
        if not dice:
            dc = ev.get("dice_count", "")
            ds = ev.get("dice_sides", "")
            if dc and ds:
                dice = f"{dc}d{ds}"

        fields = [
            # -- Identity --
            ["-- Identity --", "_hdr1", "", "section", False],
            ["Name", "name", spell.get("name", ""), "text", True],
            ["ID", "id", spell.get("id", ""), "text", True],
            ["Description", "description",
             spell.get("description", ""), "text", True],
            # -- Class & Level --
            ["-- Class & Level --", "_hdr2", "", "section", False],
            ["Casting Type", "casting_type",
             spell.get("casting_type", "sorcerer"), "choice", True],
            ["Min Level", "min_level",
             str(spell.get("min_level", 1)), "int", True],
            ["Classes", "allowable_classes",
             ", ".join(spell.get("allowable_classes", [])), "text", True],
            # -- Cost & Effect --
            ["-- Cost & Effect --", "_hdr3", "", "section", False],
            ["MP Cost", "mp_cost",
             str(spell.get("mp_cost", 3)), "int", True],
            ["Effect Type", "effect_type",
             spell.get("effect_type", "damage"), "choice", True],
            ["Dice", "dice", dice, "text", True],
            ["Duration", "duration",
             str(spell.get("duration", "instant")), "text", True],
            # -- Targeting --
            ["-- Targeting --", "_hdr4", "", "section", False],
            ["Targeting", "targeting",
             spell.get("targeting", "select_enemy"), "choice", True],
            ["Range", "range",
             str(spell.get("range", 99)), "int", True],
            ["Usable In", "usable_in",
             ", ".join(spell.get("usable_in", ["battle"])), "text", True],
            # -- Visual --
            ["-- Visual --", "_hdr5", "", "section", False],
            ["Icon", "icon",
             spell.get("icon", ""), "sprite", True],
            # -- Audio --
            ["-- Audio --", "_hdr6", "", "section", False],
            ["SFX", "sfx", spell.get("sfx", ""), "text", True],
            ["Hit SFX", "hit_sfx",
             spell.get("hit_sfx", "") or "", "text", True],
        ]
        self._feat_spell_fields = fields
        self._feat_spell_field = 0
        self._feat_spell_scroll_f = 0
        self._feat_spell_buffer = ""
        # Advance to first editable field
        self._feat_spell_field = self._feat_next_editable_generic(
            self._feat_spell_fields, 0)
        if self._feat_spell_fields:
            self._feat_spell_buffer = \
                self._feat_spell_fields[self._feat_spell_field][2]

    def _feat_resort_spells(self):
        """Re-sort spell list and update cursor to follow the
        previously-selected spell."""
        if not self._feat_spell_list:
            return
        # Remember selected spell by identity
        cur_spell = (self._feat_spell_list[self._feat_spell_cursor]
                     if 0 <= self._feat_spell_cursor
                     < len(self._feat_spell_list) else None)
        from src import data_registry as DR
        type_order = DR.casting_type_sort_order()
        self._feat_spell_list.sort(key=lambda s: (
            type_order.get(s.get("casting_type", "sorcerer"), 2),
            s.get("min_level", 1),
            s.get("name", ""),
        ))
        # Restore cursor
        if cur_spell is not None:
            for i, s in enumerate(self._feat_spell_list):
                if s is cur_spell:
                    self._feat_spell_cursor = i
                    break

    def _feat_save_spell_fields(self):
        """Apply edited fields back to the spell dict in memory."""
        if self._feat_spell_cursor >= len(self._feat_spell_list):
            return
        spell = self._feat_spell_list[self._feat_spell_cursor]
        # Commit current buffer
        if self._feat_spell_fields:
            entry = self._feat_spell_fields[self._feat_spell_field]
            entry[2] = self._feat_spell_buffer

        for entry in self._feat_spell_fields:
            key = entry[1]
            val = entry[2]
            if key.startswith("_"):
                continue
            if key == "allowable_classes":
                spell[key] = [c.strip() for c in val.split(",") if c.strip()]
            elif key == "usable_in":
                spell[key] = [u.strip() for u in val.split(",") if u.strip()]
            elif key in ("min_level", "mp_cost", "range"):
                try:
                    spell[key] = int(val)
                except ValueError:
                    pass
            elif key == "duration":
                if val.isdigit():
                    spell[key] = int(val)
                else:
                    spell[key] = val
            elif key == "dice":
                ev = spell.setdefault("effect_value", {})
                ev["dice"] = val
                # Also try to set dice_count/dice_sides for compat
                if "d" in val:
                    parts = val.split("d")
                    try:
                        ev["dice_count"] = int(parts[0])
                        ev["dice_sides"] = int(parts[1])
                    except (ValueError, IndexError):
                        pass
            else:
                spell[key] = val

    def _feat_get_spell_choices(self, key):
        """Return choice options for a spell choice field."""
        from src import data_registry as DR
        if key == "casting_type":
            return DR.all_casting_types()
        elif key == "effect_type":
            return DR.all_effect_types()
        elif key == "targeting":
            return DR.all_targeting_types()
        elif key == "icon":
            # All sprites tagged with the "spells" category
            return DR.sprites_for_category("spells")
        return []

    def _feat_add_spell(self):
        """Add a new blank spell to the list."""
        new_spell = {
            "id": f"new_spell_{len(self._feat_spell_list) + 1}",
            "name": "New Spell",
            "description": "A new spell.",
            "allowable_classes": self._feat_default_classes("sorcerer"),
            "casting_type": "sorcerer",
            "min_level": 1,
            "mp_cost": 5,
            "duration": "instant",
            "effect_type": "damage",
            "effect_value": {"dice": "1d6"},
            "range": 99,
            "targeting": "select_enemy",
            "usable_in": ["battle"],
            "sfx": "",
            "hit_sfx": "",
        }
        self._feat_spell_list.append(new_spell)
        self._feat_spell_cursor = len(self._feat_spell_list) - 1

    def _feat_remove_spell(self):
        """Remove the currently selected spell."""
        if not self._feat_spell_list:
            return
        idx = self._feat_spell_cursor
        if 0 <= idx < len(self._feat_spell_list):
            self._feat_spell_list.pop(idx)
            if self._feat_spell_cursor >= len(self._feat_spell_list):
                self._feat_spell_cursor = max(
                    0, len(self._feat_spell_list) - 1)

    # ══════════════════════════════════════════════════════════
    # ── Items editor ───────────────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def _feat_items_path(self):
        """Path to items.json (module dir first, then default)."""
        if self.active_module_path:
            p = os.path.join(self.active_module_path, "items.json")
            if os.path.isfile(p):
                return p
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "items.json")

    def _feat_load_items(self):
        """Load items from items.json into a flat list for the editor."""
        import json
        path = self._feat_items_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        items = []
        for section in ("weapons", "armors", "general"):
            for name, entry in sorted(data.get(section, {}).items()):
                items.append({"_name": name, "_section": section, **entry})
        self._feat_item_list = items
        self._feat_item_cursor = 0
        self._feat_item_scroll = 0

    def _feat_save_items(self):
        """Write item list back to items.json and reload game data."""
        import json
        path = self._feat_items_path()
        data = {"weapons": {}, "armors": {}, "general": {}}
        for item in self._feat_item_list:
            name = item["_name"]
            section = item["_section"]
            entry = {k: v for k, v in item.items()
                     if not k.startswith("_")}
            data[section][name] = entry
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            return False
        try:
            from src.party import reload_module_data as _reload
            _reload(self.active_module_path)
        except Exception:
            pass
        return True

    def _feat_build_item_fields(self, item):
        """Build editable field list for a single item."""
        section = item.get("_section", "general")
        fields = [
            ["-- Identity --", "_hdr1", "", "section", False],
            ["Name", "_name", item.get("_name", ""), "text", True],
            ["Section", "_section", section, "choice", True],
            ["Description", "description",
             item.get("description", ""), "text", True],
            ["Icon", "icon", item.get("icon", ""), "sprite", True],
            ["Item Type", "item_type",
             item.get("item_type", ""), "text", True],
        ]
        if section == "weapons":
            fields += [
                ["-- Weapon Stats --", "_hdr2", "", "section", False],
                ["Power", "power",
                 str(item.get("power", 0)), "int", True],
                ["Ranged", "ranged",
                 str(item.get("ranged", False)), "choice", True],
                ["Melee", "melee",
                 str(item.get("melee", False)), "choice", True],
                ["Throwable", "throwable",
                 str(item.get("throwable", False)), "choice", True],
                ["Slots", "_slots",
                 ", ".join(item.get("slots", [])), "text", True],
            ]
        elif section == "armors":
            fields += [
                ["-- Armor Stats --", "_hdr2", "", "section", False],
                ["Evasion", "evasion",
                 str(item.get("evasion", 50)), "int", True],
                ["Slots", "_slots",
                 ", ".join(item.get("slots", [])), "text", True],
            ]
        else:
            fields += [
                ["-- General --", "_hdr2", "", "section", False],
                ["Usable", "usable",
                 str(item.get("usable", False)), "choice", True],
                ["Effect", "effect",
                 item.get("effect", ""), "text", True],
                ["Power", "power",
                 str(item.get("power", 0)), "int", True],
                ["Stackable", "stackable",
                 str(item.get("stackable", False)), "choice", True],
            ]
        fields += [
            ["-- Shop --", "_hdr3", "", "section", False],
            ["Buy Price", "buy",
             str(item.get("buy", 0)), "int", True],
            ["Sell Price", "sell",
             str(item.get("sell", 0)), "int", True],
            ["-- Equip --", "_hdr4", "", "section", False],
            ["Party Equip", "party_can_equip",
             str(item.get("party_can_equip", False)), "choice", True],
            ["Char Equip", "character_can_equip",
             str(item.get("character_can_equip", False)), "choice", True],
        ]
        self._feat_item_fields = fields
        self._feat_item_field = 0
        self._feat_item_scroll_f = 0
        self._feat_item_buffer = ""
        self._feat_item_field = self._feat_next_editable_generic(
            self._feat_item_fields, 0)
        if self._feat_item_fields:
            self._feat_item_buffer = \
                self._feat_item_fields[self._feat_item_field][2]

    def _feat_save_item_fields(self):
        """Apply edited fields back to the item dict in memory."""
        if self._feat_item_cursor >= len(self._feat_item_list):
            return
        item = self._feat_item_list[self._feat_item_cursor]
        if self._feat_item_fields:
            entry = self._feat_item_fields[self._feat_item_field]
            entry[2] = self._feat_item_buffer
        for entry in self._feat_item_fields:
            key, val = entry[1], entry[2]
            if key.startswith("_") and key not in ("_name", "_section",
                                                    "_slots"):
                continue
            if key == "_slots":
                item["slots"] = [s.strip() for s in val.split(",")
                                 if s.strip()]
            elif key in ("power", "evasion", "buy", "sell"):
                try:
                    item[key] = int(val)
                except ValueError:
                    pass
            elif key in ("ranged", "melee", "throwable", "usable",
                         "stackable", "party_can_equip",
                         "character_can_equip"):
                item[key] = val == "True"
            else:
                item[key] = val

    def _feat_get_item_choices(self, key):
        """Return choice options for an item field."""
        if key == "_section":
            return ["weapons", "armors", "general"]
        if key == "icon":
            from src import data_registry as DR
            # Procedural icons always available, plus any manifest
            # sprites the user has tagged with the "items" category
            procedural = DR.all_item_icons()
            tagged = DR.sprites_for_category("items")
            return procedural + tagged
        if key in ("ranged", "melee", "throwable", "usable",
                   "stackable", "party_can_equip",
                   "character_can_equip"):
            return ["True", "False"]
        return []

    def _feat_add_item(self):
        """Add a new blank item."""
        new_item = {
            "_name": f"New Item {len(self._feat_item_list) + 1}",
            "_section": "general",
            "description": "A new item.",
            "icon": "tool",
            "item_type": "misc",
            "buy": 10,
            "sell": 5,
            "party_can_equip": False,
            "character_can_equip": False,
        }
        self._feat_item_list.append(new_item)
        self._feat_item_cursor = len(self._feat_item_list) - 1

    def _feat_remove_item(self):
        """Remove the currently selected item."""
        if not self._feat_item_list:
            return
        idx = self._feat_item_cursor
        if 0 <= idx < len(self._feat_item_list):
            self._feat_item_list.pop(idx)
            if self._feat_item_cursor >= len(self._feat_item_list):
                self._feat_item_cursor = max(
                    0, len(self._feat_item_list) - 1)

    # ══════════════════════════════════════════════════════════
    # ── Monsters editor ────────────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def _feat_monsters_path(self):
        """Path to monsters.json (module dir first, then default)."""
        if self.active_module_path:
            p = os.path.join(self.active_module_path, "monsters.json")
            if os.path.isfile(p):
                return p
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "monsters.json")

    def _feat_load_monsters(self):
        """Load monsters from monsters.json into the editor."""
        import json
        path = self._feat_monsters_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        monsters = []
        for name, entry in sorted(
                data.get("monsters", {}).items()):
            monsters.append({"_name": name, **entry})
        self._feat_mon_list = monsters
        self._feat_mon_cursor = 0
        self._feat_mon_scroll = 0
        # Stash spawn_tables so we can preserve them on save
        self._feat_mon_spawn_tables = data.get("spawn_tables", {})

    def _feat_save_monsters(self):
        """Write monster list back to JSON and reload."""
        import json
        path = self._feat_monsters_path()
        monsters = {}
        for mon in self._feat_mon_list:
            name = mon["_name"]
            entry = {k: v for k, v in mon.items()
                     if not k.startswith("_")}
            monsters[name] = entry
        data = {
            "monsters": monsters,
            "spawn_tables": getattr(self, "_feat_mon_spawn_tables", {}),
        }
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            return False
        try:
            from src.monster import reload_module_data as _reload
            _reload(self.active_module_path)
        except Exception:
            pass
        return True

    def _feat_build_mon_fields(self, mon):
        """Build editable field list for a single monster."""
        color = mon.get("color", [200, 50, 50])
        color_str = f"{color[0]}, {color[1]}, {color[2]}" \
            if isinstance(color, (list, tuple)) else str(color)
        fields = [
            ["-- Identity --", "_hdr1", "", "section", False],
            ["Name", "_name", mon.get("_name", ""), "text", True],
            ["Description", "description",
             mon.get("description", ""), "text", True],
            ["Tile", "tile", mon.get("tile", ""), "sprite", True],
            ["Color (R,G,B)", "_color", color_str, "text", True],
            ["-- Combat Stats --", "_hdr2", "", "section", False],
            ["HP", "hp", str(mon.get("hp", 10)), "int", True],
            ["AC", "ac", str(mon.get("ac", 10)), "int", True],
            ["Attack Bonus", "attack_bonus",
             str(mon.get("attack_bonus", 1)), "int", True],
            ["Damage Dice", "damage_dice",
             str(mon.get("damage_dice", 1)), "int", True],
            ["Damage Sides", "damage_sides",
             str(mon.get("damage_sides", 4)), "int", True],
            ["Damage Bonus", "damage_bonus",
             str(mon.get("damage_bonus", 0)), "int", True],
            ["-- Rewards --", "_hdr3", "", "section", False],
            ["XP Reward", "xp_reward",
             str(mon.get("xp_reward", 25)), "int", True],
            ["Gold Min", "gold_min",
             str(mon.get("gold_min", 5)), "int", True],
            ["Gold Max", "gold_max",
             str(mon.get("gold_max", 15)), "int", True],
            ["Spawn Weight", "spawn_weight",
             str(mon.get("spawn_weight", 20)), "int", True],
            ["-- Flags --", "_hdr4", "", "section", False],
            ["Undead", "undead",
             str(mon.get("undead", False)), "choice", True],
            ["Humanoid", "humanoid",
             str(mon.get("humanoid", False)), "choice", True],
            ["Terrain", "terrain",
             mon.get("terrain", "land"), "choice", True],
        ]
        self._feat_mon_fields = fields
        self._feat_mon_field = 0
        self._feat_mon_scroll_f = 0
        self._feat_mon_buffer = ""
        self._feat_mon_field = self._feat_next_editable_generic(
            self._feat_mon_fields, 0)
        if self._feat_mon_fields:
            self._feat_mon_buffer = \
                self._feat_mon_fields[self._feat_mon_field][2]

    def _feat_save_mon_fields(self):
        """Apply edited fields back to the monster dict."""
        if self._feat_mon_cursor >= len(self._feat_mon_list):
            return
        mon = self._feat_mon_list[self._feat_mon_cursor]
        if self._feat_mon_fields:
            entry = self._feat_mon_fields[self._feat_mon_field]
            entry[2] = self._feat_mon_buffer
        for entry in self._feat_mon_fields:
            key, val = entry[1], entry[2]
            if key.startswith("_") and key not in ("_name", "_color"):
                continue
            if key == "_color":
                try:
                    parts = [int(p.strip()) for p in val.split(",")]
                    if len(parts) == 3:
                        mon["color"] = parts
                except ValueError:
                    pass
            elif key in ("hp", "ac", "attack_bonus", "damage_dice",
                         "damage_sides", "damage_bonus", "xp_reward",
                         "gold_min", "gold_max", "spawn_weight"):
                try:
                    mon[key] = int(val)
                except ValueError:
                    pass
            elif key in ("undead", "humanoid"):
                mon[key] = val == "True"
            else:
                mon[key] = val

    def _feat_get_mon_choices(self, key):
        """Return choice options for a monster field."""
        if key == "tile":
            from src import data_registry as DR
            # All sprites tagged with the "monsters" category
            return DR.sprites_for_category("monsters")
        if key in ("undead", "humanoid"):
            return ["True", "False"]
        if key == "terrain":
            return ["land", "sea"]
        return []

    def _feat_add_monster(self):
        """Add a new blank monster."""
        new_mon = {
            "_name": f"New Monster {len(self._feat_mon_list) + 1}",
            "description": "A new creature.",
            "hp": 10,
            "ac": 10,
            "attack_bonus": 1,
            "damage_dice": 1,
            "damage_sides": 4,
            "damage_bonus": 0,
            "xp_reward": 20,
            "gold_min": 3,
            "gold_max": 10,
            "color": [200, 50, 50],
            "spawn_weight": 20,
            "undead": False,
            "humanoid": False,
            "terrain": "land",
            "tile": "",
        }
        self._feat_mon_list.append(new_mon)
        self._feat_mon_cursor = len(self._feat_mon_list) - 1

    def _feat_remove_monster(self):
        """Remove the currently selected monster."""
        if not self._feat_mon_list:
            return
        idx = self._feat_mon_cursor
        if 0 <= idx < len(self._feat_mon_list):
            self._feat_mon_list.pop(idx)
            if self._feat_mon_cursor >= len(self._feat_mon_list):
                self._feat_mon_cursor = max(
                    0, len(self._feat_mon_list) - 1)

    # ══════════════════════════════════════════════════════════
    # ── Tile Types editor ──────────────────────────────────────
    # ══════════════════════════════════════════════════════════

    def _feat_restore_tile_defs_from_disk(self):
        """Called once at startup to merge saved tile_defs.json into
        the in-memory settings.TILE_DEFS and _TILE_CONTEXT so the rest
        of the game (town rendering, map, etc.) sees user-created tiles."""
        import json
        from src import settings
        try:
            with open(self._feat_tiles_path(), "r") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return  # no saved file yet — nothing to restore
        for tid_str, entry in saved.items():
            tid = int(tid_str)
            color = entry.get("color", [128, 128, 128])
            if isinstance(color, list):
                color = tuple(color)
            tdef = {
                "name": entry.get("name", f"Tile {tid}"),
                "walkable": entry.get("walkable", True),
                "color": color,
            }
            # Carry interaction fields into TILE_DEFS for runtime access
            itype = entry.get("interaction_type", "")
            if itype and itype != "none":
                tdef["interaction_type"] = itype
                idata = entry.get("interaction_data", "")
                if idata:
                    tdef["interaction_data"] = idata
            settings.TILE_DEFS[tid] = tdef
            ctx = entry.get("context")
            if ctx:
                self._TILE_CONTEXT[tid] = ctx

    def _feat_tiles_path(self):
        """Path to tile_defs.json."""
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "tile_defs.json")

    def _feat_load_tiles(self):
        """Load tile types from disk (tile_defs.json) merged with
        hardcoded settings.TILE_DEFS into the editor."""
        import json
        from src.settings import TILE_DEFS
        from src import settings

        # --- Load saved overrides / additions from JSON ----------------
        saved = {}
        try:
            with open(self._feat_tiles_path(), "r") as f:
                saved = json.load(f)          # {str(tile_id): {...}, ...}
        except (OSError, ValueError):
            saved = {}

        # Apply saved data back into the in-memory TILE_DEFS and
        # _TILE_CONTEXT so the rest of the game sees them too.
        for tid_str, entry in saved.items():
            tid = int(tid_str)
            color = entry.get("color", [128, 128, 128])
            if isinstance(color, list):
                color = tuple(color)
            tdef = {
                "name": entry.get("name", f"Tile {tid}"),
                "walkable": entry.get("walkable", True),
                "color": color,
            }
            # Carry interaction fields into TILE_DEFS for runtime access
            itype = entry.get("interaction_type", "")
            if itype and itype != "none":
                tdef["interaction_type"] = itype
                idata = entry.get("interaction_data", "")
                if idata:
                    tdef["interaction_data"] = idata
            settings.TILE_DEFS[tid] = tdef
            ctx = entry.get("context")
            if ctx:
                self._TILE_CONTEXT[tid] = ctx

        # --- Build editor list from the (now-merged) TILE_DEFS --------
        tiles = []
        for tile_id in sorted(settings.TILE_DEFS.keys()):
            tdef = settings.TILE_DEFS[tile_id]
            context = self._TILE_CONTEXT.get(tile_id, "overworld")
            # Carry over saved sprite key if present; for tiles that
            # were never edited, resolve from the manifest so every
            # tile carries an explicit _sprite for reliable rendering.
            sprite_key = ""
            s = saved.get(str(tile_id))
            if s:
                sprite_key = s.get("sprite", "")
            if not sprite_key:
                sprite_key = self._feat_tile_sprite_key(tile_id) or ""
            # Load interaction fields from saved data
            interact_type = ""
            interact_data = ""
            if s:
                interact_type = s.get("interaction_type", "none")
                interact_data = s.get("interaction_data", "")
            if not interact_type:
                interact_type = "none"
            tiles.append({
                "_tile_id": tile_id,
                "name": tdef.get("name", f"Tile {tile_id}"),
                "walkable": tdef.get("walkable", True),
                "color": list(tdef.get("color", (128, 128, 128))),
                "_context": context,
                "_sprite": sprite_key,
                "interaction_type": interact_type,
                "interaction_data": interact_data,
            })
        self._feat_tile_list = tiles
        self._feat_tile_in_folder = False
        self._feat_tile_folder_cursor = 0
        self._feat_tile_folder_scroll = 0
        self._feat_rebuild_tile_folders()

    def _feat_rebuild_tile_folders(self):
        """Build folder list with tile counts per context."""
        # Examine screen reuses overworld tiles (Grass, Forest, Sand, Path)
        examine_ids = {0, 2, 7, 6}  # GRASS, FOREST, SAND, PATH
        folders = []
        for fdef in self._TILE_FOLDER_ORDER:
            fname = fdef["name"]
            if fname == "examine":
                count = sum(1 for t in self._feat_tile_list
                            if t["_tile_id"] in examine_ids)
            elif fname == "battle":
                count = 0  # battle uses procedural tiles
            else:
                count = sum(1 for t in self._feat_tile_list
                            if t.get("_context") == fname)
            folders.append({
                "name": fname,
                "label": fdef["label"],
                "count": count,
            })
        self._feat_tile_folders = folders

    def _feat_tile_enter_folder(self):
        """Enter the selected tile folder — build tile list."""
        if self._feat_tile_folder_cursor >= len(self._feat_tile_folders):
            return
        fname = self._feat_tile_folders[
            self._feat_tile_folder_cursor]["name"]
        examine_ids = {0, 2, 7, 6}
        if fname == "examine":
            self._feat_tile_folder_tiles = [
                i for i, t in enumerate(self._feat_tile_list)
                if t["_tile_id"] in examine_ids]
        elif fname == "battle":
            self._feat_tile_folder_tiles = []
        else:
            self._feat_tile_folder_tiles = [
                i for i, t in enumerate(self._feat_tile_list)
                if t.get("_context") == fname]
        self._feat_tile_cursor = 0
        self._feat_tile_scroll = 0
        self._feat_tile_in_folder = True

    def _feat_save_tiles(self):
        """Write tile definitions back to settings.TILE_DEFS, update
        the _TILE_CONTEXT map, persist to tile_defs.json, and update
        the tile manifest for new / changed tiles."""
        import json
        from src import settings

        disk_data = {}  # what goes to tile_defs.json

        for tile in self._feat_tile_list:
            tid = tile["_tile_id"]
            color = tile.get("color", [128, 128, 128])
            if isinstance(color, list):
                color = tuple(color)
            if tid in settings.TILE_DEFS:
                settings.TILE_DEFS[tid]["name"] = tile["name"]
                settings.TILE_DEFS[tid]["walkable"] = tile["walkable"]
                settings.TILE_DEFS[tid]["color"] = color
            else:
                # New tile — add to TILE_DEFS
                settings.TILE_DEFS[tid] = {
                    "name": tile["name"],
                    "walkable": tile["walkable"],
                    "color": color,
                }
            # Sync interaction fields into TILE_DEFS for runtime access
            itype = tile.get("interaction_type", "none")
            if itype and itype != "none":
                settings.TILE_DEFS[tid]["interaction_type"] = itype
                idata = tile.get("interaction_data", "")
                if idata:
                    settings.TILE_DEFS[tid]["interaction_data"] = idata
            else:
                # Clear stale interaction fields if type was set to "none"
                settings.TILE_DEFS[tid].pop("interaction_type", None)
                settings.TILE_DEFS[tid].pop("interaction_data", None)
            # Keep _TILE_CONTEXT in sync
            ctx = tile.get("_context")
            if ctx:
                self._TILE_CONTEXT[tid] = ctx

            # Build the JSON entry for this tile
            entry_data = {
                "name": tile["name"],
                "walkable": tile["walkable"],
                "color": list(color) if isinstance(color, tuple) else color,
                "context": tile.get("_context", "overworld"),
                "sprite": tile.get("_sprite", ""),
            }
            # Only persist interaction fields if they have meaningful values
            itype = tile.get("interaction_type", "none")
            if itype and itype != "none":
                entry_data["interaction_type"] = itype
                idata = tile.get("interaction_data", "")
                if idata:
                    entry_data["interaction_data"] = idata
            disk_data[str(tid)] = entry_data

        # Write to data/tile_defs.json
        try:
            with open(self._feat_tiles_path(), "w") as f:
                json.dump(disk_data, f, indent=2)
        except OSError:
            pass

        # Persist sprite assignments to the tile manifest
        self._feat_save_tile_sprites()
        # Invalidate cached town brushes so new/changed tiles appear
        self._feat_townlayout_brushes = None
        return True

    def _feat_save_tile_sprites(self):
        """Update tile_manifest.json with sprite ↔ tile_id bindings.

        Before writing new assignments, clear any stale tile_id entries
        so that each tile_id maps to exactly one manifest sprite.
        """
        import json, os
        mpath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "tile_manifest.json")
        try:
            with open(mpath) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return

        # Build sprite_key → lowest tile_id mapping.  When multiple
        # tiles share the same sprite, the manifest tile_id goes to the
        # lowest (original) tile_id so existing lookups keep working.
        sprite_to_tid = {}   # "cat/name" → lowest tile_id
        assigned_tids = set()
        for tile in self._feat_tile_list:
            sprite_key = tile.get("_sprite", "")
            if sprite_key and "/" in sprite_key:
                tid = tile["_tile_id"]
                assigned_tids.add(tid)
                if sprite_key not in sprite_to_tid or tid < sprite_to_tid[sprite_key]:
                    sprite_to_tid[sprite_key] = tid

        # First pass: clear stale tile_id assignments for any tile_id
        # that is about to be reassigned, so only one entry ends up
        # owning each tile_id.
        for cat in manifest:
            if cat.startswith("_"):
                continue
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            for _name, entry in section.items():
                if isinstance(entry, dict) and entry.get("tile_id") in assigned_tids:
                    del entry["tile_id"]

        # Second pass: assign the lowest tile_id per sprite key
        for sprite_key, tid in sprite_to_tid.items():
            parts = sprite_key.split("/", 1)
            if len(parts) != 2:
                continue
            cat, name = parts
            section = manifest.get(cat)
            if isinstance(section, dict) and name in section:
                entry = section[name]
                if isinstance(entry, dict):
                    entry["tile_id"] = tid
        try:
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=2)
        except OSError:
            pass
        # Reload the renderer's manifest cache so sprite lookups pick up
        # the new tile_id assignments immediately.
        self.renderer.reload_sprites()

    def _feat_build_tile_fields(self, tile):
        """Build editable field list for a single tile type."""
        color = tile.get("color", [128, 128, 128])
        color_str = f"{color[0]}, {color[1]}, {color[2]}" \
            if isinstance(color, (list, tuple)) else str(color)
        # Resolve current sprite from manifest via tile_id
        sprite_key = tile.get("_sprite", "")
        if not sprite_key:
            sprite_key = self._feat_tile_sprite_key(
                tile.get("_tile_id"))
        # Interaction fields
        interact = tile.get("interaction_type", "none")
        interact_data = tile.get("interaction_data", "")
        fields = [
            ["-- Tile Type --", "_hdr1", "", "section", False],
            ["ID", "_tile_id",
             str(tile.get("_tile_id", 0)), "int", False],
            ["Name", "name", tile.get("name", ""), "text", True],
            ["Sprite", "_sprite", sprite_key, "sprite", True],
            ["Walkable", "walkable",
             str(tile.get("walkable", True)), "choice", True],
            ["Color (R,G,B)", "_color", color_str, "text", True],
            ["-- Interaction --", "_hdr2", "", "section", False],
            ["Interaction", "interaction_type", interact, "choice", True],
        ]
        # Conditionally show the data field based on interaction type
        if interact == "shop":
            fields.append(
                ["Shop Type", "interaction_data", interact_data, "choice", True])
        elif interact == "sign":
            fields.append(
                ["Sign Text", "interaction_data", interact_data, "text", True])
        elif interact != "none":
            fields.append(
                ["Data", "interaction_data", interact_data, "text", True])
        self._feat_tile_fields = fields
        self._feat_tile_field = 0
        self._feat_tile_scroll_f = 0
        self._feat_tile_buffer = ""
        self._feat_tile_field = self._feat_next_editable_generic(
            self._feat_tile_fields, 0)
        if self._feat_tile_fields:
            self._feat_tile_buffer = \
                self._feat_tile_fields[self._feat_tile_field][2]

    def _feat_tile_real_index(self):
        """Resolve the folder-relative cursor to a real _feat_tile_list index."""
        if (self._feat_tile_in_folder
                and self._feat_tile_folder_tiles
                and self._feat_tile_cursor < len(self._feat_tile_folder_tiles)):
            return self._feat_tile_folder_tiles[self._feat_tile_cursor]
        return self._feat_tile_cursor

    def _feat_save_tile_fields(self):
        """Apply edited fields back to the tile dict."""
        real_idx = self._feat_tile_real_index()
        if real_idx >= len(self._feat_tile_list):
            return
        tile = self._feat_tile_list[real_idx]
        if self._feat_tile_fields:
            entry = self._feat_tile_fields[self._feat_tile_field]
            entry[2] = self._feat_tile_buffer
        for entry in self._feat_tile_fields:
            key, val = entry[1], entry[2]
            if key.startswith("_") and key not in ("_color", "_sprite"):
                continue
            if key == "_sprite":
                tile["_sprite"] = val
            elif key == "_color":
                try:
                    parts = [int(p.strip()) for p in val.split(",")]
                    if len(parts) == 3:
                        tile["color"] = parts
                except ValueError:
                    pass
            elif key == "walkable":
                tile[key] = val == "True"
            elif key == "name":
                tile[key] = val
            elif key == "interaction_type":
                old_type = tile.get("interaction_type", "none")
                tile["interaction_type"] = val
                # When interaction type changes, reset interaction_data
                # and rebuild fields to show/hide the conditional field
                if val != old_type:
                    tile["interaction_data"] = ""
                    # Rebuild fields so the conditional data field updates
                    self._feat_build_tile_fields(tile)
                    # Re-position cursor on the interaction_type field
                    for fi, fe in enumerate(self._feat_tile_fields):
                        if fe[1] == "interaction_type":
                            self._feat_tile_field = fi
                            self._feat_tile_buffer = val
                            break
                    # Break out of the for loop — the old field list is
                    # stale after rebuild, continuing would overwrite data
                    break
            elif key == "interaction_data":
                tile["interaction_data"] = val

    @staticmethod
    def _feat_tile_sprite_key(tile_id):
        """Resolve a tile_id to its manifest 'category/name' key."""
        if tile_id is None:
            return ""
        import json, os
        try:
            mpath = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "tile_manifest.json")
            with open(mpath) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return ""
        for cat in ("overworld", "town", "dungeon",
                     "unique_tiles", "objects"):
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            for name, entry in section.items():
                if (isinstance(entry, dict)
                        and entry.get("tile_id") == tile_id):
                    return f"{cat}/{name}"
        return ""

    def _feat_get_tile_choices(self, key):
        """Return choice options for a tile field."""
        if key == "_sprite":
            from src import data_registry as DR
            # Use sprites from the category matching the tile's context
            context = None
            if (self._feat_tile_folder_tiles
                    and self._feat_tile_cursor < len(self._feat_tile_folder_tiles)):
                ti = self._feat_tile_folder_tiles[self._feat_tile_cursor]
                if ti < len(self._feat_tile_list):
                    context = self._feat_tile_list[ti].get("_context")
            if not context:
                # Fallback: use the current folder name
                if (self._feat_tile_folders
                        and self._feat_tile_folder_cursor < len(
                            self._feat_tile_folders)):
                    context = self._feat_tile_folders[
                        self._feat_tile_folder_cursor]["name"]
            # Map context to gallery categories
            if context in ("overworld", "town", "dungeon"):
                cats = [context]
            else:
                cats = ["overworld", "town", "dungeon"]
            seen = set()
            result = []
            for cat in cats:
                for s in DR.sprites_for_category(cat):
                    if s not in seen:
                        seen.add(s)
                        result.append(s)
            return sorted(result)
        if key == "walkable":
            return ["True", "False"]
        if key == "interaction_type":
            return ["none", "shop", "sign"]
        if key == "interaction_data":
            # When interaction_type is "shop", offer shop type choices
            real_idx = self._feat_tile_real_index()
            if real_idx < len(self._feat_tile_list):
                tile = self._feat_tile_list[real_idx]
                if tile.get("interaction_type") == "shop":
                    return ["general", "reagent", "weapon", "armor",
                            "magic", "inn", "guild"]
            return []
        return []

    def _feat_add_tile(self):
        """Add a new tile type with the next available ID in the current folder."""
        used_ids = {t["_tile_id"] for t in self._feat_tile_list}
        new_id = max(used_ids) + 1 if used_ids else 100
        # Determine context from the currently selected folder
        context = "overworld"
        if (self._feat_tile_folders
                and self._feat_tile_folder_cursor < len(self._feat_tile_folders)):
            context = self._feat_tile_folders[
                self._feat_tile_folder_cursor]["name"]
        # Don't add tiles to virtual folders (examine reuses overworld,
        # battle uses procedural tiles).
        if context in ("examine", "battle"):
            context = "overworld"
        new_tile = {
            "_tile_id": new_id,
            "name": f"New Tile {new_id}",
            "walkable": True,
            "color": [128, 128, 128],
            "_context": context,
            "interaction_type": "none",
            "interaction_data": "",
        }
        self._feat_tile_list.append(new_tile)
        self._feat_tile_cursor = len(self._feat_tile_list) - 1

    def _feat_duplicate_tile(self):
        """Duplicate the currently selected tile type with a new ID."""
        if not self._feat_tile_list:
            return
        real_idx = self._feat_tile_real_index()
        if real_idx < 0 or real_idx >= len(self._feat_tile_list):
            return
        src = self._feat_tile_list[real_idx]
        used_ids = {t["_tile_id"] for t in self._feat_tile_list}
        new_id = max(used_ids) + 1 if used_ids else 100
        # Resolve sprite: use explicit _sprite if set, otherwise look up
        # from the manifest via the source tile's tile_id.
        sprite_key = src.get("_sprite", "")
        if not sprite_key:
            sprite_key = self._feat_tile_sprite_key(src.get("_tile_id"))
        dup = {
            "_tile_id": new_id,
            "name": f"{src['name']} Copy",
            "walkable": src.get("walkable", True),
            "color": list(src.get("color", [128, 128, 128])),
            "_context": src.get("_context", "overworld"),
            "_sprite": sprite_key or "",
        }
        self._feat_tile_list.append(dup)
        self._feat_tile_cursor = len(self._feat_tile_list) - 1

    def _feat_remove_tile(self):
        """Remove the currently selected tile type."""
        if not self._feat_tile_list:
            return
        real_idx = self._feat_tile_real_index()
        if 0 <= real_idx < len(self._feat_tile_list):
            self._feat_tile_list.pop(real_idx)
            # Keep the folder-relative cursor in bounds after removal
            folder_len = len(self._feat_tile_folder_tiles) - 1 \
                if self._feat_tile_in_folder else len(self._feat_tile_list)
            if self._feat_tile_cursor >= folder_len:
                self._feat_tile_cursor = max(0, folder_len - 1)

    # ══════════════════════════════════════════════════════════
    # ── Tile Gallery (read-only) ───────────────────────────────
    # ══════════════════════════════════════════════════════════

    # Default: each sprite belongs only to its own manifest category.
    # Players can add more categories via the tag editor in the gallery.

    # Rendering mode for each manifest sprite.
    # "sprite" = rendered directly from this graphic
    # "sprite+procedural" = sprite used as base, procedural overlay on top
    # "procedural" = graphic loaded but tile is mostly procedural
    _GALLERY_RENDER_MODE = {
        # Overworld: all sprites used directly
        ("overworld", "grass"): "sprite",
        ("overworld", "water"): "sprite",
        ("overworld", "forest"): "sprite",
        ("overworld", "mountain"): "sprite",
        ("overworld", "town"): "sprite",
        ("overworld", "dungeon"): "sprite",
        ("overworld", "dungeon_cleared"): "sprite+procedural",
        ("overworld", "path"): "sprite",
        ("overworld", "sand"): "sprite",
        ("overworld", "bridge"): "sprite",
        # Town: sprites used in medieval style, procedural otherwise
        ("town", "floor"): "sprite+procedural",
        ("town", "wall"): "sprite+procedural",
        ("town", "counter"): "sprite+procedural",
        ("town", "door"): "sprite+procedural",
        ("town", "exit"): "sprite",
        ("town", "altar"): "procedural",
        # Dungeon: base sprites with procedural environmental overlay
        ("dungeon", "dfloor"): "sprite+procedural",
        ("dungeon", "dwall"): "sprite+procedural",
        ("dungeon", "chest"): "sprite",
        ("dungeon", "artifact"): "sprite+procedural",
        ("dungeon", "portal"): "sprite+procedural",
        ("dungeon", "wall_torch"): "sprite+procedural",
        ("dungeon", "moss"): "sprite+procedural",
        ("dungeon", "puddle"): "sprite+procedural",
        ("dungeon", "ddoor"): "sprite+procedural",
        ("dungeon", "locked_door"): "sprite+procedural",
        ("dungeon", "stairs"): "procedural",
        ("dungeon", "stairs_down"): "procedural",
        ("dungeon", "trap"): "procedural",
        ("town", "machine"): "procedural",
        ("town", "keyslot"): "procedural",
    }

    def _feat_load_gallery(self):
        """Load all manifest sprites into a flat list for browsing.

        Each entry includes a ``usable_in`` list and a ``rendering``
        note indicating how the game uses it.
        """
        import json

        mpath = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "data", "tile_manifest.json")
        try:
            with open(mpath, "r") as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            manifest = {}

        all_cats = ("overworld", "town", "dungeon", "people",
                    "monsters", "objects", "unique_tiles",
                    "items", "unassigned")
        entries = []
        for cat in all_cats:
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            for name in sorted(section.keys()):
                entry = section[name]
                if not (isinstance(entry, dict) and "path" in entry):
                    continue
                if "usable_in" in entry:
                    usable = list(entry["usable_in"])
                else:
                    usable = [cat]
                rendering = self._GALLERY_RENDER_MODE.get(
                    (cat, name), "sprite")
                # Hide purely procedural tiles (no meaningful sprite)
                if rendering == "procedural":
                    continue
                entries.append({
                    "category": cat,
                    "name": name,
                    "path": entry["path"],
                    "tile_id": entry.get("tile_id"),
                    "usable_in": sorted(usable),
                    "rendering": rendering,
                })
        # Procedural-only item icons (no sprite file) are hidden from
        # the gallery along with other procedural-only entries.

        self._feat_gallery_list = entries
        self._feat_gallery_cat_cursor = 0
        self._feat_gallery_cat_scroll = 0
        self._feat_rebuild_gallery_cats()

    def _feat_rebuild_gallery_cats(self):
        """Rebuild the category folder list with sprite counts."""
        cats = []
        for cat in self._feat_gallery_all_cats:
            count = sum(1 for e in self._feat_gallery_list
                        if cat in e.get("usable_in", []))
            cats.append({"name": cat, "label": cat.replace("_", " ").title(),
                         "count": count})
        self._feat_gallery_cat_list = cats

    def _feat_gallery_enter_cat(self):
        """Enter the selected category folder — build sprite list."""
        if self._feat_gallery_cat_cursor >= len(self._feat_gallery_cat_list):
            return
        cat = self._feat_gallery_cat_list[
            self._feat_gallery_cat_cursor]["name"]
        sprites = []
        for gi, entry in enumerate(self._feat_gallery_list):
            if cat in entry.get("usable_in", []):
                sprites.append(gi)
        self._feat_gallery_sprites = sprites
        self._feat_gallery_spr_cursor = 0
        self._feat_gallery_spr_scroll = 0

    def _feat_save_gallery(self):
        """Persist usable_in changes back to tile_manifest.json.

        For each gallery entry, if the user added or removed a category
        from usable_in, we store the custom list in a ``_usable_in``
        key inside the manifest entry so it survives reloads.
        """
        import json
        mpath = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "data", "tile_manifest.json")
        try:
            with open(mpath, "r") as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return False

        for entry in self._feat_gallery_list:
            cat = entry["category"]
            name = entry["name"]
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            mentry = section.get(name)
            if isinstance(mentry, dict):
                mentry["usable_in"] = entry.get("usable_in", [])

        try:
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=2)
        except OSError:
            return False
        return True

    # ── Reusable Features editor ──────────────────────────────────

    _RFEAT_FOLDER_ORDER = [
        {"name": "town",      "label": "Town"},
        {"name": "dungeon",   "label": "Dungeon"},
        {"name": "overworld", "label": "Overworld"},
    ]
    _RFEAT_DEFAULTS = {
        "town":      {"width": 8, "height": 8},
        "dungeon":   {"width": 8, "height": 8},
        "overworld": {"width": 8, "height": 8},
    }

    def _feat_rfeat_path(self):
        """Path to reusable_features.json."""
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "reusable_features.json")

    def _feat_load_rfeat(self):
        """Load reusable features from disk."""
        import json
        data = {}
        try:
            with open(self._feat_rfeat_path(), "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            pass
        for ctx in ("town", "dungeon", "overworld"):
            items = []
            for raw in data.get(ctx, []):
                items.append({
                    "name": raw.get("name", "Unnamed"),
                    "width": raw.get("width",
                                     self._RFEAT_DEFAULTS[ctx]["width"]),
                    "height": raw.get("height",
                                      self._RFEAT_DEFAULTS[ctx]["height"]),
                    "tiles": dict(raw.get("tiles", {})),
                })
            self._feat_rfeat_lists[ctx] = items
        self._feat_rfeat_folder_cursor = 0
        self._feat_rfeat_folder_scroll = 0
        self._feat_rfeat_in_folder = False
        self._feat_rebuild_rfeat_folders()

    def _feat_save_rfeat(self):
        """Persist reusable features to disk."""
        import json
        data = {}
        for ctx in ("town", "dungeon", "overworld"):
            raw = []
            for feat in self._feat_rfeat_lists.get(ctx, []):
                raw.append({
                    "name": feat["name"],
                    "width": feat["width"],
                    "height": feat["height"],
                    "tiles": dict(feat.get("tiles", {})),
                })
            data[ctx] = raw
        try:
            with open(self._feat_rfeat_path(), "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def _feat_rebuild_rfeat_folders(self):
        """Build folder list with feature counts per context."""
        folders = []
        for fdef in self._RFEAT_FOLDER_ORDER:
            fname = fdef["name"]
            count = len(self._feat_rfeat_lists.get(fname, []))
            folders.append({
                "name": fname,
                "label": fdef["label"],
                "count": count,
            })
        self._feat_rfeat_folders = folders

    def _feat_rfeat_enter_folder(self):
        """Enter the selected context folder."""
        if self._feat_rfeat_folder_cursor >= len(self._feat_rfeat_folders):
            return
        self._feat_rfeat_current_ctx = self._feat_rfeat_folders[
            self._feat_rfeat_folder_cursor]["name"]
        self._feat_rfeat_in_folder = True
        self._feat_rfeat_cursor = 0
        self._feat_rfeat_scroll = 0

    def _feat_rfeat_current_list(self):
        """Return the feature list for the current folder."""
        return self._feat_rfeat_lists.get(
            self._feat_rfeat_current_ctx, [])

    def _feat_rfeat_add(self):
        """Add a new reusable feature in the current folder."""
        ctx = self._feat_rfeat_current_ctx
        defaults = self._RFEAT_DEFAULTS[ctx]
        items = self._feat_rfeat_lists.get(ctx, [])
        n = len(items) + 1
        items.append({
            "name": f"Feature {n}",
            "width": defaults["width"],
            "height": defaults["height"],
            "tiles": {},
        })
        self._feat_rfeat_lists[ctx] = items
        self._feat_rfeat_cursor = len(items) - 1
        self._feat_rebuild_rfeat_folders()

    def _feat_rfeat_remove(self):
        """Remove the selected reusable feature."""
        items = self._feat_rfeat_current_list()
        if not items:
            return
        idx = self._feat_rfeat_cursor
        if 0 <= idx < len(items):
            items.pop(idx)
            if self._feat_rfeat_cursor >= len(items):
                self._feat_rfeat_cursor = max(0, len(items) - 1)
        self._feat_rebuild_rfeat_folders()

    def _feat_rfeat_enter_painter(self):
        """Enter the grid painter for the selected feature."""
        items = self._feat_rfeat_current_list()
        if not items or self._feat_rfeat_cursor >= len(items):
            return
        self._feat_rfeat_editing = True
        self._feat_rfeat_cx = 0
        self._feat_rfeat_cy = 0
        self._feat_rfeat_brush_idx = 0
        self._feat_rfeat_brushes = None

    def _feat_get_rfeat_brushes(self):
        """Build brush list for the reusable features editor."""
        if self._feat_rfeat_brushes is not None:
            return self._feat_rfeat_brushes
        brushes = [
            {"name": "Eraser", "tile_id": None, "path": None},
        ]
        from src.settings import TILE_DEFS
        ctx = self._feat_rfeat_current_ctx
        ctx_ids = sorted(
            tid for tid, c in self._TILE_CONTEXT.items()
            if c == ctx
        )
        manifest = {}
        try:
            mpath = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "tile_manifest.json")
            with open(mpath) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            pass
        saved_tile_defs = {}
        try:
            with open(self._feat_tiles_path(), "r") as f:
                saved_tile_defs = json.load(f)
        except (OSError, ValueError):
            pass

        def _resolve_path(tid):
            saved = saved_tile_defs.get(str(tid), {})
            sprite_key = saved.get("sprite", "")
            if sprite_key and "/" in sprite_key:
                cat, name = sprite_key.split("/", 1)
                section = manifest.get(cat, {})
                if isinstance(section, dict):
                    entry = section.get(name, {})
                    if isinstance(entry, dict) and "path" in entry:
                        p = entry["path"]
                        if p.startswith("src/assets/"):
                            p = p[len("src/assets/"):]
                        return p
            for tile in getattr(self, "_feat_tile_list", []):
                if tile.get("_tile_id") == tid:
                    sk = tile.get("_sprite", "")
                    if sk and "/" in sk:
                        cat, name = sk.split("/", 1)
                        section = manifest.get(cat, {})
                        if isinstance(section, dict):
                            entry = section.get(name, {})
                            if isinstance(entry, dict) and "path" in entry:
                                p = entry["path"]
                                if p.startswith("src/assets/"):
                                    p = p[len("src/assets/"):]
                                return p
                    break
            for cat in manifest:
                if cat.startswith("_"):
                    continue
                section = manifest.get(cat, {})
                if not isinstance(section, dict):
                    continue
                for _name, entry in section.items():
                    if (isinstance(entry, dict)
                            and entry.get("tile_id") == tid
                            and "path" in entry):
                        p = entry["path"]
                        if p.startswith("src/assets/"):
                            p = p[len("src/assets/"):]
                        return p
            return None

        for tid in ctx_ids:
            td = TILE_DEFS.get(tid)
            if not td:
                continue
            brushes.append({
                "name": td.get("name", f"Tile {tid}"),
                "tile_id": tid,
                "path": _resolve_path(tid),
            })
        self._feat_rfeat_brushes = brushes
        return brushes

    # ── Default sizes for each sub-editor type ──
    _TOWN_SUB_DEFAULTS = {
        "layouts":   {"name_prefix": "Town Layout",   "width": 18, "height": 19},
        "features":  {"name_prefix": "Town Feature",  "width": 8,  "height": 8},
        "interiors": {"name_prefix": "Interior",      "width": 14, "height": 15},
    }
    def _feat_town_templates_path(self):
        """Return path to the standalone town_templates.json file."""
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "town_templates.json")

    def _feat_load_townlayouts(self):
        """Load all town sub-editor lists from town_templates.json."""
        data = {}
        path = self._feat_town_templates_path()
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            pass
        for sub_key in ("layouts", "features", "interiors"):
            items = []
            defaults = self._TOWN_SUB_DEFAULTS[sub_key]
            raw = data.get(sub_key, [])
            for tl in raw:
                item = {
                    "name": tl.get("name", "Unnamed"),
                    "width": tl.get("width", defaults["width"]),
                    "height": tl.get("height", defaults["height"]),
                    "tiles": dict(tl.get("tiles", {})),
                }
                # Layouts carry a description
                if sub_key == "layouts":
                    item["description"] = tl.get("description", "")
                # Interiors carry a parent_town to scope them to a layout
                if sub_key == "interiors":
                    item["parent_town"] = tl.get("parent_town", "")
                items.append(item)
            self._feat_town_lists[sub_key] = items

        # ── Auto-migrate: assign unscoped interiors to their parent town ──
        self._feat_migrate_interior_parents()

        self._feat_town_active_sub = None
        self._feat_town_node_cursor = 0
        self._feat_town_detail_editing = False
        self._feat_town_desc_buf = ""
        self._feat_townlayout_cursor = 0
        self._feat_townlayout_scroll = 0
        self._feat_townlayout_editing = False

    def _feat_migrate_interior_parents(self):
        """Auto-assign parent_town to interiors that don't have one yet.

        Scans all layouts to find which interior names are referenced,
        then assigns the first referencing layout as the parent.
        """
        interiors = self._feat_town_lists.get("interiors", [])
        unscoped = [i for i in interiors if not i.get("parent_town")]
        if not unscoped:
            return
        # Build a map: interior_name → first layout that references it
        name_to_town = {}
        for layout in self._feat_town_lists.get("layouts", []):
            for td in layout.get("tiles", {}).values():
                iname = td.get("interior")
                if iname and iname not in name_to_town:
                    name_to_town[iname] = layout["name"]
        # Assign parent_town based on references found
        changed = False
        for interior in unscoped:
            parent = name_to_town.get(interior["name"], "")
            if parent:
                interior["parent_town"] = parent
                changed = True
        if changed:
            self._feat_save_townlayouts()

    @property
    def _feat_townlayout_list(self):
        """Return the appropriate list based on active_sub state.

        - When active_sub is None, "nodes", or "details": return layouts list (town list)
        - When active_sub is "interiors": return filtered interiors for selected town
        """
        if self._feat_town_active_sub in ("interiors", "details", "nodes") or self._feat_town_active_sub is None:
            # For town list, nodes, details views: return layouts
            if self._feat_town_active_sub is None or self._feat_town_active_sub in ("nodes", "details"):
                return self._feat_town_lists.get("layouts", [])
            # For interiors view: return filtered list scoped to selected town
            if self._feat_town_active_sub == "interiors":
                selected_town = self._get_selected_town_name()
                if selected_town:
                    return [i for i in self._feat_town_lists.get("interiors", [])
                            if i.get("parent_town") == selected_town]
                return []
        return self._feat_town_lists.get("layouts", [])

    @_feat_townlayout_list.setter
    def _feat_townlayout_list(self, value):
        """Set the list based on active_sub state.

        For interiors, this just replaces the entire list since we work
        with filtered views. The naming/painting handlers update items
        directly by reference, so the filtered list changes are reflected
        in the main interiors list.
        """
        if self._feat_town_active_sub == "interiors":
            self._feat_town_lists["interiors"] = value
        else:
            self._feat_town_lists["layouts"] = value

    def _get_selected_town_name(self):
        """Get the name of the currently selected town."""
        layouts = self._feat_town_lists.get("layouts", [])
        if 0 <= self._feat_town_selected_idx < len(layouts):
            return layouts[self._feat_town_selected_idx]["name"]
        return None

    def _feat_save_townlayouts(self):
        """Persist all town sub-editor lists to town_templates.json."""
        data = {}
        for sub_key in ("layouts", "features", "interiors"):
            raw = []
            for tl in self._feat_town_lists.get(sub_key, []):
                item = {
                    "name": tl["name"],
                    "width": tl["width"],
                    "height": tl["height"],
                    "tiles": dict(tl.get("tiles", {})),
                }
                if sub_key == "layouts":
                    item["description"] = tl.get("description", "")
                if sub_key == "interiors":
                    item["parent_town"] = tl.get("parent_town", "")
                raw.append(item)
            data[sub_key] = raw
        path = self._feat_town_templates_path()
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

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

        # Ensure layouts are loaded from disk (they may not be if the
        # town editor hasn't been opened yet this session).
        layouts = self._feat_town_lists.get("layouts", [])
        if not layouts:
            self._feat_load_townlayouts()
            layouts = self._feat_town_lists.get("layouts", [])
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

        # Build tile map — unpainted cells are black void
        from src.settings import TILE_VOID, TILE_EXIT
        tm = TileMap(w, h, default_tile=TILE_VOID, oob_tile=TILE_VOID)
        interior_links = {}
        overworld_exits = set()
        entry_col, entry_row = 0, h - 1  # fallback

        for key, td in tiles_dict.items():
            # Keys are "col,row"
            try:
                parts = key.split(",")
                col, row = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                continue
            tile_id = td.get("tile_id", 10)
            tm.set_tile(col, row, tile_id)
            # Store sprite path so runtime rendering matches the editor
            path = td.get("path")
            if path:
                tm.sprite_overrides[(col, row)] = path
            # Check for interior link
            if td.get("interior"):
                interior_links[(col, row)] = td["interior"]
            # Check for overworld exit
            if td.get("to_overworld"):
                overworld_exits.add((col, row))
                # Use first overworld exit as entry position
                if entry_col == 0 and entry_row == h - 1:
                    entry_col, entry_row = col, row
            # Check for exit tile to set entry position
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

    def _feat_add_townlayout(self, parent_town=""):
        """Add a new empty item to the active sub-editor.

        Parameters
        ----------
        parent_town : str
            For interiors, the name of the parent layout this interior
            belongs to.  Ignored for layouts and features.
        """
        sub = self._feat_town_active_sub or "layouts"
        defaults = self._TOWN_SUB_DEFAULTS[sub]
        items = self._feat_town_lists[sub]
        idx = len(items)
        item = {
            "name": f"{defaults['name_prefix']} {idx + 1}",
            "width": defaults["width"],
            "height": defaults["height"],
            "tiles": {},
        }
        if sub == "layouts":
            item["description"] = ""
        if sub == "interiors":
            item["parent_town"] = parent_town
        items.append(item)
        # For interiors, set cursor based on the filtered list (which may
        # be shorter than the full interiors list) so it points at the
        # newly added item.
        if sub == "interiors":
            filtered = self._feat_townlayout_list
            self._feat_townlayout_cursor = max(0, len(filtered) - 1)
        else:
            self._feat_townlayout_cursor = idx
        return item

    def _feat_remove_townlayout(self):
        """Remove the currently selected item from the active sub-editor."""
        if self._feat_town_active_sub == "interiors":
            # For interiors, we need to find and remove from the full list
            filtered_items = self._feat_townlayout_list
            if not filtered_items or self._feat_townlayout_cursor >= len(filtered_items):
                return
            item_to_remove = filtered_items[self._feat_townlayout_cursor]
            # Find and remove this item from the full interiors list
            all_interiors = self._feat_town_lists.get("interiors", [])
            try:
                all_interiors.remove(item_to_remove)
            except ValueError:
                pass
            # Recalculate filtered list and adjust cursor
            filtered_items = self._feat_townlayout_list
            if self._feat_townlayout_cursor >= len(filtered_items):
                self._feat_townlayout_cursor = max(0, len(filtered_items) - 1)
        else:
            # For layouts/features, remove from list directly
            items = self._feat_townlayout_list
            if not items:
                return
            idx = self._feat_townlayout_cursor
            items.pop(idx)
            if self._feat_townlayout_cursor >= len(items):
                self._feat_townlayout_cursor = max(0, len(items) - 1)

    def _feat_enter_townlayout_painter(self):
        """Enter the grid painter for the selected item."""
        if self._feat_townlayout_cursor >= len(self._feat_townlayout_list):
            return
        self._feat_townlayout_editing = True
        self._feat_townlayout_cx = 1
        self._feat_townlayout_cy = 1
        self._feat_townlayout_brush_idx = 0
        # Invalidate brush cache so features list is rebuilt fresh
        self._feat_townlayout_brushes = None

    def _feat_get_townlayout_brushes(self):
        """Build brush list from the Tile Types (TILE_DEFS) for town context."""
        if self._feat_townlayout_brushes is not None:
            return self._feat_townlayout_brushes
        brushes = [
            {"name": "Eraser", "tile_id": None, "path": None},
        ]
        # Collect town tile IDs from Tile Types definitions
        from src.settings import TILE_DEFS
        town_ids = sorted(
            tid for tid, ctx in self._TILE_CONTEXT.items()
            if ctx == "town"
        )

        # Load saved tile defs for authoritative sprite keys
        saved_tile_defs = {}
        try:
            with open(self._feat_tiles_path(), "r") as f:
                saved_tile_defs = json.load(f)
        except (OSError, ValueError):
            pass

        # Load manifest for resolving sprite key → file path
        manifest = {}
        try:
            mpath = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "tile_manifest.json")
            with open(mpath) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            pass

        def _resolve_sprite_path(tid):
            """Get the sprite asset path for a tile_id.

            Priority: 1) saved _sprite key from tile_defs.json
                      2) manifest tile_id reverse lookup (first match)
            """
            # Try the authoritative sprite key from tile_defs.json
            saved = saved_tile_defs.get(str(tid), {})
            sprite_key = saved.get("sprite", "")
            if sprite_key and "/" in sprite_key:
                cat, name = sprite_key.split("/", 1)
                section = manifest.get(cat, {})
                if isinstance(section, dict):
                    entry = section.get(name, {})
                    if isinstance(entry, dict) and "path" in entry:
                        p = entry["path"]
                        if p.startswith("src/assets/"):
                            p = p[len("src/assets/"):]
                        return p
            # Also check the in-memory tile list (for unsaved changes)
            for tile in getattr(self, "_feat_tile_list", []):
                if tile.get("_tile_id") == tid:
                    sk = tile.get("_sprite", "")
                    if sk and "/" in sk:
                        cat, name = sk.split("/", 1)
                        section = manifest.get(cat, {})
                        if isinstance(section, dict):
                            entry = section.get(name, {})
                            if isinstance(entry, dict) and "path" in entry:
                                p = entry["path"]
                                if p.startswith("src/assets/"):
                                    p = p[len("src/assets/"):]
                                return p
                    break
            # Fallback: scan manifest for first entry with this tile_id
            for cat in manifest:
                if cat.startswith("_"):
                    continue
                section = manifest.get(cat, {})
                if not isinstance(section, dict):
                    continue
                for _name, entry in section.items():
                    if (isinstance(entry, dict)
                            and entry.get("tile_id") == tid
                            and "path" in entry):
                        p = entry["path"]
                        if p.startswith("src/assets/"):
                            p = p[len("src/assets/"):]
                        return p
            return None

        for tid in town_ids:
            td = TILE_DEFS.get(tid)
            if not td:
                continue
            brushes.append({
                "name": td.get("name", f"Tile {tid}"),
                "tile_id": tid,
                "path": _resolve_sprite_path(tid),
            })

        # ── Append town features as composite brushes (only for town layouts, not interiors) ──
        # Features should appear when editing a layout, but not when editing an interior
        sub = self._feat_town_active_sub or "layouts"
        is_editing_layout = sub in (None, "nodes", "details")
        if is_editing_layout:
            features = self._feat_town_lists.get("features", [])
            for fi, feat in enumerate(features):
                if not feat.get("tiles"):
                    continue  # skip empty features
                brushes.append({
                    "name": f"\u2726 {feat['name']}",
                    "tile_id": None,
                    "path": None,
                    "feature": feat,
                })

            # Also append reusable features (town context) from the new system
            self._feat_load_rfeat()  # ensure data is loaded from disk
            rfeat_town = self._feat_rfeat_lists.get("town", [])
            for feat in rfeat_town:
                if not feat.get("tiles"):
                    continue  # skip empty features
                brushes.append({
                    "name": f"\u2726 {feat['name']}",
                    "tile_id": None,
                    "path": None,
                    "feature": feat,
                })

        self._feat_townlayout_brushes = brushes
        return brushes

    def _feat_handle_townlayout_input(self, event):
        """Handle input for the town layouts editor with new hierarchy.

        Navigation flow:
        - active_sub is None → Town list (show layouts, Enter goes to nodes)
        - active_sub == "nodes" → Node selection (3 nodes, Enter opens selected)
        - active_sub == "details" → Detail editing (name/description text fields)
        - active_sub == "interiors" → Interior list for this town
        - Grid painter (editing=True) works for both layout and interior editing
        """
        if event.type != pygame.KEYDOWN:
            return

        # Intercept input when unsaved-changes dialog is showing
        if self._unsaved_dialog_active:
            self._handle_unsaved_dialog_input(event)
            return

        # ── Town picker overlay (for copying interior to pick parent) ──
        if self._feat_town_picker_active:
            self._feat_handle_town_picker_input(event)
            return

        # ── Naming mode: capture text input ──
        if self._feat_townlayout_naming:
            self._feat_handle_townlayout_naming_input(event)
            return

        # ── Detail editing mode (editing name/description) ──
        if self._feat_town_detail_editing:
            self._feat_handle_town_detail_editing_input(event)
            return

        # ── Tile replace overlay ──
        if self._feat_townlayout_replacing:
            self._feat_handle_townlayout_replace_input(event)
            return

        # ── Interior picker overlay ──
        if self._feat_interior_picking:
            self._feat_handle_interior_picker_input(event)
            return

        if self._feat_townlayout_editing:
            # Grid painter mode
            self._feat_handle_townlayout_painter_input(event)
            return

        # ── Town list (active_sub is None) ──
        if self._feat_town_active_sub is None:
            layouts = self._feat_town_lists.get("layouts", [])
            n = len(layouts)
            if event.key == pygame.K_ESCAPE:
                self._feat_level = 0
                self._feat_active_editor = None
            elif event.key == pygame.K_UP and n > 0:
                self._feat_townlayout_cursor = (self._feat_townlayout_cursor - 1) % n
                self._feat_townlayout_scroll = self._feat_adjust_scroll_generic(
                    self._feat_townlayout_cursor, self._feat_townlayout_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self._feat_townlayout_cursor = (self._feat_townlayout_cursor + 1) % n
                self._feat_townlayout_scroll = self._feat_adjust_scroll_generic(
                    self._feat_townlayout_cursor, self._feat_townlayout_scroll)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and n > 0:
                # Enter the nodes view for this town
                self._feat_town_selected_idx = self._feat_townlayout_cursor
                self._feat_town_active_sub = "nodes"
                self._feat_town_node_cursor = 0
            elif self._is_new_shortcut(event):
                # Add new town layout
                self._feat_add_townlayout()
                self._feat_save_townlayouts()
                self._feat_dirty = False
            elif self._is_delete_shortcut(event) and n > 0:
                self._feat_remove_townlayout()
                self._feat_save_townlayouts()
                self._feat_dirty = False
            elif event.key == pygame.K_n and n > 0:
                # Rename the selected town
                item = layouts[self._feat_townlayout_cursor]
                self._feat_townlayout_naming = True
                self._feat_townlayout_name_buf = item.get("name", "")
            return

        # ── Node selection (active_sub == "nodes") ──
        if self._feat_town_active_sub == "nodes":
            if event.key == pygame.K_ESCAPE:
                self._feat_save_townlayouts()
                self._feat_town_active_sub = None
            elif event.key == pygame.K_UP:
                self._feat_town_node_cursor = (self._feat_town_node_cursor - 1) % 3
            elif event.key == pygame.K_DOWN:
                self._feat_town_node_cursor = (self._feat_town_node_cursor + 1) % 3
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                # Open the selected node
                if self._feat_town_node_cursor == 0:
                    # Town Details — point cursor at selected town for renderer
                    self._feat_townlayout_cursor = self._feat_town_selected_idx
                    self._feat_town_active_sub = "details"
                    self._feat_town_detail_editing = False
                elif self._feat_town_node_cursor == 1:
                    # Town Interiors
                    self._feat_town_active_sub = "interiors"
                    self._feat_townlayout_cursor = 0
                    self._feat_townlayout_scroll = 0
                elif self._feat_town_node_cursor == 2:
                    # Town Layout (enter grid painter) — point cursor at selected town
                    self._feat_townlayout_cursor = self._feat_town_selected_idx
                    self._feat_enter_townlayout_painter()
                    self._feat_dirty = False
                    self._feat_level = 2
            return

        # ── Detail editing (active_sub == "details") ──
        if self._feat_town_active_sub == "details":
            if event.key == pygame.K_ESCAPE:
                self._feat_save_townlayouts()
                self._feat_town_active_sub = "nodes"
            elif event.key == pygame.K_n:
                # Start editing name — set cursor to match selected town
                # so the shared naming handler updates the right item
                self._feat_townlayout_cursor = self._feat_town_selected_idx
                layouts = self._feat_town_lists.get("layouts", [])
                if 0 <= self._feat_town_selected_idx < len(layouts):
                    item = layouts[self._feat_town_selected_idx]
                    self._feat_townlayout_naming = True
                    self._feat_townlayout_name_buf = item.get("name", "")
            elif event.key == pygame.K_d:
                # Start editing description
                self._feat_town_detail_editing = True
                layouts = self._feat_town_lists.get("layouts", [])
                if 0 <= self._feat_town_selected_idx < len(layouts):
                    item = layouts[self._feat_town_selected_idx]
                    self._feat_town_desc_buf = item.get("description", "")
            return

        # ── Interior list (active_sub == "interiors") ──
        if self._feat_town_active_sub == "interiors":
            interiors = self._feat_townlayout_list  # filtered by parent_town
            n = len(interiors)
            if event.key == pygame.K_ESCAPE:
                self._feat_save_townlayouts()
                self._feat_town_active_sub = "nodes"
                # Restore cursor to the selected town index for layout operations
                self._feat_townlayout_cursor = self._feat_town_selected_idx
            elif event.key == pygame.K_UP and n > 0:
                self._feat_townlayout_cursor = (self._feat_townlayout_cursor - 1) % n
                self._feat_townlayout_scroll = self._feat_adjust_scroll_generic(
                    self._feat_townlayout_cursor, self._feat_townlayout_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self._feat_townlayout_cursor = (self._feat_townlayout_cursor + 1) % n
                self._feat_townlayout_scroll = self._feat_adjust_scroll_generic(
                    self._feat_townlayout_cursor, self._feat_townlayout_scroll)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and n > 0:
                # Enter grid painter for selected interior
                self._feat_enter_townlayout_painter()
                self._feat_dirty = False
                self._feat_level = 2
            elif self._is_new_shortcut(event):
                # Add new interior scoped to current town
                selected_town = self._get_selected_town_name()
                self._feat_add_townlayout(parent_town=selected_town or "")
                self._feat_save_townlayouts()
                self._feat_dirty = False
            elif self._is_delete_shortcut(event) and n > 0:
                self._feat_remove_townlayout()
                self._feat_save_townlayouts()
                self._feat_dirty = False
            elif event.key == pygame.K_c and n > 0:
                # Copy interior to another town
                self._feat_copy_interior_source = self._feat_townlayout_cursor
                layouts = self._feat_town_lists.get("layouts", [])
                if layouts:
                    self._feat_town_picker_active = True
                    self._feat_town_picker_cursor = 0
                    self._feat_town_picker_mode = "copy"
                else:
                    self._feat_do_copy_interior("")
            elif event.key == pygame.K_n and n > 0:
                # Rename interior
                if self._feat_townlayout_cursor >= n:
                    self._feat_townlayout_cursor = max(0, n - 1)
                item = interiors[self._feat_townlayout_cursor]
                self._feat_townlayout_naming = True
                self._feat_townlayout_name_buf = item.get("name", "")
            return

    def _feat_handle_town_detail_editing_input(self, event):
        """Handle text input while editing town description."""
        if event.key == pygame.K_RETURN:
            # Confirm the description
            layouts = self._feat_town_lists.get("layouts", [])
            if 0 <= self._feat_town_selected_idx < len(layouts):
                layouts[self._feat_town_selected_idx]["description"] = self._feat_town_desc_buf
                self._feat_save_townlayouts()
            self._feat_town_detail_editing = False
            self._feat_town_desc_buf = ""
        elif event.key == pygame.K_ESCAPE:
            # Cancel editing
            self._feat_town_detail_editing = False
            self._feat_town_desc_buf = ""
        elif event.key == pygame.K_BACKSPACE:
            self._feat_town_desc_buf = self._feat_town_desc_buf[:-1]
        else:
            # Append typed character (if printable)
            ch = event.unicode
            if ch and ch.isprintable() and len(self._feat_town_desc_buf) < 200:
                self._feat_town_desc_buf += ch

    def _feat_do_copy_interior(self, parent_town):
        """Duplicate the selected interior as a new independent instance."""
        import copy
        interiors = self._feat_town_lists.get("interiors", [])

        # Get the source interior
        # The _feat_copy_interior_source is set from the filtered list
        # In interiors view, _feat_townlayout_cursor is the index into filtered list
        filtered_idx = getattr(self, "_feat_copy_interior_source", 0)
        filtered_list = self._feat_townlayout_list
        if filtered_idx >= len(filtered_list):
            return
        src = filtered_list[filtered_idx]
        new_item = {
            "name": f"{src['name']} (Copy)",
            "width": src["width"],
            "height": src["height"],
            "tiles": copy.deepcopy(src.get("tiles", {})),
            "parent_town": parent_town,
        }
        interiors.append(new_item)
        self._feat_townlayout_cursor = len(interiors) - 1
        self._feat_dirty = True

    def _feat_handle_town_picker_input(self, event):
        """Handle input for the town picker overlay (select parent layout).

        Supports two modes:
          - "new" (default): creates a new empty interior with the chosen parent
          - "copy": duplicates the selected interior with the chosen parent
        """
        layouts = self._feat_town_lists.get("layouts", [])
        n = len(layouts)
        if event.key == pygame.K_ESCAPE:
            self._feat_town_picker_active = False
        elif event.key == pygame.K_UP and n > 0:
            self._feat_town_picker_cursor = (
                self._feat_town_picker_cursor - 1) % n
        elif event.key == pygame.K_DOWN and n > 0:
            self._feat_town_picker_cursor = (
                self._feat_town_picker_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and n > 0:
            parent_name = layouts[self._feat_town_picker_cursor]["name"]
            mode = getattr(self, "_feat_town_picker_mode", "new")
            if mode == "copy":
                self._feat_do_copy_interior(parent_name)
            else:
                self._feat_add_townlayout(parent_town=parent_name)
            self._feat_town_picker_active = False

    def _feat_handle_townlayout_naming_input(self, event):
        """Handle text input while renaming a town layout/feature/interior."""
        if event.key == pygame.K_RETURN:
            # Confirm the name
            items = self._feat_townlayout_list
            if 0 <= self._feat_townlayout_cursor < len(items):
                new_name = self._feat_townlayout_name_buf.strip()
                if new_name:
                    items[self._feat_townlayout_cursor]["name"] = new_name
                self._feat_save_townlayouts()
            self._feat_townlayout_naming = False
            self._feat_townlayout_name_buf = ""
        elif event.key == pygame.K_ESCAPE:
            # Cancel naming
            self._feat_townlayout_naming = False
            self._feat_townlayout_name_buf = ""
        elif event.key == pygame.K_BACKSPACE:
            self._feat_townlayout_name_buf = self._feat_townlayout_name_buf[:-1]
        else:
            # Append typed character (if printable)
            ch = event.unicode
            if ch and ch.isprintable() and len(self._feat_townlayout_name_buf) < 40:
                self._feat_townlayout_name_buf += ch

    def _feat_handle_townlayout_painter_input(self, event):
        """Handle input in the town layout grid painter."""
        if self._feat_townlayout_cursor >= len(self._feat_townlayout_list):
            return
        layout = self._feat_townlayout_list[self._feat_townlayout_cursor]
        w = layout["width"]
        h = layout["height"]

        if event.key == pygame.K_ESCAPE:
            if self._feat_dirty:
                def _save_and_exit():
                    self._feat_save_townlayouts()
                    self._feat_townlayout_editing = False
                    self._feat_level = 1
                    self._feat_dirty = False
                def _discard_and_exit():
                    self._feat_townlayout_editing = False
                    self._feat_level = 1
                    self._feat_dirty = False
                self._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
            else:
                self._feat_townlayout_editing = False
                self._feat_level = 1
        elif self._is_save_shortcut(event):
            # Save (Ctrl+S / Cmd+S) — must be checked before WASD movement
            self._feat_save_townlayouts()
            self._feat_dirty = False
        elif event.key in (pygame.K_UP, pygame.K_w):
            self._feat_townlayout_cy = max(0, self._feat_townlayout_cy - 1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._feat_townlayout_cy = min(h - 1, self._feat_townlayout_cy + 1)
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._feat_townlayout_cx = max(0, self._feat_townlayout_cx - 1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._feat_townlayout_cx = min(w - 1, self._feat_townlayout_cx + 1)
        elif event.key == pygame.K_RETURN:
            # Paint current brush at cursor
            brushes = self._feat_get_townlayout_brushes()
            brush = brushes[self._feat_townlayout_brush_idx]
            pos_key = f"{self._feat_townlayout_cx},{self._feat_townlayout_cy}"
            self._feat_dirty = True
            if brush["name"] == "Eraser":
                layout["tiles"].pop(pos_key, None)
            elif "feature" in brush:
                # Composite feature brush — cursor marks top-left tile
                feat = brush["feature"]
                ftiles = feat.get("tiles", {})
                # Find the bounding box of actual tiles in the feature
                min_fc = min_fr = 9999
                for fkey in ftiles:
                    pts = fkey.split(",")
                    fc_, fr_ = int(pts[0]), int(pts[1])
                    if fc_ < min_fc:
                        min_fc = fc_
                    if fr_ < min_fr:
                        min_fr = fr_
                if not ftiles:
                    min_fc = min_fr = 0
                ox = self._feat_townlayout_cx - min_fc
                oy = self._feat_townlayout_cy - min_fr
                for fkey, fval in ftiles.items():
                    parts = fkey.split(",")
                    fc, fr = int(parts[0]), int(parts[1])
                    tx = ox + fc
                    ty = oy + fr
                    if 0 <= tx < w and 0 <= ty < h:
                        layout["tiles"][f"{tx},{ty}"] = {
                            "tile_id": fval.get("tile_id"),
                            "path": fval.get("path"),
                            "name": fval.get("name", ""),
                        }
            else:
                layout["tiles"][pos_key] = {
                    "tile_id": brush["tile_id"],
                    "path": brush.get("path"),
                    "name": brush["name"],
                }
        elif event.key in (pygame.K_TAB, pygame.K_b):
            # Cycle brush
            brushes = self._feat_get_townlayout_brushes()
            n = len(brushes)
            if event.mod & pygame.KMOD_SHIFT:
                self._feat_townlayout_brush_idx = (self._feat_townlayout_brush_idx - 1) % n
            else:
                self._feat_townlayout_brush_idx = (self._feat_townlayout_brush_idx + 1) % n
        elif event.key == pygame.K_i:
            pos_key = f"{self._feat_townlayout_cx},{self._feat_townlayout_cy}"
            if pos_key in layout["tiles"]:
                sub = self._feat_town_active_sub or "layouts"
                td = layout["tiles"][pos_key]
                # Open unified link picker for all sub-editors
                self._feat_interior_picking = True
                self._feat_interior_pick_cursor = 0
                self._feat_interior_pick_scroll = 0
                # Store context so picker knows which options to show
                self._feat_interior_pick_sub = sub
                # Build filtered interior list scoped by parent_town
                interiors = self._feat_town_lists.get("interiors", [])
                if sub == "interiors":
                    # Editing an interior — show sibling interiors
                    # (same parent_town, exclude self)
                    current_name = layout.get("name", "")
                    parent = layout.get("parent_town", "")
                    self._feat_interior_pick_list = [
                        intr for intr in interiors
                        if intr["name"] != current_name
                        and (not parent or intr.get("parent_town", "") == parent
                             or not intr.get("parent_town"))]
                else:
                    # Editing a layout — show only interiors belonging
                    # to this layout (by parent_town == layout name)
                    layout_name = layout.get("name", "")
                    self._feat_interior_pick_list = [
                        intr for intr in interiors
                        if intr.get("parent_town", "") == layout_name
                        or not intr.get("parent_town")]
                # Pre-select current link
                pick_list = self._feat_interior_pick_list
                if td.get("to_town"):
                    # "Back to Town" is index 1 for interiors
                    if sub == "interiors":
                        self._feat_interior_pick_cursor = 1
                elif td.get("to_overworld"):
                    # "Return to Overworld" is index 1 for layouts
                    if sub == "layouts":
                        self._feat_interior_pick_cursor = 1
                elif td.get("interior"):
                    current = td["interior"]
                    for i, intr in enumerate(pick_list):
                        if intr["name"] == current:
                            self._feat_interior_pick_cursor = i + 2
                            break
        elif event.key == pygame.K_x:
            # Quick-remove any link from tile under cursor
            pos_key = f"{self._feat_townlayout_cx},{self._feat_townlayout_cy}"
            td = layout["tiles"].get(pos_key)
            if td:
                changed = False
                for link_key in ("interior", "to_overworld", "to_town"):
                    if link_key in td:
                        del td[link_key]
                        changed = True
                if changed:
                    self._feat_dirty = True
        elif event.key == pygame.K_r:
            # Enter tile replace mode — source = tile under cursor (or empty)
            pos_key = f"{self._feat_townlayout_cx},{self._feat_townlayout_cy}"
            td = layout["tiles"].get(pos_key)
            self._feat_townlayout_replacing = True
            if td:
                self._feat_townlayout_replace_src_tile = td.get("tile_id")
                self._feat_townlayout_replace_src_name = td.get("name", "")
                self._feat_townlayout_replace_src_empty = False
            else:
                self._feat_townlayout_replace_src_tile = None
                self._feat_townlayout_replace_src_name = "(Empty)"
                self._feat_townlayout_replace_src_empty = True
            self._feat_townlayout_replace_dst_idx = self._feat_townlayout_brush_idx

    def _feat_handle_townlayout_replace_input(self, event):
        """Handle input for the tile replace overlay.

        Up/Down navigates the brush palette to pick a destination tile.
        Enter/Space executes the batch replace across the entire layout.
        Escape cancels replace mode.
        """
        if event.key == pygame.K_ESCAPE:
            self._feat_townlayout_replacing = False
            return

        brushes = self._feat_get_townlayout_brushes()
        n = len(brushes)

        if event.key in (pygame.K_UP, pygame.K_w):
            self._feat_townlayout_replace_dst_idx = (
                self._feat_townlayout_replace_dst_idx - 1) % n
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._feat_townlayout_replace_dst_idx = (
                self._feat_townlayout_replace_dst_idx + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            # Execute batch replace
            if self._feat_townlayout_cursor >= len(self._feat_townlayout_list):
                self._feat_townlayout_replacing = False
                return
            layout = self._feat_townlayout_list[self._feat_townlayout_cursor]
            dst_brush = brushes[self._feat_townlayout_replace_dst_idx]
            src_tile = self._feat_townlayout_replace_src_tile
            src_empty = self._feat_townlayout_replace_src_empty
            w = layout["width"]
            h = layout["height"]
            tiles = layout.get("tiles", {})
            changed = False
            if src_empty:
                # Source is empty cells — fill all empty positions with dst
                if dst_brush["name"] != "Eraser":
                    for r in range(h):
                        for c in range(w):
                            pk = f"{c},{r}"
                            if pk not in tiles:
                                tiles[pk] = {
                                    "tile_id": dst_brush["tile_id"],
                                    "path": dst_brush.get("path"),
                                    "name": dst_brush["name"],
                                }
                                changed = True
            elif dst_brush["name"] == "Eraser":
                # Replace all source tiles with empty (remove them)
                keys_to_remove = [
                    k for k, v in tiles.items()
                    if v.get("tile_id") == src_tile]
                for k in keys_to_remove:
                    del tiles[k]
                    changed = True
            else:
                # Replace all source tiles with destination tile
                for k, v in tiles.items():
                    if v.get("tile_id") == src_tile:
                        v["tile_id"] = dst_brush["tile_id"]
                        v["path"] = dst_brush.get("path")
                        v["name"] = dst_brush["name"]
                        changed = True
            if changed:
                self._feat_dirty = True
            self._feat_townlayout_replacing = False

    def _feat_handle_interior_picker_input(self, event):
        """Handle input for the unified link picker overlay.

        The picker list is:
          0 = (none)
          1 = context-dependent special option:
              - layouts:   "Return to Overworld"
              - interiors: "Back to Town"
          2.. = interior spaces (filtered)
        """
        pick_list = getattr(self, "_feat_interior_pick_list", [])
        sub = getattr(self, "_feat_interior_pick_sub", "layouts")
        n = len(pick_list) + 2  # +2 for "(none)" and special option

        if event.key == pygame.K_ESCAPE:
            self._feat_interior_picking = False
            return
        if event.key == pygame.K_UP:
            self._feat_interior_pick_cursor = (
                self._feat_interior_pick_cursor - 1) % n
            self._feat_interior_pick_scroll = (
                self._feat_adjust_scroll_generic(
                    self._feat_interior_pick_cursor,
                    self._feat_interior_pick_scroll))
        elif event.key == pygame.K_DOWN:
            self._feat_interior_pick_cursor = (
                self._feat_interior_pick_cursor + 1) % n
            self._feat_interior_pick_scroll = (
                self._feat_adjust_scroll_generic(
                    self._feat_interior_pick_cursor,
                    self._feat_interior_pick_scroll))
        elif event.key == pygame.K_RETURN:
            # Apply the selection
            layout = self._feat_townlayout_list[self._feat_townlayout_cursor]
            pos_key = f"{self._feat_townlayout_cx},{self._feat_townlayout_cy}"
            td = layout["tiles"].get(pos_key)
            if td:
                idx = self._feat_interior_pick_cursor
                # Clear all previous link types
                for lk in ("interior", "to_overworld", "to_town"):
                    td.pop(lk, None)
                if idx == 0:
                    pass  # "(none)" — links already cleared
                elif idx == 1:
                    # Special option depends on context
                    if sub == "interiors":
                        td["to_town"] = True
                    else:
                        td["to_overworld"] = True
                else:
                    td["interior"] = pick_list[idx - 2]["name"]
                self._feat_dirty = True
            self._feat_interior_picking = False

    def _feat_pxedit_open(self):
        """Open the pixel editor for the currently selected sprite."""
        gi = self._feat_gallery_cur_gi()
        if gi is None:
            return False
        entry = self._feat_gallery_list[gi]
        path = entry.get("path", "")
        if not path or path == "(procedural)":
            return False
        import os
        abs_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), path)
        if not os.path.isfile(abs_path):
            return False
        # Load image into pixel array
        import pygame
        try:
            img = pygame.image.load(abs_path).convert_alpha()
        except Exception:
            return False
        w, h = img.get_size()
        pixels = []
        for y in range(h):
            row = []
            for x in range(w):
                row.append(tuple(img.get_at((x, y))))
            pixels.append(row)
        self._feat_pxedit_pixels = pixels
        self._feat_pxedit_w = w
        self._feat_pxedit_h = h
        self._feat_pxedit_cx = w // 2
        self._feat_pxedit_cy = h // 2
        self._feat_pxedit_color_idx = 0
        self._feat_pxedit_path = abs_path
        self._feat_pxedit_undo_stack = []
        self._feat_dirty = False
        return True

    def _feat_pxedit_save(self):
        """Save the edited pixels back to the sprite file."""
        import pygame
        pixels = self._feat_pxedit_pixels
        if not pixels:
            return False
        w = self._feat_pxedit_w
        h = self._feat_pxedit_h
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            for x in range(w):
                surf.set_at((x, y), pixels[y][x])
        try:
            pygame.image.save(surf, self._feat_pxedit_path)
        except Exception:
            return False
        return True

    def _feat_gallery_cur_gi(self):
        """Return gallery_list index for the currently selected sprite."""
        sprites = self._feat_gallery_sprites
        c = self._feat_gallery_spr_cursor
        if 0 <= c < len(sprites):
            return sprites[c]
        return None

    def _feat_gallery_toggle_tag(self):
        """Toggle the currently highlighted category tag on/off."""
        gi = self._feat_gallery_cur_gi()
        if gi is None:
            return
        entry = self._feat_gallery_list[gi]
        usable = entry.get("usable_in", [])
        tag = self._feat_gallery_all_cats[self._feat_gallery_tag_cursor]
        if tag in usable:
            if tag != entry["category"]:
                usable.remove(tag)
        else:
            usable.append(tag)
            usable.sort()
        entry["usable_in"] = usable

    def _feat_gallery_duplicate(self):
        """Duplicate the currently selected sprite (file + manifest entry)."""
        import shutil
        gi = self._feat_gallery_cur_gi()
        if gi is None:
            return
        entry = self._feat_gallery_list[gi]
        src_path = entry.get("path", "")
        if not src_path or src_path == "(procedural)":
            return

        project_root = os.path.dirname(os.path.dirname(__file__))

        # Resolve absolute source path
        if src_path.startswith("src/assets/"):
            abs_src = os.path.join(project_root, src_path)
        else:
            abs_src = os.path.join(project_root, "src", "assets", src_path)
        if not os.path.isfile(abs_src):
            return

        # Generate a unique copy name and filename
        base_name = entry["name"]
        directory = os.path.dirname(abs_src)
        ext = os.path.splitext(abs_src)[1]

        copy_num = 1
        while True:
            new_name = f"{base_name}_copy{copy_num}"
            new_file = os.path.join(directory, f"{new_name}{ext}")
            if not os.path.exists(new_file):
                break
            copy_num += 1

        # Copy the sprite file
        try:
            shutil.copy2(abs_src, new_file)
        except OSError:
            return

        # Build the new path relative to project root
        new_rel_path = os.path.relpath(new_file, project_root)

        # Add to tile_manifest.json
        mpath = os.path.join(project_root, "data", "tile_manifest.json")
        try:
            with open(mpath, "r") as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return

        cat = entry["category"]
        section = manifest.get(cat, {})
        if isinstance(section, dict):
            section[new_name] = {
                "path": new_rel_path,
                "usable_in": list(entry.get("usable_in", [cat])),
            }
            # NOTE: Do NOT copy tile_id from original.
            # Duplicates must have no tile_id so the renderer loads
            # their own sprite file instead of sharing the original's
            # cached sprite.

        try:
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=2)
        except OSError:
            return

        # Add to in-memory gallery list
        new_entry = {
            "category": cat,
            "name": new_name,
            "path": new_rel_path,
            "tile_id": entry.get("tile_id"),
            "usable_in": list(entry.get("usable_in", [cat])),
            "rendering": entry.get("rendering", "sprite"),
        }
        self._feat_gallery_list.append(new_entry)
        new_gi = len(self._feat_gallery_list) - 1

        # Add to current sprite view and select the copy
        self._feat_gallery_sprites.append(new_gi)
        self._feat_gallery_spr_cursor = len(self._feat_gallery_sprites) - 1
        self._feat_gallery_spr_scroll = self._feat_adjust_scroll_generic(
            self._feat_gallery_spr_cursor, self._feat_gallery_spr_scroll)

        # Rebuild category counts
        self._feat_rebuild_gallery_cats()

        # Reload renderer sprite caches so the icon appears immediately
        self.renderer.reload_sprites()

        # Auto-enter naming mode so the player can rename immediately
        self._feat_gallery_naming = True
        self._feat_gallery_name_buf = new_name

    def _feat_gallery_rename(self, new_name):
        """Rename the currently selected gallery sprite (file + manifest)."""
        gi = self._feat_gallery_cur_gi()
        if gi is None:
            return
        entry = self._feat_gallery_list[gi]
        old_name = entry["name"]
        if new_name == old_name:
            return  # nothing to do

        project_root = os.path.dirname(os.path.dirname(__file__))
        old_path = entry.get("path", "")
        if not old_path or old_path == "(procedural)":
            return

        # Resolve absolute old path
        abs_old = os.path.join(project_root, old_path)
        if not os.path.isfile(abs_old):
            return

        # Build new file path
        directory = os.path.dirname(abs_old)
        ext = os.path.splitext(abs_old)[1]
        new_file = os.path.join(directory, f"{new_name}{ext}")

        # Don't overwrite an existing file
        if os.path.exists(new_file) and new_file != abs_old:
            return

        # Rename the sprite file
        try:
            os.rename(abs_old, new_file)
        except OSError:
            return

        new_rel_path = os.path.relpath(new_file, project_root)

        # Update tile_manifest.json
        mpath = os.path.join(project_root, "data", "tile_manifest.json")
        try:
            with open(mpath, "r") as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return

        cat = entry["category"]
        section = manifest.get(cat, {})
        if isinstance(section, dict) and old_name in section:
            section[new_name] = section.pop(old_name)
            section[new_name]["path"] = new_rel_path

        try:
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=2)
        except OSError:
            return

        # Update in-memory entry
        entry["name"] = new_name
        entry["path"] = new_rel_path

        # Reload renderer sprite caches so the icon updates immediately
        self.renderer.reload_sprites()

    def _feat_gallery_delete(self):
        """Delete the currently selected sprite (file + manifest entry).

        Only allows deleting tiles that were created by the player
        (copies), not the original base tiles that ship with the game.
        """
        gi = self._feat_gallery_cur_gi()
        if gi is None:
            return
        entry = self._feat_gallery_list[gi]
        name = entry["name"]
        cat = entry["category"]
        path = entry.get("path", "")
        if not path or path == "(procedural)":
            return

        # Safety: only allow deleting tiles whose name contains "_copy"
        # or tiles that were added by the player (not original assets)
        project_root = os.path.dirname(os.path.dirname(__file__))

        # Remove from tile_manifest.json
        mpath = os.path.join(project_root, "data", "tile_manifest.json")
        try:
            with open(mpath, "r") as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return

        section = manifest.get(cat, {})
        if isinstance(section, dict) and name in section:
            section.pop(name)

        try:
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=2)
        except OSError:
            return

        # Delete the sprite file from disk
        abs_path = os.path.join(project_root, path)
        if os.path.isfile(abs_path):
            try:
                os.remove(abs_path)
            except OSError:
                pass

        # Remove from in-memory gallery list
        self._feat_gallery_list.pop(gi)

        # Rebuild the current category sprite index list
        # (indices shifted, so regenerate from scratch)
        cat_name = ""
        if 0 <= self._feat_gallery_cat_cursor < len(self._feat_gallery_cat_list):
            cat_name = self._feat_gallery_cat_list[
                self._feat_gallery_cat_cursor]["name"]
        sprites = []
        for i, e in enumerate(self._feat_gallery_list):
            if cat_name in e.get("usable_in", []):
                sprites.append(i)
        self._feat_gallery_sprites = sprites

        # Adjust cursor
        n = len(self._feat_gallery_sprites)
        if self._feat_gallery_spr_cursor >= n:
            self._feat_gallery_spr_cursor = max(0, n - 1)
        self._feat_gallery_spr_scroll = self._feat_adjust_scroll_generic(
            self._feat_gallery_spr_cursor, self._feat_gallery_spr_scroll)

        # Rebuild category counts and reload sprites
        self._feat_rebuild_gallery_cats()
        self.renderer.reload_sprites()

    def _feat_handle_gallery_naming_input(self, event):
        """Handle text input while renaming a gallery sprite."""
        if event.key == pygame.K_RETURN:
            new_name = self._feat_gallery_name_buf.strip()
            # Sanitize: replace spaces with underscores, lowercase
            new_name = new_name.replace(" ", "_").lower()
            if new_name:
                self._feat_gallery_rename(new_name)
            self._feat_gallery_naming = False
            self._feat_gallery_name_buf = ""
        elif event.key == pygame.K_ESCAPE:
            self._feat_gallery_naming = False
            self._feat_gallery_name_buf = ""
        elif event.key == pygame.K_BACKSPACE:
            self._feat_gallery_name_buf = self._feat_gallery_name_buf[:-1]
        else:
            ch = event.unicode
            if ch and ch.isprintable() and len(self._feat_gallery_name_buf) < 40:
                self._feat_gallery_name_buf += ch

    # ══════════════════════════════════════════════════════════
    # ── Generic editor helpers (shared across all editors) ─────
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _feat_next_editable_generic(fields, start):
        """Find next editable field index from start in any field list."""
        n = len(fields)
        if n == 0:
            return 0
        idx = start % n
        for _ in range(n):
            entry = fields[idx]
            if len(entry) > 4 and entry[4] and entry[3] != "section":
                return idx
            idx = (idx + 1) % n
        return start % n

    @staticmethod
    def _feat_adjust_scroll_generic(cursor, scroll, max_visible=14):
        """Generic scroll adjustment. Returns new scroll value."""
        if cursor < scroll:
            return cursor
        if cursor >= scroll + max_visible:
            return cursor - max_visible + 1
        return scroll

    @staticmethod
    def _feat_adjust_field_scroll_generic(field_idx, scroll):
        """Generic field scroll adjustment."""
        row_h = 38
        panel_h = 500
        max_visible = panel_h // row_h
        if field_idx < scroll:
            return field_idx
        if field_idx >= scroll + max_visible:
            return field_idx - max_visible + 1
        return scroll

    # ── Module selection ──────────────────────────────────────

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
            ["DETAILS", "", "", "section", False],
            ["Name", "name", "", "text", True],
            ["Author", "author", "", "text", True],
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

        # 2) Settings (only innkeeper quests toggle remains here;
        #    world size / season / time-of-day moved to Overview Map)
        innkeeper_quests = manifest.get("progression", {}).get(
            "innkeeper_quests", False)
        sections.append({
            "label": "Settings",
            "icon": ">",
            "fields": [
                ["Towns", "num_towns",
                 str(mod_settings["num_towns"]), "int", False],
                ["Quests", "num_quests",
                 str(mod_settings["num_quests"]), "int", False],
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
            # Resolve custom layout display name
            tc_layout = tc.get("layout", "")
            layout_display = tc_layout if tc_layout else "Procedural"
            # Build fields
            fields = [
                ["Name", f"town_{i}_name", tname, "text", True],
                ["Description", f"town_{i}_desc",
                 town.get("description", ""), "text", True],
                ["Layout", f"town_{i}_layout", layout_display,
                 "choice", True],
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
        _DUNGEON_SIZE_NAMES = {"small": "Small", "medium": "Medium",
                               "large": "Large"}
        for i, dung in enumerate(dungeons):
            dname = dung.get("name", f"Dungeon {i+1}")
            n_levels = len(dung.get("levels", []))
            td_raw = dung.get("torch_density", "medium")
            td_display = _TORCH_DENSITY_NAMES.get(td_raw, "Medium")
            sz_raw = dung.get("size", "medium")
            sz_display = _DUNGEON_SIZE_NAMES.get(sz_raw, "Medium")
            re_display = "Yes" if dung.get(
                "random_encounters", True) else "No"
            dungeon_children.append({
                "label": dname,
                "icon": "D",
                "dung_idx": i,
                "fields": [
                    ["Name", f"dung_{i}_name", dname, "text", True],
                    ["Description", f"dung_{i}_desc",
                     dung.get("description", ""), "text", True],
                    ["Size", f"dung_{i}_dsize", sz_display, "choice", True],
                    ["Torch Density", f"dung_{i}_tdensity",
                     td_display, "choice", True],
                    ["Random Encounters", f"dung_{i}_randenc",
                     re_display, "choice", True],
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

        # 6) Overview Map folder — sub-sections for map editing
        #    (Load unique tiles first — they live inside Overview Map now)
        unique_tiles_data = manifest.get("unique_tiles", {})
        self.module_edit_unique_tiles = [
            {"id": tid, **tdef}
            for tid, tdef in unique_tiles_data.items()
        ]
        overworld_cfg = manifest.get("world", {}).get(
            "overworld_config", {})
        omap_children = self._build_overview_map_sections(
            overworld_cfg, manifest, mod_settings)
        sections.append({
            "label": "Overview Map",
            "icon": "F",
            "folder": "overview_map",
            "children": omap_children,
            "subtitle": overworld_cfg.get("type", "Procedural"),
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
        self.module_edit_active_enc = -1
        self._editing_level_settings = False
        # Unique tiles state (list already built above for section 6)
        self.module_edit_in_unique_tiles = False
        self.module_edit_active_utile = -1
        self.module_edit_utile_preview = False
        self._battle_screen_active = False
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

        # ── Level sections drill into level sub-browser ──
        if sec.get("icon") == "L" and sec.get("level_idx") is not None:
            dung_idx = self.module_edit_active_dung
            level_idx = sec["level_idx"]
            self._enter_level_encounters(dung_idx, level_idx)
            return

        # ── Encounter sections drill into encounter fields ──
        if sec.get("icon") == "E" and sec.get("enc_idx") is not None:
            self._enter_encounter_fields(sec["enc_idx"])
            return

        # ── Monster sections drill into monster choice field ──
        if sec.get("icon") == "M" and sec.get("mon_idx") is not None:
            self._editing_level_settings = False
            # Just enter the field editor for this monster's choice
            pass  # fall through to normal field editing below

        # ── Battle Screen section drills into battle screen painter ──
        if sec.get("is_battle_screen"):
            self._enter_battle_screen_editor(sec["enc_idx"])
            return

        # ── Individual unique tile drills into its field editor ──
        if sec.get("utile_idx") is not None:
            self._enter_single_utile_fields(sec["utile_idx"])
            return

        # ── Level-settings section flag ──
        if sec.get("is_level_settings"):
            self._editing_level_settings = True

        # ── Properties and other sections: flat field editor ──
        self.module_edit_fields = sec["fields"]
        self.module_edit_field = 0
        self.module_edit_scroll = 0
        self.module_edit_level = 1
        self._feat_dirty = False
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
        """Drill into a dungeon level — show settings + encounter list."""
        self.module_edit_active_level = level_idx
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            return
        level = levels[level_idx]

        # Push current sections onto nav stack
        self.module_edit_nav_stack.append((
            self.module_edit_sections,
            self.module_edit_section_cursor,
            self.module_edit_section_scroll,
            getattr(self, "_module_edit_folder_label", ""),
        ))
        self._module_edit_folder_label = level.get(
            "name", f"Floor {level_idx + 1}")

        self._rebuild_level_sub_sections(dung_idx, level_idx)

    def _rebuild_level_sub_sections(self, dung_idx, level_idx):
        """Build the sub-section list for a dungeon level."""
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            return
        level = levels[level_idx]
        encounters = level.get("encounters", [])

        # Inheritable settings display maps
        _td_map = {"high": "High", "medium": "Medium", "low": "Low",
                    "inherit": "Inherit"}
        _sz_map = {"small": "Small", "medium": "Medium", "large": "Large",
                   "inherit": "Inherit"}
        _re_map = {True: "Yes", False: "No", "inherit": "Inherit"}

        # Build settings fields for the "Settings" section
        settings_fields = []
        settings_fields.append(["Level Name", f"lvl_{level_idx}_name",
                                level.get("name", f"Floor {level_idx + 1}"),
                                "text", True])
        td_raw = level.get("torch_density", "inherit")
        settings_fields.append(["Torch Density",
                                f"lvl_{level_idx}_ftdensity",
                                _td_map.get(td_raw, "Inherit"),
                                "choice", True])
        sz_raw = level.get("size", "inherit")
        settings_fields.append(["Size",
                                f"lvl_{level_idx}_fdsize",
                                _sz_map.get(sz_raw, "Inherit"),
                                "choice", True])
        re_raw = level.get("random_encounters", "inherit")
        settings_fields.append(["Random Encounters",
                                f"lvl_{level_idx}_frandenc",
                                _re_map.get(re_raw, "Inherit"),
                                "choice", True])

        sub_sections = []
        # 1) Settings section
        sub_sections.append({
            "label": "Settings",
            "icon": ">",
            "fields": settings_fields,
            "is_level_settings": True,
        })

        # 2) One section per encounter
        for ei, enc in enumerate(encounters):
            monsters = _normalize_encounter(enc)
            # Build a compact summary like "Orc x2, Skeleton x1"
            from collections import Counter
            counts = Counter(monsters)
            parts = [f"{m} x{c}" if c > 1 else m
                     for m, c in counts.items()]
            subtitle = ", ".join(parts) if parts else "Empty"
            sub_sections.append({
                "label": f"Encounter {ei + 1}",
                "icon": "E",
                "enc_idx": ei,
                "subtitle": subtitle,
            })

        # 3) [+] Add Encounter action
        sub_sections.append({
            "label": "[+] Add Encounter",
            "icon": "+",
            "fields": [],
            "action": "add_encounter",
        })

        self.module_edit_sections = sub_sections
        self.module_edit_section_cursor = 0
        self.module_edit_section_scroll = 0
        self.module_edit_level = 0

    def _enter_encounter_fields(self, enc_idx):
        """Drill into a single encounter — show monster list."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            return
        level = levels[level_idx]
        encounters = level.get("encounters", [])
        if enc_idx < 0 or enc_idx >= len(encounters):
            return

        self.module_edit_active_enc = enc_idx

        # Normalize legacy format to monsters list, preserving extra keys
        enc = encounters[enc_idx]
        monsters = _normalize_encounter(enc)
        # Update in place — keep battle_screen and other extra keys
        enc.pop("monster", None)
        enc.pop("count", None)
        enc["monsters"] = monsters
        encounters[enc_idx] = enc

        # Push current sections onto nav stack
        self.module_edit_nav_stack.append((
            self.module_edit_sections,
            self.module_edit_section_cursor,
            self.module_edit_section_scroll,
            getattr(self, "_module_edit_folder_label", ""),
        ))
        self._module_edit_folder_label = f"Encounter {enc_idx + 1}"

        self._rebuild_encounter_monster_sections(enc_idx)

    def _rebuild_encounter_monster_sections(self, enc_idx):
        """Build sections showing each monster in an encounter."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            return
        enc = levels[level_idx]["encounters"][enc_idx]
        monsters = enc.get("monsters", ["Giant Rat"])

        sub_sections = []
        for mi, mon_name in enumerate(monsters):
            sub_sections.append({
                "label": mon_name,
                "icon": "M",
                "mon_idx": mi,
                "enc_idx": enc_idx,
                "fields": [
                    ["Monster", f"enc_{enc_idx}_m_{mi}_mon",
                     mon_name, "choice", True],
                ],
            })

        # Battle Screen section
        bs = enc.get("battle_screen") or {}
        bs_style = bs.get("style", "dungeon")
        bs_music = bs.get("music", "Default")
        n_obs = len(bs.get("obstacles", []))
        n_painted = len(bs.get("painted", {}))
        bs_subtitle = bs_style.title()
        if n_obs or n_painted:
            bs_subtitle += f" ({n_obs} obs, {n_painted} tiles)"
        sub_sections.append({
            "label": "Battle Screen",
            "icon": "B",
            "enc_idx": enc_idx,
            "is_battle_screen": True,
            "subtitle": bs_subtitle,
        })

        # [+] Add Monster action
        sub_sections.append({
            "label": "[+] Add Monster",
            "icon": "+",
            "fields": [],
            "action": "add_monster",
        })

        self.module_edit_sections = sub_sections
        self.module_edit_section_cursor = min(
            getattr(self, "module_edit_section_cursor", 0),
            max(0, len(sub_sections) - 1))
        self.module_edit_section_scroll = 0
        self.module_edit_level = 0

    def _leave_section_fields(self):
        """Go back from field editing to the section browser."""
        # Persist any in-progress buffer back to the field
        if self.module_edit_fields:
            entry = self.module_edit_fields[self.module_edit_field]
            entry[2] = self.module_edit_buffer

        # If we were editing a monster inside an encounter, save it
        # and return to the encounter monster browser (keep active_enc)
        if getattr(self, "module_edit_active_enc", -1) >= 0:
            self._save_monster_field()
            self.module_edit_level = 0
            return

        # If we were editing level settings, save them back
        if getattr(self, "_editing_level_settings", False):
            self._save_level_settings_fields()
            self._editing_level_settings = False
            self.module_edit_level = 0
            return

        # If we were editing a unique tile, save back to in-memory list
        # and rebuild the children so tile labels update
        if self.module_edit_in_unique_tiles:
            self._save_single_utile_fields()
            self.module_edit_in_unique_tiles = False
            self.module_edit_active_utile = -1
            # Rebuild children list to reflect any name changes
            if (self._module_edit_folder_label == "Unique Tiles"
                    and self.module_edit_nav_stack):
                self._rebuild_unique_tiles_children()

        self.module_edit_level = 0

    def _save_level_settings_fields(self):
        """Persist level settings field edits back to in-memory level data."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            return
        level = levels[level_idx]

        for entry in self.module_edit_fields:
            if entry[1] == f"lvl_{level_idx}_name":
                level["name"] = entry[2]
                # Update the breadcrumb label to reflect name changes
                self._module_edit_folder_label = entry[2]
            elif entry[1] == f"lvl_{level_idx}_ftdensity":
                v = entry[2]
                level["torch_density"] = (
                    "inherit" if v == "Inherit" else v.lower())
            elif entry[1] == f"lvl_{level_idx}_fdsize":
                v = entry[2]
                level["size"] = (
                    "inherit" if v == "Inherit" else v.lower())
            elif entry[1] == f"lvl_{level_idx}_frandenc":
                v = entry[2]
                if v == "Inherit":
                    level["random_encounters"] = "inherit"
                else:
                    level["random_encounters"] = (v == "Yes")

        # Rebuild sections so labels reflect any changes
        self._rebuild_level_sub_sections(dung_idx, level_idx)

    def _save_single_encounter_fields(self):
        """Persist a single encounter's field edits back to level data.

        In the new format, the encounter is ``{"monsters": [...]}``.
        Each field key looks like ``enc_{enc_idx}_m_{mon_idx}_mon``.
        """
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        enc_idx = getattr(self, "module_edit_active_enc", -1)
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            return
        level = levels[level_idx]
        encounters = level.get("encounters", [])
        if enc_idx < 0 or enc_idx >= len(encounters):
            return

        # Read monster names back from the field list stored on sections
        # Keys look like "enc_{enc_idx}_m_{mi}_mon"
        enc = encounters[enc_idx]
        monsters = list(enc.get("monsters", ["Giant Rat"]))
        for entry in self.module_edit_fields:
            key = entry[1]
            prefix = f"enc_{enc_idx}_m_"
            if key.startswith(prefix) and key.endswith("_mon"):
                try:
                    mi = int(key[len(prefix):-4])  # strip prefix and "_mon"
                    if 0 <= mi < len(monsters):
                        monsters[mi] = entry[2]
                except (ValueError, IndexError):
                    pass
        enc["monsters"] = monsters

    def _leave_dungeon_sub(self):
        """Pop the nav stack to return from sub-sections or folder."""
        was_in_encounter = getattr(self, "module_edit_active_enc", -1) >= 0
        was_in_level = self.module_edit_active_level >= 0

        if self.module_edit_nav_stack:
            prev = self.module_edit_nav_stack.pop()
            self.module_edit_sections = prev[0]
            self.module_edit_section_cursor = prev[1]
            self.module_edit_section_scroll = prev[2]
            self._module_edit_folder_label = (
                prev[3] if len(prev) > 3 else "")
        else:
            self._module_edit_folder_label = ""

        if was_in_encounter:
            # Returning from encounter monster browser to level sub-browser
            self.module_edit_active_enc = -1
            dung_idx = self.module_edit_active_dung
            level_idx = self.module_edit_active_level
            if dung_idx >= 0 and level_idx >= 0:
                self._rebuild_level_sub_sections(dung_idx, level_idx)
                self.module_edit_section_cursor = prev[1]
                self.module_edit_section_scroll = prev[2]
        elif was_in_level:
            # Returning from level sub-browser to dungeon sub-browser
            dung_idx = self.module_edit_active_dung
            self.module_edit_active_level = -1
            self.module_edit_active_enc = -1
            if dung_idx >= 0:
                self._rebuild_dungeon_sub_sections(dung_idx)
                self.module_edit_section_cursor = prev[1]
                self.module_edit_section_scroll = prev[2]
        else:
            # Returning from dungeon sub-browser to top-level
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
            "encounters": [],
            "random_encounters": "inherit",
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
        # Add new encounter to data (new format)
        levels[level_idx].setdefault("encounters", []).append(
            {"monsters": ["Giant Rat"]})
        # Rebuild the level sub-sections
        self._rebuild_level_sub_sections(dung_idx, level_idx)
        # Move cursor to the newly added encounter (second-to-last item)
        self.module_edit_section_cursor = max(
            0, len(self.module_edit_sections) - 2)
        self._adjust_section_scroll()

    def _remove_encounter_from_level(self, enc_idx):
        """Remove the specified encounter from the level."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        if dung_idx < 0 or level_idx < 0:
            return
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx >= len(levels):
            return
        level = levels[level_idx]
        encounters = level.get("encounters", [])
        if 0 <= enc_idx < len(encounters):
            encounters.pop(enc_idx)
            level["encounters"] = encounters
        # Rebuild the level sub-sections
        self._rebuild_level_sub_sections(dung_idx, level_idx)
        # Clamp cursor
        n = len(self.module_edit_sections)
        if self.module_edit_section_cursor >= n:
            self.module_edit_section_cursor = max(0, n - 1)
        self._adjust_section_scroll()

    def _save_monster_field(self):
        """Save the edited monster name back to encounter data and rebuild."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        enc_idx = getattr(self, "module_edit_active_enc", -1)
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            return
        encounters = levels[level_idx].get("encounters", [])
        if enc_idx < 0 or enc_idx >= len(encounters):
            return
        enc = encounters[enc_idx]
        monsters = enc.get("monsters", ["Giant Rat"])

        # Find which monster was edited from the field key
        # Keys look like "enc_{enc_idx}_m_{mi}_mon"
        for entry in self.module_edit_fields:
            key = entry[1]
            prefix = f"enc_{enc_idx}_m_"
            if key.startswith(prefix) and key.endswith("_mon"):
                try:
                    mi = int(key[len(prefix):-4])  # strip prefix and "_mon"
                    if 0 <= mi < len(monsters):
                        monsters[mi] = entry[2]
                except (ValueError, IndexError):
                    pass
        enc["monsters"] = monsters
        # Rebuild the monster sections so labels update
        self._rebuild_encounter_monster_sections(enc_idx)

    def _add_monster_to_encounter(self):
        """Add a monster to the active encounter's monster list."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        enc_idx = getattr(self, "module_edit_active_enc", -1)
        if dung_idx < 0 or level_idx < 0 or enc_idx < 0:
            return
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx >= len(levels):
            return
        encounters = levels[level_idx].get("encounters", [])
        if enc_idx >= len(encounters):
            return
        enc = encounters[enc_idx]
        monsters = enc.get("monsters", ["Giant Rat"])
        monsters.append("Giant Rat")
        enc["monsters"] = monsters
        # Rebuild monster sections
        self._rebuild_encounter_monster_sections(enc_idx)
        # Move cursor to the newly added monster (second-to-last)
        self.module_edit_section_cursor = max(
            0, len(self.module_edit_sections) - 2)
        self._adjust_section_scroll()

    def _remove_monster_from_encounter(self, mon_idx):
        """Remove a monster from the active encounter's monster list."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        enc_idx = getattr(self, "module_edit_active_enc", -1)
        if dung_idx < 0 or level_idx < 0 or enc_idx < 0:
            return
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx >= len(levels):
            return
        encounters = levels[level_idx].get("encounters", [])
        if enc_idx >= len(encounters):
            return
        enc = encounters[enc_idx]
        monsters = enc.get("monsters", ["Giant Rat"])
        if len(monsters) <= 1:
            return  # Keep at least one monster
        if 0 <= mon_idx < len(monsters):
            monsters.pop(mon_idx)
            enc["monsters"] = monsters
        # Rebuild monster sections
        self._rebuild_encounter_monster_sections(enc_idx)
        # Clamp cursor
        n = len(self.module_edit_sections)
        if self.module_edit_section_cursor >= n:
            self.module_edit_section_cursor = max(0, n - 1)
        self._adjust_section_scroll()

    # ── Battle Screen editor ─────────────────────────────────────

    # Arena style choices for the battle screen
    _BATTLE_STYLES = ["dungeon", "outdoor"]

    # Music override choices
    _BATTLE_MUSIC = ["Default", "Standard", "Dark & Moody", "Quiet",
                     "Twin Peaks", "Epic Fantasy"]

    # Obstacle palette for painting obstacles on the battle screen
    _BATTLE_OBSTACLE_TYPES = [
        "eraser", "tree", "rock", "boulder", "cactus", "pillar", "rubble",
    ]

    def _enter_battle_screen_editor(self, enc_idx):
        """Enter the battle screen painter for an encounter."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            return
        enc = levels[level_idx]["encounters"][enc_idx]
        bs = enc.get("battle_screen") or {}

        self._battle_screen_active = True
        self._battle_screen_enc_idx = enc_idx
        self._battle_screen_style_idx = max(
            0, self._BATTLE_STYLES.index(bs.get("style", "dungeon"))
            if bs.get("style", "dungeon") in self._BATTLE_STYLES else 0)
        self._battle_screen_music_idx = max(
            0, self._BATTLE_MUSIC.index(bs.get("music", "Default"))
            if bs.get("music", "Default") in self._BATTLE_MUSIC else 0)

        # Load obstacle placements: list of {"type", "col", "row"}
        self._battle_screen_obstacles = {}
        for obs in bs.get("obstacles", []):
            c, r = obs.get("col", 0), obs.get("row", 0)
            self._battle_screen_obstacles[(c, r)] = obs.get("type", "rock")

        # Load painted tiles: "col,row" -> sprite_path
        self._battle_screen_painted = {}
        for pos_key, gfx in bs.get("painted", {}).items():
            try:
                c, r = pos_key.split(",")
                self._battle_screen_painted[(int(c), int(r))] = gfx
            except (ValueError, AttributeError):
                pass

        # Editor cursor and brush
        self._battle_cursor_col = 9
        self._battle_cursor_row = 10
        self._battle_brush_idx = 0  # index into _BATTLE_OBSTACLE_TYPES
        self._battle_mode = "obstacle"  # "obstacle", "tile", "settings"
        self._battle_tile_brush_idx = 0  # index into examine brushes
        self._battle_settings_cursor = 0  # 0=style, 1=music
        self._feat_dirty = False

    def _leave_battle_screen_editor(self):
        """Exit the battle screen painter and persist data."""
        dung_idx = self.module_edit_active_dung
        level_idx = self.module_edit_active_level
        enc_idx = self._battle_screen_enc_idx
        levels = self.module_edit_dungeon_levels.get(dung_idx, [])
        if level_idx < 0 or level_idx >= len(levels):
            self._battle_screen_active = False
            return
        enc = levels[level_idx]["encounters"][enc_idx]

        # Build battle_screen dict
        style = self._BATTLE_STYLES[self._battle_screen_style_idx]
        music = self._BATTLE_MUSIC[self._battle_screen_music_idx]
        obstacles = []
        for (c, r), otype in self._battle_screen_obstacles.items():
            obstacles.append({"type": otype, "col": c, "row": r})
        painted = {}
        for (c, r), gfx in self._battle_screen_painted.items():
            painted[f"{c},{r}"] = gfx

        # Only store if non-default
        if style != "dungeon" or music != "Default" or obstacles or painted:
            enc["battle_screen"] = {
                "style": style,
                "music": music,
                "obstacles": obstacles,
                "painted": painted,
            }
        else:
            enc.pop("battle_screen", None)

        self._battle_screen_active = False
        # Rebuild encounter sections to update subtitle
        self._rebuild_encounter_monster_sections(enc_idx)

    def _handle_battle_screen_input(self, event):
        """Handle input in the battle screen painter."""
        if event.type != pygame.KEYDOWN:
            return

        # Intercept input when unsaved-changes dialog is showing
        if self._unsaved_dialog_active:
            self._handle_unsaved_dialog_input(event)
            return

        COLS, ROWS = 18, 21

        if self._battle_mode == "settings":
            self._handle_battle_settings_input(event)
            return

        # Movement — arrow keys
        if event.key in (pygame.K_UP, pygame.K_w):
            if self._battle_cursor_row > 1:
                self._battle_cursor_row -= 1
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            if self._battle_cursor_row < ROWS - 2:
                self._battle_cursor_row += 1
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            if self._battle_cursor_col > 1:
                self._battle_cursor_col -= 1
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            if self._battle_cursor_col < COLS - 2:
                self._battle_cursor_col += 1

        # Mode switch — I cycles obstacle/tile, S goes to settings
        elif event.key == pygame.K_i:
            if self._battle_mode == "obstacle":
                self._battle_mode = "tile"
            else:
                self._battle_mode = "obstacle"
        elif event.key == pygame.K_o:
            self._battle_mode = "settings"

        # Paint — Enter
        elif event.key == pygame.K_RETURN:
            pos = (self._battle_cursor_col, self._battle_cursor_row)
            self._feat_dirty = True
            if self._battle_mode == "obstacle":
                brush = self._BATTLE_OBSTACLE_TYPES[self._battle_brush_idx]
                if brush == "eraser":
                    self._battle_screen_obstacles.pop(pos, None)
                else:
                    self._battle_screen_obstacles[pos] = brush
            else:
                brush = self._get_examine_brushes()[self._battle_tile_brush_idx]
                if brush == "eraser":
                    self._battle_screen_painted.pop(pos, None)
                else:
                    self._battle_screen_painted[pos] = brush

        # Cycle brush — Tab / B
        elif event.key in (pygame.K_TAB, pygame.K_b):
            if self._battle_mode == "obstacle":
                n = len(self._BATTLE_OBSTACLE_TYPES)
                if event.mod & pygame.KMOD_SHIFT:
                    self._battle_brush_idx = (
                        self._battle_brush_idx - 1) % n
                else:
                    self._battle_brush_idx = (
                        self._battle_brush_idx + 1) % n
            else:
                n = len(self._get_examine_brushes())
                if event.mod & pygame.KMOD_SHIFT:
                    self._battle_tile_brush_idx = (
                        self._battle_tile_brush_idx - 1) % n
                else:
                    self._battle_tile_brush_idx = (
                        self._battle_tile_brush_idx + 1) % n

        # Exit
        elif event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            if self._feat_dirty:
                def _save_and_exit():
                    self._leave_battle_screen_editor()
                    self._feat_dirty = False
                def _discard_and_exit():
                    self._battle_screen_active = False
                    self._feat_dirty = False
                self._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
            else:
                self._leave_battle_screen_editor()

    def _handle_battle_settings_input(self, event):
        """Handle input on the battle screen settings sub-page."""
        if event.key == pygame.K_UP:
            self._battle_settings_cursor = max(
                0, self._battle_settings_cursor - 1)
        elif event.key == pygame.K_DOWN:
            self._battle_settings_cursor = min(
                1, self._battle_settings_cursor + 1)
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            delta = 1 if event.key == pygame.K_RIGHT else -1
            if self._battle_settings_cursor == 0:
                n = len(self._BATTLE_STYLES)
                self._battle_screen_style_idx = (
                    self._battle_screen_style_idx + delta) % n
            else:
                n = len(self._BATTLE_MUSIC)
                self._battle_screen_music_idx = (
                    self._battle_screen_music_idx + delta) % n
        elif event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE,
                           pygame.K_o):
            self._battle_mode = "obstacle"

    def _get_battle_screen_preview_data(self):
        """Return a dict describing the current battle screen editor state."""
        if not getattr(self, "_battle_screen_active", False):
            return None
        style = self._BATTLE_STYLES[self._battle_screen_style_idx]
        music = self._BATTLE_MUSIC[self._battle_screen_music_idx]
        if self._battle_mode == "obstacle":
            brush = self._BATTLE_OBSTACLE_TYPES[self._battle_brush_idx]
        elif self._battle_mode == "tile":
            brush = self._get_examine_brushes()[self._battle_tile_brush_idx]
        else:
            brush = None
        return {
            "style": style,
            "music": music,
            "obstacles": self._battle_screen_obstacles,
            "painted": self._battle_screen_painted,
            "cursor_col": self._battle_cursor_col,
            "cursor_row": self._battle_cursor_row,
            "brush": brush,
            "mode": self._battle_mode,
            "settings_cursor": self._battle_settings_cursor,
        }

    # ── Unique Tiles editing ─────────────────────────────────────

    # Base tile choice list for the editor
    _UTILE_BASE_TILES = [
        "grass", "forest", "sand", "path", "mountain",
        "dungeon_floor", "floor",
    ]

    # Tile graphic choices — built dynamically from the manifest.
    # "none" means invisible (text-only discovery).
    _UTILE_TILE_GRAPHICS = None  # built lazily

    @classmethod
    def _get_utile_tile_graphics(cls):
        """Build tile graphic choices from the manifest."""
        if cls._UTILE_TILE_GRAPHICS is not None:
            return cls._UTILE_TILE_GRAPHICS
        import json, os
        choices = ["none"]
        try:
            mpath = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "tile_manifest.json")
            with open(mpath) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            manifest = {}
        seen = set()
        for cat in ("overworld", "town", "dungeon",
                     "unique_tiles", "objects"):
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            for name, entry in sorted(section.items()):
                if not (isinstance(entry, dict) and "path" in entry):
                    continue
                p = entry["path"]
                # Convert to assets-relative path
                if p.startswith("src/assets/"):
                    p = p[len("src/assets/"):]
                if p not in seen:
                    seen.add(p)
                    choices.append(p)
        cls._UTILE_TILE_GRAPHICS = choices
        return choices

    def _in_unique_tiles_folder(self):
        """Return True if the section browser is inside the Unique Tiles folder."""
        return (self._module_edit_folder_label == "Unique Tiles"
                and self.module_edit_nav_stack
                and self.module_edit_level == 0)

    def _build_utile_child(self, idx, tid, tdef):
        """Build a single child section dict for a unique tile."""
        tname = tdef.get("name", tid)
        # Resolve tile graphic for display — None/empty → "none"
        raw_tile = tdef.get("tile") or "none"
        fields = [
            ["ID", f"utile_{idx}_id",
             tid, "text", True],
            ["Name", f"utile_{idx}_name",
             tname, "text", True],
            ["Description", f"utile_{idx}_desc",
             tdef.get("description", ""), "text", True],
            ["Tile Graphic", f"utile_{idx}_tilegfx",
             raw_tile, "choice", True],
            ["Base Tile", f"utile_{idx}_basetile",
             tdef.get("base_tile", "grass"), "choice", True],
            [">> Examine Screen Preview",
             f"utile_{idx}_examine", "", "action", True],
        ]
        return {
            "label": tname,
            "icon": "U",
            "utile_idx": idx,
            "fields": fields,
        }

    # ── Overview Map sub-section builders ──────────────────────────

    def _build_overview_map_sections(self, overworld_cfg, manifest,
                                      mod_settings=None):
        """Build the child section list for the Overview Map folder.

        Returns four sub-sections:
        1) Settings   – world size, season, time of day, map type,
                        initial build
        2) Map Layout – placeholder for the editable tile grid
        3) Unique Tiles – unique tile placements on the overview map
        4) Interior Map Locations – placeable unique locations
        """
        if mod_settings is None:
            mod_settings = {}

        # ── 1) Settings ──
        #    World Size / Season / Time of Day come from the module's
        #    settings (previously shown at top-level Settings section).
        #    Map Type and Initial Build are overview-map-specific.
        world_size = mod_settings.get("world_size", "Medium")
        season = mod_settings.get("season", "Summer")
        time_of_day = mod_settings.get("time_of_day", "Noon")
        map_type = overworld_cfg.get("type", "Procedural")
        initial_build = overworld_cfg.get(
            "initial_build", "Random")

        settings_fields = [
            ["World Size", "omap_world_size", world_size,
             "choice", True],
            ["Season", "omap_season", season, "choice", True],
            ["Time of Day", "omap_time_of_day", time_of_day,
             "choice", True],
            ["Map Type", "omap_type", map_type, "choice", True],
            ["Initial Build", "omap_initial_build",
             initial_build, "choice", True],
        ]
        settings_sec = {
            "label": "Settings",
            "icon": ">",
            "fields": settings_fields,
        }

        # ── 2) Map Layout ──
        map_layout_sec = {
            "label": "Map Layout",
            "icon": "G",
            "fields": [
                ["— Editable Tiles —", "_omap_layout_header",
                 "", "section", False],
            ],
            "subtitle": "editable tiles",
        }

        # ── 3) Unique Tiles (moved from top-level into Overview Map) ──
        utile_children = self._build_unique_tiles_sections()
        n_utiles = len(self.module_edit_unique_tiles)
        unique_tiles_sec = {
            "label": "Unique Tiles",
            "icon": "F",
            "folder": "unique_tiles",
            "children": utile_children,
            "subtitle": (
                f"{n_utiles} tile{'s' if n_utiles != 1 else ''}"
                if n_utiles > 0 else "no tiles"),
        }

        # ── 4) Interior Map Locations ──
        interior_locs = overworld_cfg.get("interior_locations", [])
        n_locs = len(interior_locs)
        interior_sec = {
            "label": "Interior Map Locations",
            "icon": "I",
            "fields": [
                ["— Placeable Locations —",
                 "_omap_intlocs_header", "", "section", False],
            ],
            "subtitle": (
                f"{n_locs} location{'s' if n_locs != 1 else ''}"
                if n_locs else "none"),
        }

        return [settings_sec, map_layout_sec,
                unique_tiles_sec, interior_sec]

    def _in_overview_map_folder(self):
        """Return True if the section browser is inside the Overview Map folder."""
        return (self._module_edit_folder_label == "Overview Map"
                and self.module_edit_nav_stack
                and self.module_edit_level == 0)

    def _build_unique_tiles_sections(self):
        """Build the full section list for the Unique Tiles folder:
        one child per tile, plus a [+] Add Tile action at the end."""
        children = []
        for i, utile in enumerate(self.module_edit_unique_tiles):
            tid = utile.get("id", f"tile_{i}")
            children.append(self._build_utile_child(i, tid, utile))
        children.append({
            "label": "[+] Add Tile",
            "icon": "+",
            "fields": [],
            "action": "add_tile",
        })
        return children

    def _rebuild_unique_tiles_children(self):
        """Rebuild the children list in the Unique Tiles folder from
        the in-memory tile list and refresh the section browser."""
        children = self._build_unique_tiles_sections()
        self.module_edit_sections = children
        n_tiles = len(self.module_edit_unique_tiles)
        self.module_edit_section_cursor = min(
            self.module_edit_section_cursor,
            max(0, len(children) - 1))
        self._adjust_section_scroll()
        # Also update the parent folder's subtitle in the nav stack
        if self.module_edit_nav_stack:
            parent_sections = self.module_edit_nav_stack[-1][0]
            for sec in parent_sections:
                if sec.get("folder") == "unique_tiles":
                    sec["children"] = children
                    sec["subtitle"] = (
                        f"{n_tiles} tile{'s' if n_tiles != 1 else ''}"
                        if n_tiles > 0 else "no tiles")
                    break

    def _enter_single_utile_fields(self, utile_idx):
        """Drill into a single unique tile's fields for editing."""
        self.module_edit_in_unique_tiles = True
        self.module_edit_active_utile = utile_idx
        sec = self.module_edit_sections[self.module_edit_section_cursor]
        self.module_edit_fields = sec["fields"]
        self.module_edit_field = 0
        self.module_edit_scroll = 0
        self.module_edit_level = 1
        self.module_edit_field = self._next_editable_field(0)
        if self.module_edit_fields:
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]

    def _save_single_utile_fields(self):
        """Persist the current tile's field edits back to in-memory list."""
        idx = self.module_edit_active_utile
        if idx < 0 or idx >= len(self.module_edit_unique_tiles):
            return
        vals = {}
        for entry in self.module_edit_fields:
            k = entry[1]
            prefix = f"utile_{idx}_"
            if k.startswith(prefix):
                suffix = k[len(prefix):]
                vals[suffix] = entry[2]
        utile = self.module_edit_unique_tiles[idx]
        utile["id"] = vals.get("id", utile.get("id", ""))
        utile["name"] = vals.get("name", utile.get("name", ""))
        utile["description"] = vals.get("desc", utile.get("description", ""))
        # Tile graphic: "none" means no sprite (invisible)
        gfx = vals.get("tilegfx", "none")
        utile["tile"] = None if gfx == "none" else gfx
        utile["base_tile"] = vals.get("basetile", utile.get("base_tile", "grass"))

    def _add_unique_tile(self):
        """Add a new unique tile and refresh the tile list browser."""
        n = len(self.module_edit_unique_tiles)
        self.module_edit_unique_tiles.append({
            "id": f"new_tile_{n + 1}",
            "name": f"New Tile {n + 1}",
            "description": "A mysterious feature.",
            "base_tile": "grass",
        })
        self._rebuild_unique_tiles_children()
        # Move cursor to the new tile
        self.module_edit_section_cursor = len(
            self.module_edit_unique_tiles) - 1
        self._adjust_section_scroll()

    def _remove_unique_tile(self):
        """Remove the selected unique tile and refresh the tile list."""
        tiles = self.module_edit_unique_tiles
        if not tiles:
            return
        idx = self.module_edit_section_cursor
        if idx < 0 or idx >= len(tiles):
            return
        tiles.pop(idx)
        self.module_edit_unique_tiles = tiles
        self._rebuild_unique_tiles_children()

    # ── Examine preview for unique tiles ────────────────────────

    # Map base_tile names → tile type constants
    _BASE_TILE_TO_TYPE = None  # built lazily

    @classmethod
    def _get_base_tile_map(cls):
        if cls._BASE_TILE_TO_TYPE is None:
            from src.settings import (
                TILE_GRASS, TILE_FOREST, TILE_SAND, TILE_PATH,
                TILE_MOUNTAIN, TILE_DFLOOR, TILE_FLOOR,
            )
            cls._BASE_TILE_TO_TYPE = {
                "grass": TILE_GRASS,
                "forest": TILE_FOREST,
                "sand": TILE_SAND,
                "path": TILE_PATH,
                "mountain": TILE_MOUNTAIN,
                "dungeon_floor": TILE_DFLOOR,
                "floor": TILE_FLOOR,
            }
        return cls._BASE_TILE_TO_TYPE

    # Brush palette for the examine editor — built dynamically.
    _EXAMINE_BRUSHES = None  # built lazily

    @classmethod
    def _get_examine_brushes(cls):
        """Build examine brush list from the manifest."""
        if cls._EXAMINE_BRUSHES is not None:
            return cls._EXAMINE_BRUSHES
        import json, os
        brushes = ["eraser"]
        try:
            mpath = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "tile_manifest.json")
            with open(mpath) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            manifest = {}
        seen = set()
        for cat in ("overworld", "town", "dungeon",
                     "unique_tiles", "objects"):
            section = manifest.get(cat, {})
            if not isinstance(section, dict):
                continue
            for name, entry in sorted(section.items()):
                if not (isinstance(entry, dict) and "path" in entry):
                    continue
                p = entry["path"]
                if p.startswith("src/assets/"):
                    p = p[len("src/assets/"):]
                if p not in seen:
                    seen.add(p)
                    brushes.append(p)
        cls._EXAMINE_BRUSHES = brushes
        return brushes

    # Item palette for the examine editor.  "eraser" clears an item.
    _EXAMINE_ITEMS = [
        "eraser",
        "Rock",
        "Healing Herb",
        "Healing Potion",
        "Mana Potion",
        "Antidote",
        "Torch",
        "Arrows",
        "Bolts",
        "Stones",
        "Rope",
        "Holy Water",
        "Scroll of Fire",
        "Lockpick",
        "Smoke Bomb",
        "Camping Supplies",
        "Moonpetal",
        "Glowcap Mushroom",
        "Serpent Root",
        "Brimite Ore",
        "Spring Water",
        "Fire Oil",
    ]

    def _enter_utile_examine_preview(self):
        """Enter examine-screen preview mode for the active unique tile."""
        idx = self.module_edit_active_utile
        if idx < 0 or idx >= len(self.module_edit_unique_tiles):
            return
        # Save current field values before switching to preview
        self._save_single_utile_fields()
        self.module_edit_utile_preview = True
        # Editor cursor starts at centre of interior
        self._examine_cursor_col = 5
        self._examine_cursor_row = 6
        self._examine_brush_idx = 0
        self._examine_item_idx = 0
        self._examine_mode = "tile"   # "tile" or "item"
        # Load any existing painted layout into a working dict
        utile = self.module_edit_unique_tiles[idx]
        raw = utile.get("examine_layout") or {}
        self._examine_painted = {}
        for pos_key, gfx in raw.items():
            try:
                c, r = pos_key.split(",")
                self._examine_painted[(int(c), int(r))] = gfx
            except (ValueError, AttributeError):
                pass
        # Load any existing placed items
        raw_items = utile.get("examine_items") or {}
        self._examine_items = {}
        for pos_key, item_name in raw_items.items():
            try:
                c, r = pos_key.split(",")
                self._examine_items[(int(c), int(r))] = item_name
            except (ValueError, AttributeError):
                pass
        self._feat_dirty = False

    def _leave_utile_examine_preview(self):
        """Exit examine-screen preview and persist painted layout + items."""
        idx = self.module_edit_active_utile
        if 0 <= idx < len(self.module_edit_unique_tiles):
            # Persist the painted layout back to the in-memory tile dict
            layout = {}
            for (c, r), gfx in self._examine_painted.items():
                layout[f"{c},{r}"] = gfx
            self.module_edit_unique_tiles[idx]["examine_layout"] = layout
            # Persist placed items
            items = {}
            for (c, r), item_name in self._examine_items.items():
                items[f"{c},{r}"] = item_name
            self.module_edit_unique_tiles[idx]["examine_items"] = items
        self.module_edit_utile_preview = False

    def _handle_examine_preview_input(self, event):
        """Handle input in the examine preview editor."""
        # Intercept input when unsaved-changes dialog is showing
        if self._unsaved_dialog_active:
            self._handle_unsaved_dialog_input(event)
            return

        from src.states.examine import EXAMINE_COLS, EXAMINE_ROWS

        # Movement — arrow keys move cursor within interior (1..cols-2)
        if event.key in (pygame.K_UP, pygame.K_w):
            if self._examine_cursor_row > 1:
                self._examine_cursor_row -= 1
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            if self._examine_cursor_row < EXAMINE_ROWS - 2:
                self._examine_cursor_row += 1
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            if self._examine_cursor_col > 1:
                self._examine_cursor_col -= 1
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            if self._examine_cursor_col < EXAMINE_COLS - 2:
                self._examine_cursor_col += 1

        # Toggle mode — I switches between tile and item modes
        elif event.key == pygame.K_i:
            if self._examine_mode == "tile":
                self._examine_mode = "item"
            else:
                self._examine_mode = "tile"

        # Paint / place — Enter
        elif event.key == pygame.K_RETURN:
            pos = (self._examine_cursor_col, self._examine_cursor_row)
            self._feat_dirty = True
            if self._examine_mode == "tile":
                brush = self._get_examine_brushes()[self._examine_brush_idx]
                if brush == "eraser":
                    self._examine_painted.pop(pos, None)
                else:
                    self._examine_painted[pos] = brush
            else:
                item = self._EXAMINE_ITEMS[self._examine_item_idx]
                if item == "eraser":
                    self._examine_items.pop(pos, None)
                else:
                    self._examine_items[pos] = item

        # Cycle brush/item — Tab / B forward, Shift+Tab backward
        elif event.key in (pygame.K_TAB, pygame.K_b):
            if self._examine_mode == "tile":
                n = len(self._get_examine_brushes())
                if event.mod & pygame.KMOD_SHIFT:
                    self._examine_brush_idx = (
                        self._examine_brush_idx - 1) % n
                else:
                    self._examine_brush_idx = (
                        self._examine_brush_idx + 1) % n
            else:
                n = len(self._EXAMINE_ITEMS)
                if event.mod & pygame.KMOD_SHIFT:
                    self._examine_item_idx = (
                        self._examine_item_idx - 1) % n
                else:
                    self._examine_item_idx = (
                        self._examine_item_idx + 1) % n

        # Escape / Backspace exits preview
        elif event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            if self._feat_dirty:
                def _save_and_exit():
                    self._leave_utile_examine_preview()
                    self._feat_dirty = False
                def _discard_and_exit():
                    self.module_edit_utile_preview = False
                    self._feat_dirty = False
                self._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
            else:
                self._leave_utile_examine_preview()

    def _get_utile_preview_data(self):
        """Return a dict with the preview data for the active tile."""
        idx = self.module_edit_active_utile
        if idx < 0 or idx >= len(self.module_edit_unique_tiles):
            return None
        utile = self.module_edit_unique_tiles[idx]
        bt_map = self._get_base_tile_map()
        from src.settings import TILE_GRASS
        mode = getattr(self, "_examine_mode", "tile")
        if mode == "tile":
            current_brush = self._get_examine_brushes()[
                getattr(self, "_examine_brush_idx", 0)]
        else:
            current_brush = self._EXAMINE_ITEMS[
                getattr(self, "_examine_item_idx", 0)]
        return {
            "tile_type": bt_map.get(
                utile.get("base_tile", "grass"), TILE_GRASS),
            "tile_name": utile.get("name", "Unknown"),
            "description": utile.get("description", ""),
            "tile_graphic": utile.get("tile"),
            "painted": getattr(self, "_examine_painted", {}),
            "placed_items": getattr(self, "_examine_items", {}),
            "cursor_col": getattr(self, "_examine_cursor_col", 5),
            "cursor_row": getattr(self, "_examine_cursor_row", 6),
            "brush": current_brush,
            "mode": mode,
        }

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
        # Intercept input when unsaved-changes dialog is showing
        if self._unsaved_dialog_active:
            self._handle_unsaved_dialog_input(event)
            return

        # ── Create-new mode uses flat field list (no hierarchy) ──
        if self.module_edit_is_new:
            self._handle_module_edit_input_flat(event)
            return

        # ── Examine preview editor mode ──
        if getattr(self, "module_edit_utile_preview", False):
            self._handle_examine_preview_input(event)
            return

        # ── Battle screen editor mode ──
        if getattr(self, "_battle_screen_active", False):
            self._handle_battle_screen_input(event)
            return

        # ── Level 0: section browser ──
        if self.module_edit_level == 0:
            self._handle_section_browser_input(event)
            return

        # ── Level 1: field editor within a section ──
        if event.key == pygame.K_ESCAPE:
            if self._feat_dirty:
                def _save_and_exit():
                    self._leave_section_fields()
                    self._feat_dirty = False
                def _discard_and_exit():
                    # Exit without saving — need to reload the editor state
                    self.module_edit_level = 0
                    self._feat_dirty = False
                self._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
            else:
                self._leave_section_fields()
            return
        if self._is_save_shortcut(event):
            # Save from within field editor
            if self.module_edit_fields:
                entry = self.module_edit_fields[self.module_edit_field]
                entry[2] = self.module_edit_buffer
            self._commit_module_edit()
            self._feat_dirty = False
            return
        # (Unique tile add/remove is now at the section browser level)

        self._handle_field_editor_input(event)

    def _handle_section_browser_input(self, event):
        """Handle input at the section browser level (level 0)."""
        n = len(self.module_edit_sections)
        if event.key == pygame.K_ESCAPE:
            # If in a dungeon sub-browser, pop back up
            if self.module_edit_nav_stack:
                self._leave_dungeon_sub()
            else:
                self._commit_module_edit()
                self.module_edit_mode = False
                self.module_edit_is_new = False
                self.module_message = None
                self._feat_dirty = False
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
            elif action == "add_encounter":
                self._add_encounter_to_level()
            elif action == "add_monster":
                self._add_monster_to_encounter()
            elif action == "add_tile":
                self._add_unique_tile()
            elif action == "remove_level":
                pass  # handled by 'd' key
            else:
                self._enter_section_fields()
        elif self._is_new_shortcut(event):
            # Ctrl+N to add: context-dependent
            if self._in_unique_tiles_folder():
                self._add_unique_tile()
            elif getattr(self, "module_edit_active_enc", -1) >= 0:
                # Inside an encounter monster browser — add monster
                self._add_monster_to_encounter()
            elif self.module_edit_active_level >= 0:
                # Inside a level sub-browser — add encounter
                self._add_encounter_to_level()
            elif (self.module_edit_nav_stack
                    and self.module_edit_active_dung >= 0):
                self._add_dungeon_level()
        elif self._is_delete_shortcut(event):
            # Ctrl+D to remove: context-dependent
            if self._in_unique_tiles_folder():
                self._remove_unique_tile()
            elif getattr(self, "module_edit_active_enc", -1) >= 0:
                # Inside encounter monster browser — remove monster
                sec = self.module_edit_sections[
                    self.module_edit_section_cursor]
                if sec.get("icon") == "M" and sec.get(
                        "mon_idx") is not None:
                    self._remove_monster_from_encounter(sec["mon_idx"])
            elif self.module_edit_active_level >= 0:
                # Inside a level sub-browser — remove selected encounter
                sec = self.module_edit_sections[
                    self.module_edit_section_cursor]
                if sec.get("icon") == "E" and sec.get(
                        "enc_idx") is not None:
                    self._remove_encounter_from_level(sec["enc_idx"])
            elif (self.module_edit_nav_stack
                    and self.module_edit_active_dung >= 0):
                sec = self.module_edit_sections[
                    self.module_edit_section_cursor]
                if sec.get("icon") == "L" and sec.get(
                        "level_idx") is not None:
                    self._remove_dungeon_level(sec["level_idx"])
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
        elif key.endswith("_ftdensity"):
            return ["Inherit", "High", "Medium", "Low"]
        elif key.endswith("_dsize"):
            return ["Small", "Medium", "Large"]
        elif key.endswith("_fdsize"):
            return ["Inherit", "Small", "Medium", "Large"]
        elif key.endswith("_frandenc"):
            return ["Inherit", "Yes", "No"]
        elif key.endswith("_exitportal"):
            return ["Yes", "No"]
        elif key == "innkeeper_quests":
            return ["Yes", "No"]
        elif key.endswith("_layout") and key.startswith("town_"):
            # "Procedural" + all layout names from town_templates.json
            layouts = self._feat_town_lists.get("layouts", [])
            if not layouts:
                self._feat_load_townlayouts()
                layouts = self._feat_town_lists.get("layouts", [])
            return ["Procedural"] + [l["name"] for l in layouts]
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
        # Unique tile choices
        elif key.endswith("_tilegfx") and key.startswith("utile_"):
            return self._get_utile_tile_graphics()
        elif key.endswith("_basetile") and key.startswith("utile_"):
            return self._UTILE_BASE_TILES
        # Overview Map choices
        elif key == "omap_world_size":
            from src.module_loader import WORLD_SIZE_NAMES
            return WORLD_SIZE_NAMES
        elif key == "omap_season":
            from src.module_loader import SEASON_NAMES
            return SEASON_NAMES
        elif key == "omap_time_of_day":
            from src.module_loader import TIME_OF_DAY_NAMES
            return TIME_OF_DAY_NAMES
        elif key == "omap_type":
            return ["Procedural", "Custom"]
        elif key == "omap_initial_build":
            return ["Random", "Blank", "Template"]
        # No match

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
            self._feat_dirty = True
            self.module_edit_field = self._next_editable_field(-1)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()
        elif event.key == pygame.K_DOWN:
            field_entry[2] = self.module_edit_buffer
            self._feat_dirty = True
            self.module_edit_field = self._next_editable_field(+1)
            self.module_edit_buffer = \
                self.module_edit_fields[self.module_edit_field][2]
            self._adjust_module_edit_scroll()
        elif field_type == "action":
            # Action fields respond to Enter/Right
            if event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                key = field_entry[1]
                if key.endswith("_examine"):
                    self._enter_utile_examine_preview()
            return
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
                self._feat_dirty = True
                # When quest type changes, rebuild the field list
                if field_entry[1].endswith("_qtype"):
                    self._on_quest_type_changed(field_entry[1])
        elif field_type == "int":
            if event.key == pygame.K_BACKSPACE:
                self.module_edit_buffer = self.module_edit_buffer[:-1]
                self._feat_dirty = True
            elif event.key == pygame.K_LEFT:
                val = max(0, int(self.module_edit_buffer or "0") - 1)
                self.module_edit_buffer = str(val)
                self._feat_dirty = True
            elif event.key == pygame.K_RIGHT:
                val = int(self.module_edit_buffer or "0") + 1
                self.module_edit_buffer = str(val)
                self._feat_dirty = True
            elif event.unicode and event.unicode.isdigit():
                self.module_edit_buffer += event.unicode
                self._feat_dirty = True
        else:
            # text field
            if event.key == pygame.K_BACKSPACE:
                self.module_edit_buffer = self.module_edit_buffer[:-1]
                self._feat_dirty = True
            elif event.unicode and event.unicode.isprintable():
                self.module_edit_buffer += event.unicode
                self._feat_dirty = True

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
            # If editing a monster inside an encounter, save it back
            if getattr(self, "module_edit_active_enc", -1) >= 0:
                self._save_monster_field()
            # If editing level settings, save them back
            if getattr(self, "_editing_level_settings", False):
                self._save_level_settings_fields()
            # If editing a unique tile, save back to in-memory list
            if self.module_edit_in_unique_tiles:
                self._save_single_utile_fields()

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
                name=values.get("name", "Untitled"),
                author=values.get("author", ""),
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
                elif suffix == "layout":
                    tc = towns[idx].setdefault("town_config", {})
                    if val and val != "Procedural":
                        tc["layout"] = val
                    else:
                        tc.pop("layout", None)
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
                "dsize": "size",
                "randenc": "random_encounters",
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
                    # Torch density / size: convert display name to key
                    if suffix in ("tdensity", "dsize"):
                        val = val.lower()
                    elif suffix == "randenc":
                        val = (val == "Yes")
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

            # ── Unique tiles ──
            ut_dict = {}
            for utile in self.module_edit_unique_tiles:
                tid = utile.get("id", "")
                if not tid:
                    continue
                entry = {
                    "name": utile.get("name", ""),
                    "description": utile.get("description", ""),
                    "tile": utile.get("tile"),
                    "base_tile": utile.get("base_tile", "grass"),
                }
                el = utile.get("examine_layout")
                if el:
                    entry["examine_layout"] = el
                ei = utile.get("examine_items")
                if ei:
                    entry["examine_items"] = ei
                ut_dict[tid] = entry
            if ut_dict:
                data["unique_tiles"] = ut_dict
            else:
                data.pop("unique_tiles", None)

            # ── Overview Map settings (omap_*) ──
            #    World Size, Season, Time of Day are stored in the
            #    module's core settings so the procedural generator
            #    keeps working exactly as before.
            from src.module_loader import (WORLD_SIZE_PRESETS,
                                           _SEASON_MONTHS,
                                           _TIME_HOURS)
            omap_keys = {k: v for k, v in values.items()
                         if k.startswith("omap_")}
            if omap_keys:
                # World Size → settings.map_width / map_height
                ws = omap_keys.get("omap_world_size")
                if ws and ws in WORLD_SIZE_PRESETS:
                    settings_d = data.setdefault("settings", {})
                    dims = WORLD_SIZE_PRESETS[ws]
                    settings_d["map_width"] = dims["map_width"]
                    settings_d["map_height"] = dims["map_height"]

                # Season → settings.start_time.month
                season_val = omap_keys.get("omap_season")
                if season_val and season_val in _SEASON_MONTHS:
                    settings_d = data.setdefault("settings", {})
                    st = settings_d.setdefault("start_time", {})
                    st["month"] = _SEASON_MONTHS[season_val]

                # Time of Day → settings.start_time.hour
                tod_val = omap_keys.get("omap_time_of_day")
                if tod_val and tod_val in _TIME_HOURS:
                    settings_d = data.setdefault("settings", {})
                    st = settings_d.setdefault("start_time", {})
                    st["hour"] = _TIME_HOURS[tod_val]

                # Overview-map-specific keys
                world = data.setdefault("world", {})
                ow_cfg = world.setdefault("overworld_config", {})
                if "omap_type" in omap_keys:
                    ow_cfg["type"] = omap_keys["omap_type"]
                if "omap_initial_build" in omap_keys:
                    ow_cfg["initial_build"] = \
                        omap_keys["omap_initial_build"]

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
            self.module_edit_in_unique_tiles = False
            self.module_edit_active_utile = -1
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
            self._feat_dirty = False
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
    def _feat_handle_field_editing(self, event, ctx, ed, exit_level):
        """Unified field-editor input handler.

        Parameters
        ----------
        event      : pygame event (KEYDOWN)
        ctx        : editor context dict from _feat_editor_ctx()
        ed         : editor name string ("spells", "items", etc.)
        exit_level : _feat_level to return to on ESC (1 for most, 2 for tiles)
        """
        # Editors that need live-sync (save_fields on every change)
        # to support conditional fields or live list-preview updates.
        needs_live_sync = (ed == "tiles")

        # ── Save shortcut (Ctrl+S) ──
        if self._is_save_shortcut(event):
            ctx["save_fields"]()
            if ed == "spells":
                self._feat_resort_spells()
            ctx["save_disk"]()
            self._feat_dirty = False
            return

        # ── Escape ──
        if event.key == pygame.K_ESCAPE:
            if self._feat_dirty:
                def _save_and_exit():
                    ctx["save_fields"]()
                    if ed == "spells":
                        self._feat_resort_spells()
                        self._feat_save_spells()
                        self._feat_spell_filter(
                            self._feat_spell_sel_ctype,
                            self._feat_spell_sel_level)
                    ctx["save_disk"]()
                    ctx["set_editing"](False)
                    self._feat_level = exit_level
                    self._feat_dirty = False
                def _discard_and_exit():
                    if ed == "spells":
                        saved_ct = self._feat_spell_sel_ctype
                        saved_lv = self._feat_spell_sel_level
                        self._feat_load_spells()
                        self._feat_spell_sel_ctype = saved_ct
                        self._feat_spell_sel_level = saved_lv
                        self._feat_spell_nav = 2
                        self._feat_spell_filter(saved_ct, saved_lv)
                    ctx["set_editing"](False)
                    self._feat_level = exit_level
                    self._feat_dirty = False
                self._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
            else:
                if ed == "spells":
                    self._feat_spell_filter(
                        self._feat_spell_sel_ctype,
                        self._feat_spell_sel_level)
                ctx["set_editing"](False)
                self._feat_level = exit_level
            return

        # ── Read current field state ──
        fields = ctx["fields"]()
        n = len(fields)
        if n == 0:
            return
        field_idx = ctx["field_idx"]()
        entry = fields[field_idx]
        ftype = entry[3] if len(entry) > 3 else "text"
        buf = ctx["buffer"]()

        # ── UP / DOWN navigation ──
        if event.key in (pygame.K_UP, pygame.K_DOWN):
            entry[2] = buf
            self._feat_dirty = True
            if needs_live_sync:
                ctx["save_fields"]()
                # Re-read — save may have triggered a field rebuild
                fields = ctx["fields"]()
                n = len(fields)
                field_idx = ctx["field_idx"]()
            direction = -1 if event.key == pygame.K_UP else 1
            idx = (field_idx + direction) % n
            idx = self._feat_next_editable_generic(fields, idx)
            ctx["set_field_idx"](idx)
            ctx["set_buffer"](fields[idx][2])
            ctx["adjust_field_scroll"]()

        # ── Choice / Sprite cycling (LEFT / RIGHT) ──
        elif ftype in ("choice", "sprite"):
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                choices = ctx["get_choices"](entry[1])
                if choices:
                    try:
                        ci = choices.index(buf)
                    except ValueError:
                        ci = 0
                    if event.key == pygame.K_RIGHT:
                        ci = (ci + 1) % len(choices)
                    else:
                        ci = (ci - 1) % len(choices)
                    ctx["set_buffer"](choices[ci])
                    entry[2] = choices[ci]
                    self._feat_dirty = True
                    if needs_live_sync:
                        ctx["save_fields"]()
                    # Spell-specific: casting_type → allowable_classes sync
                    if ed == "spells" and entry[1] == "casting_type":
                        new_cls = ", ".join(
                            self._feat_default_classes(choices[ci]))
                        for fe in self._feat_spell_fields:
                            if fe[1] == "allowable_classes":
                                fe[2] = new_cls
                                break

        # ── Int field editing ──
        elif ftype == "int":
            if event.key == pygame.K_BACKSPACE:
                ctx["set_buffer"](buf[:-1])
                self._feat_dirty = True
            elif event.key == pygame.K_LEFT:
                try:
                    v = int(buf) - 1
                    ctx["set_buffer"](str(max(0, v)))
                    self._feat_dirty = True
                except ValueError:
                    pass
            elif event.key == pygame.K_RIGHT:
                try:
                    v = int(buf) + 1
                    ctx["set_buffer"](str(v))
                    self._feat_dirty = True
                except ValueError:
                    pass
            elif event.unicode and event.unicode.isdigit():
                ctx["set_buffer"](buf + event.unicode)
                self._feat_dirty = True

        # ── Text field editing ──
        elif ftype == "text":
            if event.key == pygame.K_BACKSPACE:
                ctx["set_buffer"](buf[:-1])
                self._feat_dirty = True
            elif event.unicode and event.unicode.isprintable():
                ctx["set_buffer"](buf + event.unicode)
                self._feat_dirty = True

    def _handle_features_input(self, event):
        """Handle input for the Game Features editor.

        Uses _feat_active_editor to dispatch to the correct data
        structures while sharing the same level-1/level-2 navigation logic.
        """
        if event.type != pygame.KEYDOWN:
            return

        # Intercept input when unsaved-changes dialog is showing
        if self._unsaved_dialog_active:
            self._handle_unsaved_dialog_input(event)
            return

        # Town Layouts has its own input handler (bypasses generic ctx system)
        if self._feat_active_editor == "townlayouts":
            self._feat_handle_townlayout_input(event)
            return

        # ── Resolve active editor data pointers ──
        ed = self._feat_active_editor
        # Build a context dict so the level-1 and level-2 code
        # can work generically across all editor types
        ctx = self._feat_editor_ctx()

        # ── Level 2: editing individual fields ──
        # (tiles and gallery use level 2 for browsing, not field editing)
        if self._feat_level == 2 and ctx and ed not in ("tiles", "gallery", "features"):
            self._feat_handle_field_editing(event, ctx, ed, exit_level=1)
            return

        # ── Level 4: pixel editor ──
        if self._feat_level == 5 and ed == "gallery":
            px = self._feat_pxedit_pixels
            if px is None:
                self._feat_level = 3
                return
            w = self._feat_pxedit_w
            h = self._feat_pxedit_h
            n_pal = len(self._feat_pxedit_palette)
            pal_cols = 4  # palette grid columns

            # ── Color replace mode ──
            if self._feat_pxedit_replacing:
                if event.key == pygame.K_ESCAPE:
                    self._feat_pxedit_replacing = False
                elif event.key == pygame.K_LEFT:
                    self._feat_pxedit_replace_dst = (
                        self._feat_pxedit_replace_dst - 1) % n_pal
                elif event.key == pygame.K_RIGHT:
                    self._feat_pxedit_replace_dst = (
                        self._feat_pxedit_replace_dst + 1) % n_pal
                elif event.key == pygame.K_UP:
                    self._feat_pxedit_replace_dst = (
                        self._feat_pxedit_replace_dst - pal_cols) % n_pal
                elif event.key == pygame.K_DOWN:
                    self._feat_pxedit_replace_dst = (
                        self._feat_pxedit_replace_dst + pal_cols) % n_pal
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # Snapshot for undo before batch replace
                    self._feat_pxedit_undo_stack.append(
                        [list(row) for row in px])
                    # Execute: match the exact pixel color from canvas
                    src_c = self._feat_pxedit_replace_src_color
                    dst_c = self._feat_pxedit_palette[
                        self._feat_pxedit_replace_dst]
                    for row in px:
                        for xi in range(len(row)):
                            if tuple(row[xi]) == tuple(src_c):
                                row[xi] = dst_c
                    self._feat_dirty = True
                    self._feat_pxedit_replacing = False
                return

            if self._is_save_shortcut(event):
                # Save without leaving the pixel editor
                self._feat_pxedit_save()
                self.renderer.reload_sprites()
                self._feat_dirty = False
                return

            if event.key == pygame.K_ESCAPE:
                if self._feat_pxedit_focus == "palette":
                    # Escape from palette returns to canvas
                    self._feat_pxedit_focus = "canvas"
                else:
                    if self._feat_dirty:
                        def _save_and_exit():
                            self._feat_pxedit_save()
                            self._feat_pxedit_pixels = None
                            self.renderer.reload_sprites()
                            self._feat_level = 3
                            self._feat_dirty = False
                        def _discard_and_exit():
                            self._feat_pxedit_pixels = None
                            self.renderer.reload_sprites()
                            self._feat_level = 3
                            self._feat_dirty = False
                        self._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
                    else:
                        self._feat_pxedit_pixels = None
                        self.renderer.reload_sprites()
                        self._feat_level = 3
                return

            # Tab toggles focus between canvas and palette
            if event.key == pygame.K_TAB:
                if self._feat_pxedit_focus == "canvas":
                    self._feat_pxedit_focus = "palette"
                else:
                    self._feat_pxedit_focus = "canvas"
                return

            if self._feat_pxedit_focus == "palette":
                # ── Palette navigation (grid: 4 columns) ──
                ci = self._feat_pxedit_color_idx
                if event.key == pygame.K_LEFT:
                    self._feat_pxedit_color_idx = (ci - 1) % n_pal
                elif event.key == pygame.K_RIGHT:
                    self._feat_pxedit_color_idx = (ci + 1) % n_pal
                elif event.key == pygame.K_UP:
                    self._feat_pxedit_color_idx = (
                        ci - pal_cols) % n_pal
                elif event.key == pygame.K_DOWN:
                    self._feat_pxedit_color_idx = (
                        ci + pal_cols) % n_pal
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # Confirm selection, return to canvas
                    self._feat_pxedit_focus = "canvas"
                return

            # ── Canvas mode ──
            if event.key == pygame.K_UP:
                self._feat_pxedit_cy = (
                    self._feat_pxedit_cy - 1) % h
            elif event.key == pygame.K_DOWN:
                self._feat_pxedit_cy = (
                    self._feat_pxedit_cy + 1) % h
            elif event.key == pygame.K_LEFT:
                self._feat_pxedit_cx = (
                    self._feat_pxedit_cx - 1) % w
            elif event.key == pygame.K_RIGHT:
                self._feat_pxedit_cx = (
                    self._feat_pxedit_cx + 1) % w
            # Paint with current color
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                # Snapshot for undo
                self._feat_pxedit_undo_stack.append(
                    [list(row) for row in px])
                color = self._feat_pxedit_palette[
                    self._feat_pxedit_color_idx]
                px[self._feat_pxedit_cy][self._feat_pxedit_cx] = color
                self._feat_dirty = True
            # Quick palette cycle: Q = prev, E = next
            elif event.key == pygame.K_q:
                self._feat_pxedit_color_idx = (
                    self._feat_pxedit_color_idx - 1) % n_pal
            elif event.key == pygame.K_e:
                self._feat_pxedit_color_idx = (
                    self._feat_pxedit_color_idx + 1) % n_pal
            # Pick color from canvas (P = eyedropper)
            elif event.key == pygame.K_p:
                picked = tuple(
                    px[self._feat_pxedit_cy][self._feat_pxedit_cx])
                best_i = 0
                best_d = float("inf")
                for pi, pc in enumerate(self._feat_pxedit_palette):
                    d = sum((a - b) ** 2
                            for a, b in zip(picked[:3], pc[:3]))
                    if d < best_d:
                        best_d = d
                        best_i = pi
                self._feat_pxedit_color_idx = best_i
            # Enter color replace mode (R) — source = exact color under cursor
            elif event.key == pygame.K_r:
                picked = tuple(
                    px[self._feat_pxedit_cy][self._feat_pxedit_cx])
                self._feat_pxedit_replacing = True
                self._feat_pxedit_replace_src_color = picked
                self._feat_pxedit_replace_dst = self._feat_pxedit_color_idx
                self._feat_pxedit_replace_sel = "dst"
            # Undo (Ctrl+Z or U)
            elif (event.key == pygame.K_z
                  and (event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))) \
                    or event.key == pygame.K_u:
                if self._feat_pxedit_undo_stack:
                    restored = self._feat_pxedit_undo_stack.pop()
                    # Copy restored data back into the live pixel array
                    for yi in range(len(restored)):
                        px[yi][:] = restored[yi]
                    self._feat_dirty = True
            return

        # ── Level 4: gallery tag editing ──
        if self._feat_level == 4 and ed == "gallery":
            n_tags = len(self._feat_gallery_all_cats)
            if self._is_save_shortcut(event):
                # Save without leaving the tag editor
                self._feat_save_gallery()
                self._feat_dirty = False
                return
            if event.key == pygame.K_ESCAPE:
                if self._feat_dirty:
                    def _save_and_exit():
                        self._feat_save_gallery()
                        self._feat_level = 3
                        self._feat_rebuild_gallery_cats()
                        self._feat_dirty = False
                    def _discard_and_exit():
                        self._feat_level = 3
                        self._feat_rebuild_gallery_cats()
                        self._feat_dirty = False
                    self._show_unsaved_dialog(_save_and_exit, _discard_and_exit)
                else:
                    self._feat_level = 3
                    self._feat_rebuild_gallery_cats()
                return
            if event.key == pygame.K_UP:
                self._feat_gallery_tag_cursor = (
                    self._feat_gallery_tag_cursor - 1) % n_tags
            elif event.key == pygame.K_DOWN:
                self._feat_gallery_tag_cursor = (
                    self._feat_gallery_tag_cursor + 1) % n_tags
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE,
                               pygame.K_LEFT, pygame.K_RIGHT):
                self._feat_gallery_toggle_tag()
                self._feat_dirty = True
            return

        # ── Level 3: gallery tile detail / edit screen ──
        if self._feat_level == 3 and ed == "gallery":
            # ── Naming mode: capture text input ──
            if self._feat_gallery_naming:
                self._feat_handle_gallery_naming_input(event)
                return
            n_fields = 3  # Name, Categories, Edit Pixels
            if event.key == pygame.K_ESCAPE:
                self._feat_level = 2
                return
            if event.key == pygame.K_UP:
                self._feat_gallery_detail_cursor = (
                    self._feat_gallery_detail_cursor - 1) % n_fields
            elif event.key == pygame.K_DOWN:
                self._feat_gallery_detail_cursor = (
                    self._feat_gallery_detail_cursor + 1) % n_fields
            elif event.key == pygame.K_RETURN:
                cur = self._feat_gallery_detail_cursor
                if cur == 0:
                    # Name → enter naming mode
                    gi = self._feat_gallery_cur_gi()
                    if gi is not None:
                        self._feat_gallery_naming = True
                        self._feat_gallery_name_buf = \
                            self._feat_gallery_list[gi]["name"]
                elif cur == 1:
                    # Categories → open tag editor (Level 4)
                    self._feat_gallery_tag_cursor = 0
                    self._feat_dirty = False
                    self._feat_level = 4
                elif cur == 2:
                    # Edit Pixels → open pixel editor (Level 5)
                    if self._feat_pxedit_open():
                        self._feat_level = 5
            return

        # ── Level 2: gallery sprite list ──
        if self._feat_level == 2 and ed == "gallery":
            n = len(self._feat_gallery_sprites)
            if event.key == pygame.K_ESCAPE:
                self._feat_save_gallery()
                self._feat_rebuild_gallery_cats()
                self._feat_level = 1
                return
            if event.key == pygame.K_UP and n > 0:
                self._feat_gallery_spr_cursor = (
                    self._feat_gallery_spr_cursor - 1) % n
                self._feat_gallery_spr_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_gallery_spr_cursor,
                        self._feat_gallery_spr_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self._feat_gallery_spr_cursor = (
                    self._feat_gallery_spr_cursor + 1) % n
                self._feat_gallery_spr_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_gallery_spr_cursor,
                        self._feat_gallery_spr_scroll)
            elif event.key == pygame.K_RETURN:
                # Enter → open tile detail / edit screen
                if n > 0:
                    self._feat_gallery_detail_cursor = 0
                    self._feat_level = 3
            elif self._is_copy_shortcut(event):
                if n > 0:
                    self._feat_gallery_duplicate()
            elif self._is_delete_shortcut(event) and n > 0:
                self._feat_gallery_delete()
            return

        # ── Level 1: gallery category folders ──
        if self._feat_level == 1 and ed == "gallery":
            n = len(self._feat_gallery_cat_list)
            if event.key == pygame.K_ESCAPE:
                self._feat_save_gallery()
                self._feat_level = 0
                self._feat_active_editor = None
                return
            if event.key == pygame.K_UP and n > 0:
                self._feat_gallery_cat_cursor = (
                    self._feat_gallery_cat_cursor - 1) % n
                self._feat_gallery_cat_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_gallery_cat_cursor,
                        self._feat_gallery_cat_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self._feat_gallery_cat_cursor = (
                    self._feat_gallery_cat_cursor + 1) % n
                self._feat_gallery_cat_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_gallery_cat_cursor,
                        self._feat_gallery_cat_scroll)
            elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                if n > 0:
                    self._feat_gallery_enter_cat()
                    self._feat_dirty = False
                    self._feat_level = 2
            return

        # ── Level 3: Reusable Features grid painter ──
        if self._feat_level == 3 and ed == "features":
            if self._feat_rfeat_naming:
                # Naming overlay
                if event.key == pygame.K_RETURN:
                    items = self._feat_rfeat_current_list()
                    if 0 <= self._feat_rfeat_cursor < len(items):
                        items[self._feat_rfeat_cursor]["name"] = (
                            self._feat_rfeat_name_buf or "Unnamed")
                    self._feat_rfeat_naming = False
                    # If we entered naming from level 2 (not editing),
                    # return to level 2
                    if not self._feat_rfeat_editing:
                        self._feat_save_rfeat()
                        self._feat_level = 2
                elif event.key == pygame.K_ESCAPE:
                    self._feat_rfeat_naming = False
                    if not self._feat_rfeat_editing:
                        self._feat_level = 2
                elif event.key == pygame.K_BACKSPACE:
                    self._feat_rfeat_name_buf = self._feat_rfeat_name_buf[:-1]
                elif event.unicode and event.unicode.isprintable():
                    self._feat_rfeat_name_buf += event.unicode
                return
            if self._feat_rfeat_editing:
                # Grid painter
                items = self._feat_rfeat_current_list()
                if self._feat_rfeat_cursor >= len(items):
                    return
                feat = items[self._feat_rfeat_cursor]
                w = feat["width"]
                h = feat["height"]
                if event.key == pygame.K_ESCAPE:
                    if self._feat_dirty:
                        def _rfeat_save():
                            self._feat_save_rfeat()
                            self._feat_rfeat_editing = False
                            self._feat_dirty = False
                            self._feat_level = 2
                        def _rfeat_discard():
                            self._feat_rfeat_editing = False
                            self._feat_dirty = False
                            self._feat_level = 2
                        self._show_unsaved_dialog(_rfeat_save, _rfeat_discard)
                    else:
                        self._feat_rfeat_editing = False
                        self._feat_level = 2
                elif self._is_save_shortcut(event):
                    self._feat_save_rfeat()
                    self._feat_dirty = False
                elif event.key in (pygame.K_UP, pygame.K_w):
                    self._feat_rfeat_cy = max(0, self._feat_rfeat_cy - 1)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self._feat_rfeat_cy = min(h - 1, self._feat_rfeat_cy + 1)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    self._feat_rfeat_cx = max(0, self._feat_rfeat_cx - 1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self._feat_rfeat_cx = min(w - 1, self._feat_rfeat_cx + 1)
                elif event.key == pygame.K_RETURN:
                    brushes = self._feat_get_rfeat_brushes()
                    brush = brushes[self._feat_rfeat_brush_idx]
                    pos_key = f"{self._feat_rfeat_cx},{self._feat_rfeat_cy}"
                    self._feat_dirty = True
                    if brush["name"] == "Eraser":
                        feat["tiles"].pop(pos_key, None)
                    else:
                        feat["tiles"][pos_key] = {
                            "tile_id": brush["tile_id"],
                            "path": brush.get("path"),
                            "name": brush["name"],
                        }
                elif event.key in (pygame.K_TAB, pygame.K_b):
                    brushes = self._feat_get_rfeat_brushes()
                    n = len(brushes)
                    if event.mod & pygame.KMOD_SHIFT:
                        self._feat_rfeat_brush_idx = (
                            self._feat_rfeat_brush_idx - 1) % n
                    else:
                        self._feat_rfeat_brush_idx = (
                            self._feat_rfeat_brush_idx + 1) % n
                elif event.key == pygame.K_n:
                    items = self._feat_rfeat_current_list()
                    if 0 <= self._feat_rfeat_cursor < len(items):
                        self._feat_rfeat_naming = True
                        self._feat_rfeat_name_buf = items[
                            self._feat_rfeat_cursor]["name"]
                return
            return

        # ── Level 2: Reusable Features list inside folder ──
        if self._feat_level == 2 and ed == "features":
            items = self._feat_rfeat_current_list()
            n = len(items)
            if event.key == pygame.K_ESCAPE:
                self._feat_save_rfeat()
                self._feat_rfeat_in_folder = False
                self._feat_level = 1
                return
            if event.key == pygame.K_UP and n > 0:
                self._feat_rfeat_cursor = (
                    self._feat_rfeat_cursor - 1) % n
                self._feat_rfeat_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_rfeat_cursor,
                        self._feat_rfeat_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self._feat_rfeat_cursor = (
                    self._feat_rfeat_cursor + 1) % n
                self._feat_rfeat_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_rfeat_cursor,
                        self._feat_rfeat_scroll)
            elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                if n > 0:
                    self._feat_rfeat_enter_painter()
                    self._feat_dirty = False
                    self._feat_level = 3
            elif self._is_new_shortcut(event):
                self._feat_rfeat_add()
                self._feat_save_rfeat()
            elif self._is_delete_shortcut(event) and n > 0:
                self._feat_rfeat_remove()
                self._feat_save_rfeat()
            elif event.key == pygame.K_n:
                # Rename selected feature
                if n > 0:
                    self._feat_rfeat_naming = True
                    self._feat_rfeat_name_buf = items[
                        self._feat_rfeat_cursor]["name"]
                    self._feat_level = 3  # naming uses level 3 overlay
            return

        # ── Level 1: Reusable Features folder list ──
        if self._feat_level == 1 and ed == "features":
            n = len(self._feat_rfeat_folders)
            if event.key == pygame.K_ESCAPE:
                self._feat_save_rfeat()
                self._feat_level = 0
                self._feat_active_editor = None
                return
            if event.key == pygame.K_UP and n > 0:
                self._feat_rfeat_folder_cursor = (
                    self._feat_rfeat_folder_cursor - 1) % n
                self._feat_rfeat_folder_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_rfeat_folder_cursor,
                        self._feat_rfeat_folder_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self._feat_rfeat_folder_cursor = (
                    self._feat_rfeat_folder_cursor + 1) % n
                self._feat_rfeat_folder_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_rfeat_folder_cursor,
                        self._feat_rfeat_folder_scroll)
            elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                if n > 0:
                    self._feat_rfeat_enter_folder()
                    self._feat_level = 2
            return

        # ── Level 3: tile field editor (inside folder) ──
        if self._feat_level == 3 and ed == "tiles":
            if ctx:
                self._feat_handle_field_editing(event, ctx, ed, exit_level=2)
            return

        # ── Level 2: tile list inside folder ──
        if self._feat_level == 2 and ed == "tiles":
            tiles_in = self._feat_tile_folder_tiles
            n = len(tiles_in)
            if event.key == pygame.K_ESCAPE:
                self._feat_save_tiles()
                self._feat_tile_in_folder = False
                self._feat_level = 1
                return
            if event.key == pygame.K_UP and n > 0:
                self._feat_tile_cursor = (
                    self._feat_tile_cursor - 1) % n
                self._feat_tile_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_tile_cursor,
                        self._feat_tile_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self._feat_tile_cursor = (
                    self._feat_tile_cursor + 1) % n
                self._feat_tile_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_tile_cursor,
                        self._feat_tile_scroll)
            elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                if n > 0:
                    ti = tiles_in[self._feat_tile_cursor]
                    tile = self._feat_tile_list[ti]
                    self._feat_build_tile_fields(tile)
                    self._feat_tile_editing = True
                    self._feat_dirty = False
                    self._feat_level = 3
            elif self._is_new_shortcut(event) or self._is_copy_shortcut(event):
                # Ctrl+N / Ctrl+C both duplicate the selected tile
                self._feat_duplicate_tile()
                self._feat_save_tiles()
                self._feat_rebuild_tile_folders()
                self._feat_tile_enter_folder()
            elif self._is_delete_shortcut(event):
                self._feat_remove_tile()
                self._feat_save_tiles()
                self._feat_rebuild_tile_folders()
                self._feat_tile_enter_folder()
            return

        # ── Level 1: tile folder list ──
        if self._feat_level == 1 and ed == "tiles":
            n = len(self._feat_tile_folders)
            if event.key == pygame.K_ESCAPE:
                self._feat_save_tiles()
                self._feat_level = 0
                self._feat_active_editor = None
                return
            if event.key == pygame.K_UP and n > 0:
                self._feat_tile_folder_cursor = (
                    self._feat_tile_folder_cursor - 1) % n
                self._feat_tile_folder_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_tile_folder_cursor,
                        self._feat_tile_folder_scroll)
            elif event.key == pygame.K_DOWN and n > 0:
                self._feat_tile_folder_cursor = (
                    self._feat_tile_folder_cursor + 1) % n
                self._feat_tile_folder_scroll = \
                    self._feat_adjust_scroll_generic(
                        self._feat_tile_folder_cursor,
                        self._feat_tile_folder_scroll)
            elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                if n > 0:
                    self._feat_tile_enter_folder()
                    self._feat_level = 2
            elif self._is_new_shortcut(event):
                # Create a new tile in the selected folder and enter it
                self._feat_add_tile()
                self._feat_save_tiles()
                self._feat_rebuild_tile_folders()
                self._feat_tile_enter_folder()
                self._feat_level = 2
            return

        # ── Level 1: list browser ──
        # (tiles and gallery have their own level-1 handlers above)
        # ── Spell 3-tier folder navigation ──
        if self._feat_level == 1 and ed == "spells":
            nav = self._feat_spell_nav
            if nav == 0:
                # Tier 0: casting type folders
                ctypes = self._feat_spell_casting_types()
                n = len(ctypes)
                if event.key == pygame.K_ESCAPE:
                    self._feat_save_spells()
                    self._feat_level = 0
                    self._feat_active_editor = None
                elif event.key == pygame.K_UP and n > 0:
                    self._feat_spell_ctype_cursor = (
                        self._feat_spell_ctype_cursor - 1) % n
                elif event.key == pygame.K_DOWN and n > 0:
                    self._feat_spell_ctype_cursor = (
                        self._feat_spell_ctype_cursor + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_RIGHT) and n > 0:
                    self._feat_spell_sel_ctype = ctypes[
                        self._feat_spell_ctype_cursor]
                    self._feat_spell_level_cursor = 0
                    self._feat_spell_level_scroll = 0
                    self._feat_spell_nav = 1
                elif self._is_save_shortcut(event):
                    self._feat_save_spells()
            elif nav == 1:
                # Tier 1: level folders for selected casting type
                levels = self._feat_spell_levels_for_ctype(
                    self._feat_spell_sel_ctype)
                n = len(levels)
                if event.key in (pygame.K_ESCAPE, pygame.K_LEFT):
                    self._feat_spell_nav = 0
                elif event.key == pygame.K_UP and n > 0:
                    self._feat_spell_level_cursor = (
                        self._feat_spell_level_cursor - 1) % n
                    self._feat_spell_level_scroll = (
                        self._feat_adjust_scroll_generic(
                            self._feat_spell_level_cursor,
                            self._feat_spell_level_scroll))
                elif event.key == pygame.K_DOWN and n > 0:
                    self._feat_spell_level_cursor = (
                        self._feat_spell_level_cursor + 1) % n
                    self._feat_spell_level_scroll = (
                        self._feat_adjust_scroll_generic(
                            self._feat_spell_level_cursor,
                            self._feat_spell_level_scroll))
                elif event.key in (pygame.K_RETURN,
                                   pygame.K_RIGHT) and n > 0:
                    lvl, _count = levels[self._feat_spell_level_cursor]
                    self._feat_spell_sel_level = lvl
                    self._feat_spell_filter(
                        self._feat_spell_sel_ctype, lvl)
                    self._feat_spell_nav = 2
                elif self._is_new_shortcut(event):
                    # Add spell with current casting type + first
                    # available level
                    self._feat_add_spell()
                    new_s = self._feat_spell_list[-1]
                    new_s["casting_type"] = self._feat_spell_sel_ctype
                    new_s["allowable_classes"] = (
                        self._feat_default_classes(
                            self._feat_spell_sel_ctype))
                    self._feat_resort_spells()
                    self._feat_save_spells()
                elif self._is_save_shortcut(event):
                    self._feat_save_spells()
            elif nav == 2:
                # Tier 2: spells at selected casting type + level
                filt = self._feat_spell_filtered
                n = len(filt)
                if event.key in (pygame.K_ESCAPE, pygame.K_LEFT):
                    self._feat_spell_nav = 1
                elif event.key == pygame.K_UP and n > 0:
                    self._feat_spell_cursor = (
                        self._feat_spell_cursor - 1) % n
                    self._feat_spell_scroll = (
                        self._feat_adjust_scroll_generic(
                            self._feat_spell_cursor,
                            self._feat_spell_scroll))
                elif event.key == pygame.K_DOWN and n > 0:
                    self._feat_spell_cursor = (
                        self._feat_spell_cursor + 1) % n
                    self._feat_spell_scroll = (
                        self._feat_adjust_scroll_generic(
                            self._feat_spell_cursor,
                            self._feat_spell_scroll))
                elif event.key in (pygame.K_RETURN,
                                   pygame.K_RIGHT) and n > 0:
                    real_idx = filt[self._feat_spell_cursor]
                    # Save filter position; point cursor at real
                    # index for the field editor
                    self._feat_spell_filter_pos = (
                        self._feat_spell_cursor)
                    self._feat_spell_cursor = real_idx
                    spell = self._feat_spell_list[real_idx]
                    self._feat_build_spell_fields(spell)
                    self._feat_spell_editing = True
                    self._feat_dirty = False
                    self._feat_level = 2
                elif self._is_new_shortcut(event):
                    self._feat_add_spell()
                    new_s = self._feat_spell_list[-1]
                    new_s["casting_type"] = self._feat_spell_sel_ctype
                    new_s["min_level"] = self._feat_spell_sel_level
                    new_s["allowable_classes"] = (
                        self._feat_default_classes(
                            self._feat_spell_sel_ctype))
                    self._feat_resort_spells()
                    self._feat_save_spells()
                    self._feat_spell_filter(
                        self._feat_spell_sel_ctype,
                        self._feat_spell_sel_level)
                    self._feat_spell_cursor = max(
                        0, len(self._feat_spell_filtered) - 1)
                elif self._is_delete_shortcut(event) and n > 0:
                    real_idx = filt[self._feat_spell_cursor]
                    self._feat_spell_list.pop(real_idx)
                    self._feat_save_spells()
                    self._feat_spell_filter(
                        self._feat_spell_sel_ctype,
                        self._feat_spell_sel_level)
                    if self._feat_spell_cursor >= len(
                            self._feat_spell_filtered):
                        self._feat_spell_cursor = max(
                            0, len(self._feat_spell_filtered) - 1)
                    # If level is now empty, go back to level list
                    if not self._feat_spell_filtered:
                        self._feat_spell_nav = 1
                elif self._is_save_shortcut(event):
                    self._feat_save_spells()
            return

        # ── Level 1: generic list (items, monsters) ──
        if self._feat_level == 1 and ctx and ed not in (
                "tiles", "gallery", "spells", "features"):
            lst = ctx["list"]()
            n = len(lst)
            if event.key == pygame.K_ESCAPE:
                ctx["save_disk"]()
                self._feat_level = 0
                self._feat_active_editor = None
                return
            if event.key == pygame.K_UP and n > 0:
                ctx["set_cursor"]((ctx["cursor"]() - 1) % n)
                ctx["adjust_scroll"]()
            elif event.key == pygame.K_DOWN and n > 0:
                ctx["set_cursor"]((ctx["cursor"]() + 1) % n)
                ctx["adjust_scroll"]()
            elif event.key in (pygame.K_RETURN, pygame.K_RIGHT):
                if n > 0:
                    item = lst[ctx["cursor"]()]
                    ctx["build_fields"](item)
                    ctx["set_editing"](True)
                    self._feat_dirty = False
                    self._feat_level = 2
            elif self._is_new_shortcut(event):
                ctx["add"]()
                ctx["adjust_scroll"]()
            elif self._is_delete_shortcut(event):
                ctx["remove"]()
            elif self._is_save_shortcut(event):
                ctx["save_disk"]()
            return

        # ── Level 0: category list ──
        n = len(self._feat_categories)
        if event.key == pygame.K_ESCAPE:
            self.showing_features = False
            self.showing_title = True
            return
        if event.key == pygame.K_UP:
            self._feat_cursor = (self._feat_cursor - 1) % n
        elif event.key == pygame.K_DOWN:
            self._feat_cursor = (self._feat_cursor + 1) % n
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE,
                           pygame.K_RIGHT):
            cat = self._feat_categories[self._feat_cursor]
            if cat["label"] == "Modules":
                self._feat_open_modules()
            elif cat["label"] == "Spells":
                self._feat_active_editor = "spells"
                self._feat_load_spells()
                self._feat_level = 1
            elif cat["label"] == "Items":
                self._feat_active_editor = "items"
                self._feat_load_items()
                self._feat_level = 1
            elif cat["label"] == "Monsters":
                self._feat_active_editor = "monsters"
                self._feat_load_monsters()
                self._feat_level = 1
            elif cat["label"] == "Tile Types":
                self._feat_active_editor = "tiles"
                self.renderer.reload_sprites()
                self._feat_load_tiles()
                self._feat_level = 1
            elif cat["label"] == "Tile Gallery":
                self._feat_active_editor = "gallery"
                self.renderer.reload_sprites()
                self._feat_load_gallery()
                self._feat_level = 1
            elif cat["label"] == "Reusable Features":
                self._feat_active_editor = "features"
                self.renderer.reload_sprites()
                self._feat_load_rfeat()
                self._feat_rfeat_brushes = None
                self._feat_level = 1
            elif cat["label"] == "Town Layouts":
                self._feat_active_editor = "townlayouts"
                self.renderer.reload_sprites()
                self._feat_load_townlayouts()
                # Force brush palette to rebuild from current TILE_DEFS
                self._feat_townlayout_brushes = None
                self._feat_level = 1

    def _feat_editor_ctx(self):
        """Return a dict of lambdas/refs for the active editor,
        allowing generic level-1 and level-2 logic."""
        ed = self._feat_active_editor
        if ed == "spells":
            return {
                "list": lambda: self._feat_spell_list,
                "cursor": lambda: self._feat_spell_cursor,
                "set_cursor": lambda v: setattr(self, "_feat_spell_cursor", v),
                "adjust_scroll": lambda: setattr(
                    self, "_feat_spell_scroll",
                    self._feat_adjust_scroll_generic(
                        self._feat_spell_cursor, self._feat_spell_scroll)),
                "fields": lambda: self._feat_spell_fields,
                "field_idx": lambda: self._feat_spell_field,
                "set_field_idx": lambda v: setattr(self, "_feat_spell_field", v),
                "buffer": lambda: self._feat_spell_buffer,
                "set_buffer": lambda v: setattr(self, "_feat_spell_buffer", v),
                "adjust_field_scroll": lambda: setattr(
                    self, "_feat_spell_scroll_f",
                    self._feat_adjust_field_scroll_generic(
                        self._feat_spell_field, self._feat_spell_scroll_f)),
                "build_fields": self._feat_build_spell_fields,
                "save_fields": self._feat_save_spell_fields,
                "save_disk": self._feat_save_spells,
                "set_editing": lambda v: setattr(self, "_feat_spell_editing", v),
                "add": self._feat_add_spell,
                "remove": self._feat_remove_spell,
                "get_choices": self._feat_get_spell_choices,
            }
        elif ed == "items":
            return {
                "list": lambda: self._feat_item_list,
                "cursor": lambda: self._feat_item_cursor,
                "set_cursor": lambda v: setattr(self, "_feat_item_cursor", v),
                "adjust_scroll": lambda: setattr(
                    self, "_feat_item_scroll",
                    self._feat_adjust_scroll_generic(
                        self._feat_item_cursor, self._feat_item_scroll)),
                "fields": lambda: self._feat_item_fields,
                "field_idx": lambda: self._feat_item_field,
                "set_field_idx": lambda v: setattr(self, "_feat_item_field", v),
                "buffer": lambda: self._feat_item_buffer,
                "set_buffer": lambda v: setattr(self, "_feat_item_buffer", v),
                "adjust_field_scroll": lambda: setattr(
                    self, "_feat_item_scroll_f",
                    self._feat_adjust_field_scroll_generic(
                        self._feat_item_field, self._feat_item_scroll_f)),
                "build_fields": self._feat_build_item_fields,
                "save_fields": self._feat_save_item_fields,
                "save_disk": self._feat_save_items,
                "set_editing": lambda v: setattr(self, "_feat_item_editing", v),
                "add": self._feat_add_item,
                "remove": self._feat_remove_item,
                "get_choices": self._feat_get_item_choices,
            }
        elif ed == "monsters":
            return {
                "list": lambda: self._feat_mon_list,
                "cursor": lambda: self._feat_mon_cursor,
                "set_cursor": lambda v: setattr(self, "_feat_mon_cursor", v),
                "adjust_scroll": lambda: setattr(
                    self, "_feat_mon_scroll",
                    self._feat_adjust_scroll_generic(
                        self._feat_mon_cursor, self._feat_mon_scroll)),
                "fields": lambda: self._feat_mon_fields,
                "field_idx": lambda: self._feat_mon_field,
                "set_field_idx": lambda v: setattr(self, "_feat_mon_field", v),
                "buffer": lambda: self._feat_mon_buffer,
                "set_buffer": lambda v: setattr(self, "_feat_mon_buffer", v),
                "adjust_field_scroll": lambda: setattr(
                    self, "_feat_mon_scroll_f",
                    self._feat_adjust_field_scroll_generic(
                        self._feat_mon_field, self._feat_mon_scroll_f)),
                "build_fields": self._feat_build_mon_fields,
                "save_fields": self._feat_save_mon_fields,
                "save_disk": self._feat_save_monsters,
                "set_editing": lambda v: setattr(self, "_feat_mon_editing", v),
                "add": self._feat_add_monster,
                "remove": self._feat_remove_monster,
                "get_choices": self._feat_get_mon_choices,
            }
        elif ed == "tiles":
            return {
                "list": lambda: self._feat_tile_list,
                "cursor": lambda: self._feat_tile_cursor,
                "set_cursor": lambda v: setattr(self, "_feat_tile_cursor", v),
                "adjust_scroll": lambda: setattr(
                    self, "_feat_tile_scroll",
                    self._feat_adjust_scroll_generic(
                        self._feat_tile_cursor, self._feat_tile_scroll)),
                "fields": lambda: self._feat_tile_fields,
                "field_idx": lambda: self._feat_tile_field,
                "set_field_idx": lambda v: setattr(self, "_feat_tile_field", v),
                "buffer": lambda: self._feat_tile_buffer,
                "set_buffer": lambda v: setattr(self, "_feat_tile_buffer", v),
                "adjust_field_scroll": lambda: setattr(
                    self, "_feat_tile_scroll_f",
                    self._feat_adjust_field_scroll_generic(
                        self._feat_tile_field, self._feat_tile_scroll_f)),
                "build_fields": self._feat_build_tile_fields,
                "save_fields": self._feat_save_tile_fields,
                "save_disk": self._feat_save_tiles,
                "set_editing": lambda v: setattr(self, "_feat_tile_editing", v),
                "add": self._feat_add_tile,
                "remove": self._feat_remove_tile,
                "get_choices": self._feat_get_tile_choices,
            }
        return None

    def _feat_render_state(self):
        """Build and return the full keyword-arg dict for draw_features_screen.

        Organises all editor state into a single dict so the caller
        is a one-liner instead of 80+ keyword arguments.  The renderer
        signature is unchanged — it still receives these as kwargs.
        New editors only need to add their block here.
        """
        ed = self._feat_active_editor
        state = {
            # ── Core ──
            "categories": self._feat_categories,
            "cat_cursor": self._feat_cursor,
            "level": self._feat_level,
            "active_editor": ed,
            # ── Spells ──
            "spell_list": self._feat_spell_list,
            "spell_cursor": self._feat_spell_cursor,
            "spell_scroll": self._feat_spell_scroll,
            "spell_editing": self._feat_spell_editing,
            "spell_fields": self._feat_spell_fields,
            "spell_field": self._feat_spell_field,
            "spell_buffer": self._feat_spell_buffer,
            "spell_field_scroll": self._feat_spell_scroll_f,
            "spell_nav": self._feat_spell_nav,
            "spell_ctype_cursor": self._feat_spell_ctype_cursor,
            "spell_level_cursor": self._feat_spell_level_cursor,
            "spell_level_scroll": self._feat_spell_level_scroll,
            "spell_sel_ctype": self._feat_spell_sel_ctype,
            "spell_sel_level": self._feat_spell_sel_level,
            "spell_filtered": self._feat_spell_filtered,
            # ── Items ──
            "item_list": self._feat_item_list,
            "item_cursor": self._feat_item_cursor,
            "item_scroll": self._feat_item_scroll,
            "item_editing": self._feat_item_editing,
            "item_fields": self._feat_item_fields,
            "item_field": self._feat_item_field,
            "item_buffer": self._feat_item_buffer,
            "item_field_scroll": self._feat_item_scroll_f,
            # ── Monsters ──
            "mon_list": self._feat_mon_list,
            "mon_cursor": self._feat_mon_cursor,
            "mon_scroll": self._feat_mon_scroll,
            "mon_editing": self._feat_mon_editing,
            "mon_fields": self._feat_mon_fields,
            "mon_field": self._feat_mon_field,
            "mon_buffer": self._feat_mon_buffer,
            "mon_field_scroll": self._feat_mon_scroll_f,
            # ── Tiles ──
            "tile_list": self._feat_tile_list,
            "tile_folders": self._feat_tile_folders,
            "tile_folder_cursor": self._feat_tile_folder_cursor,
            "tile_folder_scroll": self._feat_tile_folder_scroll,
            "tile_folder_tiles": self._feat_tile_folder_tiles,
            "tile_cursor": self._feat_tile_cursor,
            "tile_scroll": self._feat_tile_scroll,
            "tile_editing": self._feat_tile_editing,
            "tile_fields": self._feat_tile_fields,
            "tile_field": self._feat_tile_field,
            "tile_buffer": self._feat_tile_buffer,
            "tile_field_scroll": self._feat_tile_scroll_f,
            # ── Gallery ──
            "gallery_list": self._feat_gallery_list,
            "gallery_cat_list": self._feat_gallery_cat_list,
            "gallery_cat_cursor": self._feat_gallery_cat_cursor,
            "gallery_cat_scroll": self._feat_gallery_cat_scroll,
            "gallery_sprites": self._feat_gallery_sprites,
            "gallery_spr_cursor": self._feat_gallery_spr_cursor,
            "gallery_spr_scroll": self._feat_gallery_spr_scroll,
            "gallery_tag_cursor": self._feat_gallery_tag_cursor,
            "gallery_all_cats": self._feat_gallery_all_cats,
            "gallery_naming": self._feat_gallery_naming,
            "gallery_name_buf": self._feat_gallery_name_buf,
            "gallery_detail_cursor": self._feat_gallery_detail_cursor,
            # ── Pixel editor ──
            "pxedit_pixels": self._feat_pxedit_pixels,
            "pxedit_cx": self._feat_pxedit_cx,
            "pxedit_cy": self._feat_pxedit_cy,
            "pxedit_w": self._feat_pxedit_w,
            "pxedit_h": self._feat_pxedit_h,
            "pxedit_color_idx": self._feat_pxedit_color_idx,
            "pxedit_palette": self._feat_pxedit_palette,
            "pxedit_focus": self._feat_pxedit_focus,
            "pxedit_replacing": self._feat_pxedit_replacing,
            "pxedit_replace_src_color": self._feat_pxedit_replace_src_color,
            "pxedit_replace_dst": self._feat_pxedit_replace_dst,
            "pxedit_replace_sel": self._feat_pxedit_replace_sel,
            # ── Reusable Features ──
            "rfeat_folders": self._feat_rfeat_folders,
            "rfeat_folder_cursor": self._feat_rfeat_folder_cursor,
            "rfeat_folder_scroll": self._feat_rfeat_folder_scroll,
            "rfeat_list": (self._feat_rfeat_current_list()
                           if ed == "features" else []),
            "rfeat_cursor": self._feat_rfeat_cursor,
            "rfeat_scroll": self._feat_rfeat_scroll,
            "rfeat_editing": self._feat_rfeat_editing,
            "rfeat_cx": self._feat_rfeat_cx,
            "rfeat_cy": self._feat_rfeat_cy,
            "rfeat_brush_idx": self._feat_rfeat_brush_idx,
            "rfeat_brushes": (self._feat_get_rfeat_brushes()
                              if ed == "features" else []),
            "rfeat_naming": self._feat_rfeat_naming,
            "rfeat_name_buf": self._feat_rfeat_name_buf,
            "rfeat_current_ctx": self._feat_rfeat_current_ctx,
            # ── Town layouts ──
            "townlayout_list": self._feat_townlayout_list,
            "townlayout_cursor": self._feat_townlayout_cursor,
            "townlayout_scroll": self._feat_townlayout_scroll,
            "townlayout_editing": self._feat_townlayout_editing,
            "townlayout_cx": self._feat_townlayout_cx,
            "townlayout_cy": self._feat_townlayout_cy,
            "townlayout_brush_idx": self._feat_townlayout_brush_idx,
            "townlayout_brushes": (
                self._feat_get_townlayout_brushes()
                if ed == "townlayouts" else []),
            "townlayout_naming": self._feat_townlayout_naming,
            "townlayout_name_buf": self._feat_townlayout_name_buf,
            "town_node_cursor": self._feat_town_node_cursor,
            "town_detail_editing": self._feat_town_detail_editing,
            "town_desc_buf": self._feat_town_desc_buf,
            "town_active_sub": self._feat_town_active_sub,
            "town_selected_idx": self._feat_town_selected_idx,
            "townlayout_replacing": self._feat_townlayout_replacing,
            "townlayout_replace_src_tile": self._feat_townlayout_replace_src_tile,
            "townlayout_replace_src_name": self._feat_townlayout_replace_src_name,
            "townlayout_replace_src_empty": self._feat_townlayout_replace_src_empty,
            "townlayout_replace_dst_idx": self._feat_townlayout_replace_dst_idx,
            "interior_picking": self._feat_interior_picking,
            "interior_pick_cursor": self._feat_interior_pick_cursor,
            "interior_pick_scroll": self._feat_interior_pick_scroll,
            "interior_list": getattr(
                self, "_feat_interior_pick_list",
                self._feat_town_lists.get("interiors", [])),
            "interior_pick_sub": getattr(
                self, "_feat_interior_pick_sub", "layouts"),
            "town_picker_active": self._feat_town_picker_active,
            "town_picker_cursor": self._feat_town_picker_cursor,
            "town_picker_layouts": self._feat_town_lists.get("layouts", []),
            "town_picker_mode": getattr(
                self, "_feat_town_picker_mode", "new"),
        }
        return state

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
                    self._handle_features_input(event)
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
                    **self._feat_render_state())
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
                    edit_nav_depth=len(self.module_edit_nav_stack),
                    edit_nav_label=getattr(
                        self, "_module_edit_folder_label", ""),
                    edit_in_encounters=(
                        self.module_edit_active_level >= 0),
                    edit_in_dungeon_sub=(
                        self.module_edit_active_dung >= 0),
                    edit_utile_preview=(
                        self._get_utile_preview_data()
                        if getattr(self, "module_edit_utile_preview", False)
                        else None),
                    edit_battle_preview=(
                        self._get_battle_screen_preview_data()
                        if getattr(self, "_battle_screen_active", False)
                        else None))
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
