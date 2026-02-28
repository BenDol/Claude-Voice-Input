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
    import sys
    if sys.platform == "darwin":
        return _macos_foreground_rect()
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


# -- macOS ------------------------------------------------------------- #

def _macos_foreground_rect():
    """Use AppleScript to get the frontmost window bounds (macOS)."""
    try:
        script = (
            'tell application "System Events" to tell (first process '
            'whose frontmost is true) to get {position, size} of window 1'
        )
        out = subprocess.check_output(
            ["osascript", "-e", script],
            stderr=subprocess.DEVNULL, timeout=1,
        ).decode().strip()
        # Output: "x, y, w, h"
        parts = [int(p.strip()) for p in out.split(",")]
        if len(parts) == 4:
            x, y, w, h = parts
            return x, y, x + w, y + h
    except Exception:
        pass
    return None


# ---- overlay --------------------------------------------------------- #

_DOT = 18
_MARGIN = 12
_LABEL_PAD = 6


class RecordingOverlay:
    """Dot + hotkey label that follows the active window (bottom-left)."""

    HIDDEN = "hidden"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"

    _COLOR = {RECORDING: "#cc0000", TRANSCRIBING: "#b8860b"}

    def __init__(self, hotkey: str = ""):
        self._desired = self.HIDDEN
        self._current = self.HIDDEN
        self._hotkey = hotkey
        self._root = None
        self._canvas = None
        self._dot_id = None
        self._label = None
        self._blink = True
        self._ready = threading.Event()
        self._screen_w = 0
        self._screen_h = 0
        self._win_w = _DOT
        self._win_h = _DOT

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

        # Make the background transparent where possible
        transparent = "#010101"
        if os.name == "nt":
            # Windows: color-key transparency
            root.configure(bg=transparent)
            try:
                root.attributes("-transparentcolor", transparent)
            except Exception:
                transparent = "#cc0000"  # fallback: match dot color
                root.configure(bg=transparent)
        else:
            # macOS / Linux: use alpha for near-transparency on the bg
            transparent = "#000000"
            root.configure(bg=transparent)
            try:
                root.attributes("-alpha", 0.95)
            except Exception:
                pass

        self._screen_w = root.winfo_screenwidth()
        self._screen_h = root.winfo_screenheight()
        self._transparent = transparent

        font_family = "Segoe UI" if os.name == "nt" else "sans-serif"

        frame = tk.Frame(root, bg=transparent)
        frame.pack(expand=True, fill="both")

        canvas = tk.Canvas(
            frame, width=_DOT, height=_DOT,
            bg=transparent, highlightthickness=0, bd=0,
        )
        canvas.pack(side="left")
        self._canvas = canvas
        self._dot_id = canvas.create_oval(
            0, 0, _DOT, _DOT, fill="#cc0000", outline="#cc0000",
        )

        label = tk.Label(
            frame, text="", fg="#cc0000", bg=transparent,
            font=(font_family, 9), anchor="w",
        )
        label.pack(side="left", padx=(_LABEL_PAD, 0))
        self._label = label

        # Measure width with hotkey text to set window size
        if self._hotkey:
            label.configure(text=self._hotkey)
            root.update_idletasks()
            self._win_w = _DOT + _LABEL_PAD + label.winfo_reqwidth() + 4
            self._win_h = max(_DOT, label.winfo_reqheight())
            label.configure(text="")
        else:
            self._win_w = _DOT
            self._win_h = _DOT

        root.geometry(self._fallback_geometry())
        root.withdraw()
        self._ready.set()
        self._poll()
        root.mainloop()

    # ---- positioning ------------------------------------------------- #

    def _fallback_geometry(self) -> str:
        x = _MARGIN
        y = self._screen_h - self._win_h - _MARGIN - 40
        return f"{self._win_w}x{self._win_h}+{x}+{y}"

    def _reposition(self):
        """Move overlay to the bottom-left corner of the foreground window."""
        rect = _get_foreground_rect()
        if rect:
            left, top, right, bottom = rect
            x = max(0, left + _MARGIN)
            y = max(0, min(bottom - self._win_h - _MARGIN, self._screen_h - self._win_h))
        else:
            x = _MARGIN
            y = self._screen_h - self._win_h - _MARGIN - 40
        self._root.geometry(f"{self._win_w}x{self._win_h}+{x}+{y}")

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
                if self._hotkey:
                    self._label.configure(text=self._hotkey, fg=color)
                self._root.deiconify()
                self._current = desired
                self._blink = True

            self._reposition()

            if desired == self.RECORDING:
                self._blink = not self._blink
                vis = color if self._blink else self._transparent
                self._canvas.itemconfigure(
                    self._dot_id, fill=vis, outline=vis,
                )
            else:
                self._canvas.itemconfigure(
                    self._dot_id, fill=color, outline=color,
                )

        interval = 600 if self._current != self.HIDDEN else 500
        self._root.after(interval, self._poll)
