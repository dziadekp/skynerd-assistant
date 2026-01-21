"""
Main daemon for the SkyNerd Assistant.

Runs background monitors that poll the SkyNerd API at configured intervals.
All monitors run every 1 minute by default.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import Settings, load_settings
from .state import StateDB
from .clients.skynerd import SkyNerdClient
from .clients.ollama import OllamaClient
from .monitors.email import EmailMonitor
from .monitors.tasks import TaskMonitor
from .monitors.calendar import CalendarMonitor
from .monitors.reminders import ReminderMonitor
from .monitors.voice import VoiceMonitor
from .notifiers.desktop import DesktopNotifier
from .notifiers.slack import SlackNotifier
from .voice.tts import TTSEngine

logger = logging.getLogger(__name__)


class AssistantDaemon:
    """
    Main daemon that orchestrates all monitors and services.

    Polls the SkyNerd API every minute (configurable) for:
    - New emails
    - Overdue/upcoming tasks
    - Calendar events
    - Due reminders
    - Voice notifications
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self._setup_logging()

        self.scheduler: AsyncIOScheduler | None = None
        self.state: StateDB | None = None
        self.running = False

        # Clients
        self.skynerd_client: SkyNerdClient | None = None
        self.ollama_client: OllamaClient | None = None

        # Notifiers
        self.desktop_notifier: DesktopNotifier | None = None
        self.slack_notifier: SlackNotifier | None = None
        self.tts_engine: TTSEngine | None = None

        # Monitors
        self.monitors: dict = {}

    def _setup_logging(self):
        """Configure logging based on settings."""
        log_level = getattr(logging, self.settings.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(
                    self.settings.data_dir / "daemon.log",
                    mode="a",
                    encoding="utf-8",
                ),
            ],
        )
        # Reduce noise from httpx
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("apscheduler").setLevel(logging.WARNING)

    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing SkyNerd Assistant daemon...")

        # Ensure data directory exists
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize state manager
        self.state = StateDB(self.settings.db_path)
        await self.state.connect()

        # Initialize clients
        self.skynerd_client = SkyNerdClient(
            base_url=self.settings.api.base_url,
            api_key=self.settings.api.api_key,
        )

        if self.settings.ollama.enabled:
            self.ollama_client = OllamaClient(
                base_url=self.settings.ollama.base_url,
                model=self.settings.ollama.model,
            )

        # Initialize notifiers
        if self.settings.notifications.desktop:
            self.desktop_notifier = DesktopNotifier()

        if self.settings.notifications.slack:
            self.slack_notifier = SlackNotifier(self.skynerd_client)

        # Initialize TTS
        if self.settings.voice.enabled:
            self.tts_engine = TTSEngine(
                engine=self.settings.voice.tts_engine,
                rate=self.settings.voice.voice_rate,
                volume=self.settings.voice.voice_volume,
            )

        # Initialize monitors
        await self._init_monitors()

        # Initialize scheduler
        self.scheduler = AsyncIOScheduler()
        self._schedule_monitors()

        logger.info("Daemon initialization complete")

    async def _init_monitors(self):
        """Initialize all monitors."""
        common_deps = {
            "client": self.skynerd_client,
            "state": self.state,
            "desktop_notifier": self.desktop_notifier,
            "slack_notifier": self.slack_notifier,
        }

        self.monitors["email"] = EmailMonitor(**common_deps)
        self.monitors["tasks"] = TaskMonitor(**common_deps)
        self.monitors["calendar"] = CalendarMonitor(**common_deps)
        self.monitors["reminders"] = ReminderMonitor(**common_deps)
        self.monitors["voice"] = VoiceMonitor(
            **common_deps,
            tts_engine=self.tts_engine,
        )

        logger.debug(f"Initialized {len(self.monitors)} monitors")

    def _schedule_monitors(self):
        """Schedule all monitors to run at configured intervals."""
        intervals = self.settings.monitors

        # Email monitor
        self.scheduler.add_job(
            self._run_monitor,
            trigger=IntervalTrigger(minutes=intervals.email_interval),
            args=["email"],
            id="email_monitor",
            name="Email Monitor",
            replace_existing=True,
        )

        # Task monitor
        self.scheduler.add_job(
            self._run_monitor,
            trigger=IntervalTrigger(minutes=intervals.task_interval),
            args=["tasks"],
            id="task_monitor",
            name="Task Monitor",
            replace_existing=True,
        )

        # Calendar monitor
        self.scheduler.add_job(
            self._run_monitor,
            trigger=IntervalTrigger(minutes=intervals.calendar_interval),
            args=["calendar"],
            id="calendar_monitor",
            name="Calendar Monitor",
            replace_existing=True,
        )

        # Reminder monitor
        self.scheduler.add_job(
            self._run_monitor,
            trigger=IntervalTrigger(minutes=intervals.reminder_interval),
            args=["reminders"],
            id="reminder_monitor",
            name="Reminder Monitor",
            replace_existing=True,
        )

        # Voice monitor
        self.scheduler.add_job(
            self._run_monitor,
            trigger=IntervalTrigger(minutes=intervals.voice_interval),
            args=["voice"],
            id="voice_monitor",
            name="Voice Monitor",
            replace_existing=True,
        )

        logger.info("All monitors scheduled")

    async def _run_monitor(self, monitor_name: str):
        """Run a single monitor with error handling."""
        monitor = self.monitors.get(monitor_name)
        if not monitor:
            logger.error(f"Monitor not found: {monitor_name}")
            return

        try:
            logger.debug(f"Running {monitor_name} monitor...")
            await monitor.check()
            logger.debug(f"{monitor_name} monitor completed")
        except Exception as e:
            logger.error(f"Error in {monitor_name} monitor: {e}", exc_info=True)

    async def run_all_monitors_once(self):
        """Run all monitors once (for initial check on startup)."""
        logger.info("Running initial monitor checks...")

        tasks = [
            self._run_monitor(name)
            for name in self.monitors
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Initial monitor checks complete")

    async def start(self):
        """Start the daemon."""
        if self.running:
            logger.warning("Daemon is already running")
            return

        await self.initialize()

        # Run all monitors once on startup
        await self.run_all_monitors_once()

        # Start scheduler
        self.scheduler.start()
        self.running = True

        logger.info("SkyNerd Assistant daemon started")
        logger.info(f"Monitoring intervals: email={self.settings.monitors.email_interval}m, "
                    f"tasks={self.settings.monitors.task_interval}m, "
                    f"calendar={self.settings.monitors.calendar_interval}m, "
                    f"reminders={self.settings.monitors.reminder_interval}m, "
                    f"voice={self.settings.monitors.voice_interval}m")

    async def stop(self):
        """Stop the daemon."""
        if not self.running:
            return

        logger.info("Stopping SkyNerd Assistant daemon...")

        if self.scheduler:
            self.scheduler.shutdown(wait=True)

        if self.skynerd_client:
            await self.skynerd_client.close()

        if self.ollama_client:
            await self.ollama_client.close()

        if self.state:
            await self.state.close()

        self.running = False
        logger.info("Daemon stopped")

    async def run_forever(self):
        """Run the daemon until interrupted."""
        await self.start()

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._shutdown(sig)),
            )

        # Keep running
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def _shutdown(self, sig):
        """Handle shutdown signals."""
        logger.info(f"Received signal {sig.name}, shutting down...")
        self.running = False

    def get_status(self) -> dict:
        """Get current daemon status."""
        return {
            "running": self.running,
            "monitors": list(self.monitors.keys()),
            "scheduler_running": self.scheduler.running if self.scheduler else False,
            "settings": {
                "api_url": self.settings.api.base_url,
                "ollama_enabled": self.settings.ollama.enabled,
                "desktop_notifications": self.settings.notifications.desktop,
                "slack_notifications": self.settings.notifications.slack,
                "voice_enabled": self.settings.voice.enabled,
            },
        }


async def run_daemon():
    """Entry point for running the daemon."""
    daemon = AssistantDaemon()
    await daemon.run_forever()


def main():
    """Synchronous entry point."""
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
