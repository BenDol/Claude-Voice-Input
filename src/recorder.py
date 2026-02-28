"""Audio recording with manual toggle and auto-stop modes."""

import os
import tempfile
import threading
import time
import wave

import numpy as np
import sounddevice as sd


class VoiceRecorder:
    """Records microphone audio in two modes:

    * **Manual toggle** – ``start()`` / ``stop()``  (hotkey daemon)
    * **Auto-stop**     – ``record_until_silence()`` (MCP tool)
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        speech_threshold: float = 500,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.speech_threshold = speech_threshold
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._is_recording = False

    # ---- manual toggle ------------------------------------------------ #

    def start(self):
        """Begin recording (call ``stop()`` later to finish)."""
        self._frames = []
        self._is_recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=self._toggle_cb,
            blocksize=1024,
        )
        self._stream.start()

    def _toggle_cb(self, indata, frame_count, time_info, status):
        if self._is_recording:
            self._frames.append(indata.copy())

    def stop(self) -> str | None:
        """Stop a toggle-mode recording.  Returns WAV path or None."""
        self._is_recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._frames:
            return None

        audio = np.concatenate(self._frames)
        self._frames = []
        return self._save_wav(audio)

    # ---- auto-stop (silence detection) -------------------------------- #

    def record_until_silence(
        self,
        max_seconds: float = 30,
        silence_timeout: float = 2.0,
        log_fn=None,
    ) -> str | None:
        """Record until speech is followed by silence.  Returns WAV path."""
        frames: list[np.ndarray] = []
        speech_started = False
        speech_start_time = 0.0
        last_speech_time = 0.0
        start_time = time.time()
        done = threading.Event()

        def callback(indata, frame_count, time_info, status):
            nonlocal speech_started, speech_start_time, last_speech_time
            frames.append(indata.copy())
            rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))
            now = time.time()

            if rms > self.speech_threshold:
                if not speech_started:
                    speech_started = True
                    speech_start_time = now
                last_speech_time = now

            if (now - start_time) >= max_seconds:
                done.set()
            elif speech_started:
                if (
                    (now - speech_start_time) > 0.5
                    and (now - last_speech_time) > silence_timeout
                ):
                    done.set()

        _beep(880, 150)

        if log_fn:
            log_fn("Listening... speak now")

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            callback=callback,
            blocksize=1024,
        ):
            while not done.is_set():
                done.wait(timeout=0.3)
                if log_fn:
                    elapsed = time.time() - start_time
                    if speech_started:
                        log_fn(f"Recording... {elapsed:.0f}s")
                    else:
                        log_fn(f"Waiting for speech... {elapsed:.0f}s")

        _beep(440, 200)

        if not frames or not speech_started:
            return None

        return self._save_wav(np.concatenate(frames))

    # ---- helpers ------------------------------------------------------ #

    def _save_wav(self, audio_data: np.ndarray) -> str:
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())
        return path

    @staticmethod
    def list_devices() -> str:
        return str(sd.query_devices())


# ---- audio feedback -------------------------------------------------- #

def _beep(freq: int, duration_ms: int):
    try:
        if os.name == "nt":
            import winsound
            winsound.Beep(freq, duration_ms)
    except Exception:
        pass
