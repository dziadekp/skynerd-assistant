"""
SkyNerd Control API Client

Async HTTP client for interacting with the SkyNerd Control API.
"""

import logging
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SkyNerdClient:
    """
    Async client for SkyNerd Control API.

    All methods return the API response data or raise exceptions on error.
    """

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        """Create the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Api-Key {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict[str, Any]:
        """Make an API request."""
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            response = await self._client.request(
                method=method,
                url=endpoint,
                params=params,
                json=json,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request error: {e}")
            raise

    # Status endpoints
    async def get_status(self) -> dict[str, Any]:
        """
        GET /api/assistant/status/

        Get unified status from all monitored sources.
        """
        return await self._request("GET", "/api/assistant/status/")

    # Email endpoints
    async def get_unread_emails(
        self, limit: int = 20, priority: str | None = None
    ) -> dict[str, Any]:
        """
        GET /api/assistant/emails/unread/

        Get unread emails with AI classification.
        """
        params = {"limit": limit}
        if priority:
            params["priority"] = priority
        return await self._request("GET", "/api/assistant/emails/unread/", params=params)

    # Task endpoints
    async def get_upcoming_tasks(
        self, limit: int = 20, days: int = 7, my_tasks: bool = False
    ) -> dict[str, Any]:
        """
        GET /api/assistant/tasks/upcoming/

        Get overdue and due-soon tasks.
        """
        params = {"limit": limit, "days": days}
        if my_tasks:
            params["my_tasks"] = "true"
        return await self._request("GET", "/api/assistant/tasks/upcoming/", params=params)

    # Reminder endpoints
    async def get_reminders(self) -> dict[str, Any]:
        """
        GET /api/assistant/reminders/

        Get all user reminders.
        """
        return await self._request("GET", "/api/assistant/reminders/")

    async def get_due_reminders(self) -> dict[str, Any]:
        """
        GET /api/assistant/reminders/due/

        Get reminders that are currently due.
        """
        return await self._request("GET", "/api/assistant/reminders/due/")

    async def get_upcoming_reminders(self, hours: int = 24) -> dict[str, Any]:
        """
        GET /api/assistant/reminders/upcoming/

        Get reminders due within the specified hours.
        """
        return await self._request(
            "GET", "/api/assistant/reminders/upcoming/", params={"hours": hours}
        )

    async def create_reminder(
        self,
        title: str,
        due_at: datetime,
        description: str = "",
        priority: str = "medium",
        source: str = "cli",
    ) -> dict[str, Any]:
        """
        POST /api/assistant/reminders/

        Create a new reminder.
        """
        return await self._request(
            "POST",
            "/api/assistant/reminders/",
            json={
                "title": title,
                "description": description,
                "due_at": due_at.isoformat(),
                "priority": priority,
                "source": source,
            },
        )

    async def complete_reminder(self, reminder_id: str) -> dict[str, Any]:
        """
        POST /api/assistant/reminders/{id}/complete/

        Mark a reminder as complete.
        """
        return await self._request(
            "POST", f"/api/assistant/reminders/{reminder_id}/complete/"
        )

    async def snooze_reminder(
        self, reminder_id: str, minutes: int = 60
    ) -> dict[str, Any]:
        """
        POST /api/assistant/reminders/{id}/snooze/

        Snooze a reminder.
        """
        return await self._request(
            "POST",
            f"/api/assistant/reminders/{reminder_id}/snooze/",
            json={"minutes": minutes},
        )

    # Notification endpoints
    async def send_notification(
        self,
        channel: str,
        title: str,
        message: str,
        priority: str = "medium",
        action_url: str = "",
    ) -> dict[str, Any]:
        """
        POST /api/assistant/notifications/send/

        Send a notification via specified channel.
        """
        return await self._request(
            "POST",
            "/api/assistant/notifications/send/",
            json={
                "channel": channel,
                "title": title,
                "message": message,
                "priority": priority,
                "action_url": action_url,
            },
        )

    async def send_slack_dm(
        self, message: str, blocks: list | None = None
    ) -> dict[str, Any]:
        """
        POST /api/assistant/slack/dm/

        Send a Slack DM to the current user.
        """
        data = {"message": message}
        if blocks:
            data["blocks"] = blocks
        return await self._request("POST", "/api/assistant/slack/dm/", json=data)

    # Voice notification endpoints
    async def get_pending_voice_notifications(
        self, limit: int = 10
    ) -> dict[str, Any]:
        """
        GET /api/assistant/voice/pending/

        Get pending voice notifications for TTS playback.
        """
        return await self._request(
            "GET", "/api/assistant/voice/pending/", params={"limit": limit}
        )

    async def mark_voice_notification_delivered(
        self, notification_id: str
    ) -> dict[str, Any]:
        """
        POST /api/assistant/voice/{id}/delivered/

        Mark a voice notification as delivered.
        """
        return await self._request(
            "POST", f"/api/assistant/voice/{notification_id}/delivered/"
        )

    async def create_voice_notification(
        self,
        message: str,
        notification_type: str = "general_alert",
        priority: str = "medium",
    ) -> dict[str, Any]:
        """
        POST /api/assistant/voice/speak/

        Create a new voice notification to be spoken.
        """
        return await self._request(
            "POST",
            "/api/assistant/voice/speak/",
            json={
                "message": message,
                "notification_type": notification_type,
                "priority": priority,
            },
        )
