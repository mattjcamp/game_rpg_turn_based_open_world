cd /Users/matthewcampbell/Projects/game_rpg_turn_based_open_world/web
npm run dev

python3 main.py

## Bugs

Deployed version:

Failed to compile.

./src/game/scenes/CombatScene.ts
1460:20  Error: React Hook "useCombatItem" cannot be called in a class component. React Hooks must be called in a React function component or a custom React Hook function.  react-hooks/rules-of-hooks

## Polish

- When a character equips an item in combat, the item that was in the slot previous should be returned to the personal inventory
- For now, we only need slots in for body (armor) and hands (weapons). In the future, we will have more detailed ways to equip items but since we don't support that yet having extra slots will confuse players.
- When a character levels up, a dialog should appear with the detailed calculations of how much their HP and MP increased and what new spells and abilities are unlocked

## V2 Features
- Infravision should act more like normal vision, just with all tiles displayed with a red tint, the range of infravision should match the other lighting effects
- In the character creation screen, add descriptions of races and classes with detailed lists of special abilities



## Web V2 Refactor Items
- rename and organize the tile graphics. create a branch as a reference so that we can transition better. Put all the originals into a backup. 
- organize the tile types better and make it simpler. We don't need special types for all three minds of maps so only have "map tiles". Map Tiles, Monster Tiles, Person Tiles, Item Tiles. Remove the unused items.
- Replace the generic looking swordsman as the party avatar and replace with the graphic used for Gimli

- create outline for random lore generation. Make a user control that lists out things like cultures, races, lost civilizations, events, epics, names, gods, current people. A user control could generate this content (outline first) and lore will be saved to data files so the user can make minor changes. The lore will be used in the content creation in some way.
- Add books feature to addd a way to communicate content