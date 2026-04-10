"""
Save and load game state to/from JSON files.

Serializes the party (members, equipment, inventory, gold, position),
party-level equipment and effects, module/quest state, and cleared
dungeon positions.  Save files are stored in data/saves/.
"""

import json
import os
import time

from src.party import Party, PartyMember
from src.settings import TILE_DUNGEON_CLEARED

# ── Save directory ────────────────────────────────────────────────
_SAVE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "saves")

# Number of regular save slots (1-based: 1, 2, 3)
NUM_SAVE_SLOTS = 3

# Quick Save uses slot 0 and a dedicated filename
QUICK_SAVE_SLOT = 0


_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "config.json")

# Default player settings
_DEFAULT_CONFIG = {
    "music_enabled": True,
    "smite_enabled": False,
    "start_with_equipment": True,
    "active_module_path": None,
}


def load_config():
    """Load player settings from config.json, returning defaults on failure."""
    try:
        with open(_CONFIG_PATH, "r") as f:
            data = json.load(f)
        # Merge with defaults so new keys are always present
        merged = dict(_DEFAULT_CONFIG)
        merged.update(data)
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULT_CONFIG)


def save_config(config):
    """Persist player settings to config.json."""
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def _ensure_save_dir():
    """Create the saves directory if it doesn't exist."""
    os.makedirs(_SAVE_DIR, exist_ok=True)


def _save_path(slot):
    """Return the file path for a given save slot.

    Slot 0 is the Quick Save slot; slots 1+ are regular saves.
    """
    if slot == QUICK_SAVE_SLOT:
        return os.path.join(_SAVE_DIR, "quick_save.json")
    return os.path.join(_SAVE_DIR, f"save_{slot}.json")


# ── Serialization helpers ─────────────────────────────────────────

def _serialize_member(member):
    """Convert a PartyMember to a JSON-safe dict."""
    return {
        "name": member.name,
        "class": member.char_class,
        "race": member.race,
        "gender": member.gender,
        "max_hp": member.max_hp,
        "hp": member.hp,
        "strength": member.base_strength,
        "dexterity": member.base_dexterity,
        "intelligence": member.base_intelligence,
        "wisdom": member.base_wisdom,
        "level": member.level,
        "exp": member.exp,
        "equipped": dict(member.equipped),
        "inventory": list(member.inventory),
        "current_mp": member._current_mp,
        "bonus_mp": member._bonus_mp,
        "ammo": dict(member.ammo),
        "sprite": member.sprite,
        "weapon_poison": dict(getattr(member, "weapon_poison",
                                       {"right_hand": None, "left_hand": None})),
    }


def _serialize_party(party):
    """Convert a Party to a JSON-safe dict."""
    return {
        "col": party.col,
        "row": party.row,
        "gold": party.gold,
        "roster": [_serialize_member(m) for m in party.roster],
        "active_party": list(party.active_indices),
        # Legacy "members" kept for backward compat with older saves
        "members": [_serialize_member(m) for m in party.members],
        "shared_inventory": list(party.shared_inventory),
        "equipped": dict(party.equipped),
        "effects": dict(party.effects),
        "clock": party.clock.to_dict(),
        "last_pickpocket_day": party.last_pickpocket_day,
        "last_tinker_day": party.last_tinker_day,
        "galadriels_light_steps": party.galadriels_light_steps,
        "last_galadriels_light_day": party.last_galadriels_light_day,
    }


def _serialize_dungeon_levels(levels):
    """Serialize a list of DungeonData objects to JSON-safe dicts."""
    if not levels:
        return []
    return [dd.to_dict() for dd in levels]


def _deserialize_dungeon_levels(data_list):
    """Reconstruct a list of DungeonData from serialized dicts."""
    from src.dungeon_generator import DungeonData
    if not data_list:
        return []
    return [DungeonData.from_dict(d) for d in data_list]


def _serialize_dungeon_cache(game):
    """Serialize the random dungeon cache: {(col,row): [DungeonData]}."""
    cache = getattr(game, "dungeon_cache", {})
    result = []
    for (col, row), levels in cache.items():
        result.append({
            "col": col,
            "row": row,
            "levels": _serialize_dungeon_levels(levels),
        })
    return result


def _serialize_key_dungeons(game):
    """Serialize key dungeon quest state including full dungeon layouts.

    Persists the complete DungeonData for each floor so that explored
    tiles, opened chests, triggered traps, and killed monsters survive
    save/load.
    """
    result = []
    for (col, row), kd in getattr(game, "key_dungeons", {}).items():
        result.append({
            "col": col,
            "row": row,
            "dungeon_number": kd["dungeon_number"],
            "name": kd["name"],
            "key_name": kd["key_name"],
            "status": kd["status"],
            "artifact_name": kd.get("artifact_name", kd["key_name"]),
            "current_level": kd.get("current_level", 0),
            "description": kd.get("description", ""),
            "quest_objective": kd.get("quest_objective", ""),
            "quest_hint": kd.get("quest_hint", ""),
            "quest_type": kd.get("quest_type", "retrieve"),
            "kill_target": kd.get("kill_target", ""),
            "kill_count": kd.get("kill_count", 0),
            "kill_progress": kd.get("kill_progress", 0),
            "module_levels": kd.get("module_levels"),
            "exit_portal": kd.get("exit_portal", True),
            "keys_needed": kd.get("keys_needed", 1),
            "gnome_town": kd.get("gnome_town", ""),
            "levels": _serialize_dungeon_levels(kd.get("levels", [])),
        })
    return result


def _serialize_quest(quest):
    """Serialize a quest dict (quest or house_quest), including dungeon levels."""
    if quest is None:
        return None
    data = {
        "status": quest.get("status", "active"),
        "dungeon_col": quest.get("dungeon_col"),
        "dungeon_row": quest.get("dungeon_row"),
        "artifact_name": quest.get("artifact_name"),
        "name": quest.get("name"),
        "current_level": quest.get("current_level", 0),
        "quest_type": quest.get("quest_type", "retrieve"),
        "kill_target": quest.get("kill_target"),
        "kill_count": quest.get("kill_count", 0),
        "kill_progress": quest.get("kill_progress", 0),
        "exit_portal": quest.get("exit_portal", True),
    }
    # Persist full dungeon layouts so state survives save/load
    levels = quest.get("levels")
    if levels:
        data["levels"] = _serialize_dungeon_levels(levels)
    return data


def _deserialize_member(data):
    """Reconstruct a PartyMember from saved data."""
    member = PartyMember(
        name=data["name"],
        char_class=data["class"],
        race=data.get("race", "Human"),
        gender=data.get("gender", "Male"),
        hp=data.get("max_hp", 20),
        strength=data.get("strength", 10),
        dexterity=data.get("dexterity", 10),
        intelligence=data.get("intelligence", 10),
        wisdom=data.get("wisdom", 10),
        level=data.get("level", 1),
    )
    member.hp = data.get("hp", member.max_hp)
    member.max_hp = data.get("max_hp", member.max_hp)
    member.exp = data.get("exp", 0)

    # Custom sprite tile
    member.sprite = data.get("sprite")

    # Equipment slots
    equip = data.get("equipped", {})
    member.equipped = {
        "right_hand": equip.get("right_hand", "Fists"),
        "left_hand": equip.get("left_hand"),
        "body": equip.get("body", "Cloth"),
        "head": equip.get("head"),
    }
    member._sync_legacy_fields()

    # Personal inventory
    member.inventory = list(data.get("inventory", []))

    # MP state
    member._current_mp = data.get("current_mp")
    member._bonus_mp = data.get("bonus_mp", 0)

    # Ammo tracking
    member.ammo = dict(data.get("ammo", {}))

    # Weapon poison
    member.weapon_poison = data.get("weapon_poison",
                                     {"right_hand": None, "left_hand": None})

    return member


def _deserialize_party(data):
    """Reconstruct a Party from saved data."""
    party = Party(data.get("col", 30), data.get("row", 11))
    party.gold = data.get("gold", 100)

    # Rebuild roster and active party
    if "roster" in data:
        # New format: full roster + active indices
        for member_data in data["roster"]:
            member = _deserialize_member(member_data)
            party.add_to_roster(member)
        active = data.get("active_party", list(range(min(4, len(party.roster)))))
        party.set_active_party(active)
    else:
        # Legacy format: only active members, no roster
        for member_data in data.get("members", []):
            member = _deserialize_member(member_data)
            party.add_to_roster(member)
        party.set_active_party(list(range(len(party.roster))))

    # Shared inventory (already in correct format — strings and dicts)
    party.shared_inventory = list(data.get("shared_inventory", []))

    # Party-level equipment slots (includes "light" which is rendered in Effects)
    saved_eq = data.get("equipped", {})
    for slot in list(party.equipped.keys()):
        entry = saved_eq.get(slot)
        party.equipped[slot] = entry  # None or {"name": ..., "charges": ...}

    # Party-level passive effects
    from src.party import EFFECTS_DATA
    valid_names = {e["name"] for e in EFFECTS_DATA} | {"Torch"}
    saved_eff = data.get("effects", {})
    for slot in party.EFFECT_SLOTS:
        eff = saved_eff.get(slot)
        # Clear any effects that no longer exist in the data files
        party.effects[slot] = eff if eff in valid_names else None

    # Game clock
    from src.game_time import GameClock
    clock_data = data.get("clock")
    if clock_data:
        party.clock = GameClock.from_dict(clock_data)

    # Pickpocket cooldown
    party.last_pickpocket_day = data.get("last_pickpocket_day", -1)
    # Tinker cooldown
    party.last_tinker_day = data.get("last_tinker_day", -1)
    # Galadriel's Light
    party.galadriels_light_steps = data.get("galadriels_light_steps", 0)
    party.last_galadriels_light_day = data.get("last_galadriels_light_day", -1)

    return party


# ── State context serialization ───────────────────────────────────

def _serialize_state_context(game, state_name):
    """Capture additional context needed to restore the player's position.

    For dungeon/town states this includes the overworld coordinates of
    the dungeon or town so the correct map can be re-entered on load.
    """
    ctx = {"state": state_name}

    if state_name == "dungeon":
        ds = game.states.get("dungeon")
        if ds:
            ctx["overworld_col"] = ds.overworld_col
            ctx["overworld_row"] = ds.overworld_row
            ctx["current_level"] = ds.current_level
            ctx["is_quest_dungeon"] = ds.quest_levels is not None
            # Save the party position *inside* the dungeon
            ctx["party_col"] = game.party.col
            ctx["party_row"] = game.party.row
            ctx["torch_active"] = ds.torch_active
            ctx["torch_steps"] = ds.torch_steps

    elif state_name == "town":
        ts = game.states.get("town")
        if ts:
            ctx["overworld_col"] = ts.overworld_col
            ctx["overworld_row"] = ts.overworld_row
            # Save the party position *inside* the town
            ctx["party_col"] = game.party.col
            ctx["party_row"] = game.party.row

    return ctx


# ── Public API ────────────────────────────────────────────────────

def save_game(slot, game):
    """Save the current game state to a numbered slot (1-based).

    Parameters
    ----------
    slot : int
        Save slot number (1 to NUM_SAVE_SLOTS).
    game : Game
        The main Game object whose state will be saved.

    Returns
    -------
    bool
        True if saved successfully, False on error.
    """
    _ensure_save_dir()
    try:
        # Determine current state name
        state_name = "overworld"
        for name, state_obj in game.states.items():
            if state_obj is game.current_state:
                state_name = name
                break

        # Collect cleared dungeon positions from the overworld tile map
        cleared_dungeons = []
        if hasattr(game, "tile_map") and game.tile_map is not None:
            tm = game.tile_map
            for r in range(tm.height):
                for c in range(tm.width):
                    if tm.get_tile(c, r) == TILE_DUNGEON_CLEARED:
                        cleared_dungeons.append([c, r])

        save_data = {
            "version": 3,
            "timestamp": time.time(),
            "state": state_name,
            "party": _serialize_party(game.party),
            "cleared_dungeons": cleared_dungeons,
            # ── Module identification ──
            "module_path": getattr(game, "active_module_path", None),
            "module_name": getattr(game, "active_module_name", None),
            "module_version": getattr(game, "active_module_version", None),
            # ── Quest state ──
            "key_dungeons": _serialize_key_dungeons(game),
            "keys_inserted": getattr(game, "keys_inserted", 0),
            "machine_col": getattr(game, "machine_col", None),
            "machine_row": getattr(game, "machine_row", None),
            "gnome_quest_accepted": getattr(
                game, "_gnome_quest_accepted", False),
            "darkness_active": getattr(game, "darkness_active", False),
            "quest_npc_assignments": getattr(
                game, "quest_npc_assignments", {}),
            "module_quest_states": getattr(
                game, "module_quest_states", {}),
            "quest": _serialize_quest(getattr(game, "quest", None)),
            "house_quest": _serialize_quest(getattr(game, "house_quest", None)),
            # ── Game log ──
            "game_log": list(getattr(game, "game_log", [])),
            # ── Visited dungeons ──
            "visited_dungeons": [list(pos) for pos in getattr(game, "visited_dungeons", set())],
            # ── Persistent dungeon cache (random dungeons) ──
            "dungeon_cache": _serialize_dungeon_cache(game),
            # ── Map seed for reproducible overworld ──
            "map_seed": getattr(game.tile_map, "seed", None)
                        if hasattr(game, "tile_map") and game.tile_map else None,
            # ── State context for restoring position in dungeon/town ──
            "state_context": _serialize_state_context(game, state_name),
        }

        path = _save_path(slot)
        with open(path, "w") as f:
            json.dump(save_data, f, indent=2)
        return True
    except Exception:
        return False


def load_game(slot, game):
    """Load game state from a numbered slot (1-based).

    Restores party data, module/quest state, overworld map, and cleared
    dungeon positions, then switches to the overworld state.

    Parameters
    ----------
    slot : int
        Save slot number (1 to NUM_SAVE_SLOTS).
    game : Game
        The main Game object to restore state into.

    Returns
    -------
    bool
        True if loaded successfully, False on error.
    """
    path = _save_path(slot)
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r") as f:
            save_data = json.load(f)

        # ── Restore module context ──────────────────────────────
        # Reload module data so items, races, monsters, etc. match
        saved_module = save_data.get("module_path")
        if saved_module and os.path.isdir(saved_module):
            game.active_module_path = saved_module
            game.active_module_name = save_data.get(
                "module_name", "Unknown Module")
            game.active_module_version = save_data.get(
                "module_version", "1.0.0")

            from src.module_loader import load_module_data
            game.module_manifest = load_module_data(saved_module)
        else:
            game.module_manifest = None

        # ── Restore the overworld map ─────────────────────────
        # If the module has a static (custom) map, use it directly —
        # this matches the New Game path and avoids regenerating a
        # different procedural map when the saved seed is missing.
        from src.tile_map import create_test_map, load_static_overworld
        from src.camera import Camera

        overworld_cfg = None
        if game.module_manifest:
            overworld_cfg = game.module_manifest.get("_overworld_cfg")

        static_map = None
        if game.active_module_path:
            static_map = load_static_overworld(game.active_module_path)

        if static_map is not None:
            game.tile_map = static_map
        else:
            saved_seed = save_data.get("map_seed")
            game.tile_map = create_test_map(
                seed=saved_seed,
                overworld_cfg=overworld_cfg,
                data_dir=game.active_module_path
                if game.module_manifest else None)
        game.camera = Camera(game.tile_map.width, game.tile_map.height)

        # ── Restore link registry ──────────────────────────────
        # The link registry must be reloaded from the module so
        # tile-to-tile links (ship tiles, town entrances, etc.)
        # are populated on the freshly-loaded tile map.
        if game.active_module_path:
            from src.link_registry import LinkRegistry
            game.link_registry = LinkRegistry()
            game.link_registry.load(game.active_module_path)
            game.link_registry.populate_tile_map(
                game.tile_map, "overworld")

        # ── Restore the party ───────────────────────────────────
        game.party = _deserialize_party(save_data["party"])

        # ── Restore cleared dungeon tiles ───────────────────────
        for pos in save_data.get("cleared_dungeons", []):
            c, r = pos
            game.tile_map.set_tile(c, r, TILE_DUNGEON_CLEARED)

        # ── Restore darkness effect ─────────────────────────────
        game.darkness_active = save_data.get("darkness_active", False)

        # ── Restore Keys of Shadow module state ─────────────────
        game.keys_inserted = save_data.get("keys_inserted", 0)
        game.machine_col = save_data.get("machine_col")
        game.machine_row = save_data.get("machine_row")
        game._gnome_quest_accepted = save_data.get(
            "gnome_quest_accepted", False)

        # Restore key dungeon levels and quest statuses from save
        _restore_key_dungeons(game, save_data)

        # ── Restore standard quest and house quest ──────────────
        _restore_quest(game, save_data, "quest")
        _restore_quest(game, save_data, "house_quest")

        # ── Restore game log ────────────────────────────────────
        game.game_log = list(save_data.get("game_log", []))

        # ── Restore visited dungeons ──────────────────────────
        game.visited_dungeons = {tuple(pos) for pos in save_data.get("visited_dungeons", [])}

        # ── Restore dungeon cache (random dungeon persistence) ──
        game.dungeon_cache = {}
        for entry in save_data.get("dungeon_cache", []):
            col, row = entry["col"], entry["row"]
            levels_data = entry.get("levels", [])
            if levels_data:
                game.dungeon_cache[(col, row)] = _deserialize_dungeon_levels(
                    levels_data)

        # ── Reset transient state ───────────────────────────────
        game.pending_combat_rewards = None

        # ── Restore quest NPC assignments (before town generation) ─
        game.quest_npc_assignments = save_data.get(
            "quest_npc_assignments", {})

        # ── Restore module quest states (before NPC injection so
        #    completed quests stay completed) ─
        saved_mqs = save_data.get("module_quest_states", {})
        if saved_mqs:
            game.module_quest_states = saved_mqs

        # ── Restore towns (module-specific) ─────────────────────
        if game.module_manifest:
            mod_id = game.module_manifest.get(
                "metadata", {}).get("id", "")
            prog = game.module_manifest.get("progression", {})
            kd_list = prog.get("key_dungeons", [])
            if kd_list:
                if mod_id == "keys_of_shadow":
                    from src.town_generator import generate_duskhollow
                    game.town_data = generate_duskhollow()
                else:
                    # Regenerate all towns from the manifest
                    game._init_module_towns()

        # ── Re-inject quest-giver NPCs into towns ──────────────
        # (Must run after _init_module_towns so town data exists)
        game._inject_module_quest_npcs()

        # ── Restore the player to the correct state ────────────
        state_ctx = save_data.get("state_context", {})
        target_state = state_ctx.get("state", "overworld")

        if target_state == "dungeon":
            _restore_dungeon_state(game, state_ctx)
        elif target_state == "town":
            _restore_town_state(game, state_ctx)
        else:
            # Default: overworld
            game.change_state("overworld")
            game.camera.update(game.party.col, game.party.row)

        return True
    except Exception:
        return False


def _restore_key_dungeons(game, save_data):
    """Restore key dungeon levels and quest statuses from save data.

    If the save file contains serialized dungeon levels (v3+ saves),
    those are restored directly — preserving explored tiles, opened
    chests, triggered traps, and killed monsters.  Otherwise falls
    back to regenerating fresh dungeons (backward compat with old saves).
    """
    from src.dungeon_generator import generate_keys_dungeon

    saved_kds = save_data.get("key_dungeons", [])
    if not saved_kds:
        game.key_dungeons = {}
        return

    if not getattr(game, "key_dungeons", {}):
        game.key_dungeons = {}

    for skd in saved_kds:
        col, row = skd["col"], skd["row"]
        dnum = skd["dungeon_number"]
        name = skd.get("name", f"Key Dungeon {dnum}")
        key_name = skd.get("key_name", f"Key {dnum}")
        status = skd.get("status", "active")

        quest_type = skd.get("quest_type", "retrieve")
        # Module-defined encounter specs (may not be in old saves)
        module_levels = skd.get("module_levels") or None

        # Restore serialized levels if present, otherwise regenerate
        saved_levels = skd.get("levels")
        needs_artifact = (quest_type != "kill")
        if saved_levels and isinstance(saved_levels, list) and saved_levels:
            # Check if first entry is a dict (serialized DungeonData)
            if isinstance(saved_levels[0], dict):
                levels = _deserialize_dungeon_levels(saved_levels)
            else:
                levels = generate_keys_dungeon(
                    dnum, name=name, place_artifact=needs_artifact,
                    module_levels=module_levels)
        else:
            levels = generate_keys_dungeon(
                dnum, name=name, place_artifact=needs_artifact,
                module_levels=module_levels)

        game.key_dungeons[(col, row)] = {
            "dungeon_number": dnum,
            "name": name,
            "key_name": key_name,
            "levels": levels,
            "current_level": skd.get("current_level", 0),
            "status": status,
            "dungeon_col": col,
            "dungeon_row": row,
            "artifact_name": skd.get("artifact_name", key_name),
            "description": skd.get("description", ""),
            "quest_objective": skd.get("quest_objective", ""),
            "quest_hint": skd.get("quest_hint", ""),
            "quest_type": quest_type,
            "kill_target": skd.get("kill_target", ""),
            "kill_count": int(skd.get("kill_count", 0)),
            "module_levels": skd.get("module_levels"),
            "kill_progress": int(skd.get("kill_progress", 0)),
            "exit_portal": skd.get("exit_portal", True),
            "keys_needed": int(skd.get("keys_needed", 1)),
            "gnome_town": skd.get("gnome_town", ""),
        }


def _restore_quest(game, save_data, quest_attr):
    """Restore a quest (quest or house_quest) from save data.

    If serialized dungeon levels are present in the save, they're
    restored directly to preserve dungeon state.  Otherwise falls
    back to regenerating fresh dungeons (backward compat).
    """
    saved_q = save_data.get(quest_attr)
    if saved_q is None:
        setattr(game, quest_attr, None)
        return

    status = saved_q.get("status", "active")
    dcol = saved_q.get("dungeon_col")
    drow = saved_q.get("dungeon_row")
    artifact = saved_q.get("artifact_name", "Shadow Crystal")
    name = saved_q.get("name")

    quest = {
        "status": status,
        "dungeon_col": dcol,
        "dungeon_row": drow,
        "artifact_name": artifact,
        "current_level": saved_q.get("current_level", 0),
        "quest_type": saved_q.get("quest_type", "retrieve"),
        "kill_target": saved_q.get("kill_target"),
        "kill_count": int(saved_q.get("kill_count", 0)),
        "kill_progress": int(saved_q.get("kill_progress", 0)),
        "exit_portal": saved_q.get("exit_portal", True),
    }
    if name:
        quest["name"] = name

    # Restore dungeon levels for active/in-progress quests
    if status in ("active", "artifact_found") and dcol is not None:
        saved_levels = saved_q.get("levels")
        if saved_levels and isinstance(saved_levels, list) and saved_levels:
            if isinstance(saved_levels[0], dict):
                quest["levels"] = _deserialize_dungeon_levels(saved_levels)
            else:
                # Old save format — regenerate
                from src.dungeon_generator import (generate_dungeon,
                                                    generate_house_dungeon)
                if quest_attr == "house_quest":
                    quest["levels"] = generate_house_dungeon()
                else:
                    quest["levels"] = [generate_dungeon(
                        name or "Shadow Crystal Dungeon")]
        else:
            # No levels saved — regenerate
            from src.dungeon_generator import (generate_dungeon,
                                                generate_house_dungeon)
            if quest_attr == "house_quest":
                quest["levels"] = generate_house_dungeon()
            else:
                quest["levels"] = [generate_dungeon(
                    name or "Shadow Crystal Dungeon")]

    setattr(game, quest_attr, quest)


def _restore_dungeon_state(game, ctx):
    """Re-enter a dungeon from saved state context.

    Locates the correct dungeon levels (key dungeon, quest, house quest,
    or cached random dungeon) using the saved overworld coordinates,
    sets up the DungeonState, and restores the party's position inside
    the dungeon.
    """
    ow_col = ctx.get("overworld_col", 0)
    ow_row = ctx.get("overworld_row", 0)
    level_idx = ctx.get("current_level", 0)
    dungeon_state = game.states["dungeon"]

    # Try key dungeon first
    kd = game.key_dungeons.get((ow_col, ow_row))
    if kd and kd.get("levels"):
        dungeon_state.enter_quest_dungeon(kd["levels"], ow_col, ow_row)
    else:
        # Check standard quest
        quest = getattr(game, "quest", None)
        hq = getattr(game, "house_quest", None)
        if (quest and quest.get("dungeon_col") == ow_col
                and quest.get("dungeon_row") == ow_row
                and quest.get("levels")):
            dungeon_state.enter_quest_dungeon(quest["levels"], ow_col, ow_row)
        elif (hq and hq.get("dungeon_col") == ow_col
              and hq.get("dungeon_row") == ow_row
              and hq.get("levels")):
            dungeon_state.enter_quest_dungeon(hq["levels"], ow_col, ow_row)
        else:
            # Random / cached dungeon
            cached = game.dungeon_cache.get((ow_col, ow_row))
            if cached:
                dungeon_state.enter_dungeon(cached[0], ow_col, ow_row)
            else:
                # Fallback: cannot find dungeon data, go to overworld
                game.change_state("overworld")
                game.camera.update(game.party.col, game.party.row)
                return

    # Advance to the correct level if multi-level
    if dungeon_state.quest_levels and level_idx < len(dungeon_state.quest_levels):
        dungeon_state.current_level = level_idx
        dungeon_state.dungeon_data = dungeon_state.quest_levels[level_idx]

    game.change_state("dungeon")

    # Restore party position inside the dungeon (override the entry point)
    if "party_col" in ctx and "party_row" in ctx:
        game.party.col = ctx["party_col"]
        game.party.row = ctx["party_row"]

    # Restore torch state
    dungeon_state.torch_active = ctx.get("torch_active", False)
    dungeon_state.torch_steps = ctx.get("torch_steps", 0)

    # Update camera for dungeon dimensions
    if dungeon_state.dungeon_data:
        game.camera.map_width = dungeon_state.dungeon_data.tile_map.width
        game.camera.map_height = dungeon_state.dungeon_data.tile_map.height
    game.camera.update(game.party.col, game.party.row)


def _restore_town_state(game, ctx):
    """Re-enter a town from saved state context.

    Looks up the correct TownData using the saved overworld coordinates,
    sets up the TownState, and restores the party's position inside
    the town.
    """
    ow_col = ctx.get("overworld_col", 0)
    ow_row = ctx.get("overworld_row", 0)
    town_state = game.states["town"]

    # Look up the town data for these coordinates
    town_data = game.get_town_at(ow_col, ow_row)
    game.town_data = town_data
    town_state.enter_town(town_data, ow_col, ow_row)
    game.change_state("town")

    # Restore party position inside the town (override the entry point)
    if "party_col" in ctx and "party_row" in ctx:
        game.party.col = ctx["party_col"]
        game.party.row = ctx["party_row"]

    # Update camera for town dimensions
    if town_state.town_data:
        game.camera.map_width = town_state.town_data.tile_map.width
        game.camera.map_height = town_state.town_data.tile_map.height
    game.camera.update(game.party.col, game.party.row)


def get_save_info(slot):
    """Return summary info about a save slot, or None if empty.

    Returns
    -------
    dict or None
        {"slot": int, "timestamp": float, "state": str,
         "party_names": list[str], "gold": int, "level_avg": float,
         "module_name": str or None}
    """
    path = _save_path(slot)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        party_data = data.get("party", {})
        members = party_data.get("members", [])
        names = [m.get("name", "???") for m in members]
        levels = [m.get("level", 1) for m in members]
        avg_level = sum(levels) / len(levels) if levels else 1

        return {
            "slot": slot,
            "timestamp": data.get("timestamp", 0),
            "state": data.get("state", "overworld"),
            "party_names": names,
            "gold": party_data.get("gold", 0),
            "level_avg": avg_level,
            "module_name": data.get("module_name"),
        }
    except Exception:
        return None


def quick_save(game):
    """Save the current game state to the Quick Save slot.

    Returns True if saved successfully, False on error.
    Does nothing (returns False) if the game is in combat or examine state.
    """
    # Determine current state name
    state_name = "overworld"
    for name, state_obj in game.states.items():
        if state_obj is game.current_state:
            state_name = name
            break

    # Block saving during combat or examine
    if state_name in ("combat", "examine"):
        return False

    return save_game(QUICK_SAVE_SLOT, game)


def delete_save(slot):
    """Delete a save file. Returns True if deleted."""
    path = _save_path(slot)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False
