"""
Email monitor - checks for new unread emails.
"""

import logging
from typing import Any

from .base import BaseMonitor

logger = logging.getLogger(__name__)


class EmailMonitor(BaseMonitor):
    """
    Monitor for unread emails.

    Detects:
    - New high-priority emails
    - Significant increase in unread count
    """

    name = "email"

    async def check(self) -> dict[str, Any]:
        """Check for new unread emails."""
        try:
            # Get current unread emails
            response = await self.client.get_unread_emails(limit=50, priority="high")
            emails = response.get("emails", [])
            total_count = response.get("total_count", 0)

            # Get previous state
            prev_count = await self.state.get_session_value("email_unread_count") or 0
            prev_high_priority = await self.state.get_session_value("email_high_priority") or []

            # Find new high-priority emails
            current_ids = {e["id"] for e in emails}
            prev_ids = set(prev_high_priority)
            new_ids = current_ids - prev_ids

            # Update state
            await self.state.set_session_value("email_unread_count", total_count)
            await self.state.set_session_value(
                "email_high_priority", list(current_ids)
            )

            # Notify for new high-priority emails
            new_emails = [e for e in emails if e["id"] in new_ids]
            for email in new_emails[:3]:  # Limit to 3 notifications
                subject = email.get("subject", "No subject")
                from_name = email.get("from_name", email.get("from_email", "Unknown"))
                priority = email.get("priority_level", "medium")

                await self.notify(
                    title=f"New email from {from_name}",
                    message=subject[:100],
                    priority=priority or "medium",
                )

            return {
                "unread_count": total_count,
                "high_priority_count": len(emails),
                "new_high_priority": len(new_ids),
            }

        except Exception as e:
            logger.error(f"Email check failed: {e}")
            return {"error": str(e)}
