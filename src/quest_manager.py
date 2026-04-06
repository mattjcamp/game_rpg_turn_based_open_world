"""Shared quest logic used by town, dungeon, and overworld states.

Centralizes quest item collection, kill tracking, and step completion
to eliminate duplication across state files.
"""


def collect_quest_item(game, quest_name, step_idx, item_name):
    """Mark a quest collect step as complete and return a UI message.

    The caller is responsible for removing the item from its own container
    (town_data.npcs, _building_interior_npcs, dungeon_data.quest_items, etc.)
    BEFORE calling this function.

    Args:
        game: The Game instance (has module_quest_states, sfx)
        quest_name: Quest name string
        step_idx: Step index in the quest
        item_name: Display name of the collected item

    Returns:
        str: Message to display to the player
    """
    mq_states = getattr(game, "module_quest_states", {})
    if quest_name and quest_name in mq_states:
        qstate = mq_states[quest_name]
        progress = qstate.get("step_progress", [])
        if step_idx < len(progress):
            progress[step_idx] = True
            if all(progress):
                qstate["status"] = "completed"
                game.sfx.play("treasure")
                return f"Collected {item_name}! Quest complete!"
            else:
                game.sfx.play("treasure")
                return f"Collected {item_name}!"
        else:
            game.sfx.play("treasure")
            return f"Collected {item_name}!"
    game.sfx.play("treasure")
    return f"Found {item_name}!"


def _normalize_monster_name(name):
    """Build a set of plausible lookup keys for a monster name.

    Monster names can appear in several forms depending on whether
    they come from the quest JSON ("Giant Rat"), the monster dict key
    ("giant_rat"), or the Monster object's ``.name`` attribute
    ("Giant Rat").  We generate all common variants so a match is
    found regardless of which form is stored.
    """
    if not name:
        return set()
    keys = set()
    keys.add(name)                               # original
    keys.add(name.lower())                        # lowercase
    keys.add(name.replace(" ", "_").lower())      # snake_case
    keys.add(name.replace("_", " ").title())      # Title Case
    keys.add(name.replace("_", " ").lower())      # lower with spaces
    return keys


def _location_matches(step_location, combat_location):
    """Return True if *combat_location* satisfies *step_location*.

    Matching rules:
    - If *step_location* is empty or missing, any location counts.
    - ``"overview"`` or ``"Overview Map"`` steps match combat in
      ``"overview"`` (overworld random encounters & quest monsters).
    - ``"building:Name"`` steps are satisfied by combat in any space
      within that building (``"space:Name/SpaceName"``), as well as
      an exact ``"building:Name"`` match.
    - Other location-specific steps (``"town:Yardley"``,
      ``"dungeon:X"``, ``"interior:Town/Area"``,
      ``"space:Building/Space"``) must match exactly
      (case-insensitive).
    """
    # No location requirement — any combat location satisfies the step
    if not step_location:
        return True
    # Overworld steps — only satisfied by overworld combat
    if step_location in ("overview", "Overview Map"):
        return combat_location in ("overview", "overworld", "")
    if not combat_location:
        return False
    sl = step_location.lower()
    cl = combat_location.lower()
    if sl == cl:
        return True
    # A "building:X" step is satisfied by combat in any space of that
    # building, i.e. "space:X/Y".
    if sl.startswith("building:"):
        bld_name = sl[len("building:"):]
        if cl.startswith("space:") and cl[len("space:"):].startswith(
                bld_name + "/"):
            return True
    # A "dungeon:X" step is satisfied by combat on any floor of that
    # dungeon, i.e. "dungeon:X - Floor N".
    if sl.startswith("dungeon:"):
        base = sl[len("dungeon:"):]
        if cl.startswith("dungeon:"):
            cl_base = cl[len("dungeon:"):]
            # Strip " - floor N" suffix from the combat location
            import re
            cl_stripped = re.sub(r"\s*-\s*floor\s+\d+$", "", cl_base)
            if cl_stripped == base:
                return True
    return False


def check_quest_kills(game):
    """Check if any pending killed monsters satisfy quest kill steps.

    Reads ``game.pending_killed_monsters`` and
    ``game.pending_combat_location``, matches against active quest
    kill steps **only when the combat location matches the step's
    spawn_location**, updates progress, and clears the pending list.

    Args:
        game: The Game instance

    Returns:
        str or None: Completion message, or None if no progress
    """
    killed = getattr(game, "pending_killed_monsters", [])
    if not killed:
        return None

    combat_location = getattr(game, "pending_combat_location", "")

    mq_states = getattr(game, "module_quest_states", {})
    quest_defs = getattr(game, "_module_quest_defs", [])

    # Build a lookup of killed monster names using all common variants
    # so that e.g. "Giant Rat", "giant_rat", and "giant rat" all match.
    killed_name_sets = [_normalize_monster_name(n) for n in killed]
    # Flatten: map each variant -> count of kills
    killed_counts = {}
    for name_set in killed_name_sets:
        for variant in name_set:
            killed_counts[variant] = killed_counts.get(variant, 0) + 1

    messages = []

    for qdef in quest_defs:
        qname = qdef.get("name", "")
        if not qname:
            continue
        state = mq_states.get(qname, {})
        if state.get("status") != "active":
            continue

        steps = qdef.get("steps", [])
        progress = state.get("step_progress", [])

        # Guard against mismatched step_progress length (e.g. quest
        # was updated after game started).  Extend with False entries.
        if len(progress) < len(steps):
            progress.extend([False] * (len(steps) - len(progress)))
            state["step_progress"] = progress

        for i, step in enumerate(steps):
            if i >= len(progress) or progress[i]:
                continue
            if step.get("step_type") != "kill":
                continue
            monster_display = step.get("monster", "")
            if not monster_display:
                continue

            # Only credit kills that happened at the right location
            step_location = step.get("spawn_location", "")
            if not _location_matches(step_location, combat_location):
                continue

            target_count = max(1, step.get("target_count", 1))

            # Match against all name variants for the quest monster
            monster_variants = _normalize_monster_name(monster_display)
            match_count = 0
            for variant in monster_variants:
                match_count = max(match_count,
                                  killed_counts.get(variant, 0))

            if match_count <= 0:
                continue

            kills_so_far = state.get(f"step_{i}_kills", 0) + match_count
            state[f"step_{i}_kills"] = kills_so_far

            if kills_so_far >= target_count:
                progress[i] = True
                desc = step.get("description", "Kill step")
                messages.append(
                    f"Quest '{qname}': {desc} - Complete!")
                game.sfx.play("treasure")
            else:
                # Show progress toward completing this step
                display_name = monster_display.replace("_", " ").title()
                messages.append(
                    f"{display_name} defeated! "
                    f"({kills_so_far}/{target_count})")

        if all(progress) and progress:
            if state["status"] != "completed":
                state["status"] = "completed"
                messages.append(
                    "All steps done! Return to the quest "
                    "giver for your reward.")

    game.pending_killed_monsters = []
    game.pending_combat_location = ""
    return " | ".join(messages) if messages else None
