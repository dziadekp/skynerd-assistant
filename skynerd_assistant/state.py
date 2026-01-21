"""
Local state persistence using SQLite.

Stores:
- Last sync timestamps
- Notification history
- Local reminders
- Session state
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite


class StateDB:
    """
    SQLite-based state management for the local agent.

    Uses async operations for non-blocking I/O.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        """Connect to the database and initialize schema."""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._init_schema()

    async def close(self):
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _init_schema(self):
        """Initialize database schema."""
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sync_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_id TEXT UNIQUE,
                notification_type TEXT,
                title TEXT,
                message TEXT,
                delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                spoken BOOLEAN DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS local_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id TEXT UNIQUE,
                title TEXT NOT NULL,
                description TEXT,
                due_at TIMESTAMP NOT NULL,
                priority TEXT DEFAULT 'medium',
                is_completed BOOLEAN DEFAULT 0,
                notification_sent BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS session_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_reminders_due
                ON local_reminders(due_at) WHERE is_completed = 0;

            CREATE INDEX IF NOT EXISTS idx_notifications_delivered
                ON notification_log(delivered_at);
        """)
        await self._conn.commit()

    # Sync state methods
    async def get_sync_state(self, key: str) -> str | None:
        """Get a sync state value."""
        async with self._conn.execute(
            "SELECT value FROM sync_state WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["value"] if row else None

    async def set_sync_state(self, key: str, value: str):
        """Set a sync state value."""
        await self._conn.execute(
            """
            INSERT INTO sync_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        await self._conn.commit()

    async def get_last_sync(self, monitor: str) -> datetime | None:
        """Get the last sync timestamp for a monitor."""
        value = await self.get_sync_state(f"last_sync_{monitor}")
        if value:
            return datetime.fromisoformat(value)
        return None

    async def set_last_sync(self, monitor: str, timestamp: datetime | None = None):
        """Set the last sync timestamp for a monitor."""
        if timestamp is None:
            timestamp = datetime.now()
        await self.set_sync_state(f"last_sync_{monitor}", timestamp.isoformat())

    # Notification log methods
    async def log_notification(
        self,
        notification_id: str,
        notification_type: str,
        title: str,
        message: str,
        spoken: bool = False,
    ):
        """Log a delivered notification."""
        try:
            await self._conn.execute(
                """
                INSERT INTO notification_log
                    (notification_id, notification_type, title, message, spoken)
                VALUES (?, ?, ?, ?, ?)
                """,
                (notification_id, notification_type, title, message, spoken),
            )
            await self._conn.commit()
        except aiosqlite.IntegrityError:
            # Already logged
            pass

    async def was_notification_delivered(self, notification_id: str) -> bool:
        """Check if a notification was already delivered."""
        async with self._conn.execute(
            "SELECT 1 FROM notification_log WHERE notification_id = ?",
            (notification_id,),
        ) as cursor:
            return await cursor.fetchone() is not None

    # Local reminder methods
    async def add_local_reminder(
        self,
        title: str,
        due_at: datetime,
        description: str = "",
        priority: str = "medium",
        server_id: str | None = None,
    ) -> int:
        """Add a local reminder."""
        cursor = await self._conn.execute(
            """
            INSERT INTO local_reminders (server_id, title, description, due_at, priority)
            VALUES (?, ?, ?, ?, ?)
            """,
            (server_id, title, description, due_at.isoformat(), priority),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_due_reminders(self) -> list[dict]:
        """Get reminders that are due and not notified."""
        async with self._conn.execute(
            """
            SELECT * FROM local_reminders
            WHERE is_completed = 0
              AND notification_sent = 0
              AND due_at <= datetime('now')
            ORDER BY due_at
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_reminder_notified(self, reminder_id: int):
        """Mark a reminder as notified."""
        await self._conn.execute(
            "UPDATE local_reminders SET notification_sent = 1 WHERE id = ?",
            (reminder_id,),
        )
        await self._conn.commit()

    async def mark_reminder_complete(self, reminder_id: int):
        """Mark a reminder as completed."""
        await self._conn.execute(
            "UPDATE local_reminders SET is_completed = 1 WHERE id = ?",
            (reminder_id,),
        )
        await self._conn.commit()

    # Session state methods
    async def get_session_value(self, key: str) -> Any:
        """Get a session value (JSON decoded)."""
        async with self._conn.execute(
            "SELECT value FROM session_state WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return json.loads(row["value"])
            return None

    async def set_session_value(self, key: str, value: Any):
        """Set a session value (JSON encoded)."""
        await self._conn.execute(
            """
            INSERT INTO session_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, json.dumps(value)),
        )
        await self._conn.commit()


# Global state instance
_state: StateDB | None = None


async def get_state(db_path: Path) -> StateDB:
    """Get the global state instance."""
    global _state
    if _state is None:
        _state = StateDB(db_path)
        await _state.connect()
    return _state
