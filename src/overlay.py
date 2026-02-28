"""Floating recording-state indicator (top-right corner of screen).

Uses tkinter (ships with Python) -- no extra dependencies.
Falls back to a silent no-op if tkinter is unavailable.
"""

import threading


class RecordingOverlay:
    """Small always-on-top pill that shows REC / transcribing state."""

    HIDDEN = "hidden"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"

    _BG = {RECORDING: "#cc0000", TRANSCRIBING: "#b8860b"}
    _TEXT = {RECORDING: "REC", TRANSCRIBING: "..."}

    def __init__(self):
        self._desired = self.HIDDEN
        self._current = self.HIDDEN
        self._root = None
        self._frame = None
        self._dot = None
        self._label = None
        self._blink = True
        self._ready = threading.Event()

    # ---- public API (thread-safe, called from any thread) ------------ #

    def start(self):
        """Spawn the tkinter thread. Call once at startup."""
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

        root.overrideredirect(True)           # no title-bar / frame
        root.attributes("-topmost", True)     # always on top
        try:
            root.attributes("-alpha", 0.92)
        except Exception:
            pass

        screen_w = root.winfo_screenwidth()
        root.geometry(f"120x34+{screen_w - 140}+12")
        root.configure(bg="#cc0000")

        frame = tk.Frame(root, bg="#cc0000")
        frame.pack(expand=True, fill="both", padx=4, pady=2)

        dot = tk.Label(
            frame, text="\u25cf", fg="white", bg="#cc0000",
            font=("Segoe UI", 14),
        )
        dot.pack(side="left", padx=(6, 0))

        label = tk.Label(
            frame, text=" REC", fg="white", bg="#cc0000",
            font=("Segoe UI", 11, "bold"),
        )
        label.pack(side="left")

        self._frame = frame
        self._dot = dot
        self._label = label

        root.withdraw()
        self._ready.set()
        self._poll()
        root.mainloop()

    def _poll(self):
        if self._root is None:
            return

        desired = self._desired

        if desired == self.HIDDEN:
            if self._current != self.HIDDEN:
                self._root.withdraw()
                self._current = self.HIDDEN
        else:
            bg = self._BG[desired]
            text = self._TEXT[desired]

            if self._current != desired:
                for widget in (self._root, self._frame):
                    widget.configure(bg=bg)
                self._dot.configure(bg=bg, fg="white")
                self._label.configure(text=f" {text}", bg=bg)
                self._root.deiconify()
                self._current = desired
                self._blink = True

            # blinking dot while recording
            if desired == self.RECORDING:
                self._blink = not self._blink
                self._dot.configure(fg="white" if self._blink else bg)
            else:
                self._dot.configure(fg="white")

        self._root.after(500, self._poll)
