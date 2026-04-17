#!/usr/bin/env python3
"""
Realm of Shadow - An Ultima III Inspired RPG
=============================================

Entry point. Run this file to start the game:

    python main.py

Requirements:
    pip install pygame

Controls:
    Arrow keys or WASD - Move the party
    Shift + Arrow keys - Scroll the map / review explored tiles
    ESC - Quit
"""

from src.game import Game


def main():
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
