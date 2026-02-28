#!/usr/bin/env python3
"""Voice Input -- MCP server + global hotkey for Claude Code.

Two ways to use:
  1. /voice  slash command  -> Claude calls the voice_input MCP tool
  2. Hotkey  (Ctrl+Shift+Space by default) -> records, transcribes,
     and pastes the text straight into the prompt input
"""

import asyncio
import json
import os
import sys
import threading
import time

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
        if os.name == "nt":
            import winsound

            winsound.Beep(freq, duration_ms)
    except Exception:
        pass


# ---- init ------------------------------------------------------------ #

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    _log("ERROR: mcp package not installed.  Run setup.bat first.")
    sys.exit(1)

from src.overlay import RecordingOverlay
from src.recorder import VoiceRecorder
from src.transcriber import create_transcriber

config = _load_config()
rec_cfg = config.get("recording", {})


def _make_recorder() -> VoiceRecorder:
    return VoiceRecorder(
        sample_rate=rec_cfg.get("sample_rate", 16000),
        channels=rec_cfg.get("channels", 1),
        speech_threshold=rec_cfg.get("speech_threshold", 500),
    )


transcriber = create_transcriber(config.get("transcriber", {}))
_log(f"Backend: {transcriber.name}")

overlay = RecordingOverlay()
overlay.start()
_log("Overlay: ready")


# ---- MCP tools ------------------------------------------------------- #

mcp_recorder = _make_recorder()
mcp = FastMCP("voice-input")

auto_stop = rec_cfg.get("auto_stop_on_silence", False)
max_seconds = rec_cfg.get("max_seconds", 300)


@mcp.tool()
async def voice_record(
    silence_timeout: float = 2.0,
) -> str:
    """Start recording voice from the microphone.

    When auto_stop_on_silence is enabled in config, recording stops
    automatically after silence is detected and returns the transcription.

    Otherwise this only **starts** recording — call voice_stop to finish
    and get the transcription.  The user controls when to stop.

    Args:
        silence_timeout: (auto-stop mode only) seconds of silence before
                         auto-stop (default 2).
    """
    if auto_stop:
        # ---- auto-stop path (opt-in) ----
        overlay.show_recording()
        _log("Recording (MCP, auto-stop)...")
        try:
            audio_path = await asyncio.to_thread(
                mcp_recorder.record_until_silence,
                max_seconds,
                silence_timeout,
                _log,
            )
        except Exception as exc:
            overlay.hide()
            return f"[Recording failed: {exc}]"

        if not audio_path:
            overlay.hide()
            return "[No speech detected.]"

        return await _transcribe(audio_path)

    # ---- manual-stop path (default) ----
    overlay.show_recording()
    _beep(880, 150)
    try:
        mcp_recorder.start()
    except Exception as exc:
        overlay.hide()
        return f"[Recording failed: {exc}]"

    _log("Recording (MCP, manual) — waiting for voice_stop...")
    return "Recording started. The user is speaking. Call voice_stop when they tell you they are done."


@mcp.tool()
async def voice_stop() -> str:
    """Stop an active recording, transcribe, and return the text.

    Call this after voice_record once the user signals they are finished.
    """
    _log("Stopping recording (MCP)...")
    _beep(440, 200)
    audio_path = await asyncio.to_thread(mcp_recorder.stop)

    if not audio_path:
        overlay.hide()
        return "[No audio was captured.]"

    return await _transcribe(audio_path)


async def _transcribe(audio_path: str) -> str:
    """Shared transcription helper for both MCP flows."""
    overlay.show_transcribing()
    _log("Transcribing...")
    try:
        text = await asyncio.to_thread(transcriber.transcribe, audio_path)
    except Exception as exc:
        return f"[Transcription failed: {exc}]"
    finally:
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
    return await asyncio.to_thread(VoiceRecorder.list_devices)


# ---- global hotkey --------------------------------------------------- #

def _setup_hotkey():
    """Register a system-wide hotkey that toggles recording.

    Press once  -> start recording  (high beep + red overlay).
    Press again -> stop, transcribe, paste into focused window (double beep).
    """
    hotkey_cfg = config.get("hotkey", {})
    if not hotkey_cfg.get("enabled", True):
        _log("Hotkey: disabled in config")
        return

    try:
        import keyboard as kb
    except ImportError:
        _log("Hotkey: disabled ('keyboard' package not installed)")
        return

    binding = hotkey_cfg.get("binding", "ctrl+shift+space")
    auto_paste = hotkey_cfg.get("auto_paste", True)

    hotkey_rec = _make_recorder()            # dedicated instance
    state = {"recording": False, "busy": False}
    lock = threading.Lock()

    def on_hotkey():
        with lock:
            if state["busy"]:
                _beep(330, 100)             # short "busy" tone
                return

            if not state["recording"]:
                # ---- START ----
                state["recording"] = True
                _beep(880, 150)
                try:
                    hotkey_rec.start()
                    overlay.show_recording()
                    _log("Hotkey: recording started")
                except Exception as exc:
                    _log(f"Hotkey: mic error - {exc}")
                    _beep(220, 300)
                    state["recording"] = False
                    overlay.hide()
            else:
                # ---- STOP ----
                state["recording"] = False
                state["busy"] = True
                _beep(440, 200)
                overlay.show_transcribing()
                _log("Hotkey: recording stopped")

                audio_path = hotkey_rec.stop()
                if not audio_path:
                    _log("Hotkey: empty recording")
                    _beep(220, 300)
                    overlay.hide()
                    state["busy"] = False
                    return

                threading.Thread(
                    target=_transcribe_and_paste,
                    args=(audio_path, auto_paste, state),
                    daemon=True,
                ).start()

    def _transcribe_and_paste(audio_path, paste, st):
        try:
            _log("Hotkey: transcribing...")
            text = transcriber.transcribe(audio_path)
        except Exception as exc:
            _log(f"Hotkey: transcription error - {exc}")
            _beep(220, 300)
            return
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass
            overlay.hide()
            st["busy"] = False

        if not text or not text.strip():
            _log("Hotkey: no text returned")
            _beep(220, 300)
            return

        text = text.strip()
        _log(f"Hotkey: transcribed {len(text)} chars")

        # Copy to clipboard and (optionally) simulate Ctrl+V
        try:
            import pyperclip

            pyperclip.copy(text)
            if paste:
                time.sleep(0.05)
                kb.send("ctrl+v")
        except Exception as exc:
            _log(f"Hotkey: paste error - {exc}")
            _beep(220, 300)
            return

        # success - double beep
        _beep(660, 100)
        time.sleep(0.06)
        _beep(660, 100)

    try:
        kb.add_hotkey(binding, on_hotkey, suppress=True)
        _log(f"Hotkey: registered  [{binding}]")
    except Exception as exc:
        _log(f"Hotkey: failed to register - {exc}")


# ---- main ------------------------------------------------------------ #

_setup_hotkey()

if __name__ == "__main__":
    mcp.run()
