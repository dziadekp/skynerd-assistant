"""
Calendar monitor - checks for upcoming events.
"""

import logging
from datetime import datetime
from typing import Any

from .base import BaseMonitor

logger = logging.getLogger(__name__)


class CalendarMonitor(BaseMonitor):
    """
    Monitor for calendar events.

    Detects:
    - Upcoming meetings (15-minute warning)
    - Schedule changes
    """

    name = "calendar"

    async def check(self) -> dict[str, Any]:
        """Check for upcoming calendar events."""
        try:
            # Get status which includes calendar info
            status = await self.client.get_status()
            calendar = status.get("calendar", {})

            events_today = calendar.get("events_today", 0)
            next_event = calendar.get("next_event")

            # Check for upcoming meeting (within 15 minutes)
            if next_event:
                start_time_str = next_event.get("start_time")
                if start_time_str:
                    start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    now = datetime.now(start_time.tzinfo)
                    minutes_until = (start_time - now).total_seconds() / 60

                    # Check if we already notified for this event
                    last_notified = await self.state.get_session_value("calendar_last_notified")

                    # Notify if within 15 minutes and not already notified
                    if 0 < minutes_until <= 15 and last_notified != next_event.get("id"):
                        await self.notify(
                            title=f"Meeting in {int(minutes_until)} minutes",
                            message=next_event.get("title", "Upcoming meeting"),
                            priority="high",
                        )
                        await self.state.set_session_value(
                            "calendar_last_notified", next_event.get("id")
                        )

            return {
                "events_today": events_today,
                "next_event": next_event.get("title") if next_event else None,
            }

        except Exception as e:
            logger.error(f"Calendar check failed: {e}")
            return {"error": str(e)}
