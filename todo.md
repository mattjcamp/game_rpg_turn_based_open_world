## Polish

## Bugs


## Features


# Map Hierarchy
Overview Map
- Towns
- - Town Enclosures
- Buildings
- - Building Enclosures
- Dungeons
- - Levels (Stairs Up, Stairs Down)

# Tiles on Maps
- All tiles can be located in a map hierarchy and an X, Y coordinate
- Some tiles can be linked to any other tile in the map hierarchy and will contain a pointer with the map in the hierarchy and the X,Y coordinate

For example, it could be possible for a special tile to "link" to the 3rd level of Dank Dungeon at x = 20 and y = 3. This system should work regardless of where the originating tile is located.