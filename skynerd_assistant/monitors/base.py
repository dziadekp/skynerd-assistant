"""
Base monitor class for all monitors.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from skynerd_assistant.clients import SkyNerdClient
from skynerd_assistant.state import StateDB

logger = logging.getLogger(__name__)


class BaseMonitor(ABC):
    """
    Base class for all monitors.

    Each monitor:
    - Polls the SkyNerd API at a configured interval
    - Compares against local state to detect changes
    - Triggers notifications for new/changed items
    """

    name: str = "base"

    def __init__(
        self,
        client: SkyNerdClient,
        state: StateDB,
        on_notification: Any = None,
    ):
        self.client = client
        self.state = state
        self.on_notification = on_notification

    @abstractmethod
    async def check(self) -> dict[str, Any]:
        """
        Check for updates and return status.

        Returns:
            dict with check results and any new items
        """
        pass

    async def notify(self, title: str, message: str, priority: str = "medium"):
        """Send a notification via the callback."""
        if self.on_notification:
            await self.on_notification(title, message, priority)
        else:
            logger.info(f"[{self.name}] {title}: {message}")

    async def run(self):
        """Run a single check cycle."""
        try:
            result = await self.check()
            await self.state.set_last_sync(self.name)
            return result
        except Exception as e:
            logger.error(f"[{self.name}] Error during check: {e}")
            return {"error": str(e)}
