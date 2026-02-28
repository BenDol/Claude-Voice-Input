#!/usr/bin/env python3
"""Clean reinstall of the voice-input plugin.

Wipes the virtual environment and re-runs the full installer.

    python reinstall.py
"""

import os
import shutil
import subprocess
import sys

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(PLUGIN_DIR, ".venv")
INSTALLER = os.path.join(PLUGIN_DIR, "install_plugin.py")


def main():
    print()
    print("  Reinstalling voice-input plugin...")
    print()

    if os.path.isdir(VENV_DIR):
        print(f"  Removing old venv: {VENV_DIR}")
        shutil.rmtree(VENV_DIR)
        print("  Done.")
        print()

    subprocess.run([sys.executable, INSTALLER])


if __name__ == "__main__":
    main()
