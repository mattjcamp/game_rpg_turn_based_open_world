# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Realm of Shadow.

Build with:
    pyinstaller realm_of_shadow.spec

This produces a one-folder bundle in dist/RealmOfShadow/ containing the
executable and all game data.  The folder can be zipped and distributed.
"""

import os
import sys

block_cipher = None

# ── Paths ────────────────────────────────────────────────────────
HERE = os.path.abspath(os.path.dirname(SPECPATH))

a = Analysis(
    ['main.py'],
    pathex=[HERE],
    binaries=[],
    datas=[
        # Game data (JSON configs, class defs, save slots)
        ('data', 'data'),
        # Sprite sheets and tile images
        ('src/assets', 'src/assets'),
        # Adventure modules
        ('modules', 'modules'),
        # Documentation (optional — nice to include for players)
        ('docs/manuals', 'docs/manuals'),
    ],
    hiddenimports=[
        'numpy',
        'pygame',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'email',
        'html',
        'http',
        'xml',
        'pydoc',
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RealmOfShadow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # windowed app, no terminal
    icon=None,              # add an .ico/.icns later if desired
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RealmOfShadow',
)
