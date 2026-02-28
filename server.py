#!/usr/bin/env python3
"""Voice Input -- MCP server for Claude Code.

Two ways to use:
  1. /voice  slash command  -> Claude calls the voice_record / voice_stop tools
  2. Hotkey  (Ctrl+Shift+D by default) -> handled by hotkey_daemon.py,
     which this server spawns automatically on startup
"""

import asyncio
import json
import os
import subprocess
import sys
import threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ---- helpers --------------------------------------------------------- #

def _load_config() -> dict:
    path = os.path.join(SCRIPT_DIR, "config.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _log(msg: str):
    print(f"[voice-input] {msg}", file=sys.stderr, flush=True)


def _beep(freq: int, duration_ms: int):
    try:
        from src.audio_feedback import beep
        beep(freq, duration_ms)
    except Exception:
        pass


# ---- MCP server (must be created immediately for fast handshake) ----- #

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    _log("ERROR: mcp package not installed.  Run setup.bat first.")
    sys.exit(1)

mcp = FastMCP("voice-input")
config = _load_config()
rec_cfg = config.get("recording", {})
auto_stop = rec_cfg.get("auto_stop_on_silence", False)
max_seconds = rec_cfg.get("max_seconds", 300)


# ---- lazy-loaded components ------------------------------------------ #
# These are initialized in a background thread AFTER the MCP handshake
# so that Claude Code doesn't time out waiting for the server to start.

_components = {
    "recorder": None,
    "transcriber": None,
    "overlay": None,
    "ready": threading.Event(),
}


def _init_components():
    """Heavy initialization in a background thread."""
    try:
        from src.overlay import RecordingOverlay
        from src.recorder import VoiceRecorder
        from src.transcriber import create_transcriber

        _components["recorder"] = VoiceRecorder(
            sample_rate=rec_cfg.get("sample_rate", 16000),
            channels=rec_cfg.get("channels", 1),
            speech_threshold=rec_cfg.get("speech_threshold", 500),
        )

        _components["transcriber"] = create_transcriber(config.get("transcriber", {}))
        _log(f"Backend: {_components['transcriber'].name}")

        overlay = RecordingOverlay()
        overlay.start()
        _components["overlay"] = overlay
        _log("Overlay: ready")

        _spawn_hotkey_daemon()
    except Exception as exc:
        _log(f"Component init error: {exc}")
    finally:
        _components["ready"].set()


def _wait_ready(timeout: float = 15):
    """Block until components are initialized."""
    _components["ready"].wait(timeout=timeout)


# Start background init immediately
threading.Thread(target=_init_components, daemon=True).start()


# ---- MCP tools ------------------------------------------------------- #

@mcp.tool()
async def voice_record(
    silence_timeout: float = 2.0,
) -> str:
    """Start recording voice from the microphone.

    When auto_stop_on_silence is enabled in config, recording stops
    automatically after silence is detected and returns the transcription.

    Otherwise this only **starts** recording -- call voice_stop to finish
    and get the transcription.  The user controls when to stop.

    Args:
        silence_timeout: (auto-stop mode only) seconds of silence before
                         auto-stop (default 2).
    """
    await asyncio.to_thread(_wait_ready)
    recorder = _components["recorder"]
    overlay = _components["overlay"]

    if not recorder:
        return "[Error: recorder not initialized]"

    if auto_stop:
        # ---- auto-stop path (opt-in) ----
        if overlay:
            overlay.show_recording()
        _log("Recording (MCP, auto-stop)...")
        try:
            audio_path = await asyncio.to_thread(
                recorder.record_until_silence,
                max_seconds,
                silence_timeout,
                _log,
            )
        except Exception as exc:
            if overlay:
                overlay.hide()
            return f"[Recording failed: {exc}]"

        if not audio_path:
            if overlay:
                overlay.hide()
            return "[No speech detected.]"

        return await _transcribe(audio_path)

    # ---- manual-stop path (default) ----
    if overlay:
        overlay.show_recording()
    _beep(880, 150)
    try:
        recorder.start()
    except Exception as exc:
        if overlay:
            overlay.hide()
        return f"[Recording failed: {exc}]"

    _log("Recording (MCP, manual) -- waiting for voice_stop...")
    return "Recording started. The user is speaking. Call voice_stop when they tell you they are done."


@mcp.tool()
async def voice_stop() -> str:
    """Stop an active recording, transcribe, and return the text.

    Call this after voice_record once the user signals they are finished.
    """
    await asyncio.to_thread(_wait_ready)
    recorder = _components["recorder"]
    overlay = _components["overlay"]

    _log("Stopping recording (MCP)...")
    _beep(440, 200)
    audio_path = await asyncio.to_thread(recorder.stop)

    if not audio_path:
        if overlay:
            overlay.hide()
        return "[No audio was captured.]"

    return await _transcribe(audio_path)


async def _transcribe(audio_path: str) -> str:
    """Shared transcription helper for both MCP flows."""
    transcriber = _components["transcriber"]
    overlay = _components["overlay"]

    if overlay:
        overlay.show_transcribing()
    _log("Transcribing...")
    try:
        text = await asyncio.to_thread(transcriber.transcribe, audio_path)
    except Exception as exc:
        return f"[Transcription failed: {exc}]"
    finally:
        if overlay:
            overlay.hide()
        try:
            os.unlink(audio_path)
        except OSError:
            pass

    if not text or not text.strip():
        return "[No speech could be transcribed.]"

    text = text.strip()
    _log(f"Transcribed: {text[:100]}{'...' if len(text) > 100 else ''}")
    return text


@mcp.tool()
async def voice_list_devices() -> str:
    """List available audio input devices.  Useful for troubleshooting."""
    await asyncio.to_thread(_wait_ready)
    from src.recorder import VoiceRecorder
    return await asyncio.to_thread(VoiceRecorder.list_devices)


# ---- spawn hotkey daemon --------------------------------------------- #

def _spawn_hotkey_daemon():
    """Launch hotkey_daemon.py as a detached background process."""
    hotkey_cfg = config.get("hotkey", {})
    if not hotkey_cfg.get("enabled", True):
        _log("Hotkey: disabled in config")
        return

    daemon_path = os.path.join(SCRIPT_DIR, "hotkey_daemon.py")
    if not os.path.isfile(daemon_path):
        _log("Hotkey: hotkey_daemon.py not found")
        return

    try:
        kwargs: dict = dict(
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if os.name == "nt":
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        # Use pythonw.exe on Windows to avoid a console window
        python = sys.executable
        if os.name == "nt":
            pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
            if os.path.isfile(pythonw):
                python = pythonw
        subprocess.Popen([python, daemon_path], **kwargs)
        _log("Hotkey: daemon spawned")
    except Exception as exc:
        _log(f"Hotkey: failed to spawn daemon - {exc}")


# ---- main ------------------------------------------------------------ #

if __name__ == "__main__":
    mcp.run()
