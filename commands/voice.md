This command accepts an optional action argument: `/voice [action]`

**No argument (default) — record voice:**
Call voice_record to start recording my voice from the microphone. Then wait — do NOT call voice_stop until I explicitly tell you I am done (e.g. "stop", "done", "submit", "send it"). Once I say I'm done, call voice_stop to get the transcription. Then respond to the transcribed text as if I had typed it directly as my message.

**`/voice kill` — kill all processes:**
Kill all voice-input server and hotkey daemon processes by running: `python C:/Projects/claude/plugins/voice-input/kill_servers.py`

**`/voice start` — start the daemon:**
Start the voice-input hotkey daemon by running: `C:/Projects/claude/plugins/voice-input/.venv/Scripts/pythonw.exe C:/Projects/claude/plugins/voice-input/hotkey_daemon.py` (in background)
After starting, wait 2 seconds then verify it's running by checking the log file at `C:/Projects/claude/plugins/voice-input/.hotkey.log`.

**`/voice restart` — restart the daemon:**
Restart the voice-input hotkey daemon by first killing existing processes, then starting a fresh instance.
1. Run: `python C:/Projects/claude/plugins/voice-input/kill_servers.py`
2. Run: `C:/Projects/claude/plugins/voice-input/.venv/Scripts/pythonw.exe C:/Projects/claude/plugins/voice-input/hotkey_daemon.py` (in background)
3. Wait 2 seconds, then verify it's running by checking the log file at `C:/Projects/claude/plugins/voice-input/.hotkey.log`.
