"""
Voice notification monitor - fetches and plays voice notifications.
"""

import logging
from typing import Any, Callable

from .base import BaseMonitor

logger = logging.getLogger(__name__)


class VoiceMonitor(BaseMonitor):
    """
    Monitor for voice notifications.

    Fetches pending voice notifications from the server
    and plays them via local TTS.
    """

    name = "voice"

    def __init__(self, *args, on_speak: Callable[[str], Any] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_speak = on_speak

    async def check(self) -> dict[str, Any]:
        """Check for pending voice notifications."""
        try:
            # Get pending notifications from server
            response = await self.client.get_pending_voice_notifications(limit=5)
            notifications = response.get("notifications", [])

            played_count = 0

            for notification in notifications:
                notification_id = str(notification.get("id"))

                # Check if already delivered locally
                if await self.state.was_notification_delivered(notification_id):
                    continue

                # Get the spoken message
                spoken_message = notification.get("spoken_message", "")
                if not spoken_message:
                    spoken_message = notification.get("full_message", "")

                if spoken_message:
                    # Play via TTS
                    if self.on_speak:
                        await self.on_speak(spoken_message)
                        played_count += 1

                    # Log locally
                    await self.state.log_notification(
                        notification_id=notification_id,
                        notification_type=notification.get("notification_type", ""),
                        title=notification.get("title", ""),
                        message=spoken_message,
                        spoken=True,
                    )

                    # Mark as delivered on server
                    try:
                        await self.client.mark_voice_notification_delivered(notification_id)
                    except Exception as e:
                        logger.warning(f"Failed to mark notification delivered: {e}")

            return {
                "pending_count": len(notifications),
                "played_count": played_count,
            }

        except Exception as e:
            logger.error(f"Voice check failed: {e}")
            return {"error": str(e)}
