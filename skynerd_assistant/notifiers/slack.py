"""
Slack notification handler.

Sends notifications via the SkyNerd API to the user's Slack.
"""

import logging

from skynerd_assistant.clients import SkyNerdClient

logger = logging.getLogger(__name__)


class SlackNotifier:
    """
    Slack notification handler.

    Uses the SkyNerd API to send DMs to the user.
    """

    def __init__(self, client: SkyNerdClient):
        self.client = client

    async def notify(
        self,
        title: str,
        message: str,
        priority: str = "medium",
    ):
        """
        Send a notification via Slack DM.

        Args:
            title: Notification title
            message: Notification message
            priority: Priority level (low, medium, high, urgent)
        """
        try:
            # Format message with title
            formatted_message = f"*{title}*\n{message}"

            result = await self.client.send_slack_dm(formatted_message)

            if result.get("success"):
                logger.debug(f"Slack notification sent: {title}")
            else:
                logger.warning(f"Slack notification failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")

    async def send_blocks(self, text: str, blocks: list):
        """
        Send a rich Slack message with Block Kit blocks.

        Args:
            text: Fallback text for notifications
            blocks: Block Kit blocks
        """
        try:
            result = await self.client.send_slack_dm(text, blocks=blocks)

            if result.get("success"):
                logger.debug("Slack blocks sent")
            else:
                logger.warning(f"Slack blocks failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Failed to send Slack blocks: {e}")
