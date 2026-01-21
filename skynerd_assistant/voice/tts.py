"""
Text-to-Speech engine for local voice notifications.

Supports multiple backends:
- pyttsx3 (cross-platform, offline)
- Windows SAPI (Windows only, higher quality)
- AWS Polly via API (requires internet, highest quality)
"""

import asyncio
import logging
import sys
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseTTS(ABC):
    """Base class for TTS engines."""

    @abstractmethod
    def speak(self, text: str):
        """Speak the given text."""
        pass

    @abstractmethod
    def set_rate(self, rate: int):
        """Set speech rate (words per minute)."""
        pass

    @abstractmethod
    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)."""
        pass


class Pyttsx3TTS(BaseTTS):
    """pyttsx3-based TTS engine (cross-platform)."""

    def __init__(self, rate: int = 150, volume: float = 0.8):
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.set_rate(rate)
            self.set_volume(volume)
            logger.debug("Initialized pyttsx3 TTS")
        except Exception as e:
            logger.error(f"Failed to initialize pyttsx3: {e}")
            self.engine = None

    def speak(self, text: str):
        if self.engine:
            self.engine.say(text)
            self.engine.runAndWait()

    def set_rate(self, rate: int):
        if self.engine:
            self.engine.setProperty("rate", rate)

    def set_volume(self, volume: float):
        if self.engine:
            self.engine.setProperty("volume", volume)


class WindowsSAPITTS(BaseTTS):
    """Windows SAPI-based TTS (Windows only, higher quality)."""

    def __init__(self, rate: int = 150, volume: float = 0.8):
        if sys.platform != "win32":
            raise RuntimeError("Windows SAPI is only available on Windows")

        try:
            import win32com.client
            self.speaker = win32com.client.Dispatch("SAPI.SpVoice")
            self._rate = rate
            self._volume = volume
            self._apply_settings()
            logger.debug("Initialized Windows SAPI TTS")
        except Exception as e:
            logger.error(f"Failed to initialize Windows SAPI: {e}")
            self.speaker = None

    def _apply_settings(self):
        if self.speaker:
            # SAPI rate: -10 to 10
            # Convert from WPM (roughly 150 = 0)
            sapi_rate = (self._rate - 150) // 15
            self.speaker.Rate = max(-10, min(10, sapi_rate))
            # SAPI volume: 0 to 100
            self.speaker.Volume = int(self._volume * 100)

    def speak(self, text: str):
        if self.speaker:
            self.speaker.Speak(text)

    def set_rate(self, rate: int):
        self._rate = rate
        self._apply_settings()

    def set_volume(self, volume: float):
        self._volume = volume
        self._apply_settings()


class TTSEngine:
    """
    Main TTS engine that manages different backends.

    Automatically selects the best available backend.
    """

    def __init__(
        self,
        engine: str = "pyttsx3",
        rate: int = 150,
        volume: float = 0.8,
    ):
        self.engine_name = engine
        self.rate = rate
        self.volume = volume
        self._engine: BaseTTS | None = None
        self._init_engine()

    def _init_engine(self):
        """Initialize the TTS engine."""
        if self.engine_name == "sapi" and sys.platform == "win32":
            try:
                self._engine = WindowsSAPITTS(self.rate, self.volume)
                return
            except Exception as e:
                logger.warning(f"Windows SAPI not available: {e}")

        # Fall back to pyttsx3
        try:
            self._engine = Pyttsx3TTS(self.rate, self.volume)
        except Exception as e:
            logger.error(f"Failed to initialize any TTS engine: {e}")
            self._engine = None

    def speak(self, text: str):
        """
        Speak the given text synchronously.

        Args:
            text: Text to speak
        """
        if not self._engine:
            logger.warning(f"TTS not available, would speak: {text}")
            return

        try:
            self._engine.speak(text)
        except Exception as e:
            logger.error(f"TTS speak failed: {e}")

    async def speak_async(self, text: str):
        """
        Speak the given text asynchronously.

        Runs TTS in a thread pool to avoid blocking.

        Args:
            text: Text to speak
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.speak, text)

    def set_rate(self, rate: int):
        """Set speech rate (words per minute)."""
        self.rate = rate
        if self._engine:
            self._engine.set_rate(rate)

    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)."""
        self.volume = volume
        if self._engine:
            self._engine.set_volume(volume)

    @property
    def is_available(self) -> bool:
        """Check if TTS is available."""
        return self._engine is not None
