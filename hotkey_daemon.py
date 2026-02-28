#!/usr/bin/env python3
"""Background daemon that listens for a global hotkey to toggle voice recording.

Spawned automatically by the MCP server when Claude Code starts.
Can also be run standalone:  python hotkey_daemon.py

Uses a PID file (.hotkey.pid) to ensure only one instance runs at a time.
Logs to .hotkey.log for troubleshooting.
"""

import atexit
import json
import os
import signal
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(SCRIPT_DIR, ".hotkey.pid")
LOG_FILE = os.path.join(SCRIPT_DIR, ".hotkey.log")

# make sure our package is importable
sys.path.insert(0, SCRIPT_DIR)


def _log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _beep(freq: int, dur: int):
    try:
        from src.audio_feedback import beep
        beep(freq, dur)
    except Exception:
        pass


# ---- single-instance management ------------------------------------- #

def _kill_existing():
    if not os.path.exists(PID_FILE):
        return
    try:
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
        os.kill(old_pid, signal.SIGTERM)
        _log(f"Killed previous daemon (PID {old_pid})")
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        pass
    try:
        os.unlink(PID_FILE)
    except OSError:
        pass


def _write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def _cleanup_pid():
    try:
        os.unlink(PID_FILE)
    except OSError:
        pass


# ---- main ------------------------------------------------------------ #

def main():
    _kill_existing()
    _write_pid()
    atexit.register(_cleanup_pid)

    # Truncate log on fresh start
    try:
        with open(LOG_FILE, "w") as f:
            f.write("")
    except OSError:
        pass

    _log(f"Daemon starting (PID {os.getpid()})")

    config_path = os.path.join(SCRIPT_DIR, "config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
    except Exception as exc:
        _log(f"Failed to load config: {exc}")
        return

    hotkey_cfg = config.get("hotkey", {})
    if not hotkey_cfg.get("enabled", True):
        _log("Hotkey disabled in config — exiting")
        return

    binding = hotkey_cfg.get("binding", "ctrl+alt+v")
    auto_paste = hotkey_cfg.get("auto_paste", True)
    auto_send_keywords = [kw.lower().strip() for kw in hotkey_cfg.get("auto_send_keywords", [])]
    auto_stop_on_keyword = hotkey_cfg.get("auto_stop_on_keyword", True)

    # ---- load components ---- #

    try:
        import keyboard as kb
    except ImportError:
        _log("'keyboard' package not installed — exiting")
        return
    except Exception as exc:
        # keyboard library needs root on Linux and doesn't work on macOS
        _log(f"keyboard init failed: {exc}")
        if os.name != "nt":
            _log("NOTE: The 'keyboard' library requires root on Linux "
                 "and is unsupported on macOS. Use /voice command instead.")
        return

    from src.recorder import VoiceRecorder
    from src.transcriber import create_transcriber
    from src.overlay import RecordingOverlay

    overlay = RecordingOverlay(hotkey=binding)
    overlay.start()

    rec_cfg = config.get("recording", {})
    recorder = VoiceRecorder(
        sample_rate=rec_cfg.get("sample_rate", 16000),
        channels=rec_cfg.get("channels", 1),
        speech_threshold=rec_cfg.get("speech_threshold", 500),
        on_levels=overlay.set_levels,
    )

    try:
        transcriber = create_transcriber(config.get("transcriber", {}))
    except Exception as exc:
        _log(f"Transcriber init failed: {exc}")
        return

    _log(f"Backend: {transcriber.name}")

    # ---- hotkey toggle ---- #

    state = {"recording": False, "busy": False}
    lock = threading.Lock()

    def _stop_and_transcribe():
        """Stop recording and kick off transcription. Caller must hold lock."""
        state["recording"] = False
        state["busy"] = True
        _beep(440, 200)
        overlay.show_transcribing()
        _log("Recording stopped")

        audio_path = recorder.stop()
        if not audio_path:
            _log("Empty recording")
            _beep(220, 300)
            overlay.hide()
            state["busy"] = False
            return

        threading.Thread(
            target=_transcribe_and_paste,
            args=(audio_path,),
            daemon=True,
        ).start()

    def on_hotkey():
        with lock:
            if state["busy"]:
                _beep(330, 100)
                return

            if not state["recording"]:
                # ---- START ----
                state["recording"] = True
                _beep(880, 150)
                try:
                    recorder.start()
                    overlay.show_recording()
                    _log("Recording started")
                    if auto_stop_on_keyword and auto_send_keywords:
                        threading.Thread(
                            target=_keyword_watch_loop,
                            daemon=True,
                        ).start()
                except Exception as exc:
                    _log(f"Mic error: {exc}")
                    _beep(220, 300)
                    state["recording"] = False
                    overlay.hide()
            else:
                # ---- STOP ----
                _stop_and_transcribe()

    def _keyword_watch_loop():
        """Periodically transcribe tail audio to detect auto-send keywords."""
        _log("Keyword watch started")
        # Wait a bit before first check to accumulate audio
        time.sleep(2.0)
        while state["recording"] and not state["busy"]:
            tail_path = recorder.get_tail_wav(seconds=3.0)
            if tail_path:
                try:
                    tail_text = transcriber.transcribe(tail_path)
                except Exception:
                    tail_text = ""
                finally:
                    try:
                        os.unlink(tail_path)
                    except OSError:
                        pass
                if tail_text:
                    norm = tail_text.lower().replace("'", "").replace("\u2019", "").rstrip(".!?,;: ")
                    for kw in auto_send_keywords:
                        if norm.endswith(kw):
                            _log(f"Keyword '{kw}' detected in live audio — auto-stopping")
                            with lock:
                                if state["recording"] and not state["busy"]:
                                    _stop_and_transcribe()
                            return
            time.sleep(1.5)
        _log("Keyword watch ended")

    def _transcribe_and_paste(audio_path: str):
        try:
            _log("Transcribing...")
            text = transcriber.transcribe(audio_path)
        except Exception as exc:
            _log(f"Transcription error: {exc}")
            _beep(220, 300)
            return
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass
            overlay.hide()
            state["busy"] = False

        if not text or not text.strip():
            _log("No text returned")
            _beep(220, 300)
            return

        text = text.strip()
        _log(f"Transcribed ({len(text)} chars): {text[:120]}")

        # Check for auto-send keyword at the end
        # Strip apostrophes/punctuation for fuzzy matching
        # so "Let's go" matches keyword "lets go"
        def _normalize(s: str) -> str:
            return s.lower().replace("'", "").replace("\u2019", "").rstrip(".!?,;: ")

        should_send = False
        if auto_send_keywords:
            norm = _normalize(text)
            for kw in auto_send_keywords:
                if norm.endswith(kw):
                    # Find where the keyword starts in the original text
                    # by counting characters from the end (ignoring trailing punct)
                    stripped = text.rstrip(".!?,;: ''\u2019")
                    # Remove len(kw) worth of normalized chars from the end
                    cut = len(stripped)
                    norm_count = 0
                    while norm_count < len(kw) and cut > 0:
                        cut -= 1
                        ch = stripped[cut].lower()
                        if ch not in ("'", "\u2019"):
                            norm_count += 1
                    text = stripped[:cut].rstrip()
                    should_send = True
                    _log(f"Auto-send keyword '{kw}' detected")
                    break

        try:
            import pyperclip
            if text:
                pyperclip.copy(text)
                if auto_paste:
                    time.sleep(0.05)
                    kb.send("ctrl+v")
            if should_send:
                time.sleep(0.3)
                kb.press_and_release("enter")
        except Exception as exc:
            _log(f"Paste error: {exc}")
            _beep(220, 300)
            return

        _beep(660, 100)
        time.sleep(0.06)
        _beep(660, 100)

    # ---- register and block ---- #

    try:
        kb.add_hotkey(binding, on_hotkey, suppress=True)
    except Exception as exc:
        _log(f"Failed to register hotkey: {exc}")
        return

    _log(f"Hotkey [{binding}] active — waiting for input")

    try:
        kb.wait()
    except KeyboardInterrupt:
        pass

    _log("Daemon exiting")


if __name__ == "__main__":
    main()
