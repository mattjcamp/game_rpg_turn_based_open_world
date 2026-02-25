# Ultima III: Exodus — Character & Party System Reference

Reference compiled from StrategyWiki, Ultima Codex, Mike's RPG Center, and GameFAQs guides.
For use as a template when building out the party/character system in our game.

---

## Character Creation Overview

Each character is defined by: **Race**, **Class (Profession)**, **Gender**, and four **Attributes**.

- Up to 20 characters can be created and stored at once
- Parties are formed by selecting 4 characters from that roster
- Parties can be dispersed and re-formed even mid-game
- Gender options: Male, Female, Other (purely cosmetic)
- At creation, 50 points are distributed among 4 attributes (min 5, max 25 per stat)

---

## Races

Five playable races, each with different maximum attribute caps (raised via Shrines in Ambrosia at 100 gold per point).

| Race     | Max STR | Max DEX | Max INT | Max WIS | Best For                    |
|----------|---------|---------|---------|---------|------------------------------|
| Human    | 75      | 75      | 75      | 75      | Jack-of-all-trades, Ranger   |
| Elf      | 75      | 99      | 75      | 50      | Thief, Lark                  |
| Dwarf    | 99      | 75      | 50      | 75      | Fighter, Paladin, Barbarian  |
| Bobbit   | 75      | 50      | 75      | 99      | Cleric, Druid                |
| Fuzzy    | 25      | 99      | 99      | 75      | Wizard, Alchemist            |

---

## Attributes (Stats)

| Attribute      | Effect                                                    |
|----------------|-----------------------------------------------------------|
| **Strength**   | Modifies melee damage (total damage = weapon base + 150% STR) |
| **Dexterity**  | Chance to hit, chance to evade attacks and traps           |
| **Intelligence**| Magic points for Sorcerer (Wizard) spells                 |
| **Wisdom**     | Magic points for Priest (Cleric) spells                   |

---

## Health & Leveling

- 100 experience points (XP) needed to gain one level
- Levels are granted by visiting Lord British
- Max HP at each level = (100 × current level) + 50
- HP example: Level 1 = 150 max HP, Level 5 = 550 max HP

---

## Classes (Professions)

### The Four Basic Classes

| Class    | Role             | Weapon Access | Armor Access | Magic Type | MP Source     | Steal/Disarm |
|----------|------------------|---------------|--------------|------------|---------------|--------------|
| Fighter  | Pure melee       | All (Sun Sword)| All (Dragon) | None       | —             | None         |
| Cleric   | Priest healer    | Up to Mace    | Up to Chain  | Priest     | = Wisdom      | None         |
| Wizard   | Arcane nuker     | Dagger only   | Cloth only   | Sorcerer   | = Intelligence| None         |
| Thief    | Dex specialist   | Up to Sword   | Up to Leather| None       | —             | Superior     |

### The Seven Hybrid Classes

Each hybrid is a combination of two (or all four) basic classes:

| Class       | Hybrid Of        | Best Weapon  | Best Armor | Magic Type    | MP Source              | Steal/Disarm |
|-------------|------------------|-------------|------------|---------------|------------------------|--------------|
| Paladin     | Fighter + Cleric | Sun Sword   | Iron/Plate | Priest        | = ½ Wisdom             | Ordinary     |
| Barbarian   | Fighter + Thief  | Sun Sword   | Leather    | None          | —                      | None         |
| Lark        | Fighter + Wizard | Sun Sword   | Cloth      | Sorcerer      | = ½ Intelligence       | Ordinary     |
| Illusionist | Cleric + Thief   | Mace        | Leather    | Priest        | = ½ Wisdom             | None         |
| Druid       | Cleric + Wizard  | Mace        | Cloth      | Both          | = ½ of stronger stat   | Ordinary     |
| Alchemist   | Wizard + Thief   | Dagger      | Cloth      | Sorcerer      | = ½ Intelligence       | Ordinary     |
| Ranger      | All four         | Iron Sword  | Dragon     | Both          | = ½ of weaker stat     | Ordinary     |

### Key Class Notes

- **Druid** recovers MP twice as fast as all other classes (2 per turn on surface, vs 1 per turn for others)
- **Ranger** uses the *weaker* of INT/WIS for MP (opposite of Druid), making them weak casters but strong fighters
- Classes with Steal/Disarm need high DEX to be effective
- Only one party member needs Steal/Disarm to open chests safely
- A party without at least one Cleric or Wizard will struggle to complete the game

---

## Weapons

Weapons ranked weakest to strongest. Ranged weapons can attack at distance; melee only hits adjacent.

| #  | Weapon       | Power | Range  | Who Can Equip                                        |
|----|-------------|-------|--------|------------------------------------------------------|
| 1  | Dagger       | 1     | Melee* | All classes                                          |
| 2  | Mace         | 2     | Melee  | All except Wizard, Alchemist                         |
| 3  | Sling        | 3     | Ranged | Fighter, Thief, Paladin, Barbarian, Lark, Ranger     |
| 4  | Axe          | 4     | Melee  | Fighter, Thief, Paladin, Barbarian, Lark, Ranger     |
| 5  | Sword        | 5     | Melee  | Fighter, Thief, Paladin, Barbarian, Lark, Ranger     |
| 6  | Spear        | 6     | Melee  | Fighter, Paladin, Barbarian, Lark, Ranger             |
| 7  | Broad Axe    | 7     | Melee  | Fighter, Paladin, Barbarian, Lark, Ranger             |
| 8  | Bow          | 7     | Ranged | Fighter, Paladin, Barbarian, Lark, Ranger             |
| 9  | Iron Sword   | 8     | Melee  | Fighter, Paladin, Barbarian, Lark, Ranger             |
| 10 | Gloves       | 8     | Melee  | Fighter, Paladin, Barbarian, Lark                     |
| 11 | Halberd      | 9     | Melee  | Fighter, Paladin, Barbarian, Lark                     |
| 12 | Silver Bow   | 9     | Ranged | Fighter, Paladin, Barbarian, Lark                     |
| 13 | Sun Sword    | 10    | Melee  | Fighter, Paladin, Barbarian, Lark                     |
| 14 | Mystic Sword | 10    | Melee  | All classes                                          |

*Dagger can be thrown once as a ranged weapon (consumed on use), otherwise functions as melee.

**Damage formula**: Total damage = weapon power + (1.5 × STR)

---

## Armor

Armor determines evasion rate (chance to dodge). It does NOT absorb damage. Ineffective against dragons.

| #  | Armor       | Evasion % | Who Can Equip                                     |
|----|-------------|-----------|---------------------------------------------------|
| 1  | Cloth       | ~50%      | All classes                                       |
| 2  | Leather     | 56%       | Fighter, Ranger, Paladin, Cleric, Barbarian, Thief, Illusionist |
| 3  | Chain       | 58%       | Fighter, Ranger, Paladin, Cleric                   |
| 4  | Plate       | 60%       | Fighter, Ranger, Paladin                           |
| 5  | +2 Chain    | 62%       | Fighter, Ranger                                    |
| 6  | +2 Plate    | 64%       | Fighter, Ranger                                    |
| 7  | Exotic      | 67%       | All classes (only armor that works on Isle of Fire) |

---

## Magic — Priest (Cleric) Spells

16 spells, labeled A through P. MP source = Wisdom. Used by: Cleric, Paladin, Illusionist, Druid, Ranger.

| # | Name     | MP  | Effect                                                         |
|---|----------|-----|----------------------------------------------------------------|
| A | Undead   | 0   | Instantly kills Skeletons and Ghouls                           |
| B | Open     | 5   | Opens a chest, bypassing traps                                 |
| C | Heal     | 10  | Restores 25–50 HP                                              |
| D | Glow     | 15  | Short-duration light in dungeons                               |
| E | Rise     | 20  | Move to random spot on floor above (dungeon only)              |
| F | Sink     | 25  | Move to random spot on floor below (dungeon only)              |
| G | Move     | 30  | Teleport to random spot on current floor (dungeon only)        |
| H | Cure     | 35  | Cure poison from one character                                 |
| I | Surface  | 40  | Return to surface from dungeon                                 |
| J | Star     | 45  | Long-duration light in dungeons                                |
| K | Great Heal| 50 | Restores 125–250 HP                                            |
| L | Map      | 55  | Displays map of current area                                   |
| M | Banish   | 60  | Strong fireball — instant kill on one enemy                    |
| N | Raise    | 65  | Resurrect a dead character (may fail → turns to ash)           |

---

## Magic — Sorcerer (Wizard) Spells

16 spells, labeled A through P. MP source = Intelligence. Used by: Wizard, Lark, Alchemist, Druid, Ranger.

| # | Name       | MP  | Target   | Effect                                           |
|---|-----------|-----|----------|--------------------------------------------------|
| A | Repond     | 0   | Group    | Instantly kills all Orcs, Goblins, Trolls        |
| B | Mittar     | 5   | Single   | Magic missile (2 to INT damage, range 3)         |
| C | Lorum      | 10  | —        | Short-duration light (dungeon only)              |
| D | Dor Acron  | 15  | —        | Move down one dungeon level                      |
| E | Sur Acron  | 20  | —        | Move up one dungeon level                        |
| F | Fulgar     | 25  | Single   | Strong magic missile                             |
| G | Dag Acron  | 30  | —        | Random teleport on surface                       |
| H | Mentar     | 35  | Single   | Potent attack (scales with INT)                  |
| I | Dag Lorum  | 40  | —        | Long-duration light (dungeon only)               |
| J | Fal Divi   | 45  | —        | Allows caster to cast one Cleric spell           |
| K | Noxum      | 50  | All      | Damages all enemies                              |
| L | Decorp     | 55  | Single   | Instant kill on one enemy                        |
| M | Altair     | 60  | —        | Stops time (enemies freeze)                      |
| N | Dag Mentar | 65  | All      | Strong damage to all enemies                     |
| O | Necorp     | 70  | All      | Weakens all enemies                              |
| P | (Secret)   | 75  | All      | Destroys all enemies (most powerful spell)        |

---

## MP Regeneration

| Location  | Rate              |
|-----------|-------------------|
| Surface   | 1 MP per turn     |
| Town      | 1 MP per 4 turns  |
| Dungeon   | 1 MP per 4 turns  |
| Druid     | 2× normal rate    |

---

## Optimal Race/Class Pairings

| Class     | Best Race | Reasoning                                         |
|-----------|-----------|---------------------------------------------------|
| Fighter   | Dwarf     | Max 99 STR for highest damage                     |
| Cleric    | Bobbit    | Max 99 WIS for most MP                            |
| Wizard    | Fuzzy     | Max 99 INT for most MP                            |
| Thief     | Elf       | Max 99 DEX for best steal/dodge                   |
| Paladin   | Dwarf     | Strong STR + decent WIS for half-casting          |
| Barbarian | Dwarf     | Max STR, doesn't need magic                       |
| Lark      | Elf       | Good DEX + decent INT for half-casting            |
| Druid     | Bobbit    | High WIS (or Fuzzy for high INT) — uses stronger  |
| Ranger    | Human     | Balanced stats needed since MP = half of weaker   |
| Alchemist | Fuzzy     | Max INT for half-casting sorcerer spells           |
| Illusionist| Elf      | Good DEX makes surprisingly strong melee          |

---

## Recommended Party Compositions

### Classic Balanced Party
1. **Dwarf Fighter** — Front-line tank, best weapons/armor
2. **Bobbit Cleric** — Healer, priest spells, decent armor
3. **Fuzzy Wizard** — Nuker, mass-destruction spells
4. **Elf Thief** — Trap disarmer, ranged attacks, high evasion

### Hybrid Power Party
1. **Dwarf Paladin** — Heavy fighter + priest healing
2. **Bobbit Druid** — Both spell types + 2× MP regen
3. **Fuzzy Wizard** — Pure arcane power
4. **Elf Thief** — Trap handling + ranged support

### Min-Max Party
1. **Dwarf Fighter** — Pure damage dealer
2. **Dwarf Paladin** — Tank + off-healer
3. **Fuzzy Wizard** — Arcane nukes
4. **Bobbit Cleric** — Full priest spell access

---

## Sources

- [StrategyWiki — Ultima III: Exodus/Characters](https://strategywiki.org/wiki/Ultima_III:_Exodus/Characters)
- [StrategyWiki — Ultima III: Exodus/Parties](https://strategywiki.org/wiki/Ultima_III:_Exodus/Parties)
- [StrategyWiki — Ultima III: Exodus/Magic](https://strategywiki.org/wiki/Ultima_III:_Exodus/Magic)
- [StrategyWiki — Ultima III: Exodus/Items](https://strategywiki.org/wiki/Ultima_III:_Exodus/Items)
- [Mike's RPG Center — Professions](http://mikesrpgcenter.com/ultima3/professions.html)
- [Mike's RPG Center — Magic](http://mikesrpgcenter.com/ultima3/magic.html)
- [Ultima Codex — Character Attributes in Ultima III](https://wiki.ultimacodex.com/wiki/Character_attributes_in_Ultima_III)
- [Ultima Codex — Weapon Values](https://wiki.ultimacodex.com/wiki/Weapon_values)
- [Ultima Codex — Armour Values](https://wiki.ultimacodex.com/wiki/Armour_values)
