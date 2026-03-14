"""
hook_processor.py — Processes raw Apify data into enriched, deduplicated hooks.

Sits between the scrapers (Phase 1) and generators (Phase 2). Raw Apify data
uses inconsistent field names (text/description, playCount/plays, authorMeta/author).
This module normalizes everything into a clean schema that build_user_prompt() expects.

Pipeline:
  raw Apify data → process → deduplicate → filter low-quality → sort → save to data/processed/

Output schema (per hook):
  video_id, author, author_fans, author_verified, hook_text, full_text,
  stats: {plays, likes, shares, comments, engagement_rate},
  video_duration_sec, hashtags, music, is_ad, url, created_at, source_query

Usage:
  from src.scrapers.hook_processor import process_and_save
  process_and_save(raw_videos, raw_ads)
"""

import re

from rich import print as rprint

from src.utils.config import DATA_PROCESSED_DIR
from src.utils.data_io import save_json


def _extract_hook_text(text: str) -> str:
    """Extract hook (opening line) from video text. First sentence < 150 chars, or first 100 chars."""
    if not text:
        return ""
    for end_char in [".", "!", "?"]:
        idx = text.find(end_char)
        if idx != -1 and idx < 150:
            return text[: idx + 1].strip()
    return text[:100].strip()


def _extract_hashtags(text: str) -> list[str]:
    """Pull all #hashtags from text."""
    return re.findall(r"#(\w+)", text)


def process_trending_videos(raw_videos: list[dict], source_query: str = "") -> list[dict]:
    """
    Enrich raw Apify video data into normalized hook dicts.

    Handles both naming conventions from Apify actors (authorMeta vs author,
    playCount vs plays, etc.) and computes engagement_rate.

    Args:
        raw_videos: Raw dicts from Apify TikTok scraper
        source_query: Search query that produced these results

    Returns:
        List of enriched hook dicts with normalized fields
    """
    hooks = []
    for video in raw_videos:
        full_text = video.get("text", "") or video.get("description", "") or ""
        hook_text = _extract_hook_text(full_text)

        # Author info — handle authorMeta dict or flat fields
        author_meta = video.get("authorMeta", {})
        if isinstance(author_meta, dict) and author_meta:
            author = author_meta.get("name", "") or author_meta.get("nickName", "")
            author_fans = author_meta.get("fans", 0) or 0
            author_verified = author_meta.get("verified", False)
        else:
            author = video.get("author", "")
            author_fans = video.get("authorFans", 0) or 0
            author_verified = video.get("authorVerified", False)

        # Stats — handle both naming conventions (use 'in' check, not truthiness,
        # because 0 is falsy and would skip a valid zero value)
        plays = video.get("playCount") if "playCount" in video else video.get("plays", 0) or 0
        likes = video.get("diggCount") if "diggCount" in video else video.get("likes", 0) or 0
        shares = video.get("shareCount") if "shareCount" in video else video.get("shares", 0) or 0
        comments = video.get("commentCount") if "commentCount" in video else video.get("comments", 0) or 0

        engagement_rate = round(likes / plays, 4) if plays > 0 else 0.0

        # Hashtags from text or structured data
        hashtags = _extract_hashtags(full_text)
        if not hashtags and isinstance(video.get("hashtags"), list):
            hashtags = [
                h.get("name", "") if isinstance(h, dict) else str(h)
                for h in video["hashtags"]
            ]

        # Music info
        music_meta = video.get("musicMeta", {})
        if isinstance(music_meta, dict) and music_meta:
            music = music_meta.get("musicName", "") or music_meta.get("title", "")
        else:
            music = video.get("music", "")

        hooks.append({
            "video_id": video.get("id", "") or video.get("videoId", ""),
            "author": author,
            "author_fans": author_fans,
            "author_verified": author_verified,
            "hook_text": hook_text,
            "full_text": full_text,
            "stats": {
                "plays": plays,
                "likes": likes,
                "shares": shares,
                "comments": comments,
                "engagement_rate": engagement_rate,
            },
            "video_duration_sec": video.get("videoMeta", {}).get("duration", 0)
                                  if isinstance(video.get("videoMeta"), dict)
                                  else video.get("duration", 0) or 0,
            "hashtags": hashtags,
            "music": music,
            "is_ad": False,
            "url": video.get("webVideoUrl", "") or video.get("url", ""),
            "created_at": video.get("createTimeISO", "") or video.get("createTime", ""),
            "source_query": source_query,
        })

    return hooks


def process_ads(raw_ads: list[dict]) -> list[dict]:
    """
    Enrich raw Apify ad data into normalized hook dicts.

    Args:
        raw_ads: Raw dicts from Apify TikTok Ads Library actor

    Returns:
        List of enriched ad hook dicts
    """
    hooks = []
    for ad in raw_ads:
        full_text = ad.get("text", "") or ad.get("adText", "") or ""
        hook_text = _extract_hook_text(full_text)

        # CTA extraction
        cta_text = ad.get("callToAction", "") or ad.get("cta", "") or ""
        if not cta_text and full_text:
            lines = [line.strip() for line in full_text.strip().splitlines() if line.strip()]
            if len(lines) > 1:
                cta_text = lines[-1]

        hooks.append({
            "ad_id": ad.get("id", "") or ad.get("adId", ""),
            "advertiser": ad.get("advertiserName", "") or ad.get("advertiser", ""),
            "hook_text": hook_text,
            "full_text": full_text,
            "cta_text": cta_text,
            "estimated_spend": ad.get("estimatedSpend", 0) or ad.get("spend", 0),
        })

    return hooks


def deduplicate(hooks: list[dict], id_field: str = "video_id") -> list[dict]:
    """
    Remove duplicate hooks by ID. Keeps the entry with higher engagement rate.

    Args:
        hooks: List of hook dicts
        id_field: Which field to deduplicate on

    Returns:
        Deduplicated list
    """
    seen: dict[str, dict] = {}
    for hook in hooks:
        key = hook.get(id_field, "")
        if not key:
            # No ID — use hook_text as fallback key for content-based dedup
            key = f"_noid_{hook.get('hook_text', '')}"
            if not hook.get("hook_text"):
                # Truly unidentifiable — keep it with a unique counter key
                key = f"_noid_{len(seen)}"
        existing = seen.get(key)
        if existing is None:
            seen[key] = hook
        else:
            # Keep the one with higher engagement
            new_rate = hook.get("stats", {}).get("engagement_rate", 0)
            old_rate = existing.get("stats", {}).get("engagement_rate", 0)
            if new_rate > old_rate:
                seen[key] = hook
    return list(seen.values())


def filter_low_quality(hooks: list[dict], min_text_length: int = 15) -> list[dict]:
    """
    Remove hooks with empty, too-short, or hashtag-only text.

    Filters out:
    - Empty hook_text
    - Text shorter than min_text_length
    - Text where >50% of characters are # tokens

    Args:
        hooks: List of hook dicts
        min_text_length: Minimum character count for hook_text

    Returns:
        Filtered list
    """
    result = []
    for hook in hooks:
        text = hook.get("hook_text", "")
        if not text:
            continue
        if len(text) < min_text_length:
            continue
        # Check if mostly hashtags
        hashtag_chars = sum(len(m) for m in re.findall(r"#\w+", text))
        if len(text) > 0 and hashtag_chars / len(text) > 0.5:
            continue
        result.append(hook)
    return result


def process_and_save(
    raw_videos: list[dict],
    raw_ads: list[dict],
    source_query: str = "",
) -> tuple[list[dict], list[dict]]:
    """
    Full processing pipeline: enrich → dedup → filter → sort → save.

    Args:
        raw_videos: Raw trending video data from Apify
        raw_ads: Raw ad data from Apify
        source_query: Search query label for video source tracking

    Returns:
        Tuple of (processed_hooks, processed_ad_hooks)
    """
    # Process
    video_hooks = process_trending_videos(raw_videos, source_query)
    ad_hooks = process_ads(raw_ads)

    # Dedup videos by video_id
    video_hooks = deduplicate(video_hooks, id_field="video_id")
    # Dedup ads by ad_id
    ad_hooks = deduplicate(ad_hooks, id_field="ad_id")

    # Filter low-quality
    before_filter = len(video_hooks)
    video_hooks = filter_low_quality(video_hooks)
    filtered_count = before_filter - len(video_hooks)

    before_filter_ads = len(ad_hooks)
    ad_hooks = filter_low_quality(ad_hooks)
    filtered_ads_count = before_filter_ads - len(ad_hooks)

    # Sort by engagement rate (descending)
    video_hooks.sort(key=lambda h: h.get("stats", {}).get("engagement_rate", 0), reverse=True)

    # Save
    if video_hooks:
        save_json(video_hooks, "processed_hooks", DATA_PROCESSED_DIR)
        rprint(f"[green]Processed {len(video_hooks)} video hooks[/green]"
               f" [dim](filtered {filtered_count} low-quality)[/dim]")
    if ad_hooks:
        save_json(ad_hooks, "processed_ad_hooks", DATA_PROCESSED_DIR)
        rprint(f"[green]Processed {len(ad_hooks)} ad hooks[/green]"
               f" [dim](filtered {filtered_ads_count} low-quality)[/dim]")

    return video_hooks, ad_hooks
