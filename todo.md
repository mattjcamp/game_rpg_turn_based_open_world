cd /Users/matthewcampbell/Projects/game_rpg_turn_based_open_world/web
npm run dev

python3 main.py

## Polish

- Arrows, bolts, and stones should all be consumable. You get them in stacks of 20 and each time you fire a weapon you loss one. As you buy more stacks of arrows and other consumable items they should be stacked in the party inventory. For example if you buy one stack of arrows you get arrows(20), but if you buy three stacks of arrows you would have arrows(60). The same is true for camping supplies, torches, lockpicks, potions, herbs, and regents.
- Do a full QA on party creation attributes, combat, etc. Do a few playthroughs.
- Add soundtrack (only two mpg3 to keep it small)
- Lighting should not pass through walls and essentially only light based on Light of Sight and the lighting effect range


## Features
- In the character creation screen, add descriptions of races and classes with detailed lists of special abilities

## Bugs
- When the party received arrows from a quest giver, they arrows showed up as their own entry when they should have been added to the collection of arrows that was already there.
- Keep an eye open for when the party did not have it's normal options appear on the right (range, cast, throw).

## Web V2 Refactor Items
- rename and organize the tile graphics. create a branch as a reference so that we can transition better. Put all the originals into a backup. 
- organize the tile types better and make it simpler. We don't need special types for all three minds of maps so only have "map tiles". Map Tiles, Monster Tiles, Person Tiles, Item Tiles. Remove the unused items.

- create outline for random lore generation. Make a user control that lists out things like cultures, races, lost civilizations, events, epics, names, gods, current people. A user control could generate this content (outline first) and lore will be saved to data files so the user can make minor changes. The lore will be used in the content creation in some way.
- Add books feature to addd a way to communicate content