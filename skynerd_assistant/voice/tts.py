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


class PollyTTS(BaseTTS):
    """AWS Polly TTS engine (highest quality, requires AWS credentials)."""

    def __init__(
        self,
        rate: int = 150,
        volume: float = 0.8,
        voice_id: str = "Matthew",
        region: str = "us-east-1",
    ):
        try:
            import boto3
            import pygame

            self.polly = boto3.client("polly", region_name=region)
            self.voice_id = voice_id
            self._rate = rate
            self._volume = volume

            # Initialize pygame for audio playback
            pygame.mixer.init()
            self._pygame = pygame

            logger.debug(f"Initialized AWS Polly TTS with voice {voice_id}")
        except Exception as e:
            logger.error(f"Failed to initialize AWS Polly: {e}")
            self.polly = None
            self._pygame = None

    def speak(self, text: str):
        if not self.polly or not self._pygame:
            logger.warning("Polly not available")
            return

        try:
            import io
            import tempfile

            # Adjust rate using SSML
            rate_percent = int((self._rate / 150) * 100)
            ssml_text = f'<speak><prosody rate="{rate_percent}%">{text}</prosody></speak>'

            # Call Polly
            response = self.polly.synthesize_speech(
                Text=ssml_text,
                TextType="ssml",
                OutputFormat="mp3",
                VoiceId=self.voice_id,
                Engine="neural",  # Use neural voice for higher quality
            )

            # Play audio
            audio_stream = response["AudioStream"].read()

            # Save to temp file and play
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio_stream)
                temp_path = f.name

            self._pygame.mixer.music.load(temp_path)
            self._pygame.mixer.music.set_volume(self._volume)
            self._pygame.mixer.music.play()

            # Wait for playback to finish
            while self._pygame.mixer.music.get_busy():
                self._pygame.time.wait(100)

            # Cleanup
            import os
            os.unlink(temp_path)

        except Exception as e:
            logger.error(f"Polly speak failed: {e}")

    def set_rate(self, rate: int):
        self._rate = rate

    def set_volume(self, volume: float):
        self._volume = volume


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
        polly_voice: str = "Matthew",
        polly_region: str = "us-east-1",
    ):
        self.engine_name = engine
        self.rate = rate
        self.volume = volume
        self.polly_voice = polly_voice
        self.polly_region = polly_region
        self._engine: BaseTTS | None = None
        self._init_engine()

    def _init_engine(self):
        """Initialize the TTS engine."""
        # Try Polly first if requested
        if self.engine_name == "polly":
            try:
                self._engine = PollyTTS(
                    self.rate,
                    self.volume,
                    voice_id=self.polly_voice,
                    region=self.polly_region,
                )
                if self._engine.polly:
                    logger.info("Using AWS Polly for TTS")
                    return
            except Exception as e:
                logger.warning(f"AWS Polly not available: {e}")

        # Try Windows SAPI if requested
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
