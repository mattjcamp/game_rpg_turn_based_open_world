cd /Users/matthewcampbell/Projects/game_rpg_turn_based_open_world/web
npm run dev
python3 main.py

## Bugs

## Polish

- Add spells, abilities, AC Calc, Damage Calc to character sheets
- Double check that class abilities have been ported

Thief Shadow Step doesn't exist in Python either. No Shadow Step, no Backstab, no Sneak ability anywhere in the source data or code. Thieves have lockpicking ungated from level 1 in Python, and that's the extent of their class abilities. So if you want Shadow Step, that's a content-design request, not a porting one — separate scope from the dialog.

## V2 Features
- Infravision should act more like normal vision, just with all tiles displayed with a red tint, the range of infravision should match the other lighting effects
- In the character creation screen, add descriptions of races and classes with detailed lists of special abilities



## Web V2 Refactor Items
- rename and organize the tile graphics. create a branch as a reference so that we can transition better. Put all the originals into a backup. 
- organize the tile types better and make it simpler. We don't need special types for all three minds of maps so only have "map tiles". Map Tiles, Monster Tiles, Person Tiles, Item Tiles. Remove the unused items.
- Replace the generic looking swordsman as the party avatar and replace with the graphic used for Gimli

- create outline for random lore generation. Make a user control that lists out things like cultures, races, lost civilizations, events, epics, names, gods, current people. A user control could generate this content (outline first) and lore will be saved to data files so the user can make minor changes. The lore will be used in the content creation in some way.
- Add books feature to addd a way to communicate content