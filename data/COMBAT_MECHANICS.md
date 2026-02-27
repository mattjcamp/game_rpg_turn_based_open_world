# Combat Mechanics Reference

This document describes all combat math used in **Realm of Shadow**.
Keep it updated as the engine changes — it is the single source of truth
for how attacks, damage, defense, and spells work.

---

## Dice Notation

Standard tabletop notation is used throughout: `NdS` means roll N dice
with S sides each and sum the results. For example, `2d8` means roll
two eight-sided dice. A modifier like `+3` is added after the roll.

---

## Ability Modifiers

Every character has four stats: **STR**, **DEX**, **INT**, **WIS**.
Each produces a modifier used in combat formulas:

    modifier = (stat_value - 10) / 2   (rounded down)

| Stat Value | Modifier |
|------------|----------|
| 6–7        | −2       |
| 8–9        | −1       |
| 10–11      | +0       |
| 12–13      | +1       |
| 14–15      | +2       |
| 16–17      | +3       |
| 18–19      | +4       |

---

## Attack Rolls (Melee and Ranged)

All physical attacks — melee swings, ranged shots, and thrown weapons —
use the same core resolution:

    roll = 1d20 + attack_bonus

Compare the total to the **defender's AC**:

- **Total >= AC** → hit
- **Total < AC**  → miss
- **Natural 20**  → automatic hit (critical)
- **Natural 1**   → automatic miss (never a critical)

### Player Attack Bonus

    attack_bonus = STR modifier

_(Weapon-specific bonuses may be added later.)_

### Monster Attack Bonus

Monsters have a flat `attack_bonus` stat defined per creature type.

---

## Armor Class (AC)

Player AC is calculated as:

    AC = 10 + DEX modifier + armor_bonus

Where `armor_bonus` comes from the equipped armor's evasion rating:

    armor_bonus = (evasion - 50) / 5   (rounded down)

| Armor       | Evasion | Bonus | Effective AC (DEX +0) |
|-------------|---------|-------|-----------------------|
| Cloth       | 50      | +0    | 10                    |
| Leather     | 56      | +1    | 11                    |
| Chain       | 58      | +1    | 11                    |
| Plate       | 60      | +2    | 12                    |
| +2 Chain    | 62      | +2    | 12                    |
| +2 Plate    | 64      | +2    | 12                    |
| Exotic      | 67      | +3    | 13                    |

**Defending** adds +2 AC for the round (the character skips their action
to brace).

Monster AC is a flat value defined per creature type.

---

## Damage

### Player Damage

Weapon power determines the dice used:

| Weapon Power | Damage Dice |
|--------------|-------------|
| 0–2          | 1d4         |
| 3–5          | 1d6         |
| 6–8          | 1d8         |
| 9–10         | 1d10        |

The final damage roll is:

    damage = (damage_dice) + STR modifier
    minimum 1 damage on any hit

On a **critical hit**, the dice count is doubled (but the STR modifier
is not). For example, a weapon that normally rolls `1d8 + 3` would roll
`2d8 + 3` on a crit.

### Monster Damage

Monsters roll their own damage dice (defined per type). Same critical
rules apply — double the dice count, not the bonus.

    damage = (damage_dice)d(damage_sides) + damage_bonus
    minimum 1 damage on any hit

---

## Ranged Attacks

Ranged weapons come in two flavors:

### Standard Ranged (Bows, Slings)

The weapon has `ranged: true` in its data. The attack uses the same
d20 + STR mod vs AC formula. The weapon is **not consumed** — the
character can fire indefinitely.

### Throwable Weapons (Daggers)

The weapon has `throwable: true` in its data. Each ranged attack
**consumes one copy** of the weapon from the character's personal
inventory or the party's shared inventory. When all copies are
exhausted, the character can no longer make ranged attacks with that
weapon (but can still use it in melee if it has `melee: true`).

Attack resolution is the same: d20 + STR mod vs AC.

---

## Spells

### Fireball (Sorcerer)

- **Cost:** 5 MP
- **Caster requirement:** Sorcerer-type class (Wizard, Lark, Alchemist,
  Druid, Ranger)
- **Targeting:** Directional (arrow keys). Fires in a straight line
  until hitting the monster or a wall.
- **Hit:** Always hits (no attack roll). Cannot miss.
- **Damage:** 2d8 + INT modifier (minimum 1)
- **Critical:** Not applicable (no d20 roll)

### Heal (Priest)

- **Cost:** 4 MP
- **Caster requirement:** Priest-type class (Cleric, Paladin,
  Illusionist, Druid, Ranger)
- **Targeting:** Directional (arrow keys). Ray-traces in a straight line
  to find the first living ally.
- **Effect:** Restores 1d8 + WIS modifier HP (minimum 1, capped at the
  target's max HP)

---

## Magic Points (MP)

MP is derived from character class and the relevant mental stat:

| Class       | MP Formula             |
|-------------|------------------------|
| Wizard      | INT                    |
| Alchemist   | INT                    |
| Cleric      | WIS                    |
| Illusionist | WIS                    |
| Lark        | INT / 2                |
| Paladin     | WIS / 2                |
| Druid       | max(INT, WIS) / 2      |
| Ranger      | min(INT, WIS) / 2      |
| Others      | 0                      |

MP is spent when casting spells and does not regenerate during combat.

---

## Initiative

At the start of each round, turn order is determined by:

    initiative = 1d20 + DEX modifier

Higher rolls go first. All party members and the monster roll
initiative each round.

---

## Fleeing

A character can attempt to flee on their turn:

    roll = 1d20 + DEX modifier
    DC = 10

- **Roll >= DC** → escape succeeds, combat ends (party retreats)
- **Roll < DC**  → escape fails, turn is wasted

---

## Monster Types (Current)

| Monster      | HP  | AC  | ATK Bonus | Damage      | XP  | Gold     |
|-------------|-----|-----|-----------|-------------|-----|----------|
| Giant Rat   | 8   | 12  | +2        | 1d4         | 15  | 2–8      |
| Skeleton    | 16  | 13  | +3        | 1d6 + 1     | 30  | 5–20     |
| Orc         | 22  | 13  | +5        | 1d8 + 2     | 50  | 10–30    |

---

## Weapon Reference

See `data/items.json` for the full item database. Key combat-relevant
fields for weapons:

| Field      | Type | Description                                    |
|------------|------|------------------------------------------------|
| power      | int  | Determines damage dice tier (see table above)  |
| ranged     | bool | Can attack at distance                         |
| melee      | bool | Can be used in melee (even if also ranged)     |
| throwable  | bool | Consumed from inventory on each ranged attack  |

---

*Last updated: Feb 2026*
