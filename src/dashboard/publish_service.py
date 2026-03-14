"""publish_service.py — Content staging and post-history tracking per account.

The VA manually posts videos to TikTok. This service tracks what's ready,
builds captions, and records post history — no TikTok API calls.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.dashboard.accounts import get_account_paths, DATA_ACCOUNTS_DIR
from src.dashboard.services import list_videos, match_scripts_to_videos
from src.dashboard.queue_service import update_queue_item, load_queue
from src.utils.config import PROJECT_ROOT


# ── Post history I/O ─────────────────────────────────────────────────────────

def _history_path(account_id: str) -> Path:
    """Get the post_history.json path for an account."""
    if account_id == "default":
        return PROJECT_ROOT / "data" / "post_history.json"
    return DATA_ACCOUNTS_DIR / account_id / "post_history.json"


def load_post_history(account_id: str) -> list[dict]:
    """Load post history for an account. Returns [] if missing."""
    path = _history_path(account_id)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_post_history(account_id: str, history: list[dict]) -> None:
    """Write post history JSON."""
    path = _history_path(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


# ── Record a post ────────────────────────────────────────────────────────────

def record_post(
    account_id: str,
    video_filename: str,
    script_id: str = "",
    caption_used: str = "",
    tiktok_url: str = "",
    notes: str = "",
    queue_id: str = "",
    status: str = "posted",
) -> dict:
    """Create a post record, append to history, return it.

    If queue_id is provided, updates the queue item status to match.
    """
    history = load_post_history(account_id)

    record = {
        "post_id": uuid.uuid4().hex[:12],
        "video_filename": video_filename,
        "script_id": script_id,
        "caption_used": caption_used,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "tiktok_url": tiktok_url,
        "status": status,
        "notes": notes,
        "queue_id": queue_id,
    }

    history.append(record)
    _save_post_history(account_id, history)

    # Update linked queue item if applicable
    if queue_id:
        update_queue_item(account_id, queue_id, {"status": status})

    return record


# ── Ready-to-post logic ─────────────────────────────────────────────────────

def get_posts_today(account_id: str) -> int:
    """Count posts with today's date."""
    today = datetime.now(timezone.utc).date().isoformat()
    history = load_post_history(account_id)
    return sum(
        1 for post in history
        if post.get("posted_at", "").startswith(today)
    )


def get_ready_to_post(account_id: str) -> list[dict]:
    """Return videos NOT yet in post history, each enriched with script data.

    Cross-references list_videos() and match_scripts_to_videos() against
    post history. Videos that are posted or skipped are excluded.
    """
    history = load_post_history(account_id)
    posted_filenames = {post["video_filename"] for post in history}

    # Also exclude videos whose queue items are already posted
    queue = load_queue(account_id)
    posted_queue_scripts = {
        item.get("script_id", "")
        for item in queue
        if item.get("status") == "posted"
    }

    matched = match_scripts_to_videos(account_id)
    ready = []
    for video in matched:
        if video["filename"] in posted_filenames:
            continue
        # Check if video's script was posted via queue
        script = video.get("script")
        if script and script.get("script_id", "") in posted_queue_scripts:
            continue
        ready.append(video)

    return ready


# ── Caption builder ──────────────────────────────────────────────────────────

def build_caption(script: dict) -> str:
    """Assemble caption from script: hook + CTA + hashtags.

    The VA can edit before copying.
    """
    parts = []

    hook = script.get("hook", "")
    if hook:
        parts.append(hook)

    cta = script.get("cta", "")
    if cta:
        parts.append(cta)

    hashtags = script.get("suggested_hashtags", [])
    if hashtags:
        tag_str = " ".join(
            f"#{tag.lstrip('#')}" for tag in hashtags
        )
        parts.append(tag_str)

    return "\n\n".join(parts)


# ── Posting notes I/O ────────────────────────────────────────────────────────

def _notes_path(account_id: str) -> Path:
    """Get the posting_notes.json path for an account."""
    if account_id == "default":
        return PROJECT_ROOT / "data" / "posting_notes.json"
    return DATA_ACCOUNTS_DIR / account_id / "posting_notes.json"


def load_posting_notes(account_id: str) -> str:
    """Load free-text posting notes. Returns '' if missing."""
    path = _notes_path(account_id)
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("notes", "")


def save_posting_notes(account_id: str, notes: str) -> None:
    """Save posting notes."""
    path = _notes_path(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"notes": notes}, f, indent=2, ensure_ascii=False)
