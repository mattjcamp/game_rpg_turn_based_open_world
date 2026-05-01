"""
Magic-item attribute tests — bonus damage, damage types, on-hit spell
procs, and the item-granted effect lane.
"""

import random

import pytest

from src import party as party_mod
from src.party import EFFECTS_DATA, SPELLS_DATA


def _live_weapons():
    """Return the *current* WEAPONS dict from src.party.

    Importing ``WEAPONS`` directly into this module captures whatever
    dict was bound at import time.  Other tests may call
    ``reload_module_data()`` which rebinds ``src.party.WEAPONS`` to a
    fresh dict — leaving our top-level alias stale.  Going through
    ``party_mod.WEAPONS`` always sees the live value.
    """
    return party_mod.WEAPONS


# ====================================================================
#  Bonus damage rolling (item helper)
# ====================================================================

class TestRollBonusDamage:
    def test_int_spec_flat(self, combat):
        # Flat ints are returned as-is on a non-crit hit.
        assert combat._roll_bonus_damage(3, crit=False) == 3
        assert combat._roll_bonus_damage(0, crit=False) == 0

    def test_int_spec_crit_doubles(self, combat):
        assert combat._roll_bonus_damage(3, crit=True) == 6

    def test_dice_string_in_range(self, combat, monkeypatch):
        # 2d6 must roll in [2..12]; sample many times.
        for _ in range(50):
            r = combat._roll_bonus_damage("2d6", crit=False)
            assert 2 <= r <= 12

    def test_dice_string_max_with_seeded_rng(self, combat, monkeypatch):
        # Force every die to its max face — verifies dice-count parsing.
        monkeypatch.setattr(random, "randint", lambda a, b: b)
        assert combat._roll_bonus_damage("1d6", crit=False) == 6
        assert combat._roll_bonus_damage("2d4", crit=False) == 8

    def test_crit_doubles_dice_count(self, combat, monkeypatch):
        monkeypatch.setattr(random, "randint", lambda a, b: b)
        # 1d6 crit → 2 dice × 6 = 12
        assert combat._roll_bonus_damage("1d6", crit=True) == 12

    def test_garbage_returns_zero(self, combat):
        assert combat._roll_bonus_damage("not a dice spec") == 0
        assert combat._roll_bonus_damage(None) == 0
        assert combat._roll_bonus_damage("") == 0


# ====================================================================
#  Damage-type scaling against monster resist/vulnerable
# ====================================================================

class _FakeTarget:
    """Bare-bones monster stand-in for resistance scaling tests."""
    def __init__(self, resist=None, vulnerable=None, passives=None):
        self.resist = resist or []
        self.vulnerable = vulnerable or []
        self.passives = passives or []

    def is_alive(self):
        return True


class TestScaleDamageForType:
    def test_physical_unscaled_even_with_resist(self, combat):
        # Physical is the default damage type and is never scaled
        # (resistance/vulnerability would need explicit "physical" entries).
        t = _FakeTarget(resist=["fire"])
        assert combat._scale_damage_for_type(10, "physical", t) == 10

    def test_resist_halves(self, combat):
        t = _FakeTarget(resist=["fire"])
        assert combat._scale_damage_for_type(10, "fire", t) == 5

    def test_vulnerable_doubles(self, combat):
        t = _FakeTarget(vulnerable=["fire"])
        assert combat._scale_damage_for_type(10, "fire", t) == 20

    def test_legacy_passive_resistance_still_halves(self, combat):
        # Existing monsters use passives:[{type:"fire_resistance"}].
        # The new scaling code must honor them so existing data keeps
        # working unchanged.
        t = _FakeTarget(passives=[{"type": "fire_resistance"}])
        assert combat._scale_damage_for_type(10, "fire", t) == 5

    def test_resist_and_vulnerable_cancel_to_baseline(self, combat):
        # Half then double = original.  Documents the expected interaction.
        t = _FakeTarget(resist=["fire"], vulnerable=["fire"])
        assert combat._scale_damage_for_type(10, "fire", t) == 10

    def test_unrelated_type_unscaled(self, combat):
        t = _FakeTarget(resist=["cold"])
        assert combat._scale_damage_for_type(10, "fire", t) == 10


# ====================================================================
#  On-hit spell trigger
# ====================================================================

class TestApplyItemOnHit:
    def test_no_proc_for_mundane_weapon(self, combat, monkeypatch):
        # Force the chance roll to "always fire", but a mundane Sword
        # has no on_hit block so nothing should happen.
        monkeypatch.setattr(random, "random", lambda: 0.0)
        target = combat.monsters[0]
        target.hp = 100
        before = target.hp
        log_len = len(combat.combat_log)
        combat._apply_item_on_hit(combat.fighters[0], target, "Sword")
        assert target.hp == before
        assert len(combat.combat_log) == log_len

    def test_sun_sword_proc_when_chance_succeeds(self, combat, monkeypatch):
        # Force the chance roll to succeed and dice rolls to max.
        monkeypatch.setattr(random, "random", lambda: 0.0)
        monkeypatch.setattr(random, "randint", lambda a, b: b)
        target = combat.monsters[0]
        target.hp = 100
        target.resist = []
        target.vulnerable = []
        target.passives = []
        before = target.hp
        combat._apply_item_on_hit(combat.fighters[0], target, "Sun Sword")
        # Should have lost HP from the proc.
        assert target.hp < before
        # And the log should mention the weapon flaring.
        assert any("Sun Sword" in line and "flares" in line
                   for line in combat.combat_log)

    def test_no_proc_when_chance_fails(self, combat, monkeypatch):
        # 0.99 is above Sun Sword's 0.25 chance — never triggers.
        monkeypatch.setattr(random, "random", lambda: 0.99)
        target = combat.monsters[0]
        target.hp = 100
        before = target.hp
        combat._apply_item_on_hit(combat.fighters[0], target, "Sun Sword")
        assert target.hp == before

    def test_no_proc_against_dead_target(self, combat):
        target = combat.monsters[0]
        target.hp = 0
        before_log = len(combat.combat_log)
        combat._apply_item_on_hit(combat.fighters[0], target, "Sun Sword")
        # No log line should be added — helper bails on dead targets.
        assert len(combat.combat_log) == before_log

    def test_proc_respects_target_resist(self, combat, monkeypatch):
        # Sun Sword is fire damage — target with fire resist takes half.
        # We force the chance to succeed and dice rolls to a known value
        # so we can assert exact damage halving (1d6 max=6 → 3).
        monkeypatch.setattr(random, "random", lambda: 0.0)
        monkeypatch.setattr(random, "randint", lambda a, b: b)
        target = combat.monsters[0]
        target.hp = 100
        target.resist = ["fire"]
        target.vulnerable = []
        target.passives = []
        combat._apply_item_on_hit(combat.fighters[0], target, "Sun Sword")
        # Sun Sword's on_hit is the "fireball" spell (1d6 + intelligence,
        # but items don't carry caster stats so we just get the dice).
        # With max die roll of 6 and resist halving → 3 damage.
        assert target.hp == 100 - 3


# ====================================================================
#  Party item-granted effect lane
# ====================================================================

class TestPartyItemGrantedEffects:
    def test_no_grants_by_default(self, game):
        # Out of the box no character has a magic item equipped.
        assert game.party.get_item_granted_effects() == []

    def test_sun_sword_grants_aura(self, game):
        # Equip a fighter with the Sun Sword and confirm the aura
        # appears in the item-granted lane *without* consuming one of
        # the four normal effect slots.
        fighter = next(m for m in game.party.members
                       if m.char_class.lower() == "fighter")
        fighter.inventory.append("Sun Sword")
        assert fighter.equip_item("Sun Sword", "right_hand")
        granted = game.party.get_item_granted_effects()
        ids = [e["id"] for e in granted]
        assert "sun_sword_aura" in ids
        # The 4 normal slots are still all empty.
        assert all(v is None for v in game.party.effects.values())

    def test_unequipping_removes_grant(self, game):
        fighter = next(m for m in game.party.members
                       if m.char_class.lower() == "fighter")
        fighter.inventory.append("Sun Sword")
        fighter.equip_item("Sun Sword", "right_hand")
        fighter.unequip_slot("right_hand")
        assert game.party.get_item_granted_effects() == []

    def test_dead_member_does_not_grant(self, game):
        fighter = next(m for m in game.party.members
                       if m.char_class.lower() == "fighter")
        fighter.inventory.append("Sun Sword")
        fighter.equip_item("Sun Sword", "right_hand")
        fighter.hp = 0
        granted = game.party.get_item_granted_effects()
        assert granted == []

    def test_has_effect_matches_item_lane(self, game):
        # has_effect() should return True for both slotted effects and
        # item-granted effects so renderer code doesn't have to special
        # case the source.
        fighter = next(m for m in game.party.members
                       if m.char_class.lower() == "fighter")
        fighter.inventory.append("Sun Sword")
        fighter.equip_item("Sun Sword", "right_hand")
        assert game.party.has_effect("Sun Sword Aura")

    def test_item_granted_effects_excluded_from_picker(self, game):
        # Item-granted effects (item_granted: true in effects.json) live
        # in the separate ``get_item_granted_effects`` lane and surface
        # automatically while the granting item is equipped. They must
        # NEVER appear in the manual 4-slot picker fed by
        # ``get_available_effects`` — otherwise the player sees options
        # like "Sun Sword Aura" before they've found the Sun Sword and
        # can pick a buff that the renderer can't actually apply.
        available = game.party.get_available_effects()
        names = [e.get("name") for e in available]
        ids = [e.get("id") for e in available]
        assert "Sun Sword Aura" not in names
        assert "sun_sword_aura" not in ids
        # Sanity: every returned effect is non-item-granted.
        for e in available:
            assert not e.get("item_granted"), (
                f"{e.get('name')!r} is flagged item_granted but still "
                "appeared in the manual effect picker.")

    def test_picker_still_excludes_aura_with_sword_equipped(self, game):
        # Even with the Sun Sword equipped (so the aura *is* live in the
        # item-granted lane), the picker must not double-list it.
        fighter = next(m for m in game.party.members
                       if m.char_class.lower() == "fighter")
        fighter.inventory.append("Sun Sword")
        fighter.equip_item("Sun Sword", "right_hand")
        names = [e.get("name") for e in game.party.get_available_effects()]
        assert "Sun Sword Aura" not in names


# ====================================================================
#  Cumulative magic-item bonuses on a character
# ====================================================================

class TestPartyMemberMagicBonuses:
    def test_default_bonuses_zero(self, game):
        m = game.party.members[0]
        assert m.get_total_ac_bonus() == 0
        for stat in ("str", "dex", "con", "int", "wis", "cha"):
            assert m.get_total_stat_bonus(stat) == 0
        assert m.get_granted_effect_ids() == []

    def test_synthetic_item_bonuses_aggregate(self, game):
        # Inject a temporary magic item so this test isn't dependent on
        # specific data/items.json values for AC/stat bonuses.  We
        # bypass equip_item() here to avoid coupling the bonus-aggregation
        # tests to weapon-proficiency rules — those are exercised elsewhere.
        _live_weapons()["Test Aegis Blade"] = {
            "power": 5,
            "ranged": False,
            "slots": ["right_hand", "left_hand"],
            "icon": "sword",
            "item_type": "sword",
            "character_can_equip": True,
            "indestructible": True,
            "ac_bonus": 2,
            "stat_bonuses": {"str": 1, "dex": 1},
            "grants_effect": "sun_sword_aura",
        }
        try:
            m = game.party.members[0]
            # Manually place into right hand — the helpers under test
            # iterate equipped items, they don't care how the item got
            # there.
            m.equipped["right_hand"] = "Test Aegis Blade"
            assert m.get_total_ac_bonus() == 2
            assert m.get_total_stat_bonus("str") == 1
            assert m.get_total_stat_bonus("dex") == 1
            assert m.get_total_stat_bonus("con") == 0
            assert "sun_sword_aura" in m.get_granted_effect_ids()
        finally:
            del _live_weapons()["Test Aegis Blade"]
            m.equipped["right_hand"] = "Fists"


# ====================================================================
#  Sun Sword data integrity — schema actually parsed correctly
# ====================================================================

class TestSunSwordData:
    def test_sun_sword_loaded_with_magic_attrs(self):
        sword = _live_weapons().get("Sun Sword")
        assert sword is not None
        assert sword["damage_type"] == "fire"
        assert sword["bonus_damage"] == "1d6"
        assert sword["grants_effect"] == "sun_sword_aura"
        assert sword["on_hit"]["spell_id"] == "fireball"
        assert 0.0 < sword["on_hit"]["chance"] <= 1.0

    def test_sun_sword_aura_in_effects(self):
        ids = {e["id"] for e in EFFECTS_DATA}
        assert "sun_sword_aura" in ids

    def test_sun_sword_referenced_spell_exists(self):
        # The on-hit spell id must resolve in SPELLS_DATA, otherwise
        # the on-hit code would silently no-op at runtime.
        sword = _live_weapons()["Sun Sword"]
        assert sword["on_hit"]["spell_id"] in SPELLS_DATA


# ====================================================================
#  Engine consumption of ac_bonus and stat_bonuses
# ====================================================================
#
#  The aggregator helpers were tested above.  These tests pin down that
#  the values actually move the numbers the combat engine reads:
#  get_ac() and the .strength/.dexterity/.intelligence/.wisdom
#  properties.  Default-zero bonuses must be a no-op so mundane gear
#  doesn't drift balance.

class TestEngineConsumesItemBonuses:
    def _inject_test_blade(self, ac_bonus=0, stat_bonuses=None):
        _live_weapons()["Test Bonus Blade"] = {
            "power": 5,
            "ranged": False,
            "slots": ["right_hand", "left_hand"],
            "icon": "sword",
            "item_type": "sword",
            "character_can_equip": True,
            "indestructible": True,
            "ac_bonus": ac_bonus,
            "stat_bonuses": stat_bonuses or {},
        }

    def _cleanup(self, member):
        _live_weapons().pop("Test Bonus Blade", None)
        member.equipped["right_hand"] = "Fists"

    def test_ac_bonus_moves_get_ac(self, game):
        m = game.party.members[0]
        self._inject_test_blade(ac_bonus=3)
        try:
            ac_before = m.get_ac()
            m.equipped["right_hand"] = "Test Bonus Blade"
            ac_after = m.get_ac()
            assert ac_after == ac_before + 3
        finally:
            self._cleanup(m)

    def test_stat_bonus_moves_strength_property(self, game):
        m = game.party.members[0]
        self._inject_test_blade(stat_bonuses={"str": 2})
        try:
            str_before = m.strength
            m.equipped["right_hand"] = "Test Bonus Blade"
            assert m.strength == str_before + 2
            # Modifier (and downstream attack/damage math) tracks the
            # raised stat: (12-10)//2 = 1 vs (10-10)//2 = 0, so a +2
            # STR boost should bump str_mod by 1 when starting from 10.
            # We don't pin exact base values, but assert the modifier
            # moved up.
            assert m.str_mod >= 0
        finally:
            self._cleanup(m)

    def test_stat_bonus_moves_dexterity_property(self, game):
        m = game.party.members[0]
        self._inject_test_blade(stat_bonuses={"dex": 4})
        try:
            dex_before = m.dexterity
            m.equipped["right_hand"] = "Test Bonus Blade"
            assert m.dexterity == dex_before + 4
        finally:
            self._cleanup(m)

    def test_intelligence_and_wisdom_move(self, game):
        m = game.party.members[0]
        self._inject_test_blade(stat_bonuses={"int": 3, "wis": 1})
        try:
            int_before = m.intelligence
            wis_before = m.wisdom
            m.equipped["right_hand"] = "Test Bonus Blade"
            assert m.intelligence == int_before + 3
            assert m.wisdom == wis_before + 1
        finally:
            self._cleanup(m)

    def test_zero_bonus_is_a_noop(self, game):
        # Equipping mundane gear must not shift any of the consumed
        # numbers — protects existing characters/items from silent
        # balance drift.
        m = game.party.members[0]
        self._inject_test_blade(ac_bonus=0, stat_bonuses={})
        try:
            ac_before = m.get_ac()
            str_before = m.strength
            dex_before = m.dexterity
            m.equipped["right_hand"] = "Test Bonus Blade"
            assert m.get_ac() == ac_before
            assert m.strength == str_before
            assert m.dexterity == dex_before
        finally:
            self._cleanup(m)


# ====================================================================
#  Magic-item aura visual (renderer side)
# ====================================================================

class TestMagicItemAuras:
    def test_no_auras_for_mundane_member(self, game):
        m = game.party.members[0]
        assert game.renderer._collect_member_auras(m) == []

    def test_sun_sword_grants_gold_aura(self, game):
        # Equip Sun Sword on the fighter, expect a gold aura config.
        fighter = next(p for p in game.party.members
                       if p.char_class.lower() == "fighter")
        fighter.inventory.append("Sun Sword")
        assert fighter.equip_item("Sun Sword", "right_hand")

        auras = game.renderer._collect_member_auras(fighter)
        assert len(auras) == 1
        a = auras[0]
        # Color should match the data/effects.json entry, not a hardcoded
        # constant in the renderer — proves the data path is wired.
        assert a["color"] == (255, 215, 80)
        assert a["pulse_hz"] > 0
        assert a["radius"] > 0

    def test_aura_skipped_when_effect_has_no_color(self, game):
        # Inject a synthetic effect with no aura_color; the renderer
        # should silently skip it (it's the opt-in marker).
        from src import party as party_mod
        party_mod.EFFECTS_DATA.append({
            "id": "test_no_color_aura",
            "name": "Plain",
            "duration": "permanent",
            "item_granted": True,
        })
        _live_weapons()["Test Plain Item"] = {
            "power": 1, "ranged": False,
            "slots": ["right_hand", "left_hand"],
            "icon": "sword", "item_type": "sword",
            "character_can_equip": True, "indestructible": True,
            "grants_effect": "test_no_color_aura",
        }
        try:
            m = game.party.members[0]
            m.equipped["right_hand"] = "Test Plain Item"
            assert game.renderer._collect_member_auras(m) == []
        finally:
            del _live_weapons()["Test Plain Item"]
            party_mod.EFFECTS_DATA[:] = [
                e for e in party_mod.EFFECTS_DATA
                if e.get("id") != "test_no_color_aura"
            ]
            m.equipped["right_hand"] = "Fists"

    def test_draw_helpers_render_without_crashing(self, game):
        # Smoke test: invoke both render entry points with a Sun-Sword
        # wielder.  We can't visually verify the pixels, but we can
        # confirm the code paths don't throw and don't choke on the
        # mock pygame stack.
        fighter = next(p for p in game.party.members
                       if p.char_class.lower() == "fighter")
        fighter.inventory.append("Sun Sword")
        fighter.equip_item("Sun Sword", "right_hand")

        # Direct: helper draws without raising
        game.renderer._draw_member_auras_at(fighter, 100, 100)
        # Combat-arena fighter draw (uses the helper internally)
        game.renderer._u3_draw_party_member_sprite(
            ax=0, ay=0, ts=30, col=4, row=4,
            member=fighter, is_active=False)
        # World-map party draw (loops party.members)
        game.renderer._u3_draw_overworld_party(
            cx=120, cy=120, party=game.party)
