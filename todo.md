cd /Users/matthewcampbell/Projects/game_rpg_turn_based_open_world/web
npm run dev
python3 main.py

## Marketing
- Make Github site simpler and focus on web version
- Link to other page to show Python and editor version since that is really a challenging process for people to use. In the figure, I will build a cleaner version of this along with a module sharing feature.

## Bugs
- THe last Dragon quest had no other encounters. Double check before trying to fix.

## Polish
- Do another run through of the quest system
- Do a full playthrough with the debug party
- Do a full playthrough with Level 1 characters

# V2

## Polish
- Make the Fire Breath look more like fire
- When the party completes the last quest, the game should end
- Audit the quest system and test how encounters are applied. Add a feature to quest steps that allows us to specify what floor of the dungeon the step occurs. Item retrieval quest may have that I think this issue is mainly for procedural dungeons.

## Web V2 Refactor Items
- Curate the data model and remove attributes that are unused
- rename and organize the tile graphics. create a branch as a reference so that we can transition better. Put all the originals into a backup. 
- organize the tile types better and make it simpler. We don't need special types for all three minds of maps so only have "map tiles". Map Tiles, Monster Tiles, Person Tiles, Item Tiles. Remove the unused items.
- Replace the generic looking swordsman as the party avatar and replace with the graphic used for Gimli

## V2 Features
- create outline for random lore generation. Make a user control that lists out things like cultures, races, lost civilizations, events, epics, names, gods, current people. A user control could generate this content (outline first) and lore will be saved to data files so the user can make minor changes. The lore will be used in the content creation in some way.
- Add books feature to add a way to communicate content
- Make sure that the manual is in sync with the game, character creation screens, etc


