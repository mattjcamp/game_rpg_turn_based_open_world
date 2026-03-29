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


def _location_matches(step_location, combat_location):
    """Return True if *combat_location* satisfies *step_location*.

    Matching rules:
    - ``"overview"`` or ``"Overview Map"`` steps match combat in
      ``"overview"`` (overworld random encounters & quest monsters).
    - Location-specific steps (``"town:Yardley"``, ``"dungeon:X"``,
      ``"interior:Town/Area"``, ``"space:Building/Space"``,
      ``"building:Name"``) must match exactly (case-insensitive).
    - If *step_location* is empty or missing, any location counts.
    """
    if not step_location or step_location in ("overview", "Overview Map"):
        # Overworld steps — only satisfied by overworld combat
        return combat_location in ("overview", "overworld", "")
    if not combat_location:
        return False
    return step_location.lower() == combat_location.lower()


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
    from collections import Counter

    killed = getattr(game, "pending_killed_monsters", [])
    if not killed:
        return None

    combat_location = getattr(game, "pending_combat_location", "")

    mq_states = getattr(game, "module_quest_states", {})
    quest_defs = getattr(game, "_module_quest_defs", [])

    killed_counts = Counter()
    for name in killed:
        display = name.replace("_", " ").title()
        killed_counts[display] += 1
        killed_counts[name] += 1

    result_msg = None

    for qdef in quest_defs:
        qname = qdef.get("name", "")
        if not qname:
            continue
        state = mq_states.get(qname, {})
        if state.get("status") != "active":
            continue

        steps = qdef.get("steps", [])
        progress = state.get("step_progress", [])

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

            monster_key = monster_display.lower().replace(" ", "_")
            match_count = max(
                killed_counts.get(monster_display, 0),
                killed_counts.get(monster_key, 0))

            if match_count <= 0:
                continue

            kills_so_far = state.get(f"step_{i}_kills", 0) + match_count
            state[f"step_{i}_kills"] = kills_so_far

            if kills_so_far >= target_count:
                progress[i] = True
                desc = step.get("description", "Kill step")
                result_msg = f"Quest '{qname}': {desc} - Complete!"
                game.sfx.play("treasure")

        if all(progress) and progress:
            if state["status"] != "completed":
                state["status"] = "completed"
                result_msg = (
                    "All steps done! Return to the quest "
                    "giver for your reward.")

    game.pending_killed_monsters = []
    game.pending_combat_location = ""
    return result_msg
