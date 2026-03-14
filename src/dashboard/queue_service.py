"""queue_service.py — Content queue management per account.

Each account has a queue.json file listing scheduled/draft posts.
The queue is a simple list of dicts with UUIDs, not a database.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.dashboard.accounts import get_account_paths, DATA_ACCOUNTS_DIR
from src.utils.config import PROJECT_ROOT


def _queue_path(account_id: str) -> Path:
    """Get the queue.json path for an account."""
    if account_id == "default":
        return PROJECT_ROOT / "data" / "queue.json"
    return DATA_ACCOUNTS_DIR / account_id / "queue.json"


def load_queue(account_id: str) -> list[dict]:
    """Load the content queue for an account."""
    path = _queue_path(account_id)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_queue(account_id: str, queue: list[dict]) -> None:
    """Save the content queue for an account."""
    path = _queue_path(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)


def add_to_queue(
    account_id: str,
    script_id: str = "",
    video_path: str = "",
    scheduled_date: str = "",
    scheduled_time: str = "12:00",
    hook_preview: str = "",
) -> dict:
    """Add an item to the content queue."""
    queue = load_queue(account_id)

    item = {
        "queue_id": uuid.uuid4().hex[:12],
        "script_id": script_id,
        "video_path": video_path,
        "hook_preview": hook_preview,
        "scheduled_date": scheduled_date,
        "scheduled_time": scheduled_time,
        "status": "draft" if not scheduled_date else "scheduled",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    queue.append(item)
    _save_queue(account_id, queue)
    return item


def update_queue_item(account_id: str, queue_id: str, updates: dict) -> dict | None:
    """Update a queue item's fields. Returns updated item or None."""
    queue = load_queue(account_id)
    for item in queue:
        if item["queue_id"] == queue_id:
            for key in ("scheduled_date", "scheduled_time", "status", "video_path", "hook_preview"):
                if key in updates:
                    item[key] = updates[key]
            # Auto-set status based on date
            if "scheduled_date" in updates and updates["scheduled_date"]:
                if item["status"] == "draft":
                    item["status"] = "scheduled"
            _save_queue(account_id, queue)
            return item
    return None


def remove_from_queue(account_id: str, queue_id: str) -> bool:
    """Remove an item from the queue. Returns True if found and removed."""
    queue = load_queue(account_id)
    original_len = len(queue)
    queue = [item for item in queue if item["queue_id"] != queue_id]
    if len(queue) == original_len:
        return False
    _save_queue(account_id, queue)
    return True


def get_week_view(account_id: str, start_date: datetime | None = None) -> dict[str, list]:
    """Get queue items grouped by date for a 7-day week view.

    Returns: {date_str: [items]} for 7 days starting from start_date.
    """
    if start_date is None:
        today = datetime.now().date()
        # Start from Monday of current week
        start_date = today - timedelta(days=today.weekday())
    elif hasattr(start_date, 'date'):
        start_date = start_date.date()

    queue = load_queue(account_id)

    # Build 7-day grid
    week: dict[str, list] = {}
    for i in range(7):
        day = start_date + timedelta(days=i)
        date_str = day.isoformat()
        week[date_str] = []

    # Place items into their day slots
    for item in queue:
        scheduled = item.get("scheduled_date", "")
        if scheduled in week:
            week[scheduled].append(item)

    return week
