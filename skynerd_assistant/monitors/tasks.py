"""
Task monitor - checks for overdue and due-soon tasks.
"""

import logging
from typing import Any

from .base import BaseMonitor

logger = logging.getLogger(__name__)


class TaskMonitor(BaseMonitor):
    """
    Monitor for tasks.

    Detects:
    - Newly overdue tasks
    - Tasks due today
    - Newly assigned tasks
    """

    name = "tasks"

    async def check(self) -> dict[str, Any]:
        """Check for task updates."""
        try:
            # Get upcoming tasks (overdue + due soon)
            response = await self.client.get_upcoming_tasks(limit=50, days=1, my_tasks=True)
            tasks = response.get("tasks", [])
            total_count = response.get("total_count", 0)

            # Get previous state
            prev_overdue_ids = await self.state.get_session_value("task_overdue_ids") or []
            prev_overdue_ids = set(prev_overdue_ids)

            # Categorize tasks
            overdue_tasks = [t for t in tasks if t.get("is_overdue")]
            due_today_tasks = [t for t in tasks if not t.get("is_overdue")]

            current_overdue_ids = {str(t["id"]) for t in overdue_tasks}
            new_overdue_ids = current_overdue_ids - prev_overdue_ids

            # Update state
            await self.state.set_session_value(
                "task_overdue_ids", list(current_overdue_ids)
            )

            # Notify for newly overdue tasks
            new_overdue = [t for t in overdue_tasks if str(t["id"]) in new_overdue_ids]
            for task in new_overdue[:3]:  # Limit notifications
                await self.notify(
                    title="Task overdue",
                    message=task.get("title", "Unknown task"),
                    priority=task.get("priority", "high"),
                )

            return {
                "total_upcoming": total_count,
                "overdue_count": len(overdue_tasks),
                "due_today_count": len(due_today_tasks),
                "new_overdue": len(new_overdue_ids),
            }

        except Exception as e:
            logger.error(f"Task check failed: {e}")
            return {"error": str(e)}
