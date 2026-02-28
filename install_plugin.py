#!/usr/bin/env python3
"""One-command installer for the voice-input Claude Code plugin.

Run with any system Python (3.10+):
    python install_plugin.py

Handles everything:
  1. Creates / refreshes the virtual environment
  2. Installs pip dependencies
  3. Registers the MCP server in ~/.claude/settings.json
  4. Installs the /voice slash command
"""

import json
import os
import shutil
import subprocess
import sys
import venv

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


# ---- utilities ------------------------------------------------------- #

def _print(msg: str = ""):
    print(f"  {msg}")


def _fail(msg: str):
    print(f"\n  ERROR: {msg}\n")
    sys.exit(1)


def _run(cmd: list[str], **kwargs):
    """Run a subprocess, stream output, and abort on failure."""
    result = subprocess.run(cmd, cwd=PLUGIN_DIR, **kwargs)
    if result.returncode != 0:
        _fail(f"Command failed: {' '.join(cmd)}")


def _venv_python() -> str:
    venv_dir = os.path.join(PLUGIN_DIR, ".venv")
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


# ---- steps ----------------------------------------------------------- #

def step_check_python():
    v = sys.version_info
    _print(f"Python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        _fail("Python 3.10+ is required. https://www.python.org/downloads/")


def step_create_venv():
    venv_dir = os.path.join(PLUGIN_DIR, ".venv")
    if os.path.isfile(_venv_python()):
        _print("Virtual environment already exists, reusing it.")
    else:
        _print("Creating virtual environment...")
        venv.create(venv_dir, with_pip=True)
    if not os.path.isfile(_venv_python()):
        _fail(f"venv Python not found at {_venv_python()}")


def step_install_deps():
    _print("Installing dependencies (this may take a minute)...")
    req = os.path.join(PLUGIN_DIR, "requirements.txt")
    _run([_venv_python(), "-m", "pip", "install", "--quiet", "-r", req])


def step_register_mcp():
    claude_dir = os.path.expanduser("~/.claude")
    os.makedirs(claude_dir, exist_ok=True)
    settings_path = os.path.join(claude_dir, "settings.json")

    settings: dict = {}
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError:
                backup = settings_path + ".bak"
                shutil.copy2(settings_path, backup)
                _print(f"WARNING: corrupt {settings_path} — backup at {backup}")

    if "mcpServers" not in settings:
        settings["mcpServers"] = {}

    server_path = os.path.join(PLUGIN_DIR, "server.py")
    settings["mcpServers"]["voice-input"] = {
        "command": _venv_python().replace("\\", "/"),
        "args": [server_path.replace("\\", "/")],
    }

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    _print(f"MCP server registered in {settings_path}")


def step_install_slash_command():
    claude_dir = os.path.expanduser("~/.claude")
    commands_dir = os.path.join(claude_dir, "commands")
    os.makedirs(commands_dir, exist_ok=True)

    src = os.path.join(PLUGIN_DIR, "commands", "voice.md")
    dst = os.path.join(commands_dir, "voice.md")

    # Always overwrite to keep it in sync with the plugin version
    shutil.copy2(src, dst)
    _print(f"/voice command installed to {dst}")


def step_show_summary():
    config_path = os.path.join(PLUGIN_DIR, "config.json")
    binding = "ctrl+shift+space"
    if os.path.exists(config_path):
        with open(config_path) as f:
            try:
                binding = json.load(f).get("hotkey", {}).get("binding", binding)
            except json.JSONDecodeError:
                pass

    _print()
    _print("================================================")
    _print("  Installation complete!")
    _print("================================================")
    _print()
    _print("Restart Claude Code to activate the plugin.")
    _print()
    _print("Usage:")
    _print(f"  Hotkey:  {binding}")
    _print("           Press once to record, again to stop.")
    _print("           Text is pasted into the prompt automatically.")
    _print()
    _print("  /voice   Alternative: triggers recording via Claude.")
    _print()
    _print("Visual indicator:")
    _print("  Red pill (top-right corner) = recording")
    _print("  Amber pill                  = transcribing")
    _print()
    _print("Audio cues:")
    _print("  High beep   = recording started")
    _print("  Mid beep    = recording stopped")
    _print("  Double beep = text pasted")
    _print("  Low beep    = error")
    _print()
    _print(f"Config: {os.path.join(PLUGIN_DIR, 'config.json')}")
    _print()


# ---- main ------------------------------------------------------------ #

def main():
    print()
    print("  ================================================")
    print("  Voice Input Plugin for Claude Code — Installer")
    print("  ================================================")
    print()

    steps = [
        ("[1/5] Checking Python version", step_check_python),
        ("[2/5] Setting up virtual environment", step_create_venv),
        ("[3/5] Installing dependencies", step_install_deps),
        ("[4/5] Registering MCP server", step_register_mcp),
        ("[5/5] Installing /voice command", step_install_slash_command),
    ]

    for label, fn in steps:
        _print(label)
        fn()
        _print()

    step_show_summary()


if __name__ == "__main__":
    main()
