#!/usr/bin/env python3
"""Kill all voice-input server and hotkey daemon processes."""

import os
import signal
import subprocess
import sys


def main():
    pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hotkey.pid")

    # Kill hotkey daemon via PID file
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"  Killed hotkey daemon (PID {pid})")
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass
        try:
            os.unlink(pid_file)
        except OSError:
            pass

    # Kill any pythonw/python processes running server.py or hotkey_daemon.py
    if os.name == "nt":
        _kill_windows()
    else:
        _kill_unix()


def _kill_windows():
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where",
             "name='python.exe' or name='pythonw.exe'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            stderr=subprocess.DEVNULL, text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # wmic not available, try powershell
        try:
            out = subprocess.check_output(
                ["powershell", "-Command",
                 "Get-Process python,pythonw -ErrorAction SilentlyContinue | "
                 "Select-Object Id,Path | Format-List"],
                stderr=subprocess.DEVNULL, text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("  Could not enumerate processes")
            return
        return

    killed = 0
    for line in out.splitlines():
        if "server.py" in line or "hotkey_daemon.py" in line:
            parts = line.rstrip().split(",")
            try:
                pid = int(parts[-1])
                os.kill(pid, signal.SIGTERM)
                print(f"  Killed PID {pid}")
                killed += 1
            except (ValueError, OSError):
                pass

    if killed == 0:
        print("  No voice-input processes found")


def _kill_unix():
    try:
        out = subprocess.check_output(
            ["pgrep", "-af", "server.py|hotkey_daemon.py"],
            stderr=subprocess.DEVNULL, text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("  No voice-input processes found")
        return

    killed = 0
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) >= 2 and ("server.py" in parts[1] or "hotkey_daemon.py" in parts[1]):
            try:
                pid = int(parts[0])
                os.kill(pid, signal.SIGTERM)
                print(f"  Killed PID {pid}")
                killed += 1
            except (ValueError, OSError):
                pass

    if killed == 0:
        print("  No voice-input processes found")


if __name__ == "__main__":
    main()
