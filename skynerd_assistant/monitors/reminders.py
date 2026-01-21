"""
Reminder monitor - checks for due reminders.
"""

import logging
from typing import Any

from .base import BaseMonitor

logger = logging.getLogger(__name__)


class ReminderMonitor(BaseMonitor):
    """
    Monitor for reminders.

    Detects:
    - Reminders that are now due
    - Upcoming reminders
    """

    name = "reminders"

    async def check(self) -> dict[str, Any]:
        """Check for due reminders."""
        try:
            # Get due reminders from server
            response = await self.client.get_due_reminders()
            due_reminders = response.get("reminders", [])

            # Get already notified IDs from local state
            notified_ids = await self.state.get_session_value("reminder_notified_ids") or []
            notified_ids = set(notified_ids)

            # Find new due reminders
            new_due = []
            for reminder in due_reminders:
                reminder_id = str(reminder.get("id"))
                if reminder_id not in notified_ids:
                    new_due.append(reminder)
                    notified_ids.add(reminder_id)

            # Update state
            await self.state.set_session_value(
                "reminder_notified_ids", list(notified_ids)
            )

            # Notify for new due reminders
            for reminder in new_due:
                await self.notify(
                    title="Reminder",
                    message=reminder.get("title", "You have a reminder"),
                    priority=reminder.get("priority", "medium"),
                )

            # Also check local reminders
            local_due = await self.state.get_due_reminders()
            for local_reminder in local_due:
                await self.notify(
                    title="Reminder",
                    message=local_reminder.get("title", "Local reminder"),
                    priority=local_reminder.get("priority", "medium"),
                )
                await self.state.mark_reminder_notified(local_reminder["id"])

            return {
                "server_due": len(due_reminders),
                "new_notifications": len(new_due),
                "local_due": len(local_due),
            }

        except Exception as e:
            logger.error(f"Reminder check failed: {e}")
            return {"error": str(e)}
