"""
Desktop notification handler.

Uses plyer for cross-platform notifications.
On Windows, can also use win10toast for more features.
"""

import logging
import sys

logger = logging.getLogger(__name__)


class DesktopNotifier:
    """
    Cross-platform desktop notification handler.

    Uses plyer as the primary method, with fallbacks for Windows.
    """

    def __init__(self, app_name: str = "SkyNerd Assistant"):
        self.app_name = app_name
        self._notifier = None
        self._init_notifier()

    def _init_notifier(self):
        """Initialize the notification backend."""
        # Try plyer first (cross-platform)
        try:
            from plyer import notification
            self._notifier = "plyer"
            logger.debug("Using plyer for notifications")
            return
        except ImportError:
            pass

        # Windows fallback: win10toast
        if sys.platform == "win32":
            try:
                from win10toast import ToastNotifier
                self._win_toaster = ToastNotifier()
                self._notifier = "win10toast"
                logger.debug("Using win10toast for notifications")
                return
            except ImportError:
                pass

        logger.warning("No notification backend available")
        self._notifier = None

    def notify(
        self,
        title: str,
        message: str,
        timeout: int = 10,
        app_icon: str | None = None,
    ):
        """
        Show a desktop notification.

        Args:
            title: Notification title
            message: Notification message
            timeout: Time to show notification (seconds)
            app_icon: Path to icon file (optional)
        """
        if not self._notifier:
            logger.debug(f"Notification (no backend): {title} - {message}")
            return

        try:
            if self._notifier == "plyer":
                from plyer import notification
                notification.notify(
                    title=title,
                    message=message,
                    app_name=self.app_name,
                    app_icon=app_icon,
                    timeout=timeout,
                )
            elif self._notifier == "win10toast":
                self._win_toaster.show_toast(
                    title=title,
                    msg=message,
                    duration=timeout,
                    icon_path=app_icon,
                    threaded=True,
                )

            logger.debug(f"Notification sent: {title}")

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    async def notify_async(
        self,
        title: str,
        message: str,
        timeout: int = 10,
        app_icon: str | None = None,
    ):
        """Async wrapper for notify()."""
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self.notify(title, message, timeout, app_icon),
        )
