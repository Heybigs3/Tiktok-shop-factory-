"""
tiktok_api.py — TikTok Content Posting API client.

This module talks to TikTok's servers. Three things it does:

1. query_creator_info() — Asks TikTok: "Who is this user? What are they
   allowed to do?" We need this before every post to show the right options.

2. init_video_post() — Tells TikTok: "I want to upload a video with these
   settings." TikTok responds with an upload URL.

3. upload_video_file() — Actually sends the video file to that upload URL.

4. check_post_status() — Asks TikTok: "Is my video done processing yet?"
"""

import requests
from pathlib import Path
from rich import print as rprint

# ── TikTok API base URL ──
API_BASE = "https://open.tiktokapis.com/v2"


def _headers(access_token: str) -> dict:
    """Build the standard headers TikTok requires."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def query_creator_info(access_token: str) -> dict | None:
    """
    Get the creator's info — nickname, avatar, privacy options, etc.

    We MUST call this before every post because:
    - Privacy options can change (user might switch to private account)
    - Interaction settings can change (user might disable duets)
    - TikTok requires it for audit compliance

    Returns dict with keys like:
        creator_nickname, creator_username, creator_avatar_url,
        privacy_level_options, comment_disabled, duet_disabled,
        stitch_disabled, max_video_post_duration_sec
    """
    url = f"{API_BASE}/post/publish/creator_info/query/"

    resp = requests.post(url, headers=_headers(access_token), json={})

    if resp.status_code != 200:
        rprint(f"[red]Creator info request failed: {resp.status_code}[/red]")
        rprint(f"[dim]{resp.text}[/dim]")
        return None

    data = resp.json()

    if data.get("error", {}).get("code") != "ok":
        error_msg = data.get("error", {}).get("message", "Unknown error")
        rprint(f"[red]Creator info error: {error_msg}[/red]")
        return None

    return data.get("data")


def init_video_post(
    access_token: str,
    video_path: Path,
    title: str,
    privacy_level: str,
    disable_comment: bool = True,
    disable_duet: bool = True,
    disable_stitch: bool = True,
    brand_content_toggle: bool = False,
    brand_organic_toggle: bool = False,
) -> dict | None:
    """
    Initialize a video upload with TikTok.

    This is step 1 of posting: we tell TikTok about the video and its settings,
    and TikTok gives us an upload URL where we send the actual file.

    Returns dict with publish_id and upload_url, or None on error.
    """
    url = f"{API_BASE}/post/publish/video/init/"

    video_size = video_path.stat().st_size

    payload = {
        "post_info": {
            "title": title[:2200],  # TikTok's max title length
            "privacy_level": privacy_level,
            "disable_comment": disable_comment,
            "disable_duet": disable_duet,
            "disable_stitch": disable_stitch,
            "brand_content_toggle": brand_content_toggle,
            "brand_organic_toggle": brand_organic_toggle,
            "is_aigc": True,  # Our content is AI-generated, be honest about it
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,  # Upload in one chunk (our videos are small)
            "total_chunk_count": 1,
        },
    }

    resp = requests.post(url, headers=_headers(access_token), json=payload)

    if resp.status_code != 200:
        rprint(f"[red]Post init failed: {resp.status_code}[/red]")
        rprint(f"[dim]{resp.text}[/dim]")
        return None

    data = resp.json()

    if data.get("error", {}).get("code") != "ok":
        error_msg = data.get("error", {}).get("message", "Unknown error")
        rprint(f"[red]Post init error: {error_msg}[/red]")
        return None

    return data.get("data")


def upload_video_file(upload_url: str, video_path: Path) -> bool:
    """
    Upload the actual video file to TikTok's servers.

    This is step 2: we PUT the file bytes to the upload URL we got from init.
    The upload URL is only valid for 1 hour.
    """
    video_size = video_path.stat().st_size

    headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(video_size),
        "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
    }

    with open(video_path, "rb") as f:
        resp = requests.put(upload_url, headers=headers, data=f)

    if resp.status_code in (200, 201):
        rprint("[green]Video uploaded successfully[/green]")
        return True
    else:
        rprint(f"[red]Upload failed: {resp.status_code}[/red]")
        rprint(f"[dim]{resp.text}[/dim]")
        return False


def check_post_status(access_token: str, publish_id: str) -> dict | None:
    """
    Check if TikTok is done processing our uploaded video.

    After uploading, TikTok needs a few minutes to process the video.
    This endpoint tells us the current status.
    """
    url = f"{API_BASE}/post/publish/status/fetch/"

    resp = requests.post(
        url,
        headers=_headers(access_token),
        json={"publish_id": publish_id},
    )

    if resp.status_code != 200:
        return None

    data = resp.json()
    if data.get("error", {}).get("code") != "ok":
        return None

    return data.get("data")
