"""Tests for src/scrapers/hook_processor.py — processing, dedup, filtering."""

import pytest

from src.scrapers.hook_processor import (
    deduplicate,
    filter_low_quality,
    process_ads,
    process_and_save,
    process_trending_videos,
)


# ── Fixtures ──

@pytest.fixture
def raw_apify_videos():
    """3 raw Apify video dicts (one duplicate ID for dedup testing)."""
    return [
        {
            "id": "vid001",
            "text": "Stop scrolling if you have acne. This routine changed everything for me.",
            "authorMeta": {"name": "skincarequeen", "fans": 500000, "verified": True},
            "playCount": 2500000,
            "diggCount": 125000,
            "shareCount": 8000,
            "commentCount": 3200,
            "videoMeta": {"duration": 22},
            "webVideoUrl": "https://tiktok.com/@skincarequeen/vid001",
            "createTimeISO": "2026-03-08T10:00:00Z",
        },
        {
            "id": "vid002",
            "text": "POV: you found the perfect moisturizer",
            "author": "glowgirl",
            "plays": 800000,
            "likes": 40000,
            "shares": 2000,
            "comments": 1500,
            "duration": 15,
        },
        {
            "id": "vid001",  # duplicate of first — lower engagement
            "text": "Stop scrolling if you have acne. This routine changed everything for me.",
            "authorMeta": {"name": "skincarequeen", "fans": 500000, "verified": True},
            "playCount": 2500000,
            "diggCount": 50000,  # lower likes → lower engagement
            "shareCount": 8000,
            "commentCount": 3200,
        },
    ]


@pytest.fixture
def raw_apify_ads():
    """2 raw Apify ad dicts."""
    return [
        {
            "id": "ad001",
            "text": "This serum changed my skin in 3 days. Dermatologists recommend it.\nShop now!",
            "advertiserName": "GlowBrand",
            "callToAction": "Shop Now",
            "estimatedSpend": 5000,
        },
        {
            "id": "ad002",
            "adText": "You need this in your routine",
            "advertiser": "SkinCo",
            "cta": "Learn More",
            "spend": 2000,
        },
    ]


# ── TestProcessTrendingVideos ──

class TestProcessTrendingVideos:
    """Tests for process_trending_videos() enrichment."""

    def test_extracts_hook_text(self, raw_apify_videos):
        hooks = process_trending_videos(raw_apify_videos)
        assert hooks[0]["hook_text"] == "Stop scrolling if you have acne."

    def test_enriched_fields_present(self, raw_apify_videos):
        hooks = process_trending_videos(raw_apify_videos)
        h = hooks[0]
        assert h["video_id"] == "vid001"
        assert h["author"] == "skincarequeen"
        assert h["author_fans"] == 500000
        assert h["author_verified"] is True
        assert h["full_text"].startswith("Stop scrolling")

    def test_engagement_rate_calculated(self, raw_apify_videos):
        hooks = process_trending_videos(raw_apify_videos)
        # 125000 / 2500000 = 0.05
        assert hooks[0]["stats"]["engagement_rate"] == 0.05

    def test_zero_plays_engagement(self):
        videos = [{"id": "v1", "text": "Some text here for the hook", "playCount": 0}]
        hooks = process_trending_videos(videos)
        assert hooks[0]["stats"]["engagement_rate"] == 0.0

    def test_missing_fields_graceful(self):
        videos = [{"text": "Just a video with text only please"}]
        hooks = process_trending_videos(videos)
        assert hooks[0]["video_id"] == ""
        assert hooks[0]["author"] == ""
        assert hooks[0]["stats"]["plays"] == 0

    def test_source_query_tag(self, raw_apify_videos):
        hooks = process_trending_videos(raw_apify_videos, source_query="skincare tips")
        assert all(h["source_query"] == "skincare tips" for h in hooks)

    def test_flat_author_fields(self):
        """Handle videos with flat author/plays fields (no authorMeta)."""
        videos = [{"id": "v1", "text": "Test hook text for flat fields", "author": "flatuser", "plays": 1000, "likes": 100}]
        hooks = process_trending_videos(videos)
        assert hooks[0]["author"] == "flatuser"
        assert hooks[0]["stats"]["plays"] == 1000

    def test_hashtag_extraction(self):
        videos = [{"id": "v1", "text": "Great routine #skincare #glowup"}]
        hooks = process_trending_videos(videos)
        assert "skincare" in hooks[0]["hashtags"]
        assert "glowup" in hooks[0]["hashtags"]


# ── TestProcessAds ──

class TestProcessAds:
    """Tests for process_ads() enrichment."""

    def test_extracts_hook_and_cta(self, raw_apify_ads):
        hooks = process_ads(raw_apify_ads)
        assert hooks[0]["hook_text"] == "This serum changed my skin in 3 days."
        assert hooks[0]["cta_text"] == "Shop Now"

    def test_full_text_preserved(self, raw_apify_ads):
        hooks = process_ads(raw_apify_ads)
        assert "Dermatologists recommend it" in hooks[0]["full_text"]

    def test_alternate_field_names(self, raw_apify_ads):
        hooks = process_ads(raw_apify_ads)
        assert hooks[1]["advertiser"] == "SkinCo"
        assert hooks[1]["cta_text"] == "Learn More"


# ── TestDeduplicate ──

class TestDeduplicate:
    """Tests for deduplicate()."""

    def test_removes_dupes_keeps_higher_engagement(self, raw_apify_videos):
        hooks = process_trending_videos(raw_apify_videos)
        deduped = deduplicate(hooks)
        ids = [h["video_id"] for h in deduped]
        assert ids.count("vid001") == 1
        # Should keep the one with higher engagement (125000 likes, not 50000)
        vid001 = next(h for h in deduped if h["video_id"] == "vid001")
        assert vid001["stats"]["likes"] == 125000

    def test_keeps_unique(self):
        hooks = [
            {"video_id": "a", "stats": {"engagement_rate": 0.1}},
            {"video_id": "b", "stats": {"engagement_rate": 0.2}},
        ]
        assert len(deduplicate(hooks)) == 2

    def test_empty_input(self):
        assert deduplicate([]) == []


# ── TestFilterLowQuality ──

class TestFilterLowQuality:
    """Tests for filter_low_quality()."""

    def test_removes_empty_hooks(self):
        hooks = [{"hook_text": ""}, {"hook_text": "Good hook text here"}]
        result = filter_low_quality(hooks)
        assert len(result) == 1

    def test_removes_hashtag_only(self):
        hooks = [{"hook_text": "#skincare #glowup #beauty #routine"}]
        result = filter_low_quality(hooks)
        assert len(result) == 0

    def test_removes_short_text(self):
        hooks = [{"hook_text": "Hi"}]
        result = filter_low_quality(hooks)
        assert len(result) == 0

    def test_keeps_good_hooks(self):
        hooks = [
            {"hook_text": "Stop scrolling if you have acne"},
            {"hook_text": "This changed my skin in 3 days"},
        ]
        result = filter_low_quality(hooks)
        assert len(result) == 2

    def test_custom_min_length(self):
        hooks = [{"hook_text": "Short but ok"}]
        assert len(filter_low_quality(hooks, min_text_length=5)) == 1
        assert len(filter_low_quality(hooks, min_text_length=50)) == 0


# ── TestProcessAndSave ──

class TestProcessAndSave:
    """Tests for process_and_save() end-to-end."""

    def test_saves_files(self, raw_apify_videos, raw_apify_ads, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scrapers.hook_processor.DATA_PROCESSED_DIR", tmp_path)
        video_hooks, ad_hooks = process_and_save(raw_apify_videos, raw_apify_ads)
        # Check files were created
        json_files = list(tmp_path.glob("*.json"))
        assert len(json_files) == 2  # processed_hooks + processed_ad_hooks

    def test_sorted_by_engagement(self, raw_apify_videos, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scrapers.hook_processor.DATA_PROCESSED_DIR", tmp_path)
        video_hooks, _ = process_and_save(raw_apify_videos, [])
        # First hook should have highest engagement rate
        if len(video_hooks) >= 2:
            assert video_hooks[0]["stats"]["engagement_rate"] >= video_hooks[1]["stats"]["engagement_rate"]
