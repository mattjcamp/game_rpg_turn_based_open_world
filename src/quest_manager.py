"""Shared quest logic used by town, dungeon, and overworld states.

Centralizes quest item collection, kill tracking, and step completion
to eliminate duplication across state files.
"""


def _coerce_int(value):
    """Best-effort int parse — returns ``None`` on blank / non-numeric.

    Used for the optional ``spawn_col`` / ``spawn_row`` overrides on
    collect steps, which authors leave blank when they want random
    placement.  Empty strings, ``None``, and unparseable values all
    map to ``None`` so ``pick_quest_item_position`` treats them as
    "no override".
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def pick_quest_item_position(item_info, walkable, occupied, rng):
    """Choose a tile for a quest collectible.

    Honors the optional ``spawn_col`` / ``spawn_row`` override on
    ``item_info`` when both are present, non-negative, and resolve to
    a walkable tile that isn't already occupied.  Otherwise falls
    back to a random walkable, unoccupied tile and prints a warning
    to the console (so the author can spot mis-placed coordinates
    during testing).

    Parameters
    ----------
    item_info : dict
        Per-item registration carrying at minimum ``item_name``;
        ``spawn_col`` and ``spawn_row`` are optional.
    walkable : iterable of (col, row)
        Every walkable tile in the destination map.  May be a list
        or set; the function handles both.
    occupied : set of (col, row)
        Tiles already taken (other NPCs, exits, etc.).
    rng : random.Random
        Source of randomness for the fallback path so callers stay
        deterministic across save/load.

    Returns
    -------
    (col, row) tuple, or ``None`` if no suitable tile exists.
    """
    walkable_set = walkable if isinstance(walkable, set) else set(walkable)

    sc = _coerce_int(item_info.get("spawn_col"))
    sr = _coerce_int(item_info.get("spawn_row"))

    if sc is not None and sr is not None and sc >= 0 and sr >= 0:
        pos = (sc, sr)
        if pos in walkable_set and pos not in occupied:
            return pos
        # Authors usually want to know when their override didn't
        # land on a valid tile.  Print rather than log so headless
        # tests don't need a logging fixture.
        print(
            f"[quest] Spawn coord ({sc},{sr}) for "
            f"{item_info.get('item_name', '?')!r} is invalid "
            f"(not walkable or occupied) — falling back to random."
        )

    free = [p for p in walkable_set if p not in occupied]
    if not free:
        return None
    return rng.choice(free)


def build_quest_location_hint(qdef):
    """Return a human-readable notice of dungeon locations referenced by
    a quest's steps, or an empty string if the quest doesn't involve any
    dungeons.

    This is appended to the quest giver's dialogue when a quest is first
    offered so the player clearly knows they're signing up for a dungeon
    crawl (e.g. the Goblin Stronghold) rather than a surface-level
    errand.  Collect-step ``has_guardian`` flags are also surfaced so
    the player knows to expect a boss fight for artifact retrieval.
    """
    if not qdef:
        return ""
    steps = qdef.get("steps", []) or []
    dungeon_names = []
    has_guardian = False
    for step in steps:
        loc = step.get("spawn_location", "") or ""
        if loc.startswith("dungeon:"):
            name = loc[len("dungeon:"):].strip()
            if name and name not in dungeon_names:
                dungeon_names.append(name)
        if step.get("has_guardian") == "yes":
            has_guardian = True
    if not dungeon_names:
        return ""
    if len(dungeon_names) == 1:
        line = (f"[Adventurer's Note: This quest will take you into "
                f"the {dungeon_names[0]} dungeon — tread carefully.]")
    else:
        joined = ", ".join(dungeon_names[:-1]) + f" and {dungeon_names[-1]}"
        line = (f"[Adventurer's Note: This quest will take you into "
                f"the following dungeons: {joined}.]")
    if has_guardian:
        line = line[:-1] + " A powerful guardian is said to watch over "
        line += "what you seek.]"
    return line


def augment_quest_dialogue(dialogue_lines, qdef):
    """Return a copy of *dialogue_lines* with a dungeon hint appended when
    the quest involves a dungeon.

    Always returns a list.  Safe to call with ``None``/missing data —
    this makes the call-site one-liner free of defensive checks.
    """
    lines = list(dialogue_lines or [])
    hint = build_quest_location_hint(qdef)
    if hint:
        lines.append(hint)
    return lines


def queue_quest_step_callout(game, quest_name, step_desc, quest_complete=False):
    """Push a quest-step-completion callout onto the game's pending list.

    The active state's mixin drains ``game.pending_quest_callouts`` each
    update tick into its own animation queue so the on-screen banner runs
    on the same lifecycle as level-up callouts.  ``quest_complete=True``
    flags the entry so the renderer can show a different title (e.g.
    "QUEST COMPLETE!" instead of "STEP COMPLETE").
    """
    if not hasattr(game, "pending_quest_callouts"):
        game.pending_quest_callouts = []
    game.pending_quest_callouts.append({
        "quest": quest_name or "",
        "desc": step_desc or "",
        "quest_complete": bool(quest_complete),
    })


def _resolve_step_description(qdef, step_idx):
    """Pull a human-readable label off the quest step (falls back to a
    generic 'Step N complete')."""
    steps = (qdef or {}).get("steps", []) or []
    if 0 <= step_idx < len(steps):
        step = steps[step_idx]
        for key in ("description", "summary", "name", "title"):
            v = step.get(key)
            if v:
                return str(v)
    return f"Step {step_idx + 1} complete"


def _find_quest_def(game, quest_name):
    for qd in getattr(game, "_module_quest_defs", []) or []:
        if qd.get("name") == quest_name:
            return qd
    return None


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
            qdef = _find_quest_def(game, quest_name)
            step_desc = _resolve_step_description(qdef, step_idx)
            if all(progress):
                qstate["status"] = "completed"
                game.sfx.play("treasure")
                queue_quest_step_callout(
                    game, quest_name, step_desc, quest_complete=True)
                return f"Collected {item_name}! Quest complete!"
            else:
                game.sfx.play("treasure")
                queue_quest_step_callout(game, quest_name, step_desc)
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


def _is_localized_step(step_location):
    """Return True for steps that pin the encounter to a specific
    place (dungeon, town, building, interior, space).

    Localized steps require the killed monster to actually be the
    quest-tagged spawn at that location. Without this, a player can
    accidentally finish e.g. "Slay the Ancient Dragon — Floor 10" by
    killing a random Dragon on floor 1, because every monster in the
    encounter's roster shares the name. Overview/overworld steps stay
    on the legacy roster-name match for back-compat with quests like
    "kill 5 goblins anywhere on the map".
    """
    if not step_location:
        return False
    sl = step_location.lower()
    if sl in ("overview", "overview map"):
        return False
    return (
        sl.startswith("dungeon:")
        or sl.startswith("town:")
        or sl.startswith("building:")
        or sl.startswith("interior:")
        or sl.startswith("space:")
    )


def check_quest_kills(game):
    """Check if any pending killed monsters satisfy quest kill steps.

    Reads ``game.pending_killed_monsters`` and
    ``game.pending_combat_location``, matches against active quest
    kill steps **only when the combat location matches the step's
    spawn_location**, updates progress, and clears the pending list.

    Kill steps now target an *encounter* (a named group from
    encounters.json). A step gets ``+1`` credit per combat in which
    any monster from that encounter's roster is defeated at the
    matching location — i.e. one completed encounter battle = one
    step credit, regardless of how many monsters were in the group.

    For steps localized to a specific place (dungeon, town, building,
    interior, space) the killed monster must additionally bear the
    matching quest tag — otherwise random encounters that happen to
    share the boss's name would credit the quest. Overview/overworld
    steps still credit roster-name matches alone for back-compat.

    Args:
        game: The Game instance

    Returns:
        str or None: Completion message, or None if no progress
    """
    from src.monster import find_encounter_template

    killed = getattr(game, "pending_killed_monsters", [])
    if not killed:
        return None

    combat_location = getattr(game, "pending_combat_location", "")
    # Set of (quest_name, step_idx) for monsters that were placed by
    # the quest spawner. Populated in CombatState._trigger_victory.
    killed_quest_tag_keys = {
        (t["quest_name"], int(t["step_idx"]))
        for t in getattr(game, "pending_killed_quest_tags", []) or []
        if isinstance(t, dict) and "quest_name" in t and "step_idx" in t
    }

    mq_states = getattr(game, "module_quest_states", {})
    quest_defs = getattr(game, "_module_quest_defs", [])

    # Build a lookup of killed monster names using all common variants
    # so that e.g. "Giant Rat", "giant_rat", and "giant rat" all match.
    killed_name_sets = [_normalize_monster_name(n) for n in killed]
    killed_variants = set()
    for name_set in killed_name_sets:
        killed_variants.update(name_set)

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
            encounter_name = step.get("encounter", "")
            if not encounter_name:
                continue

            # Only credit kills that happened at the right location
            step_location = step.get("spawn_location", "")
            if not _location_matches(step_location, combat_location):
                continue

            # Resolve the encounter's roster; a kill counts if any of
            # those monsters shows up in pending_killed_monsters.
            enc_tmpl = find_encounter_template(encounter_name)
            if enc_tmpl:
                roster = enc_tmpl.get("monsters", [])
            else:
                # Template missing (e.g. module removed an encounter
                # after the quest was authored) — nothing to credit.
                continue

            roster_hit = False
            for mname in roster:
                if _normalize_monster_name(mname) & killed_variants:
                    roster_hit = True
                    break
            if not roster_hit:
                continue

            # For localized steps, additionally require that one of
            # the killed monsters carried this quest's tag — i.e. it
            # was the spawn the quest placed, not a random encounter
            # that happened to share the boss's name.
            if _is_localized_step(step_location):
                if (qname, i) not in killed_quest_tag_keys:
                    continue

            # One encounter cleared = one credit toward target_count.
            target_count = max(1, step.get("target_count", 1))
            kills_so_far = state.get(f"step_{i}_kills", 0) + 1
            state[f"step_{i}_kills"] = kills_so_far

            if kills_so_far >= target_count:
                progress[i] = True
                desc = step.get("description", "Kill step")
                messages.append(
                    f"Quest '{qname}': {desc} - Complete!")
                game.sfx.play("treasure")
                # Queue an on-screen callout so the player sees the step
                # land even if the message log scrolls off-screen.
                quest_done = all(progress) and progress
                queue_quest_step_callout(
                    game, qname, desc, quest_complete=quest_done)
            else:
                messages.append(
                    f"{encounter_name} defeated! "
                    f"({kills_so_far}/{target_count})")

        if all(progress) and progress:
            if state["status"] != "completed":
                state["status"] = "completed"
                messages.append(
                    "All steps done! Return to the quest "
                    "giver for your reward.")

    game.pending_killed_monsters = []
    game.pending_killed_quest_tags = []
    game.pending_combat_location = ""
    return " | ".join(messages) if messages else None
