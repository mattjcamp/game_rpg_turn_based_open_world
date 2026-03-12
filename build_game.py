#!/usr/bin/env python3
"""
Build script for Realm of Shadow.

Creates a distributable folder using PyInstaller.
Run from the project root:

    python3 build_game.py

Prerequisites:
    pip3 install pyinstaller

The finished build lands in dist/RealmOfShadow/.  Zip that folder
and share it — recipients can run the game without installing Python.
"""

import os
import platform
import shutil
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(ROOT, "realm_of_shadow.spec")
DIST = os.path.join(ROOT, "dist", "RealmOfShadow")


def check_pyinstaller():
    """Make sure PyInstaller is installed."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found.  Installing...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller"])


def build():
    """Run PyInstaller with the spec file."""
    print(f"Building Realm of Shadow for {platform.system()} "
          f"({platform.machine()})...\n")
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        SPEC,
    ], cwd=ROOT)


def ensure_writable_dirs():
    """Create writable directories that the game needs at runtime."""
    saves_dir = os.path.join(DIST, "data", "saves")
    os.makedirs(saves_dir, exist_ok=True)

    # Ensure an empty config exists so first-run writes succeed
    config_path = os.path.join(DIST, "data", "config.json")
    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            f.write("{}")


def codesign_mac():
    """Ad-hoc code sign on macOS so Gatekeeper treats the bundle as one app.

    Without this, macOS quarantine flags every .so and .dylib individually,
    forcing the user to approve each one in System Settings.  Ad-hoc signing
    is free and doesn't require an Apple Developer account.
    """
    if platform.system() != "Darwin":
        return

    print("\nCode-signing for macOS (ad-hoc)...")
    try:
        subprocess.check_call([
            "codesign", "--force", "--deep", "--sign", "-",
            DIST,
        ])
        print("  Signed successfully.")
    except FileNotFoundError:
        print("  codesign not found — skipping (are you on macOS?)")
    except subprocess.CalledProcessError as exc:
        print(f"  codesign failed ({exc}) — the build is still usable,")
        print("  but users may need to run:  xattr -cr dist/RealmOfShadow/")


def report():
    """Print the build result."""
    if os.path.isdir(DIST):
        size_mb = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fnames in os.walk(DIST)
            for f in fnames
        ) / (1024 * 1024)
        print(f"\nBuild complete!  Output: {DIST}")
        print(f"Total size: {size_mb:.1f} MB")
        print(f"\nTo distribute, zip the folder:")
        print(f"  cd dist && zip -r RealmOfShadow-{platform.system().lower()}.zip RealmOfShadow/")
        if platform.system() == "Darwin":
            print(f"\nIf a Mac user has trouble opening the app, tell them to run:")
            print(f"  xattr -cr path/to/RealmOfShadow/")
    else:
        print("\nBuild failed — dist/RealmOfShadow/ was not created.")
        sys.exit(1)


if __name__ == "__main__":
    check_pyinstaller()
    build()
    ensure_writable_dirs()
    codesign_mac()
    report()
