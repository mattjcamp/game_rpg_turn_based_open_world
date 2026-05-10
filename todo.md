cd /Users/matthewcampbell/Projects/game_rpg_turn_based_open_world/web
npm run dev
python3 main.py

## Marketing
- Make Github site simpler and focus on web version
- Link to other page to show Python and editor version since that is really a challenging process for people to use. In the figure, I will build a cleaner version of this along with a module sharing feature.

## Bugs
- The Veyron Family Heirloom quest is broken, there is no scroll in the abandoned building. This is the first quest with an abandoned building FYI.
- in Shanty Town, an NPC Quest Giver was outside of the town walls in an impossible location. Seat of the Realm had something similar with the quest giver stuck in the water.
- The Orc Stronghold looked very strange with lighting. You could see torches even when they were not line of sight. It was very difficult to navigate in that way.
- I encountered a locked door in the orc stronghold and even though I had a Knock spell I could not use it
- I was not able to attack the Man Eater spawn to destroy it

## Polish

# V2

## Web V2 Refactor Items
- Curate the data model and remove attributes that are unused
- rename and organize the tile graphics. create a branch as a reference so that we can transition better. Put all the originals into a backup. 
- organize the tile types better and make it simpler. We don't need special types for all three minds of maps so only have "map tiles". Map Tiles, Monster Tiles, Person Tiles, Item Tiles. Remove the unused items.
- Replace the generic looking swordsman as the party avatar and replace with the graphic used for Gimli

## V2 Features
- Polish the various "light effects". Make sure they are consistant and behave as expected. Infravision should act more like normal vision, just with all tiles displayed with a red tint, the range of infravision should match the other lighting effects
- create outline for random lore generation. Make a user control that lists out things like cultures, races, lost civilizations, events, epics, names, gods, current people. A user control could generate this content (outline first) and lore will be saved to data files so the user can make minor changes. The lore will be used in the content creation in some way.
- Add books feature to add a way to communicate content
- Note that experience level is different in the game vs the manual, once we decide on which way to go we need to make sure they are in sync



