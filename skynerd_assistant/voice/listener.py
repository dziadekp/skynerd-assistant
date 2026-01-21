"""
Voice input using speech recognition.

Listens for voice commands and converts them to text.
"""

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# Try to import speech recognition
try:
    import speech_recognition as sr
    SPEECH_AVAILABLE = True
except ImportError:
    SPEECH_AVAILABLE = False
    sr = None


class VoiceListener:
    """
    Listens for voice commands using the microphone.

    Uses Google's free speech recognition by default.
    """

    def __init__(self, timeout: int = 5, phrase_limit: int = 10):
        if not SPEECH_AVAILABLE:
            raise RuntimeError(
                "Speech recognition not available. "
                "Install with: pip install SpeechRecognition pyaudio"
            )

        self.recognizer = sr.Recognizer()
        self.timeout = timeout  # How long to wait for speech to start
        self.phrase_limit = phrase_limit  # Max seconds for a phrase

        # Adjust for ambient noise on first use
        self._calibrated = False

    def calibrate(self, duration: float = 1.0):
        """Calibrate for ambient noise."""
        with sr.Microphone() as source:
            logger.debug("Calibrating for ambient noise...")
            self.recognizer.adjust_for_ambient_noise(source, duration=duration)
            self._calibrated = True

    def listen_once(self) -> str | None:
        """
        Listen for a single voice command.

        Returns:
            Recognized text, or None if nothing recognized
        """
        if not self._calibrated:
            self.calibrate()

        with sr.Microphone() as source:
            logger.debug("Listening...")
            try:
                audio = self.recognizer.listen(
                    source,
                    timeout=self.timeout,
                    phrase_time_limit=self.phrase_limit,
                )
            except sr.WaitTimeoutError:
                logger.debug("No speech detected")
                return None

        # Try to recognize
        try:
            # Use Google's free speech recognition
            text = self.recognizer.recognize_google(audio)
            logger.info(f"Recognized: {text}")
            return text
        except sr.UnknownValueError:
            logger.debug("Could not understand audio")
            return None
        except sr.RequestError as e:
            logger.error(f"Speech recognition error: {e}")
            return None

    def listen_continuous(self, callback: Callable[[str], None], wake_word: str | None = None):
        """
        Continuously listen for commands.

        Args:
            callback: Function to call with recognized text
            wake_word: Optional wake word to trigger (e.g., "hey skynerd")
        """
        if not self._calibrated:
            self.calibrate()

        logger.info("Starting continuous listening...")
        if wake_word:
            logger.info(f"Wake word: '{wake_word}'")

        while True:
            text = self.listen_once()
            if text:
                text_lower = text.lower()

                # Check for wake word if configured
                if wake_word:
                    if wake_word.lower() in text_lower:
                        # Remove wake word from command
                        command = text_lower.replace(wake_word.lower(), "").strip()
                        if command:
                            callback(command)
                else:
                    callback(text)


def check_microphone() -> bool:
    """Check if microphone is available."""
    if not SPEECH_AVAILABLE:
        return False

    try:
        with sr.Microphone() as source:
            return True
    except (OSError, AttributeError):
        return False


def list_microphones() -> list[str]:
    """List available microphones."""
    if not SPEECH_AVAILABLE:
        return []

    try:
        return sr.Microphone.list_microphone_names()
    except (OSError, AttributeError):
        return []
