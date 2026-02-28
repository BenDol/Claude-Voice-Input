"""Pluggable speech-to-text backends."""

import os
from abc import ABC, abstractmethod


class Transcriber(ABC):
    """Base class -- subclass to add a new STT backend."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name."""

    @abstractmethod
    def transcribe(self, audio_path: str) -> str:
        """Transcribe a WAV file and return the text."""


# ---------- OpenAI Whisper API (remote) ---------- #


class OpenAIWhisperAPI(Transcriber):
    def __init__(self, api_key: str = "", model: str = "whisper-1"):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model

    @property
    def name(self) -> str:
        return "OpenAI Whisper API"

    def transcribe(self, audio_path: str) -> str:
        if not self._api_key:
            raise ValueError(
                "OpenAI API key not configured. "
                "Set OPENAI_API_KEY env var or add it to config.json"
            )
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(model=self._model, file=f)
        return result.text


# ---------- Faster-Whisper (local) ---------- #


class FasterWhisperLocal(Transcriber):
    def __init__(self, model_size: str = "base", device: str = "auto"):
        self._model_size = model_size
        self._device = device
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "faster-whisper is not installed.  Run:  pip install faster-whisper"
            )
        self._model = WhisperModel(self._model_size, device=self._device)

    @property
    def name(self) -> str:
        return "Faster Whisper (local)"

    def transcribe(self, audio_path: str) -> str:
        self._ensure_model()
        segments, _ = self._model.transcribe(audio_path)
        return " ".join(seg.text.strip() for seg in segments)


# ---------- Factory ---------- #


def create_transcriber(config: dict) -> Transcriber:
    """Build a Transcriber from the ``transcriber`` config section."""
    backend = config.get("backend", "openai_api")

    if backend == "openai_api":
        s = config.get("openai_api", {})
        return OpenAIWhisperAPI(api_key=s.get("api_key", ""), model=s.get("model", "whisper-1"))

    if backend == "faster_whisper":
        s = config.get("faster_whisper", {})
        return FasterWhisperLocal(model_size=s.get("model_size", "base"), device=s.get("device", "auto"))

    raise ValueError(f"Unknown transcriber backend: '{backend}'.  Supported: openai_api, faster_whisper")
