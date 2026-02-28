#!/usr/bin/env python3
"""One-command installer for the voice-input Claude Code plugin.

Run with any system Python (3.10+):
    python install_plugin.py

Handles everything:
  1. Creates / refreshes the virtual environment
  2. Installs pip dependencies
  3. Registers the MCP server in ~/.claude.json (user scope, all projects)
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
    """Return path to the venv Python used for pip / setup tasks."""
    venv_dir = os.path.join(PLUGIN_DIR, ".venv")
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def _venv_pythonw() -> str:
    """Return path to the windowless Python (no console on Windows)."""
    venv_dir = os.path.join(PLUGIN_DIR, ".venv")
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "pythonw.exe")
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
    """Register via `claude mcp add -s user` (user scope = all projects).

    Falls back to manually editing ~/.claude.json if the CLI isn't available.
    """
    server_py = os.path.join(PLUGIN_DIR, "server.py").replace("\\", "/")
    python = _venv_pythonw().replace("\\", "/")

    # Prefer the CLI — it knows the exact config format
    claude_bin = shutil.which("claude")
    if claude_bin:
        # Remove first (ignore errors if not present)
        subprocess.run(
            [claude_bin, "mcp", "remove", "-s", "user", "voice-input"],
            capture_output=True,
        )
        result = subprocess.run(
            [claude_bin, "mcp", "add", "-s", "user",
             "--transport", "stdio", "voice-input", "--", python, server_py],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            _print("MCP server registered (user scope) via claude CLI")
            return
        _print(f"CLI registration failed ({result.stderr.strip()}), using fallback...")

    # Fallback: write directly to ~/.claude.json top-level mcpServers
    claude_json = os.path.join(os.path.expanduser("~"), ".claude.json")
    data: dict = {}
    if os.path.exists(claude_json):
        with open(claude_json) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                backup = claude_json + ".bak"
                shutil.copy2(claude_json, backup)
                _print(f"WARNING: corrupt {claude_json} — backup at {backup}")

    if "mcpServers" not in data:
        data["mcpServers"] = {}

    data["mcpServers"]["voice-input"] = {
        "type": "stdio",
        "command": python,
        "args": [server_py],
        "env": {},
    }

    with open(claude_json, "w") as f:
        json.dump(data, f, indent=2)

    _print(f"MCP server registered (user scope) in {claude_json}")


def step_install_slash_commands():
    claude_dir = os.path.expanduser("~/.claude")
    commands_dir = os.path.join(claude_dir, "commands")
    os.makedirs(commands_dir, exist_ok=True)

    # Remove old separate voice-* commands (consolidated into /voice)
    for old in ("voice-kill.md", "voice-start.md", "voice-restart.md"):
        old_path = os.path.join(commands_dir, old)
        if os.path.exists(old_path):
            os.unlink(old_path)
            _print(f"  Removed old /{old.removesuffix('.md')}")

    src_dir = os.path.join(PLUGIN_DIR, "commands")
    for filename in sorted(os.listdir(src_dir)):
        if not filename.endswith(".md"):
            continue
        src = os.path.join(src_dir, filename)
        dst = os.path.join(commands_dir, filename)
        shutil.copy2(src, dst)
        name = filename.removesuffix(".md")
        _print(f"  /{name} installed")
    _print("Slash commands installed")


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
    _print("  /voice          Record voice via Claude")
    _print("  /voice start    Start the hotkey daemon")
    _print("  /voice restart  Restart the hotkey daemon")
    _print("  /voice kill     Stop all voice processes")
    _print()
    _print("Visual indicator:")
    _print("  Red pill (bottom-right of active window) = recording")
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
        ("[5/5] Installing slash commands", step_install_slash_commands),
    ]

    for label, fn in steps:
        _print(label)
        fn()
        _print()

    step_show_summary()


if __name__ == "__main__":
    main()
