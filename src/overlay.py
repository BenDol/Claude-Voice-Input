"""Floating recording-state indicator pinned to the active window's bottom-right.

Tracks the focused window on both Windows (ctypes/Win32) and
X11-based Linux (via xdotool/xprop).  macOS and Wayland fall back
to the screen bottom-right corner.
"""

import os
import shutil
import subprocess
import threading


# ---- active-window rectangle ----------------------------------------- #

def _get_foreground_rect() -> tuple[int, int, int, int] | None:
    """Return (left, top, right, bottom) of the focused window, or None."""
    if os.name == "nt":
        return _win32_foreground_rect()
    return _x11_foreground_rect()


# -- Windows ----------------------------------------------------------- #

def _win32_foreground_rect():
    try:
        import ctypes

        user32 = ctypes.windll.user32

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        r = RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return None


# -- X11 (Linux) ------------------------------------------------------- #

def _x11_foreground_rect():
    """Use xdotool to get the active window geometry (X11 only)."""
    if not shutil.which("xdotool"):
        return None
    try:
        wid = subprocess.check_output(
            ["xdotool", "getactivewindow"], stderr=subprocess.DEVNULL, timeout=1,
        ).strip()
        geo = subprocess.check_output(
            ["xdotool", "getwindowgeometry", "--shell", wid],
            stderr=subprocess.DEVNULL, timeout=1,
        ).decode()
        vals = {}
        for line in geo.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                vals[k] = int(v)
        x = vals.get("X", 0)
        y = vals.get("Y", 0)
        w = vals.get("WIDTH", 0)
        h = vals.get("HEIGHT", 0)
        if w and h:
            return x, y, x + w, y + h
    except Exception:
        pass
    return None


# ---- overlay --------------------------------------------------------- #

_SIZE = 18
_MARGIN = 12


class RecordingOverlay:
    """Tiny solid-colored dot that follows the active window (bottom-right)."""

    HIDDEN = "hidden"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"

    _COLOR = {RECORDING: "#cc0000", TRANSCRIBING: "#b8860b"}

    def __init__(self):
        self._desired = self.HIDDEN
        self._current = self.HIDDEN
        self._root = None
        self._canvas = None
        self._dot_id = None
        self._blink = True
        self._ready = threading.Event()
        self._screen_w = 0
        self._screen_h = 0

    # ---- public API (thread-safe) ------------------------------------ #

    def start(self):
        threading.Thread(target=self._tk_main, daemon=True).start()
        self._ready.wait(timeout=3)

    def show_recording(self):
        self._desired = self.RECORDING

    def show_transcribing(self):
        self._desired = self.TRANSCRIBING

    def hide(self):
        self._desired = self.HIDDEN

    # ---- tkinter thread ---------------------------------------------- #

    def _tk_main(self):
        try:
            import tkinter as tk
        except ImportError:
            self._ready.set()
            return

        root = tk.Tk()
        self._root = root

        root.overrideredirect(True)
        root.attributes("-topmost", True)

        # Fully transparent background; only the drawn oval is visible
        transparent = "#010101"
        root.configure(bg=transparent)
        try:
            root.attributes("-transparentcolor", transparent)
        except Exception:
            pass

        self._screen_w = root.winfo_screenwidth()
        self._screen_h = root.winfo_screenheight()

        root.geometry(self._fallback_geometry())

        canvas = tk.Canvas(
            root, width=_SIZE, height=_SIZE,
            bg=transparent, highlightthickness=0, bd=0,
        )
        canvas.pack()
        self._canvas = canvas
        self._dot_id = canvas.create_oval(
            0, 0, _SIZE, _SIZE, fill="#cc0000", outline="#cc0000",
        )

        root.withdraw()
        self._ready.set()
        self._poll()
        root.mainloop()

    # ---- positioning ------------------------------------------------- #

    def _fallback_geometry(self) -> str:
        x = self._screen_w - _SIZE - _MARGIN
        y = self._screen_h - _SIZE - _MARGIN - 40   # above taskbar
        return f"{_SIZE}x{_SIZE}+{x}+{y}"

    def _reposition(self):
        """Move overlay to the bottom-right corner of the foreground window."""
        rect = _get_foreground_rect()
        if rect:
            left, top, right, bottom = rect
            x = max(0, min(right - _SIZE - _MARGIN, self._screen_w - _SIZE))
            y = max(0, min(bottom - _SIZE - _MARGIN, self._screen_h - _SIZE))
        else:
            x = self._screen_w - _SIZE - _MARGIN
            y = self._screen_h - _SIZE - _MARGIN - 40
        self._root.geometry(f"{_SIZE}x{_SIZE}+{x}+{y}")

    # ---- poll loop --------------------------------------------------- #

    def _poll(self):
        if self._root is None:
            return

        desired = self._desired

        if desired == self.HIDDEN:
            if self._current != self.HIDDEN:
                self._root.withdraw()
                self._current = self.HIDDEN
        else:
            color = self._COLOR[desired]

            if self._current != desired:
                self._canvas.itemconfigure(
                    self._dot_id, fill=color, outline=color,
                )
                self._root.deiconify()
                self._current = desired
                self._blink = True

            self._reposition()

            if desired == self.RECORDING:
                self._blink = not self._blink
                vis = color if self._blink else ""
                self._canvas.itemconfigure(
                    self._dot_id, fill=vis, outline=vis,
                )
            else:
                self._canvas.itemconfigure(
                    self._dot_id, fill=color, outline=color,
                )

        interval = 200 if self._current != self.HIDDEN else 500
        self._root.after(interval, self._poll)
