#!/usr/bin/env python3
"""Uninstaller for the voice-input Claude Code plugin.

Run with any system Python (3.10+):
    python uninstall.py

Reverses everything install_plugin.py set up:
  1. Kills running voice-input processes
  2. Removes the MCP server registration from ~/.claude.json
  3. Removes the /voice slash command from ~/.claude/commands/
  4. Removes the virtual environment
  5. Cleans up temp files (.hotkey.pid, .hotkey.log)

Does NOT delete the plugin source code itself.
"""

import json
import os
import shutil
import subprocess
import sys

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


# ---- utilities ------------------------------------------------------- #

def _print(msg: str = ""):
    print(f"  {msg}")


# ---- steps ----------------------------------------------------------- #

def step_kill_processes():
    """Kill any running voice-input server or hotkey daemon processes."""
    kill_script = os.path.join(PLUGIN_DIR, "kill_servers.py")
    if os.path.isfile(kill_script):
        subprocess.run([sys.executable, kill_script])
    else:
        _print("kill_servers.py not found, skipping process cleanup")


def step_remove_mcp():
    """Remove voice-input from ~/.claude.json mcpServers."""
    claude_bin = shutil.which("claude")
    if claude_bin:
        result = subprocess.run(
            [claude_bin, "mcp", "remove", "-s", "user", "voice-input"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            _print("MCP server removed via claude CLI")
            return
        _print(f"CLI removal failed ({result.stderr.strip()}), using fallback...")

    claude_json = os.path.join(os.path.expanduser("~"), ".claude.json")
    if not os.path.exists(claude_json):
        _print("~/.claude.json not found, nothing to remove")
        return

    try:
        with open(claude_json) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        _print(f"Could not read ~/.claude.json: {e}")
        return

    servers = data.get("mcpServers", {})
    if "voice-input" not in servers:
        _print("voice-input not registered in ~/.claude.json")
        return

    del servers["voice-input"]
    with open(claude_json, "w") as f:
        json.dump(data, f, indent=2)
    _print("MCP server removed from ~/.claude.json")


def step_remove_slash_commands():
    """Remove /voice (and any legacy voice-* commands) from ~/.claude/commands/."""
    commands_dir = os.path.join(os.path.expanduser("~"), ".claude", "commands")
    removed = 0
    for name in ("voice.md", "voice-kill.md", "voice-start.md", "voice-restart.md"):
        path = os.path.join(commands_dir, name)
        if os.path.exists(path):
            os.unlink(path)
            _print(f"Removed /{name.removesuffix('.md')}")
            removed += 1
    if removed == 0:
        _print("No slash commands found to remove")


def step_remove_venv():
    """Remove the .venv directory."""
    venv_dir = os.path.join(PLUGIN_DIR, ".venv")
    if not os.path.isdir(venv_dir):
        _print("No virtual environment found")
        return

    _print("Removing virtual environment...")

    def _on_rm_error(func, path, exc_info):
        """Handle locked files on Windows by clearing read-only and retrying."""
        import stat
        os.chmod(path, stat.S_IWRITE)
        func(path)

    try:
        shutil.rmtree(venv_dir, onexc=_on_rm_error)
        _print("Virtual environment removed")
    except Exception:
        # Files may still be locked by a just-killed process; try rd /s /q on Windows
        if os.name == "nt":
            _print("Retrying with rd /s /q ...")
            result = subprocess.run(
                ["cmd", "/c", "rd", "/s", "/q", venv_dir],
                capture_output=True, text=True,
            )
            if result.returncode == 0 and not os.path.isdir(venv_dir):
                _print("Virtual environment removed")
            else:
                _print(f"Could not fully remove .venv — delete it manually:")
                _print(f"  rd /s /q \"{venv_dir}\"")
        else:
            _print(f"Could not fully remove .venv — delete it manually:")
            _print(f"  rm -rf \"{venv_dir}\"")


def step_cleanup_temp_files():
    """Remove temp/runtime files."""
    removed = 0
    for name in (".hotkey.pid", ".hotkey.log"):
        path = os.path.join(PLUGIN_DIR, name)
        if os.path.exists(path):
            os.unlink(path)
            _print(f"Removed {name}")
            removed += 1
    if removed == 0:
        _print("No temp files to clean up")


# ---- main ------------------------------------------------------------ #

def main():
    print()
    print("  ================================================")
    print("  Voice Input Plugin for Claude Code — Uninstaller")
    print("  ================================================")
    print()

    steps = [
        ("[1/5] Killing running processes", step_kill_processes),
        ("[2/5] Removing MCP server registration", step_remove_mcp),
        ("[3/5] Removing slash commands", step_remove_slash_commands),
        ("[4/5] Removing virtual environment", step_remove_venv),
        ("[5/5] Cleaning up temp files", step_cleanup_temp_files),
    ]

    for label, fn in steps:
        _print(label)
        fn()
        _print()

    _print("================================================")
    _print("  Uninstall complete!")
    _print("================================================")
    _print()
    _print("The plugin source code has NOT been deleted.")
    _print(f"To fully remove it: delete {PLUGIN_DIR}")
    _print()
    _print("Restart Claude Code to finish cleanup.")
    _print()


if __name__ == "__main__":
    main()
