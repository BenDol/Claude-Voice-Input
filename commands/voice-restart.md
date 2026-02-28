Restart the voice-input hotkey daemon by first killing existing processes, then starting a fresh instance.

1. Run: `python C:/Projects/claude/plugins/voice-input/kill_servers.py`
2. Run: `C:/Projects/claude/plugins/voice-input/.venv/Scripts/pythonw.exe C:/Projects/claude/plugins/voice-input/hotkey_daemon.py` (in background)
3. Wait 2 seconds, then verify it's running by checking the log file at `C:/Projects/claude/plugins/voice-input/.hotkey.log`.
